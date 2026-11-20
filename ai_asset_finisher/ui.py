import bpy


class _Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Asset"


class AAF_PT_main(_Panel, bpy.types.Panel):
    bl_label = "AI Asset Finisher"
    bl_idname = "AAF_PT_main"

    def draw(self, context):
        s = context.scene.aaf
        col = self.layout.column(align=True)
        col.prop(s, "high_obj")
        col.prop(s, "low_obj")
        self.layout.operator("aaf.run_all", icon="PLAY")
        if s.status:
            box = self.layout.box()
            box.label(text=s.status, icon="INFO")


class AAF_PT_retopo(_Panel, bpy.types.Panel):
    bl_label = "1. Retopology"
    bl_idname = "AAF_PT_retopo"
    bl_parent_id = "AAF_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.aaf
        col = self.layout.column()
        col.prop(s, "retopo_method")
        col.prop(s, "target_faces")
        if s.retopo_method == "QUADRIFLOW":
            col.prop(s, "preserve_sharp")
            col.prop(s, "preserve_boundary")
        col.prop(s, "fill_holes_sides")
        col.prop(s, "weld_fraction")
        col.prop(s, "smooth_angle")
        col.prop(s, "triangulate")
        col.operator("aaf.retopo")


class AAF_PT_uv(_Panel, bpy.types.Panel):
    bl_label = "2. Seams & UV"
    bl_idname = "AAF_PT_uv"
    bl_parent_id = "AAF_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.aaf
        col = self.layout.column()
        col.prop(s, "uv_angle")
        col.prop(s, "unwrap_method")
        col.prop(s, "uv_margin")
        col.operator("aaf.uv")


class AAF_PT_bake(_Panel, bpy.types.Panel):
    bl_label = "3. Bake"
    bl_idname = "AAF_PT_bake"
    bl_parent_id = "AAF_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.aaf
        col = self.layout.column()
        col.prop(s, "resolution")
        col.prop(s, "samples")
        col.prop(s, "margin_px")
        col.prop(s, "use_gpu")
        row = col.row(align=True)
        row.prop(s, "cage_extrusion_pct")
        row.prop(s, "max_ray_pct")
        box = col.box()
        box.label(text="Maps")
        grid = box.grid_flow(columns=2, align=True)
        for p in ("bake_basecolor", "bake_normal", "bake_roughness", "bake_metallic", "bake_ao"):
            grid.prop(s, p)
        col.prop(s, "normal_convention")
        col.operator("aaf.bake")


class AAF_PT_output(_Panel, bpy.types.Panel):
    bl_label = "Output"
    bl_idname = "AAF_PT_output"
    bl_parent_id = "AAF_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.aaf
        col = self.layout.column()
        col.prop(s, "out_dir")
        col.prop(s, "export_format")
        col.prop(s, "hide_high")
        col.operator("aaf.export")


classes = (AAF_PT_main, AAF_PT_retopo, AAF_PT_uv, AAF_PT_bake, AAF_PT_output)
