import bpy, sys
print("VERSION", bpy.app.version_string)
for name in ("quadriflow_remesh","voxel_remesh","bake"):
    print(name, hasattr(bpy.ops.object, name))
for name in ("smart_project","unwrap","pack_islands","seams_from_islands","average_islands_scale","minimize_stretch"):
    print("uv."+name, hasattr(bpy.ops.uv, name))
print("mesh.mark_seam", hasattr(bpy.ops.mesh,"mark_seam"), "edges_select_sharp", hasattr(bpy.ops.mesh,"edges_select_sharp"))
print("pack_islands props:", [p.identifier for p in bpy.ops.uv.pack_islands.get_rna_type().properties])
print("smart_project props:", [p.identifier for p in bpy.ops.uv.smart_project.get_rna_type().properties])
print("unwrap props:", [p.identifier for p in bpy.ops.uv.unwrap.get_rna_type().properties])
print("quadriflow props:", [p.identifier for p in bpy.ops.object.quadriflow_remesh.get_rna_type().properties])
b = bpy.context.scene.render.bake
print("bake props:", [p.identifier for p in b.bl_rna.properties])
print("bake_type items:", [i.identifier for i in bpy.types.BakeSettings.bl_rna.properties['type'].enum_items] if 'type' in bpy.types.BakeSettings.bl_rna.properties else 'n/a')
print("bake op props:", [p.identifier for p in bpy.ops.object.bake.get_rna_type().properties])
print("cycles addon", 'cycles' in bpy.context.preferences.addons)
