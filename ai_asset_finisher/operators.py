import bpy

from . import core


class _AAFOperator(bpy.types.Operator):
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context, s):
        raise NotImplementedError

    def execute(self, context):
        s = context.scene.aaf
        try:
            self.run(context, s)
        except Exception as exc:  # surface any failure in the UI instead of a traceback popup
            s.status = f"Failed: {exc}"
            self.report({"ERROR"}, str(exc))
            core.log(f"FAILED: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, s.status)
        return {"FINISHED"}


class AAF_OT_retopo(_AAFOperator):
    bl_idname = "aaf.retopo"
    bl_label = "1. Retopologize"
    bl_description = "Duplicate the high-poly and rebuild it as an optimized low-poly mesh"

    def run(self, context, s):
        core.retopologize(context, s)


class AAF_OT_uv(_AAFOperator):
    bl_idname = "aaf.uv"
    bl_label = "2. Seams & UV"
    bl_description = "Create seams, unwrap and pack UVs on the low-poly"

    def run(self, context, s):
        core.build_uvs(context, s)


class AAF_OT_bake(_AAFOperator):
    bl_idname = "aaf.bake"
    bl_label = "3. Bake & Rebuild Material"
    bl_description = "Bake high-poly maps into the low-poly UVs and build a clean PBR material"

    def run(self, context, s):
        core.bake_textures(context, s)


class AAF_OT_run_all(_AAFOperator):
    bl_idname = "aaf.run_all"
    bl_label = "Run Full Pipeline"
    bl_description = "Retopology, seams/UV, bake and (optionally) export in one go"

    def run(self, context, s):
        core.run_all(context, s)


class AAF_OT_export(_AAFOperator):
    bl_idname = "aaf.export"
    bl_label = "Export"
    bl_description = "Export the finished low-poly with its textures"

    def run(self, context, s):
        if s.export_format == "NONE":
            raise RuntimeError("Choose an export format first.")
        path = core.export_asset(context, s)
        s.status = f"Exported {path}"


classes = (AAF_OT_retopo, AAF_OT_uv, AAF_OT_bake, AAF_OT_run_all, AAF_OT_export)
