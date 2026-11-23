import math

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


def _is_mesh(_self, obj):
    return obj.type == "MESH"


class AAFSettings(bpy.types.PropertyGroup):
    high_obj: PointerProperty(
        name="High-poly",
        description="The AI-generated mesh to convert. Falls back to the active object",
        type=bpy.types.Object,
        poll=_is_mesh,
    )
    low_obj: PointerProperty(
        name="Low-poly",
        description="Result of the retopology step (created for you)",
        type=bpy.types.Object,
        poll=_is_mesh,
    )

    # --- Retopology ---
    retopo_method: EnumProperty(
        name="Method",
        items=[
            ("QUADRIFLOW", "Quad remesh", "Clean quad topology (Quadriflow). Falls back to voxel+quad, then decimate"),
            ("DECIMATE", "Decimate", "Triangle collapse decimation. Fast and robust, triangle output"),
        ],
        default="QUADRIFLOW",
    )
    target_tris: IntProperty(
        name="Target triangles",
        description="Triangle budget of the optimized mesh (a quad counts as 2). Quad remesh lands within roughly +-15%",
        default=12000, min=200, max=500000,
    )
    max_tris: IntProperty(
        name="Hard cap (tris)",
        description="The result is never allowed to exceed this many triangles; the remesh is retried lower, then decimated",
        default=15000, min=200, max=500000,
    )
    drop_island_pct: FloatProperty(
        name="Drop debris below %",
        description="Delete disconnected fragments smaller than this % of the largest piece (scan floaters, AI debris). 0 disables",
        default=0.5, min=0.0, max=50.0,
    )
    preserve_sharp: BoolProperty(name="Preserve sharp edges", default=False)
    preserve_boundary: BoolProperty(name="Preserve boundaries", default=False)
    weld_fraction: FloatProperty(
        name="Weld distance",
        description="Merge vertices closer than this fraction of the object size before remeshing",
        default=1e-5, min=0.0, max=0.01, precision=6,
    )
    fill_holes_sides: IntProperty(
        name="Fill holes up to",
        description="Close holes with at most this many boundary edges (needed for a clean remesh). 0 disables",
        default=64, min=0, max=10000,
    )
    triangulate: BoolProperty(
        name="Triangulate result",
        description="Triangulate before baking so the normal map matches game engines exactly",
        default=False,
    )
    smooth_angle: FloatProperty(
        name="Smooth shading angle",
        description="Edges sharper than this stay hard. Normal maps bake against this shading",
        subtype="ANGLE", default=math.radians(60), min=0.0, max=math.pi,
    )

    # --- UV ---
    uv_angle: FloatProperty(
        name="Island angle",
        description="Smaller angle = more seams and islands, less distortion",
        subtype="ANGLE", default=math.radians(66), min=math.radians(1), max=math.radians(89),
    )
    uv_max_islands: IntProperty(
        name="Max islands",
        description="Merge small UV islands into neighbours until at most this many remain (fewer seams, easier texture painting)",
        default=16, min=1, max=500,
    )
    uv_merge_cone: FloatProperty(
        name="Max chart curvature",
        description="A merged island may not curve around more than this angle (keeps stretching low)",
        subtype="ANGLE", default=math.radians(100), min=math.radians(30), max=math.radians(170),
    )
    unwrap_method: EnumProperty(
        name="Unwrap",
        items=[
            ("ANGLE_BASED", "Angle based", "Low distortion, good general default"),
            ("CONFORMAL", "Conformal", "Preserves angles, can vary island scale"),
        ],
        default="ANGLE_BASED",
    )
    uv_margin: FloatProperty(
        name="Island margin",
        description="Gap between islands in UV space. Raised automatically if smaller than the bake margin",
        default=0.004, min=0.0, max=0.1, precision=4,
    )

    # --- Bake ---
    resolution: EnumProperty(
        name="Texture size",
        items=[("1024", "1K", ""), ("2048", "2K", ""), ("4096", "4K", ""), ("8192", "8K", "")],
        default="2048",
    )
    samples: IntProperty(name="Samples", description="Cycles samples (anti-aliasing and AO quality)", default=16, min=1, max=4096)
    margin_px: IntProperty(name="Margin (px)", description="Edge padding that prevents seams showing", default=16, min=0, max=128)
    cage_extrusion_pct: FloatProperty(
        name="Cage extrusion %", description="How far rays start above the low-poly, as % of object size",
        default=2.0, min=0.0, max=50.0,
    )
    max_ray_pct: FloatProperty(
        name="Max ray distance %", description="How far rays search for the high-poly, as % of object size",
        default=5.0, min=0.0, max=100.0,
    )
    bake_normal: BoolProperty(name="Normal", default=True)
    bake_basecolor: BoolProperty(name="Base color", default=True)
    bake_roughness: BoolProperty(name="Roughness", default=True)
    bake_metallic: BoolProperty(name="Metallic", default=True)
    bake_ao: BoolProperty(name="Ambient occlusion", default=False)
    normal_convention: EnumProperty(
        name="Normal map",
        items=[
            ("OPENGL", "OpenGL (+Y)", "Blender, Unity, glTF"),
            ("DIRECTX", "DirectX (-Y)", "Unreal Engine"),
        ],
        default="OPENGL",
    )
    use_gpu: BoolProperty(name="Use GPU", default=True)

    # --- Output ---
    out_dir: StringProperty(
        name="Texture folder",
        description="Where baked PNGs are saved. Empty = pack into the .blend",
        subtype="DIR_PATH", default="",
    )
    export_format: EnumProperty(
        name="Export",
        items=[("NONE", "None", ""), ("GLB", "glTF binary (.glb)", ""), ("FBX", "FBX (.fbx)", "")],
        default="NONE",
    )
    hide_high: BoolProperty(name="Hide high-poly when done", default=True)
    status: StringProperty(default="")
    report: StringProperty(default="")


classes = (AAFSettings,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.aaf = PointerProperty(type=AAFSettings)


def unregister():
    del bpy.types.Scene.aaf
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
