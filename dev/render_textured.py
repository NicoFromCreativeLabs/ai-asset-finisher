"""blender -b --factory-startup --python render_textured.py -- in.obj out.png  (albedo shown, 3 views)"""
import sys, math, bpy
from mathutils import Vector
inp, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
if inp.lower().endswith((".glb", ".gltf")):
    bpy.ops.import_scene.gltf(filepath=inp)
else:
    bpy.ops.wm.obj_import(filepath=inp)
meshes = [x for x in bpy.context.scene.objects if x.type == "MESH"]
for m in meshes[1:]:
    m.select_set(True)
o = meshes[0]
d = max(o.dimensions); o.scale = o.scale * (1.4 / d); bpy.context.view_layer.update()
c = sum((o.matrix_world @ Vector(v) for v in o.bound_box), Vector()) / 8; o.location -= c
sc = bpy.context.scene
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 70
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading; sh.light = "FLAT"; sh.color_type = "TEXTURE"
sc.render.resolution_x = 900; sc.render.resolution_y = 700
sc.render.film_transparent = False
bpy.data.worlds.new("w"); sc.world = bpy.data.worlds["w"]; sc.world.color = (0.12, 0.12, 0.14)
views = [("front", 0), ("side", 90), ("back", 180), ("front34", 35)]
for name, az in views:
    r = 4.2
    cam.location = (r * math.sin(math.radians(az)), -r * math.cos(math.radians(az)), 0.3)
    cam.rotation_euler = (math.radians(86), 0, math.radians(az))
    sc.render.filepath = out.replace(".png", f"_{name}.png")
    bpy.ops.render.render(write_still=True)
