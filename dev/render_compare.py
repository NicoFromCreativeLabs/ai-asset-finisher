"""blender -b --factory-startup --python render_compare.py -- out.png a.glb b.glb [...]  (side-by-side, workbench shading)"""
import sys, math, bpy
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
out, files = argv[0], argv[1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
objs = []
for i, f in enumerate(files):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f)
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    o = new[0]
    for p in new[1:]: p.parent = None
    d = max(o.dimensions)
    o.scale = o.scale * (1.2 / d)
    bpy.context.view_layer.update()
    c = sum((o.matrix_world @ Vector(v) for v in o.bound_box), Vector()) / 8
    o.location += Vector((i * 1.5, 0, 0)) - c
    objs.append(o)
scene = bpy.context.scene
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam)
n = len(files)
cam.location = ((n - 1) * 0.75, -4.6, 0.0); cam.rotation_euler = (math.radians(90), 0, 0)
cam.data.lens = 60; scene.camera = cam
scene.render.engine = "BLENDER_WORKBENCH"
sh = scene.display.shading; sh.light = "STUDIO"; sh.color_type = "SINGLE"; sh.single_color = (0.8, 0.8, 0.82); sh.show_cavity = True
scene.render.resolution_x = 700 * n; scene.render.resolution_y = 800
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
