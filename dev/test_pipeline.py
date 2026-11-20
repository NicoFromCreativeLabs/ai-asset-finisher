"""Headless end-to-end test. Run:
blender -b --factory-startup --python test_pipeline.py -- <input.obj> <out_dir> [resolution] [faces] [method] [export]
Uses a textured OBJ (albedo + separate metallic/roughness JPGs next to it, hy3d21 naming)."""
import os
import sys
import time

import bpy

ADDON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ADDON_ROOT)
import ai_asset_finisher  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
src, out_dir = argv[0], argv[1]
res = argv[2] if len(argv) > 2 else "1024"
faces = int(argv[3]) if len(argv) > 3 else 4000
method = argv[4] if len(argv) > 4 else "QUADRIFLOW"
export = argv[5] if len(argv) > 5 else "NONE"
os.makedirs(out_dir, exist_ok=True)

# clean scene
bpy.ops.wm.read_factory_settings(use_empty=True)
ai_asset_finisher.register()

t0 = time.time()
bpy.ops.wm.obj_import(filepath=src)
high = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
high.name = "scan_high"
print(f"[TEST] imported {len(high.data.polygons):,} faces in {time.time()-t0:.1f}s")

# build the high-poly PBR material from the three maps next to the OBJ
stem = os.path.splitext(src)[0]
mat = bpy.data.materials.new("high_mat")
mat.use_nodes = True
nt = mat.node_tree
bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")


def tex(path, cs, socket):
    if not os.path.exists(path):
        print("[TEST] missing", path)
        return
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(path)
    n.image.colorspace_settings.name = cs
    nt.links.new(n.outputs["Color"], bsdf.inputs[socket])


tex(stem + ".jpg", "sRGB", "Base Color")
tex(stem + "_metallic.jpg", "Non-Color", "Metallic")
tex(stem + "_roughness.jpg", "Non-Color", "Roughness")
high.data.materials.clear()
high.data.materials.append(mat)

s = bpy.context.scene.aaf
s.high_obj = high
s.retopo_method = method
s.target_faces = faces
s.resolution = res
s.samples = 8
s.bake_ao = True
s.out_dir = out_dir
s.export_format = export
s.use_gpu = True

bpy.context.view_layer.objects.active = high
t1 = time.time()
r = bpy.ops.aaf.run_all()
print(f"[TEST] run_all -> {r} in {time.time()-t1:.1f}s | status: {s.status}")
if "FINISHED" not in r:
    sys.exit(2)

low = s.low_obj
from ai_asset_finisher import core  # noqa: E402

rep = core.uv_report(low)
print(f"[TEST] low faces={len(low.data.polygons):,} verts={len(low.data.vertices):,} UV={rep}")
assert len(low.data.polygons) > 100, "low-poly is empty"
assert rep["out_of_bounds"] == 0, "UVs leave the 0-1 square"
assert rep["coverage"] > 0.2, "UV space is mostly empty"

import numpy as np  # noqa: E402

for key in ("basecolor", "roughness", "metallic", "normal", "ao"):
    img = bpy.data.images.get(f"{low.name}_{key}")
    assert img is not None, f"missing {key}"
    px = np.array(img.pixels[:], dtype=np.float32).reshape(-1, 4)[:, :3]
    print(f"[TEST] {key}: mean={px.mean(0).round(3)} std={px.std(0).round(3)} size={img.size[:]}")
    assert px.std() > 1e-3 or key in ("metallic",), f"{key} looks blank"

mat = low.data.materials[0]
linked = {l.to_socket.name for l in mat.node_tree.links}
print("[TEST] material links ->", sorted(linked))
for need in ("Base Color", "Roughness", "Metallic", "Normal"):
    assert need in linked, f"{need} not connected"
print("[TEST] PASS")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "result.blend"))
