bl_info = {
    "name": "AI Asset Finisher",
    "author": "3D Labs",
    "version": (0, 2, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > AI Asset",
    "description": "Turn AI generations and photoscans into game-ready assets: retopology, seams/UV, and high-to-low baking",
    "category": "Object",
}

if "bpy" in locals():
    import importlib

    for _m in ("settings", "core", "operators", "ui"):
        if _m in locals():
            importlib.reload(locals()[_m])

import bpy  # noqa: E402

from . import core, operators, settings, ui  # noqa: E402,F401


def register():
    settings.register()
    for cls in operators.classes + ui.classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(operators.classes + ui.classes):
        bpy.utils.unregister_class(cls)
    settings.unregister()
