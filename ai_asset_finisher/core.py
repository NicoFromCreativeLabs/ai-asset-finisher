"""Pipeline: retopology -> seams/UV -> bake high->low -> rebuild material -> export."""
import math
import os

import bmesh
import bpy
from mathutils import Vector

PREFIX = "AAF"
# Quadriflow is slow on very dense meshes (photoscans are often millions of faces),
# so decimate first. The collapse pass preserves the shape well enough to remesh from.
PREDECIMATE_ABOVE = 150_000
PREDECIMATE_TO = 120_000


def log(msg):
    print(f"[AAF] {msg}", flush=True)


# --------------------------------------------------------------------------- helpers
def world_diag(obj):
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mn = Vector([min(p[i] for p in pts) for i in range(3)])
    mx = Vector([max(p[i] for p in pts) for i in range(3)])
    return max((mx - mn).length, 1e-9)


def ensure_object_mode():
    obj = bpy.context.view_layer.objects.active
    if obj is not None and obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def select_only(*objs, active=None):
    ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[-1]


def get_high(context, s):
    obj = s.high_obj or context.active_object
    if obj is None or obj.type != "MESH":
        raise RuntimeError("Pick a high-poly mesh object (or make it the active object).")
    return obj


def get_low(s):
    low = s.low_obj
    if low is None or low.name not in bpy.data.objects:
        raise RuntimeError("No low-poly yet. Run 'Retopologize' first.")
    return low


# --------------------------------------------------------------------------- 1. retopology
def _duplicate_as_low(high):
    name = f"{high.name}_low"
    old = bpy.data.objects.get(name)
    if old is not None:
        mesh = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    low = high.copy()
    low.data = high.data.copy()
    low.name = name
    low.data.name = name
    for coll in high.users_collection:
        coll.objects.link(low)
    low.modifiers.clear()
    return low


def _clean_mesh(obj, weld_fraction, fill_sides):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    dist = world_diag(obj) * weld_fraction
    if dist > 0:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    loose = [v for v in bm.verts if not v.link_edges]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    if fill_sides > 0:
        boundary = [e for e in bm.edges if e.is_boundary]
        if boundary:
            res = bmesh.ops.holes_fill(bm, edges=boundary, sides=fill_sides)
            if res.get("faces"):
                bmesh.ops.triangulate(bm, faces=res["faces"])
    bmesh.ops.dissolve_degenerate(bm, dist=max(dist, 1e-9), edges=bm.edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def count_tris(obj):
    me = obj.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def _remove_small_islands(obj, min_fraction):
    """Delete floating fragments (scan debris, AI floaters) smaller than min_fraction of the biggest piece."""
    if min_fraction <= 0:
        return 0
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    seen = set()
    islands = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for e in cur.edges:
                for nb in e.link_faces:
                    if nb.index not in seen:
                        seen.add(nb.index)
                        stack.append(nb)
        islands.append(comp)
    removed = 0
    if len(islands) > 1:
        biggest = max(len(c) for c in islands)
        kill = [f for c in islands if len(c) < biggest * min_fraction for f in c]
        if kill:
            removed = len(kill)
            bmesh.ops.delete(bm, geom=kill, context="FACES")
            loose = [v for v in bm.verts if not v.link_faces]
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return removed


def _decimate_to_tris(obj, target_tris):
    """Collapse-decimate to a triangle budget (output is triangles)."""
    n = count_tris(obj)
    if n <= target_tris:
        return
    select_only(obj)
    mod = obj.modifiers.new("AAF_decimate", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = max(min(target_tris / n, 1.0), 0.0001)
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)


def _quadriflow(obj, s, quads):
    select_only(obj)
    try:
        res = bpy.ops.object.quadriflow_remesh(
            use_mesh_symmetry=False,
            use_preserve_sharp=s.preserve_sharp,
            use_preserve_boundary=s.preserve_boundary,
            smooth_normals=True,
            mode="FACES",
            target_faces=int(max(quads, 50)),
            seed=0,
        )
    except RuntimeError as exc:
        log(f"Quadriflow raised: {exc}")
        return False
    ok = "FINISHED" in res and len(obj.data.polygons) > 0
    if not ok:
        log("Quadriflow did not produce a mesh")
    return ok


def _voxel_remesh(obj, divisions):
    select_only(obj)
    obj.data.remesh_voxel_size = world_diag(obj) / divisions
    try:
        bpy.ops.object.voxel_remesh()
        return len(obj.data.polygons) > 0
    except RuntimeError as exc:
        log(f"Voxel remesh raised: {exc}")
        return False


def _quad_budget_pass(low, s, base_mesh, target_tris, cap_tris):
    """Quadriflow aims at a quad count but can overshoot; retry lower until under the cap."""
    quads = target_tris / 2.0
    for attempt in range(1, 5):
        low.data = base_mesh.copy()
        if not _quadriflow(low, s, quads):
            return False
        tris = count_tris(low)
        log(f"Quadriflow attempt {attempt}: asked {int(quads):,} quads -> {tris:,} tris")
        if tris <= cap_tris:
            return True
        quads *= (target_tris / tris) * 0.93
    return False


def quality_report(low, high_eval_obj):
    """Shape deviation of low vs high (closest-surface distance, as % of size) plus topology health."""
    from mathutils.bvhtree import BVHTree

    diag = world_diag(low)
    deps = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(high_eval_obj, deps)
    mw = low.matrix_world
    inv = high_eval_obj.matrix_world.inverted()
    devs = []
    for v in low.data.vertices:
        hit = bvh.find_nearest(inv @ (mw @ v.co))
        if hit and hit[0] is not None:
            devs.append(((high_eval_obj.matrix_world @ hit[0]) - (mw @ v.co)).length)
    devs.sort()
    me = low.data
    quads = sum(1 for p in me.polygons if len(p.vertices) == 4)
    ngons = sum(1 for p in me.polygons if len(p.vertices) > 4)
    bm = bmesh.new()
    bm.from_mesh(me)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return {
        "tris": count_tris(low),
        "faces": len(me.polygons),
        "quads": quads,
        "ngons": ngons,
        "non_manifold_edges": nonman,
        "mean_dev_pct": (sum(devs) / len(devs) / diag * 100) if devs else 0.0,
        "p99_dev_pct": (devs[int(len(devs) * 0.99)] / diag * 100) if devs else 0.0,
        "max_dev_pct": (devs[-1] / diag * 100) if devs else 0.0,
    }


def retopologize(context, s):
    high = get_high(context, s)
    cap = int(s.max_tris)
    target = min(int(s.target_tris), cap)
    low = _duplicate_as_low(high)
    s.high_obj = high
    s.low_obj = low
    select_only(low)

    n0 = len(low.data.polygons)
    log(f"Retopology: {high.name} has {n0:,} faces; budget {target:,} tris (hard cap {cap:,})")
    _clean_mesh(low, s.weld_fraction, s.fill_holes_sides)

    if n0 > PREDECIMATE_ABOVE:
        log(f"Pre-decimating to {PREDECIMATE_TO:,} tris so the remesher stays fast")
        _decimate_to_tris(low, PREDECIMATE_TO)
        _clean_mesh(low, s.weld_fraction, s.fill_holes_sides)  # decimation can leave pinholes that break Quadriflow
    removed = _remove_small_islands(low, s.drop_island_pct / 100.0)
    if removed:
        log(f"Removed {removed:,} faces of floating debris")

    method_used = s.retopo_method
    if s.retopo_method == "QUADRIFLOW":
        base = low.data.copy()
        ok = _quad_budget_pass(low, s, base, target, cap)
        if not ok:
            log("Falling back: voxel remesh (rebuilds a watertight surface), then quad remesh again")
            method_used = "VOXEL+QUADRIFLOW"
            # Noisy scans give Quadriflow trouble at fine voxel sizes, so go from coarse to fine.
            for div in (120, 80, 200):
                low.data = base.copy()
                if _voxel_remesh(low, div):
                    base2 = low.data.copy()
                    ok = _quad_budget_pass(low, s, base2, target, cap)
                    bpy.data.meshes.remove(base2)
                    if ok:
                        break
        if not ok:
            log("Falling back: decimate")
            method_used = "DECIMATE (fallback)"
            low.data = base.copy()
            _decimate_to_tris(low, target)
        if base.users == 0:
            bpy.data.meshes.remove(base)
    else:
        _decimate_to_tris(low, target)

    # last line of defence: never exceed the cap
    if count_tris(low) > cap:
        log(f"Still over cap ({count_tris(low):,}); decimating to {target:,}")
        _decimate_to_tris(low, target)
        method_used += " + cap decimate"

    # AI meshes carry vertex data we are about to rebuild; keep only the shape.
    me = low.data
    me.name = low.name
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    if s.triangulate:
        select_only(low)
        mod = low.modifiers.new("AAF_tri", "TRIANGULATE")
        bpy.ops.object.modifier_apply(modifier=mod.name)
    select_only(low)
    bpy.ops.object.shade_smooth()
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=s.smooth_angle)
    except (RuntimeError, AttributeError):
        pass

    rep = quality_report(low, high)
    s.report = (
        f"{rep['tris']:,} tris / {rep['faces']:,} faces ({rep['quads']:,} quads, {rep['ngons']} ngons); "
        f"{rep['non_manifold_edges']} non-manifold edges; "
        f"deviation mean {rep['mean_dev_pct']:.2f}% p99 {rep['p99_dev_pct']:.2f}% max {rep['max_dev_pct']:.2f}%"
    )
    s.status = f"Retopology: {n0:,} -> {rep['tris']:,} tris ({method_used})"
    log(s.status)
    log(s.report)
    return low


# --------------------------------------------------------------------------- 2. seams + UV
def build_uvs(context, s):
    low = get_low(s)
    select_only(low)
    me = low.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name="UVMap")

    if s.triangulate:
        mod = low.modifiers.new("AAF_tri", "TRIANGULATE")
        mod.quad_method = "BEAUTY"
        mod.keep_custom_normals = True
        bpy.ops.object.modifier_apply(modifier=mod.name)
        select_only(low)

    # Keep a gap between islands at least as wide as the bake padding.
    margin = max(s.uv_margin, (s.margin_px * 1.0) / float(s.resolution))

    ts = context.scene.tool_settings
    prev_sync = ts.use_uv_select_sync
    ts.use_uv_select_sync = True
    try:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.mark_seam(clear=True)
        # 1. Angle-based projection decides *where* the cuts go ...
        bpy.ops.uv.smart_project(
            angle_limit=s.uv_angle, island_margin=margin,
            area_weight=0.0, correct_aspect=True, scale_to_bounds=False,
        )
        # 2. ... we turn those island borders into real seams ...
        bpy.ops.uv.seams_from_islands(mark_seams=True, mark_sharp=False)
        # 3. ... and unwrap properly across them. Smart-project islands are flat
        # projections and stretch on curved surfaces; a real unwrap does not.
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.unwrap(method=s.unwrap_method, fill_holes=True, correct_aspect=True, margin=margin)
        bpy.ops.uv.average_islands_scale()
        bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        ts.use_uv_select_sync = prev_sync

    seams = sum(1 for e in low.data.edges if e.use_seam)
    s.status = f"UV: {seams:,} seam edges, margin {margin:.4f}"
    log(s.status)
    return uv_report(low)


def uv_report(obj):
    """Cheap sanity numbers: how much of 0-1 space is used and whether anything left it."""
    me = obj.data
    uv = me.uv_layers.active.data
    if len(uv) == 0:
        return {"coverage": 0.0, "out_of_bounds": 0, "islands": 0}
    out = 0
    area = 0.0
    for poly in me.polygons:
        pts = [uv[i].uv for i in poly.loop_indices]
        for p in pts:
            if p.x < -1e-4 or p.x > 1 + 1e-4 or p.y < -1e-4 or p.y > 1 + 1e-4:
                out += 1
        for i in range(1, len(pts) - 1):
            a, b, c = pts[0], pts[i], pts[i + 1]
            area += abs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) * 0.5
    return {"coverage": area, "out_of_bounds": out, "islands": _count_islands(me)}


def _count_islands(me):
    uv = me.uv_layers.active.data
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    key = {}
    for poly in me.polygons:
        for li in poly.loop_indices:
            k = (poly.vertices[li - poly.loop_start], round(uv[li].uv.x, 5), round(uv[li].uv.y, 5))
            key[li] = k
            find(k)
    for poly in me.polygons:
        loops = list(poly.loop_indices)
        for a, b in zip(loops, loops[1:] + loops[:1]):
            find(key[a])
            parent[find(key[a])] = find(key[b])
    return len({find(k) for k in key.values()})


# --------------------------------------------------------------------------- 3. bake
def _configure_cycles(context, s):
    scene = context.scene
    scene.render.engine = "CYCLES"
    cy = scene.cycles
    cy.samples = s.samples
    cy.use_denoising = False
    cy.device = "CPU"
    if not s.use_gpu:
        return "CPU"
    try:
        prefs = context.preferences.addons["cycles"].preferences
        for dev_type in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
            try:
                prefs.compute_device_type = dev_type
            except TypeError:
                continue
            prefs.get_devices()
            devs = [d for d in prefs.devices if d.type == dev_type]
            if devs:
                for d in prefs.devices:
                    d.use = d.type == dev_type
                cy.device = "GPU"
                return f"GPU ({dev_type})"
    except Exception as exc:  # GPU setup must never block baking
        log(f"GPU setup failed, using CPU: {exc}")
    return "CPU"


def _find_principled(nt, out_node):
    if out_node is not None and out_node.inputs["Surface"].links:
        src = out_node.inputs["Surface"].links[0].from_node
        if src.bl_idname == "ShaderNodeBsdfPrincipled":
            return src
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeBsdfPrincipled":
            return n
    return None


def _output_node(nt):
    outs = [n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial"]
    for n in outs:
        if n.is_active_output:
            return n
    return outs[0] if outs else None


class _EmitRewire:
    """Temporarily route one Principled input into an Emission shader so that
    Cycles' EMIT bake returns exactly that channel (Base Color, Roughness, Metallic).
    Cycles' own DIFFUSE/COLOR pass darkens metals, so this is the reliable path."""

    def __init__(self, obj, socket):
        self.obj = obj
        self.socket = socket
        self.undo = []

    def __enter__(self):
        for slot in self.obj.material_slots:
            mat = slot.material
            if mat is None or not mat.node_tree:
                continue
            nt = mat.node_tree
            out = _output_node(nt)
            if out is None:
                continue
            principled = _find_principled(nt, out)
            if principled is None:
                continue
            src = principled.inputs[self.socket]
            emit = nt.nodes.new("ShaderNodeEmission")
            if src.links:
                nt.links.new(src.links[0].from_socket, emit.inputs["Color"])
            else:
                v = src.default_value
                try:
                    emit.inputs["Color"].default_value = (v[0], v[1], v[2], 1.0)
                except TypeError:
                    emit.inputs["Color"].default_value = (v, v, v, 1.0)
            surf = out.inputs["Surface"]
            old = surf.links[0].from_socket if surf.links else None
            nt.links.new(emit.outputs["Emission"], surf)
            self.undo.append((nt, out, emit, old))
        return self

    def __exit__(self, *exc):
        for nt, out, emit, old in self.undo:
            nt.nodes.remove(emit)
            if old is not None:
                nt.links.new(old, out.inputs["Surface"])
        return False


def _ensure_high_material(high):
    """Vertex-color-only or material-less meshes get a temporary material so every
    bake path below works the same way. Returns a cleanup callable."""
    has_nodes = any(sl.material and sl.material.node_tree for sl in high.material_slots)
    if has_nodes:
        return lambda: None
    mat = bpy.data.materials.new(f"{PREFIX}_tmp_high")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    attrs = high.data.color_attributes
    if len(attrs):
        attr = attrs.active_color or attrs[0]
        node = nt.nodes.new("ShaderNodeVertexColor")
        node.layer_name = attr.name
        nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    high.data.materials.clear()
    high.data.materials.append(mat)

    def cleanup():
        high.data.materials.clear()
        bpy.data.materials.remove(mat)

    return cleanup


def _new_image(name, size, color_space):
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, size, size, alpha=False)
    img.colorspace_settings.name = color_space
    return img


def _bake_one(context, s, high, low, mat, name, img, bake_type, socket=None, extra=None):
    nt = mat.node_tree
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    node.label = name
    for n in nt.nodes:
        n.select = False
    node.select = True
    nt.nodes.active = node

    diag = world_diag(low)
    select_only(high, low, active=low)
    args = dict(
        type=bake_type,
        margin=s.margin_px,
        margin_type="EXTEND",
        use_selected_to_active=True,
        cage_extrusion=diag * s.cage_extrusion_pct / 100.0,
        max_ray_distance=diag * s.max_ray_pct / 100.0,
        use_clear=True,
        target="IMAGE_TEXTURES",
    )
    if bake_type == "NORMAL":
        args["normal_space"] = "TANGENT"
        args["normal_g"] = "POS_Y" if s.normal_convention == "OPENGL" else "NEG_Y"
    if extra:
        args.update(extra)

    log(f"Baking {name} ({bake_type})...")
    if socket is None:
        bpy.ops.object.bake(**args)
    else:
        with _EmitRewire(high, socket):
            bpy.ops.object.bake(**args)
    return node


def bake_textures(context, s):
    high = get_high(context, s)
    low = get_low(s)
    if not low.data.uv_layers:
        raise RuntimeError("Low-poly has no UVs. Run 'Seams & UV' first.")
    size = int(s.resolution)
    device = _configure_cycles(context, s)
    log(f"Baking at {size}px on {device}")

    base = low.name
    mat = bpy.data.materials.new(f"{base}_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    low.data.materials.clear()
    low.data.materials.append(mat)

    cleanup = _ensure_high_material(high)
    images = {}
    nodes = {}
    try:
        plan = []
        if s.bake_basecolor:
            plan.append(("basecolor", "sRGB", "EMIT", "Base Color"))
        if s.bake_roughness:
            plan.append(("roughness", "Non-Color", "EMIT", "Roughness"))
        if s.bake_metallic:
            plan.append(("metallic", "Non-Color", "EMIT", "Metallic"))
        if s.bake_ao:
            plan.append(("ao", "Non-Color", "AO", None))
        if s.bake_normal:
            plan.append(("normal", "Non-Color", "NORMAL", None))

        for key, cs, bake_type, socket in plan:
            img = _new_image(f"{base}_{key}", size, cs)
            nodes[key] = _bake_one(context, s, high, low, mat, f"{key}", img, bake_type, socket)
            images[key] = img
    finally:
        cleanup()

    # --- rebuild a clean material on the optimized asset
    for key, node in nodes.items():
        if key == "basecolor":
            nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
        elif key == "roughness":
            nt.links.new(node.outputs["Color"], bsdf.inputs["Roughness"])
        elif key == "metallic":
            nt.links.new(node.outputs["Color"], bsdf.inputs["Metallic"])
        elif key == "normal":
            nm = nt.nodes.new("ShaderNodeNormalMap")
            nm.space = "TANGENT"
            nm.uv_map = low.data.uv_layers.active.name
            nt.links.new(node.outputs["Color"], nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    _layout_nodes(nt, nodes, bsdf)

    _save_images(s, images)
    s.status = f"Baked {', '.join(images)} at {size}px"
    log(s.status)
    return images


def _layout_nodes(nt, nodes, bsdf):
    y = 300
    for node in nodes.values():
        node.location = (-700, y)
        y -= 300
    bsdf.location = (-100, 0)


def _save_images(s, images):
    out = bpy.path.abspath(s.out_dir) if s.out_dir else ""
    for key, img in images.items():
        if out:
            os.makedirs(out, exist_ok=True)
            path = os.path.join(out, f"{img.name}.png")
            img.filepath_raw = path
            img.file_format = "PNG"
            img.save()
        else:
            img.pack()


# --------------------------------------------------------------------------- 4. export + full run
def export_asset(context, s):
    if s.export_format == "NONE":
        return None
    low = get_low(s)
    out = bpy.path.abspath(s.out_dir) if s.out_dir else os.path.dirname(bpy.data.filepath)
    if not out:
        raise RuntimeError("Set a texture folder (or save the .blend) so there is somewhere to export to.")
    os.makedirs(out, exist_ok=True)
    select_only(low)
    if s.export_format == "GLB":
        path = os.path.join(out, f"{low.name}.glb")
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True)
    else:
        path = os.path.join(out, f"{low.name}.fbx")
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, path_mode="COPY", embed_textures=True)
    log(f"Exported {path}")
    return path


def run_all(context, s):
    retopologize(context, s)
    report = build_uvs(context, s)
    bake_textures(context, s)
    path = export_asset(context, s)
    high, low = get_high(context, s), get_low(s)
    if s.hide_high:
        high.hide_set(True)
    select_only(low)
    s.status = f"Done: {len(low.data.polygons):,} faces" + (f", exported {os.path.basename(path)}" if path else "")
    return report
