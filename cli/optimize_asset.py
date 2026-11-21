"""Headless entry point used by the Creativelabs 3D app (and usable by hand):

  blender -b --factory-startup --python cli/optimize_asset.py -- <in.glb> <out_dir> <target_tris> <max_tris> <resolution>

Imports a (textured) mesh, then runs the AI Asset Finisher pipeline: retopology under the triangle
budget, seams + UVs, bake normal/base colour/roughness/metallic/AO into the new UVs, and exports
GLB + FBX + PNG maps to out_dir. Prints `[STAGE] <name> <0-1>` progress lines and a final
`[RESULT] {json}` line.
"""
import json
import os
import sys

import bpy

ADDON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ADDON_ROOT)
import ai_asset_finisher  # noqa: E402
from ai_asset_finisher import core  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
src, out_dir = argv[0], argv[1]
target_tris, max_tris, resolution = int(argv[2]), int(argv[3]), argv[4]
os.makedirs(out_dir, exist_ok=True)


def stage(name, frac):
    print(f"[STAGE] {name} {frac:.2f}", flush=True)


stage("starting Blender", 0.02)
bpy.ops.wm.read_factory_settings(use_empty=True)
ai_asset_finisher.register()

stage("importing mesh", 0.05)
if src.lower().endswith((".glb", ".gltf")):
    bpy.ops.import_scene.gltf(filepath=src)
else:
    bpy.ops.wm.obj_import(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit("no mesh found in input file")
if len(meshes) > 1:
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
high = meshes[0]  # (join merges into the active object, which we set to meshes[0])
# glTF import parents meshes under empties; detach so transforms are baked into the mesh.
if high.parent is not None:
    mw = high.matrix_world.copy()
    high.parent = None
    high.matrix_world = mw
bpy.context.view_layer.objects.active = high
high.select_set(True)
high.name = "asset_high"

s = bpy.context.scene.aaf
s.high_obj = high
s.retopo_method = "QUADRIFLOW"
s.target_tris = min(target_tris, max_tris)
s.max_tris = max_tris
s.resolution = resolution
s.samples = 16
s.bake_ao = True
s.out_dir = out_dir
s.use_gpu = True
s.hide_high = True

stage("retopology (quad remesh)", 0.10)
ctx = bpy.context
core.retopologize(ctx, s)
low = s.low_obj
tris = core.count_tris(low)
stage("seams and UV unwrap", 0.40)
uv = core.build_uvs(ctx, s)
stage("baking maps", 0.55)
core.bake_textures(ctx, s)
stage("exporting", 0.92)
files = []
for fmt in ("GLB", "FBX"):
    s.export_format = fmt
    p = core.export_asset(ctx, s)
    if p:
        files.append(os.path.basename(p))
print("[RESULT] " + json.dumps({
    "tris": tris,
    "faces": len(low.data.polygons),
    "uv": uv,
    "report": s.report,
    "files": files,
    "glb": f"{low.name}.glb",
}), flush=True)
stage("done", 1.0)
