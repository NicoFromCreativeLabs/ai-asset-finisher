"""Headless entry point used by the CreativelabsStudio app (and usable by hand):

  blender -b --factory-startup --python cli/optimize_asset.py -- <in.glb> <out_dir> <target_tris> <max_tris> <resolution>

Imports a (textured) mesh, then runs the AI Asset Finisher pipeline: retopology under the triangle
budget, seams + UVs, bake normal/base colour/roughness/metallic/AO into the new UVs, and exports
GLB + FBX + PNG maps to out_dir. Prints `[STAGE] <name> <0-1>` progress lines and a final
`[RESULT] {json}` line.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import bpy

ADDON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ADDON_ROOT)
import ai_asset_finisher  # noqa: E402
from ai_asset_finisher import core  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
src, out_dir = argv[0], argv[1]
target_tris, max_tris, resolution = int(argv[2]), int(argv[3]), argv[4]
# Internal: `--variant-sharp <file.blend>` runs only the sharp-edge remesh and saves it (see below).
VARIANT_OUT = argv[6] if len(argv) > 6 and argv[5] == "--variant-sharp" else None
if VARIANT_OUT is None:
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

ctx = bpy.context
if VARIANT_OUT is not None:
    # Child process: the sharp-edge remesh, saved to a .blend for the parent to load.
    s.preserve_sharp = True
    cand = core.retopologize(ctx, s)
    cand.name = "aaf_variant_sharp"
    bpy.data.libraries.write(VARIANT_OUT, {cand}, fake_user=True)
    print("[VARIANT] saved", flush=True)
    sys.exit(0)

stage("retopology (quad remesh)", 0.10)
# Two quad remeshes: free flow, and one that follows sharp creases; keep the one that loses the least of the
# original's detail (hard-surface parts like grilles and panel lines need the second). Quadriflow can hang
# forever with sharp edges on, so that variant runs in its own Blender process, in parallel, with a time limit.
tmp_dir = tempfile.mkdtemp(prefix="aaf_variant_")
variant_blend = os.path.join(tmp_dir, "sharp.blend")
child = subprocess.Popen(
    [bpy.app.binary_path, "-b", "--factory-startup", "--python", os.path.abspath(__file__), "--",
     src, tmp_dir, str(target_tris), str(max_tris), str(resolution), "--variant-sharp", variant_blend],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
)
t0 = time.time()
s.preserve_sharp = False
free = core.retopologize(ctx, s)
free.name = "aaf_candidate_free"  # retopologize replaces any object named <high>_low
candidates = [(float(free.get("aaf_loss_p99", 1e9)), int(free.get("aaf_non_manifold", 0)), False, free, s.report)]
stage("retopology (sharp-edge variant)", 0.25)
try:
    child.wait(timeout=max(45.0, 2.0 * (time.time() - t0)))
except subprocess.TimeoutExpired:
    child.kill()
    child.wait()
    print("[AAF] Sharp-edge remesh took too long; keeping the free-flow remesh", flush=True)
if child.returncode == 0 and os.path.exists(variant_blend):
    with bpy.data.libraries.load(variant_blend) as (data_from, data_to):
        data_to.objects = [n for n in data_from.objects if n == "aaf_variant_sharp"]
    for cand in data_to.objects:
        if cand is None:
            continue
        cand.use_fake_user = False
        ctx.scene.collection.objects.link(cand)
        rep = core.quality_report(cand, high)  # re-measured here, against this process's high-poly
        report = (
            f"{rep['tris']:,} tris / {rep['faces']:,} faces ({rep['quads']:,} quads, {rep['ngons']} ngons); "
            f"{rep['non_manifold_edges']} non-manifold edges; deviation mean {rep['mean_dev_pct']:.2f}% "
            f"p99 {rep['p99_dev_pct']:.2f}% max {rep['max_dev_pct']:.2f}%; "
            f"detail lost mean {rep['loss_mean_pct']:.2f}% p99 {rep['loss_p99_pct']:.2f}%"
        )
        candidates.append((rep["loss_p99_pct"], rep["non_manifold_edges"], True, cand, report))
shutil.rmtree(tmp_dir, ignore_errors=True)
candidates.sort(key=lambda c: (c[0] * (1.0 + 0.02 * c[1]), c[2]))
loss, _nm, sharp, low, report = candidates[0]
for c in candidates[1:]:
    bpy.data.objects.remove(c[3], do_unlink=True)
low.name = "asset_high_low"
s.low_obj, s.preserve_sharp, s.report = low, sharp, report
tris = core.count_tris(low)
print(f"[AAF] Kept the {'sharp-edge' if sharp else 'free-flow'} remesh (detail lost p99 {loss:.2f}%)", flush=True)
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
    "detail_loss_p99_pct": round(loss, 3),
    "preserve_sharp": sharp,
    "files": files,
    "glb": f"{low.name}.glb",
}), flush=True)
stage("done", 1.0)
