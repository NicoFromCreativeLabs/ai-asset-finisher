"""Step 1 test (retopology only). Run:
blender -b --factory-startup --python test_retopo.py -- <input.obj> [subdivisions] [target_tris] [cap] [method]
subdivisions>0 subdivides + roughens the mesh first to imitate a dense, noisy photoscan."""
import os
import sys
import time

import bpy

ADDON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ADDON_ROOT)
import ai_asset_finisher  # noqa: E402
from ai_asset_finisher import core  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
src = argv[0]
subdiv = int(argv[1]) if len(argv) > 1 else 0
target = int(argv[2]) if len(argv) > 2 else 12000
cap = int(argv[3]) if len(argv) > 3 else 15000
method = argv[4] if len(argv) > 4 else "QUADRIFLOW"

bpy.ops.wm.read_factory_settings(use_empty=True)
ai_asset_finisher.register()
bpy.ops.wm.obj_import(filepath=src)
high = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
high.name = "scan_high"
bpy.context.view_layer.objects.active = high

if subdiv:
    # photoscan imitation: dense triangles + surface noise + a floating speck
    sub = high.modifiers.new("sub", "SUBSURF")
    sub.levels = subdiv
    sub.subdivision_type = "SIMPLE"
    tex = bpy.data.textures.new("n", "CLOUDS")
    tex.noise_scale = 0.02
    disp = high.modifiers.new("disp", "DISPLACE")
    disp.texture = tex
    disp.strength = 0.002 * max(high.dimensions)
    bpy.ops.object.modifier_apply(modifier="sub")
    bpy.ops.object.modifier_apply(modifier="disp")
    bpy.ops.mesh.primitive_ico_sphere_add(radius=max(high.dimensions) * 0.002, location=(max(high.dimensions), 0, 0))
    bpy.context.view_layer.objects.active = high
    high.select_set(True)
    bpy.context.scene.objects[-1].select_set(True)
    bpy.ops.object.join()
print(f"[TEST] input: {len(high.data.polygons):,} faces")

s = bpy.context.scene.aaf
s.high_obj = high
s.retopo_method = method
s.target_tris = target
s.max_tris = cap
t = time.time()
r = bpy.ops.aaf.retopo()
dt = time.time() - t
print(f"[TEST] retopo -> {r} in {dt:.1f}s | {s.status}")
print(f"[TEST] {s.report}")
low = s.low_obj
tris = core.count_tris(low)
assert "FINISHED" in r
assert tris <= cap, f"{tris} tris exceeds cap {cap}"
assert tris > target * 0.4, f"{tris} tris is far below the target {target}"
rep = core.quality_report(low, high)
assert rep["mean_dev_pct"] < 1.0, f"mean deviation {rep['mean_dev_pct']:.2f}% too high"
assert len(low.data.uv_layers) == 0
print("[TEST] PASS")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.dirname(__file__), "out", "retopo_result.blend"))
