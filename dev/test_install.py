import sys, bpy, addon_utils
zp = sys.argv[sys.argv.index("--") + 1]
bpy.ops.preferences.addon_install(filepath=zp, overwrite=True)
addon_utils.enable("ai_asset_finisher", default_set=False)
print("[INSTALL]", bpy.app.version_string, "enabled:", hasattr(bpy.context.scene, "aaf"), bpy.types.Scene.bl_rna.properties.get("aaf") is not None)
