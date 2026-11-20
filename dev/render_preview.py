"""blender -b result.blend --python render_preview.py -- <out.png> [wire]
High-poly (left) vs low-poly with baked maps (right), same camera and light."""
import math
import sys

import bpy
from mathutils import Vector

out = sys.argv[sys.argv.index("--") + 1]
wire = "wire" in sys.argv

scene = bpy.context.scene
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
high = next(o for o in meshes if not o.name.endswith("_low"))
low = next(o for o in meshes if o.name.endswith("_low"))
high.hide_set(False)
high.hide_viewport = False

diag = max(high.dimensions.length, 1e-6)
low.location.x += diag * 0.75
high.location.x -= diag * 0.75
center = Vector((0, 0, 0))
for o in (high, low):
    center += o.matrix_world @ Vector([sum(c[i] for c in o.bound_box) / 8 for i in range(3)])
center /= 2

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 70
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
cam.location = center + Vector((0, -diag * 3.6, diag * 0.9))
track = cam.constraints.new("TRACK_TO")
track.target = bpy.data.objects.new("t", None)
scene.collection.objects.link(track.target)
track.target.location = center
track.track_axis = "TRACK_NEGATIVE_Z"
track.up_axis = "UP_Y"
scene.camera = cam

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 4
sun.rotation_euler = (math.radians(50), 0, math.radians(30))
scene.collection.objects.link(sun)
scene.world = bpy.data.worlds.new("w")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.4, 0.4, 0.42, 1)

if wire:
    mod = low.modifiers.new("wire", "WIREFRAME")
    mod.thickness = diag * 0.0015
    mod.use_replace = False
    wmat = bpy.data.materials.new("wire")
    wmat.use_nodes = True
    wmat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0, 0, 0, 1)
    low.data.materials.append(wmat)
    mod.material_offset = 1

scene.render.engine = "CYCLES"
scene.cycles.samples = 48
scene.cycles.device = "GPU"
scene.render.resolution_x = 1400
scene.render.resolution_y = 700
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print("[PREVIEW] wrote", out)
