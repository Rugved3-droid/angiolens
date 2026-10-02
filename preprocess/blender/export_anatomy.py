"""Blender 4.2: export Z-Anatomy skeleton and heart to GLB in the canonical LPS-mm atlas frame.

    powershell -File preprocess/blender/run_blender.ps1 -Script preprocess/blender/export_anatomy.py -Log assets/anatomy/blender_stdout.txt
               -ScriptArgs "assets/anatomy/frame.json|assets/anatomy|assets/anatomy/provenance.json"
    (= blender -b --disable-autoexec --python-exit-code 1 Startup.blend --python export_anatomy.py -- <frame.json> <out_dir> <provenance.json>,
     after a free-memory check). Then: python preprocess/scripts/weld_skin.py (writes the welded z_anatomy_skin.glb).

Rules (CONVENTIONS.md section 10):
  * ONE source-to-LPS matrix (frame.json: rigid rotation x uniform mm scale) for every structure; no structure is
    individually recentred, rotated, scaled or moved to the origin. No translation is applied at all.
  * CURVE objects (the coronaries, cardiac veins, many vessels) are converted from their EVALUATED geometry
    (bevel applied, via the depsgraph), never from raw control points.
  * Vertices are baked into LPS mm; every exported node has an IDENTITY transform (the web loader rejects others).
  * glTF axis conversion is OFF (export_yup=False): coordinates are written verbatim.
  * Original names are kept as node names AND in extras (glTF/three.js may sanitize node names).
  * Multi-spline coronary curves (LAD, LCx, RCA) are ALSO exported spline by spline as child nodes named
    "<VESSEL>_branch_NN" (NN = spline index + 1). Each is evaluated exactly like its parent (same bevel, same object,
    same single transform), never moved. No clinical branch names are assigned (Rugved labels them in Label mode).
  * The heart is exported twice in one run (D46): z_anatomy_heart.glb keeps the atlas's AUTHORED per-point coronary radii
    (THE geometry), z_anatomy_heart_illustrative.glb overwrites them with an illustrative linear taper (comparison only).
  * Great vessels (D46): the full aorta (root to the iliac bifurcation), the three arch branches, SVC, thoracic IVC and the
    pulmonary arteries, with their authored radii. Tubes are tessellated finer and their ends closed (in memory only: the
    curve, its radii and its position are untouched). The pulmonary trunk (a coarse mesh) is subdivided and smoothed with
    every vertex kept within PT_MAX_DEV_MM of where it was; the deviation is measured both ways and logged.
  * Effective ostium (D46): where each coronary centreline crosses the ascending-aortic wall. A proximal end OUTSIDE the
    wall (a floating ostium) stops the export.
  * Catheter access routes (D47): femoral (both sides) and right radial, exported as z_anatomy_access_routes.glb, same rules.
  * The skin is the atlas's own "9: Regions of human body" (D44), exported per region to z_anatomy_skin_regions.glb;
    preprocess/scripts/weld_skin.py welds it into one surface (D48).
  * Export runs from a separate EMPTY staging scene with materials off: exporting from the Z-Anatomy scene itself stalls in
    the glTF gatherer (observed here; also reported by Anatria-3D). The viewer does its own shading.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import mathutils
import mathutils.kdtree
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
frame = json.loads(Path(argv[0]).read_text())
out_dir = Path(argv[1])
prov = json.loads(Path(argv[2]).read_text())
M = mathutils.Matrix([list(r) + [0.0] for r in frame["matrix_source_to_LPS_mm"]] + [[0, 0, 0, 1]])
assert abs(M.to_3x3().determinant()) > 0 and M.to_3x3().determinant() > 0, "frame matrix must be a proper rotation x positive scale"

dg = bpy.context.evaluated_depsgraph_get()
LOG = open(Path(argv[1]) / "export_log.txt", "w")


def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    LOG.write(msg + "\n")
    LOG.flush()


scene_objs = set(bpy.context.scene.objects)


def coll_path(o):
    def walk(c, prefix):
        p = f"{prefix}/{c.name}" if prefix else c.name
        if o.name in c.objects:
            return p
        for ch in c.children:
            r = walk(ch, p)
            if r:
                return r
        return None
    return walk(bpy.context.scene.collection, "")


def descendants(root_name):
    root = bpy.data.objects.get(root_name)
    if root is None:
        return []
    out, stack = [], [root]
    while stack:
        o = stack.pop()
        out.append(o)
        stack.extend(o.children)
    return out


def has_geometry(o):
    if o.type not in ("MESH", "CURVE", "SURFACE", "META") or o not in scene_objs:
        return False
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.polygons) if me else 0
    ev.to_mesh_clear()
    return n > 0


# ---------------- selections ----------------
# great vessels (D46): the full aorta (root to the iliac bifurcation, for the catheter route) with the three arch branches,
# SVC, thoracic IVC, and the pulmonary ARTERIES (no pulmonary veins, by decision)
GREAT = ["Ascending aorta", "Aortic arch", "Thoracic aorta", "Abdominal aorta", "Brachiocephalic trunk", "Left common carotid artery",
         "Left subclavian artery", "Superior vena cava", "Inferior vena cava (thoracic part)", "Pulmonary trunk",
         "Bifurcation of pulmonary trunk", "Left pulmonary artery", "Right pulmonary artery"]
# catheter access routes (D47): femoral both sides (the atlas has no separate common femoral object: "Femoral artery" runs from
# the inguinal ligament down the thigh) and the right radial route; the brachiocephalic trunk is already a great vessel
ACCESS = ["Common iliac artery.r", "Common iliac artery.l", "External iliac artery.r", "External iliac artery.l",
          "Femoral artery.r", "Femoral artery.l", "Right subclavian artery", "Axillary artery.r", "Brachial artery.r", "Radial artery.r"]
ACCESS_CHAINS = [["Abdominal aorta", "Common iliac artery.r", "External iliac artery.r", "Femoral artery.r"],
                 ["Abdominal aorta", "Common iliac artery.l", "External iliac artery.l", "Femoral artery.l"],
                 ["Brachiocephalic trunk", "Right subclavian artery", "Axillary artery.r", "Brachial artery.r", "Radial artery.r"],
                 ["Ascending aorta", "Aortic arch", "Thoracic aorta", "Abdominal aorta"]]
# finer tessellation + closed ends for the big tubes (display only: the curve, its radii and its placement are untouched)
TUBE_RES_U, TUBE_BEVEL_RES = 24, 12
tube_settings = {}
for n in GREAT + ACCESS:
    o = bpy.data.objects.get(n)
    if o is not None and o.type == "CURVE":
        cu = o.data
        tube_settings[n] = {"resolution_u": [cu.resolution_u, max(cu.resolution_u, TUBE_RES_U)],
                            "bevel_resolution": [cu.bevel_resolution, max(cu.bevel_resolution, TUBE_BEVEL_RES)],
                            "use_fill_caps": [cu.use_fill_caps, True]}
        cu.resolution_u = max(cu.resolution_u, TUBE_RES_U)
        cu.bevel_resolution = max(cu.bevel_resolution, TUBE_BEVEL_RES)
        cu.use_fill_caps = True
dg = bpy.context.evaluated_depsgraph_get()
dg.update()

heart_roots = ["Heart.g", "Arteries of heart.g", "Cardiac veins.g"]
heart = [o for r in heart_roots for o in descendants(r) if has_geometry(o)]
great = [bpy.data.objects[n] for n in GREAT if n in bpy.data.objects and has_geometry(bpy.data.objects[n])]
missing_great = [n for n in GREAT if n not in {o.name for o in great}]
access = [bpy.data.objects[n] for n in ACCESS if n in bpy.data.objects and has_geometry(bpy.data.objects[n])]
missing_access = [n for n in ACCESS if n not in {o.name for o in access}]
heart_set = list(dict.fromkeys(heart + great))
skel = [o for o in bpy.context.scene.objects if (coll_path(o) or "").startswith("Scene Collection/1: Skeletal system") and has_geometry(o)]

src_sha = prov.get("startup_blend_sha256")
manifest = []
new_objects = {}


def export_copy(o, group):
    """Evaluated geometry -> new mesh, vertices baked to LPS mm, identity object transform, original name kept."""
    ev = o.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=False, depsgraph=dg)
    me.transform(M @ o.matrix_world)
    if (M @ o.matrix_world).determinant() < 0:          # mirrored source transform: keep outward normals
        me.flip_normals()
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.triangulate(bm, faces=bm.faces[:]); tris = len(bm.faces); bm.free()
    name = o.name
    o.name = "__src__" + name                             # free the name (in memory only; the source file is never saved)
    ob = bpy.data.objects.new(name, me)
    ob["anatomical_name"] = name
    ob["source_blender_name"] = name
    ob["source_collection"] = coll_path(o) or ""
    ob["source_object_type"] = o.type
    ob["source_parent"] = (o.parent.name.replace("__src__", "") if o.parent else "")
    ob["curve_or_mesh"] = "curve(evaluated bevel)" if o.type == "CURVE" else "mesh"
    ob["export_group"] = group
    me.materials.clear()                                  # no materials: the viewer shades by anatomy
    co = [v.co for v in me.vertices]
    lo = [min(p[i] for p in co) for i in range(3)]
    hi = [max(p[i] for p in co) for i in range(3)]
    ev_src = o.evaluated_get(dg).to_mesh()
    pts = [o.matrix_world @ v.co for v in ev_src.vertices]
    slo = [min(p[i] for p in pts) for i in range(3)]
    shi = [max(p[i] for p in pts) for i in range(3)]
    o.evaluated_get(dg).to_mesh_clear()
    manifest.append({
        "anatomical_name": name, "source_blender_name": name, "source_collection": ob["source_collection"],
        "source_parent": ob["source_parent"], "source_object_type": o.type, "exported_node_name": name,
        "curve_or_mesh": ob["curve_or_mesh"], "triangle_count": tris, "export_group": group,
        "bbox_source": [slo, shi], "bbox_LPS": [lo, hi], "center_LPS": [(a + b) / 2 for a, b in zip(lo, hi)],
        "provenance": {"source": "Z-Anatomy Startup.blend", "repo_commit": prov.get("repo_commit"), "startup_blend_sha256": src_sha,
                       "transform": "matrix_source_to_LPS_mm @ matrix_world (shared by every structure)"},
    })
    return ob


ATTACH_TOL_MM = 2.0
SPLIT = {"Anterior interventricular artery": "LAD", "Circumflex artery of heart": "LCx", "Right coronary artery": "RCA"}
PARENT_VESSEL_OF = {"Anterior interventricular artery": "Left coronary artery", "Circumflex artery of heart": "Left coronary artery"}


def spline_centreline_lps(obj, spline):
    """Evaluated centreline of one spline in LPS mm (Bezier: interpolate_bezier at the curve's resolution_u)."""
    W = M @ obj.matrix_world
    res = max(int(obj.data.resolution_u), 2)
    pts = []
    if spline.type == "BEZIER":
        bp = list(spline.bezier_points)
        pairs = list(zip(bp[:-1], bp[1:])) + ([(bp[-1], bp[0])] if spline.use_cyclic_u else [])
        for a, b in pairs:
            seg = mathutils.geometry.interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co, res + 1)
            pts.extend(seg if not pts else seg[1:])
    else:                                                  # POLY / NURBS: points (NURBS: control polygon, flagged)
        pts = [mathutils.Vector(q.co[:3]) for q in spline.points]
    return [W @ v for v in pts]


def polyline_len(P):
    return sum((b - a).length for a, b in zip(P[:-1], P[1:]))


def nearest_on(P, q):
    best = (1e18, None, None)
    for a, b in zip(P[:-1], P[1:]):
        c, t = mathutils.geometry.intersect_point_line(q, a, b)
        t = min(1.0, max(0.0, t))
        c = a + (b - a) * t
        d = (c - q).length
        if d < best[0]:
            best = (d, c, t)
    return best


def export_branches(src, vessel_ob, stage, group):
    """One child node per spline of a multi-spline coronary curve, same evaluated-geometry conversion and transform."""
    vessel = vessel_ob.name
    tag = SPLIT[vessel]
    cu = src.data
    lines = [spline_centreline_lps(src, sp) for sp in cu.splines]
    parent_lines = []
    pv = PARENT_VESSEL_OF.get(vessel)
    if pv:
        pobj = bpy.data.objects.get("__src__" + pv) or bpy.data.objects.get(pv)
        if pobj is not None and pobj.type == "CURVE":
            parent_lines = [(pv, spline_centreline_lps(pobj, sp)) for sp in pobj.data.splines]
    made = []
    for i, sp in enumerate(cu.splines):
        tmp = src.copy()
        tmp.data = cu.copy()
        for j in reversed(range(len(tmp.data.splines))):
            if j != i:
                tmp.data.splines.remove(tmp.data.splines[j])
        bpy.context.scene.collection.objects.link(tmp)
        dgl = bpy.context.evaluated_depsgraph_get()
        dgl.update()
        ev = tmp.evaluated_get(dgl)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=False, depsgraph=dgl)
        me.transform(M @ tmp.matrix_world)                 # the SAME shared transform as every other structure
        if (M @ tmp.matrix_world).determinant() < 0:
            me.flip_normals()
        me.materials.clear()
        bpy.context.scene.collection.objects.unlink(tmp)
        tmp_curve = tmp.data
        bpy.data.objects.remove(tmp, do_unlink=True)
        bpy.data.curves.remove(tmp_curve)
        bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.triangulate(bm, faces=bm.faces[:]); tris = len(bm.faces); bm.free()
        name = f"{tag}_branch_{i + 1:02d}"
        ob = bpy.data.objects.new(name, me)
        ob.parent = vessel_ob                              # identity transforms on both: hierarchy only, no motion
        stage.collection.objects.link(ob)
        P = lines[i]
        e0, e1 = P[0], P[-1]
        # attachment: the endpoint closest to another spline of this vessel or to the parent vessel's centreline
        cands = [(f"{tag}_branch_{j + 1:02d}", L) for j, L in enumerate(lines) if j != i] + parent_lines
        best = None
        for end_name, e in (("start", e0), ("end", e1)):
            for other, L in cands:
                d, c, t = nearest_on(L, e)
                if best is None or d < best[0]:
                    best = (d, end_name, other, c)
        co = [v.co for v in me.vertices]
        lo = [min(q[k] for q in co) for k in range(3)]
        hi = [max(q[k] for q in co) for k in range(3)]
        for key, val in (("anatomical_name", name), ("parent_vessel", vessel), ("spline_index", i), ("export_group", group),
                         ("source_blender_name", vessel), ("source_object_type", "CURVE(spline)")):
            ob[key] = val
        manifest.append({
            "anatomical_name": name, "exported_node_name": name, "source_blender_name": vessel, "source_object_type": "CURVE",
            "source_collection": vessel_ob["source_collection"], "source_parent": vessel,
            "curve_or_mesh": "curve spline (evaluated bevel, single spline)", "export_group": group,
            "parent_vessel": vessel, "spline_index": i, "spline_type": sp.type,
            "control_points": len(sp.bezier_points) + len(sp.points),
            "length_mm": round(polyline_len(P), 2), "length_method": "evaluated Bezier centreline" if sp.type == "BEZIER" else "control polygon (NURBS/POLY)",
            "endpoints_LPS": [list(e0), list(e1)],
            "attachment": (None if best is None else
                           {"end": best[1], "attached_to": best[2], "point_LPS": list(best[3]), "gap_mm": round(best[0], 2)}
                           if best[0] <= ATTACH_TOL_MM else
                           {"end": None, "attached_to": None, "note": "proximal end = ostium: no vessel within "
                            f"{ATTACH_TOL_MM} mm (nearest other spline {best[2]} at {best[0]:.1f} mm)"}),
            "triangle_count": tris, "bbox_LPS": [lo, hi], "center_LPS": [(a + b) / 2 for a, b in zip(lo, hi)],
            "provenance": {"source": "Z-Anatomy Startup.blend", "repo_commit": prov.get("repo_commit"), "startup_blend_sha256": src_sha,
                           "transform": "matrix_source_to_LPS_mm @ matrix_world (shared by every structure)"},
        })
        made.append(ob)
    log(f"[{group}] {vessel}: {len(made)} spline branches exported")
    return made


# ---------------- pulmonary trunk: display refinement of a coarse mesh (D46) ----------------
PT_MAX_DEV_MM = 1.0
pt_report = {}


def refine_mesh(ob, max_dev=PT_MAX_DEV_MM):
    """Subdivide twice (linear: new vertices lie ON the original surface), Laplacian-smooth the interior, then clamp every
    vertex to within max_dev of its on-surface start. Boundary vertices (the open rims) stay put. Deviation measured both ways."""
    me = ob.data
    bm0 = bmesh.new(); bm0.from_mesh(me)
    bvh0 = BVHTree.FromBMesh(bm0)
    probe0 = [v.co.copy() for v in bm0.verts] + [f.calc_center_median() for f in bm0.faces]
    n_v0, n_f0 = len(bm0.verts), len(bm0.faces)
    bm0.free()
    bm = bmesh.new(); bm.from_mesh(me)
    for _ in range(2):
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1, use_grid_fill=True)
    start = {v: v.co.copy() for v in bm.verts}
    inner = [v for v in bm.verts if not v.is_boundary]
    for _ in range(10):
        bmesh.ops.smooth_vert(bm, verts=inner, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    clamped = 0
    for v in bm.verts:
        dv = v.co - start[v]
        if dv.length > max_dev:
            v.co = start[v] + dv * (max_dev / dv.length)
            clamped += 1
    bm.normal_update()
    bvh1 = BVHTree.FromBMesh(bm)
    new_to_old = max(bvh0.find_nearest(v.co)[3] for v in bm.verts)
    old_to_new = max(bvh1.find_nearest(p)[3] for p in probe0)
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    rep = {"method": "2x linear subdivision, 10x Laplacian smoothing of interior vertices, per-vertex displacement clamped",
           "clamp_mm": max_dev, "vertices": [n_v0, len(me.vertices)], "faces": [n_f0, len(me.polygons)], "vertices_clamped": clamped,
           "max_deviation_new_to_original_mm": round(new_to_old, 3), "max_deviation_original_to_new_mm": round(old_to_new, 3)}
    assert max(new_to_old, old_to_new) <= max_dev + 1e-3, rep
    log(f"[refine] {ob.name}: {rep}")
    return rep


def export(objs, group, path, pre_export=None, **gltf_extra):
    stage = bpy.data.scenes.new(f"__EXPORT_{group}__")      # empty staging scene: nothing of the atlas scene is walked
    made = []
    for i, o in enumerate(objs):
        orig = o.name
        ob = export_copy(o, group)
        if orig == "Pulmonary trunk":
            pt_report[group] = refine_mesh(ob)
            manifest[-1]["refinement"] = pt_report[group]
            manifest[-1]["triangle_count"] = sum(len(p.vertices) - 2 for p in ob.data.polygons)
        if orig in tube_settings:
            manifest[-1]["tube_settings_old_new"] = tube_settings[orig]
        stage.collection.objects.link(ob)
        made.append(ob)
        if o.type == "CURVE" and orig in SPLIT and len(o.data.splines) > 1:
            made.extend(export_branches(o, ob, stage, group))
        if i % 100 == 0:
            log(f"[{group}] baked {i + 1}/{len(objs)}: {ob.name}")
    if pre_export:
        pre_export(made)
    vl = stage.view_layers[0]
    for ob in made:
        ob.select_set(True, view_layer=vl)
    log(f"[{group}] exporting {len(made)} objects -> {path}")
    with bpy.context.temp_override(scene=stage, view_layer=vl):
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_active_scene=True, use_selection=True,
                                  export_extras=True, export_yup=False, export_apply=False, export_animations=False,
                                  export_cameras=False, export_lights=False, export_texcoords=False, export_normals=True,
                                  export_materials="NONE", **gltf_extra)
    log(f"[{group}] done")
    return made


# ---------------- illustrative calibre (radius taper) ----------------
# COMPARISON ONLY since D46: Z-Anatomy's coronaries already carry authored per-point radii (bevel 0.5 mm x radius 0.4-4.0),
# which the main export keeps. This pass overwrites them with an ILLUSTRATIVE linear taper (curve point radius, arc length from
# the proximal end) and writes z_anatomy_heart_illustrative.glb. Nothing is moved: only tube radius changes.
TAPER_MM = {"LM": (4.5, 4.5), "MAIN": (3.5, 1.5), "SIDE": (2.0, 1.0)}   # (proximal, distal) DIAMETER, mm
CORONARY_OBJECTS = ["Left coronary artery", "Anterior interventricular artery", "Septal branches of anterior interventricular artery",
                    "Circumflex artery of heart", "Right coronary artery", "Right inferolateral branch of right coronary artery"]
MAIN_PARENT = {"Anterior interventricular artery": "Left coronary artery", "Circumflex artery of heart": "Left coronary artery",
               "Right coronary artery": "OSTIUM", "Left coronary artery": "OSTIUM"}


def control_point_arclength(obj, sp):
    """Arc length (mm, LPS) of the evaluated centreline at each control point, and the total length."""
    P = spline_centreline_lps(obj, sp)
    cum = [0.0]
    for a, b in zip(P[:-1], P[1:]):
        cum.append(cum[-1] + (b - a).length)
    if sp.type == "BEZIER":
        res = max(int(obj.data.resolution_u), 2)
        return [cum[min(k * res, len(cum) - 1)] for k in range(len(sp.bezier_points))], cum[-1]
    return cum, cum[-1]


def apply_taper():
    lines = {(n, i): spline_centreline_lps(bpy.data.objects[n], sp)
             for n in CORONARY_OBJECTS for i, sp in enumerate(bpy.data.objects[n].data.splines)}
    aorta = bpy.data.objects.get("Ascending aorta")
    aorta_lines = [spline_centreline_lps(aorta, sp) for sp in aorta.data.splines]
    out = []
    for n in CORONARY_OBJECTS:
        o = bpy.data.objects[n]
        base_r_mm = o.data.bevel_depth * (M @ o.matrix_world).to_scale()[0]
        for i, sp in enumerate(o.data.splines):
            P = lines[(n, i)]
            ends = {"start": P[0], "end": P[-1]}
            if MAIN_PARENT.get(n) == "OSTIUM" and i == 0:
                # ostial trunk: proximal end = endpoint nearer the ascending-aorta centreline (aortic root)
                d = {k: min(nearest_on(L, e)[0] for L in aorta_lines) for k, e in ends.items()}
                prox = min(d, key=d.get)
                why = f"ostial trunk: endpoint nearer the aortic-root centreline ({d[prox]:.1f} vs {max(d.values()):.1f} mm)"
            else:
                best = None
                for k, e in ends.items():
                    for key, L in lines.items():
                        if key != (n, i):
                            g = nearest_on(L, e)[0]
                            if best is None or g < best[0]:
                                best = (g, k, key)
                prox = best[1]
                why = f"attached end: {best[2][0]} spline {best[2][1]} at {best[0]:.2f} mm"
                if best[0] > ATTACH_TOL_MM:
                    raise SystemExit(f"taper {n} spline {i}: no attachment within {ATTACH_TOL_MM} mm ({why})")
            kind = "LM" if n == "Left coronary artery" else "MAIN" if (i == 0 and n in MAIN_PARENT) else "SIDE"
            d0, d1 = TAPER_MM[kind]
            s_cp, total = control_point_arclength(o, sp)
            pts = list(sp.bezier_points) if sp.type == "BEZIER" else list(sp.points)
            old = [p.radius for p in pts]
            for p, sv in zip(pts, s_cp):
                t = sv / total if total > 0 else 0.0
                if prox == "end":
                    t = 1.0 - t
                p.radius = ((d0 + (d1 - d0) * t) / 2.0) / base_r_mm
            out.append({"object": n, "spline_index": i, "kind": kind, "proximal_end": prox, "proximal_reason": why,
                        "diameter_mm_proximal": d0, "diameter_mm_distal": d1, "length_mm": round(total, 2),
                        "base_bevel_radius_mm": round(base_r_mm, 4), "previous_point_radii_range": [min(old), max(old)],
                        "calibre": "illustrative"})
    log(f"taper applied to {len(out)} coronary splines")
    return out


def measured_end_diameters(ob, centreline):
    """Mean tube diameter (mm) over the first and last 8% of the centreline samples, measured on the exported mesh."""
    kd = mathutils.kdtree.KDTree(len(centreline))
    for k, c in enumerate(centreline):
        kd.insert(c, k)
    kd.balance()
    n = len(centreline)
    a, b = [], []
    for v in ob.data.vertices:
        c, k, d = kd.find(v.co)
        if 0 < k < 0.08 * n:
            a.append(2 * d)
        elif 0.92 * n < k < n - 1:
            b.append(2 * d)
    return (round(sum(a) / len(a), 2) if a else None, round(sum(b) / len(b), 2) if b else None)


def cleanup(made):
    """Remove one export pass's objects and meshes and give the atlas objects their names back (in memory; never saved)."""
    for ob in made:
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    for o in bpy.data.objects:
        if o.name.startswith("__src__"):
            o.name = o.name[len("__src__"):]
    for sc in list(bpy.data.scenes):
        if sc.name.startswith("__EXPORT_"):
            bpy.data.scenes.remove(sc)


# skin = Z-Anatomy's own body surface ("9: Regions of human body", tiled into named surface regions), same atlas
SKIN_EXCLUDE = ("hair", "nail", "perionyx", "eyelash", "eyebrow")
skin = [o for o in bpy.context.scene.objects if (coll_path(o) or "").startswith("Scene Collection/9: Regions of human body")
        and not o.name.endswith(".g") and not any(k in o.name.lower() for k in SKIN_EXCLUDE) and has_geometry(o)]
log(f"skin: {len(skin)} surface-region meshes (excluded *.g boards and {SKIN_EXCLUDE})")
# Every skin region carries a Solidify modifier: evaluated, each region is a thin CLOSED SHELL (outer + inner sheet with opposite
# normals), so neighbouring shells overlap and a welded "surface" would be two sheets. The single body surface is the region's
# base sheet: Solidify is switched off for the export (in memory only; the file is never saved) and its settings are logged.
skin_solidify = {}
for o in skin:
    for md in o.modifiers:
        if md.type == "SOLIDIFY":
            skin_solidify.setdefault(f"thickness {md.thickness * 1000:.2f} mm, offset {md.offset:+.2f}", []).append(o.name)
            md.show_viewport = False
            md.show_render = False
dg = bpy.context.evaluated_depsgraph_get()
dg.update()
log(f"skin: Solidify switched off for export: { {k: len(v) for k, v in skin_solidify.items()} }")

# ---------------- effective ostium (D46) ----------------
RAY_DIRS = [mathutils.Vector(d).normalized() for d in ((0.5773, 0.5778, 0.5769), (-0.61, 0.33, 0.72), (0.27, -0.81, 0.52),
                                                         (-0.42, -0.55, -0.72), (0.83, 0.12, -0.54), (-0.15, 0.91, -0.38),
                                                         (0.04, -0.21, -0.98))]   # skewed: never parallel to a tube axis or cap


def _parity(bvh, p, d):
    n, o = 0, p.copy()
    for _ in range(256):
        hit = bvh.ray_cast(o, d)[0]
        if hit is None:
            break
        n += 1
        o = hit + d * 1e-4
    return n % 2 == 1


def inside_votes(bvh, p):
    return sum(_parity(bvh, p, d) for d in RAY_DIRS)


def inside_closed(bvh, p):
    """Majority vote of ray parity over 7 skewed directions (one ray can graze an edge or cross doubled faces)."""
    return inside_votes(bvh, p) >= 4


def inside_by_normal(bvh, p):
    loc, nrm, _, _ = bvh.find_nearest(p)
    return (p - loc).dot(nrm) < 0


def effective_ostium(wall_ob, vessel, P, label):
    """P: the coronary's evaluated centreline from its ostial end (LPS mm). The effective ostium is where P first leaves the
    closed aortic surface. A proximal end outside the wall (a floating ostium) is a defect and stops the export."""
    bm = bmesh.new(); bm.from_mesh(wall_ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)   # test copy only (cap rims may be separate vertices)
    open_edges = sum(1 for e in bm.edges if e.is_boundary)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    log(f"[ostium] wall {wall_ob.name}: {len(bm.verts)} verts, {len(bm.faces)} faces, open edges {open_edges}, "
        f"edges with >2 faces {nonmanifold}")
    bvh = BVHTree.FromBMesh(bm); bm.free()
    if open_edges:
        raise SystemExit(f"{wall_ob.name} mesh is not closed ({open_edges} open edges): cannot test ostia")
    d0 = bvh.find_nearest(P[0])[3]
    votes, by_normal = inside_votes(bvh, P[0]), inside_by_normal(bvh, P[0])
    if (votes >= 4) != by_normal or votes in (3, 4):
        raise SystemExit(f"{label}: inside test is ambiguous at the proximal end (ray votes {votes}/7 inside, nearest-normal says "
                         f"{'inside' if by_normal else 'outside'}, {d0:.2f} mm from the wall): check the {wall_ob.name} mesh")
    if votes < 4:
        raise SystemExit(f"FLOATING OSTIUM {label}: proximal end lies {d0:.2f} mm OUTSIDE the {wall_ob.name} wall")
    cum = [0.0]
    for a, b in zip(P[:-1], P[1:]):
        cum.append(cum[-1] + (b - a).length)
    k = next((i for i in range(1, len(P)) if not inside_closed(bvh, P[i])), None)
    if k is None:
        raise SystemExit(f"{label}: centreline never leaves the {wall_ob.name}")
    a, b = P[k - 1], P[k]
    lo, hi = 0.0, 1.0
    for _ in range(40):
        m = (lo + hi) / 2
        if inside_closed(bvh, a.lerp(b, m)):
            lo = m
        else:
            hi = m
    c = a.lerp(b, (lo + hi) / 2)
    s = cum[k - 1] + (cum[k] - cum[k - 1]) * (lo + hi) / 2
    loc, nrm, _, dist = bvh.find_nearest(c)
    tangent = (b - a).normalized()
    reenter = [round(cum[i], 1) for i in range(k, len(P)) if cum[i] <= s + 10.0 and inside_closed(bvh, P[i])]
    if reenter:
        raise SystemExit(f"{label}: centreline re-enters the aortic wall within 10 mm of the crossing at arc {reenter}")
    return {"vessel": vessel, "wall": wall_ob.name, "wall_closed": True,
            "proximal_end_LPS": [round(x, 3) for x in P[0]], "proximal_end_inside_wall": True,
            "inside_test": {"ray_votes_inside_of_7": votes, "nearest_normal_inside": by_normal},
            "wall_mesh": {"open_edges": open_edges, "edges_with_more_than_2_faces": nonmanifold},
            "proximal_end_depth_below_wall_mm": round(d0, 2), "buried_centreline_length_mm": round(s, 2),
            "effective_ostium_LPS": [round(x, 3) for x in c], "distance_to_wall_surface_mm": round(dist, 4),
            "wall_normal_LPS": [round(x, 4) for x in nrm], "vessel_direction_LPS": [round(x, 4) for x in tangent],
            "angle_vessel_to_wall_normal_deg": round(math.degrees(tangent.angle(nrm)), 1), "floating": False,
            "note": "future catheter engagement target"}


OSTIAL = {"LM": ("Left coronary artery", 0), "RCA": ("Right coronary artery", 0)}
ostia = {}


def ostial_centreline(vessel, i, aorta_src):
    src = bpy.data.objects.get("__src__" + vessel) or bpy.data.objects[vessel]
    P = spline_centreline_lps(src, src.data.splines[i])
    A = spline_centreline_lps(aorta_src, aorta_src.data.splines[0])
    return P if nearest_on(A, P[0])[0] <= nearest_on(A, P[-1])[0] else P[::-1]


def tag_ostia(made):
    """Before the GLB is written: compute both effective ostia on the exported (capped) ascending aorta and store them on the
    coronary nodes (glTF extras -> three.js userData) and in the manifest."""
    by = {o.name: o for o in made}
    wall = by["Ascending aorta"]
    aorta_src = bpy.data.objects.get("__src__Ascending aorta")
    for label, (vessel, i) in OSTIAL.items():
        r = effective_ostium(wall, vessel, ostial_centreline(vessel, i, aorta_src), label)
        ostia[label] = r
        node = by[vessel] if label == "LM" else by["RCA_branch_01"]
        node["effective_ostium_LPS"] = r["effective_ostium_LPS"]
        node["effective_ostium_wall_normal_LPS"] = r["wall_normal_LPS"]
        log(f"[ostium] {label}: {r}")


# ---------------- authored (atlas) calibre: what the main export keeps ----------------
def authored_end_diameters(obj, sp, n):
    """Mean authored tube diameter (bevel x point radius, mm) over the same sample windows as measured_end_diameters."""
    base_r_mm = obj.data.bevel_depth * abs((M @ obj.matrix_world).to_scale()[0])
    pts = list(sp.bezier_points) if sp.type == "BEZIER" else list(sp.points)
    R = [p.radius for p in pts]
    res = max(int(obj.data.resolution_u), 2) if sp.type == "BEZIER" else 1
    r = [R[min(k // res, len(R) - 1)] + (R[min(k // res + 1, len(R) - 1)] - R[min(k // res, len(R) - 1)]) * ((k % res) / res)
         for k in range(n)]
    a = [2 * base_r_mm * r[k] for k in range(n) if 0 < k < 0.08 * n]
    b = [2 * base_r_mm * r[k] for k in range(n) if 0.92 * n < k < n - 1]
    return (round(sum(a) / len(a), 2) if a else None, round(sum(b) / len(b), 2) if b else None), [min(R), max(R)], base_r_mm


def atlas_calibre(made):
    out = []
    for ob in made:
        if "_branch_" in ob.name:
            src = bpy.data.objects["__src__" + ob["parent_vessel"]]
            sp = src.data.splines[ob["spline_index"]]
        elif ob.name == "Left coronary artery":            # the LM stem: one spline, not split
            src = bpy.data.objects["__src__" + ob.name]
            ob["parent_vessel"], ob["spline_index"] = ob.name, 0
            sp = src.data.splines[0]
        else:
            continue
        P = spline_centreline_lps(src, sp)
        meas = measured_end_diameters(ob, P)
        auth, rr, base = authored_end_diameters(src, sp, len(P))
        out.append({"node": ob.name, "object": ob["parent_vessel"], "spline_index": ob["spline_index"],
                    "base_bevel_radius_mm": round(base, 4), "point_radius_range": [round(rr[0], 3), round(rr[1], 3)],
                    "authored_diameter_mm_start_end": list(auth), "measured_diameter_mm_start_end": list(meas)})
    return out


# ---------------- access routes: continuity (D47) ----------------
def chain_gaps(chains):
    rows = []
    for ch in chains:
        for p, c in zip(ch[:-1], ch[1:]):
            po, co = bpy.data.objects[p], bpy.data.objects[c]
            Pp = spline_centreline_lps(po, po.data.splines[0])
            Pc = spline_centreline_lps(co, co.data.splines[0])
            d_start, d_end = nearest_on(Pp, Pc[0])[0], nearest_on(Pp, Pc[-1])[0]
            prox = "start" if d_start <= d_end else "end"
            rows.append({"parent": p, "child": c, "child_proximal_end": prox, "gap_to_parent_centreline_mm": round(min(d_start, d_end), 3),
                         "gap_to_parent_distal_end_mm": round(((Pc[0] if prox == "start" else Pc[-1]) - Pp[-1]).length, 3),
                         "child_length_mm": round(polyline_len(Pc), 1)})
    return rows


out_dir.mkdir(parents=True, exist_ok=True)
log(f"selected heart {len(heart_set)} objects (missing great vessels: {missing_great}), access routes {len(access)} "
    f"(missing: {missing_access}), skeleton {len(skel)} objects")
heart_names = [o.name for o in heart_set]
calib_atlas = []
heart_objs = export(heart_set, "heart", out_dir / "z_anatomy_heart.glb",
                    pre_export=lambda made: (tag_ostia(made), calib_atlas.extend(atlas_calibre(made))))
chk_verts = {o.name: [tuple(v.co) for v in o.data.vertices] for o in heart_objs
             if o.name in ("Left ventricle", "Right ventricle", "Left atrium", "Right atrium")}
for e in manifest:
    if e.get("parent_vessel") or e["anatomical_name"] in CORONARY_OBJECTS:
        e["calibre"] = "atlas (authored per-point radii; see manifest.calibre.atlas)"
n_main = len(manifest)
cleanup(heart_objs)

taper = apply_taper()
dg = bpy.context.evaluated_depsgraph_get()
dg.update()
tap_objs = export([bpy.data.objects[n] for n in heart_names], "heart_illustrative", out_dir / "z_anatomy_heart_illustrative.glb")
meas = {}
for ob in tap_objs:
    if "_branch_" in ob.name:
        src = bpy.data.objects["__src__" + ob["parent_vessel"]]
        meas[(ob["parent_vessel"], ob["spline_index"])] = measured_end_diameters(
            ob, spline_centreline_lps(src, src.data.splines[ob["spline_index"]]))
for t in taper:
    m0 = meas.get((t["object"], t["spline_index"]))
    if m0:
        t["measured_diameter_mm_proximal"], t["measured_diameter_mm_distal"] = m0 if t["proximal_end"] == "start" else m0[::-1]
for e in manifest[n_main:]:
    if e.get("parent_vessel") or e["anatomical_name"] in CORONARY_OBJECTS:
        e["calibre"] = "illustrative (taper via curve point radius; comparison only; see manifest.calibre.illustrative)"
cleanup(tap_objs)

access_objs = export(access, "access_routes", out_dir / "z_anatomy_access_routes.glb")
cleanup(access_objs)
gaps = chain_gaps(ACCESS_CHAINS)
for g in gaps:
    log(f"[access] {g}")
landmark_z = {}
for n in ("Vertebra L3", "Vertebra L4", "Vertebra L5"):
    o = bpy.data.objects.get(n)
    if o is not None:
        zs = [(M @ o.matrix_world @ v.co).z for v in o.data.vertices]
        landmark_z[n] = [round(min(zs), 1), round(max(zs), 1)]
abd = bpy.data.objects["Abdominal aorta"]
abd_end = spline_centreline_lps(abd, abd.data.splines[0])[-1]
cia_starts = {n: list(spline_centreline_lps(bpy.data.objects[n], bpy.data.objects[n].data.splines[0])[0])
              for n in ("Common iliac artery.r", "Common iliac artery.l")}
bif_label = bpy.data.objects.get("Aortic bifurcation.g")
bifurcation = {"abdominal_aorta_distal_end_LPS": [round(x, 2) for x in abd_end],
               "common_iliac_starts_LPS": {k: [round(x, 2) for x in v] for k, v in cia_starts.items()},
               "atlas_label_Aortic_bifurcation_g_LPS": [round(x, 2) for x in (M @ bif_label.matrix_world.translation)] if bif_label else None,
               "vertebra_z_range_LPS": landmark_z}
log(f"[access] bifurcation {bifurcation}")

skel_objs = export(skel, "skeleton", out_dir / "z_anatomy_skeleton.glb")
skin_objs = export(skin, "skin", out_dir / "z_anatomy_skin_regions.glb")   # per region; weld_skin.py -> z_anatomy_skin.glb (D48)

# ---------------- scale checks with real vertices (LPS mm) ----------------
import numpy as np  # noqa: E402  (Blender ships numpy)

CH = {n: np.array(v) for n, v in chk_verts.items()}
chamber = np.vstack([CH[n] for n in ("Left ventricle", "Right ventricle", "Left atrium", "Right atrium")])
cen = chamber.mean(0)
w, V = np.linalg.eigh(np.cov((chamber - cen).T))
ax = V[:, -1]
proj = (chamber - cen) @ ax
four_chamber_mm = float(proj.max() - proj.min())
lv, la = CH["Left ventricle"], CH["Left atrium"]
atria = np.vstack([CH["Left atrium"], CH["Right atrium"]]).mean(0)
dirn = ax if np.dot(lv.mean(0) - atria, ax) > 0 else -ax
apex = lv[np.argmax((lv - atria) @ dirn)]                  # LV vertex farthest from the atria along the principal axis
dla = np.linalg.norm(lv - la.mean(0), axis=1)
base = lv[dla <= np.percentile(dla, 10)].mean(0)            # LV base: the 10% of LV vertices nearest the left atrium (mitral side)
lv_long_mm = float(np.linalg.norm(apex - base))
t6 = np.array([v.co[:] for v in next(o for o in skel_objs if o.name == "Vertebra T6").data.vertices])
ys = t6[:, 1]
body = t6[ys <= ys.min() + 0.35 * (ys.max() - ys.min())]   # anterior 35% of the AP extent = vertebral body (+Y is posterior)
t6_body_width = float(body[:, 0].max() - body[:, 0].min())
long_axis_from_sagittal_deg = float(np.degrees(np.arcsin(abs(dirn[0]))))  # angle of the axis out of the sagittal (y-z) plane
checks = {
    # D42: primary = LV long axis 70-110 mm; secondary = four-chamber principal-axis length 100-160 mm (both catch unit errors)
    "lv_long_axis_mm": round(lv_long_mm, 1), "lv_long_axis_ok": 70 <= lv_long_mm <= 110,
    "four_chamber_principal_axis_mm": round(four_chamber_mm, 1), "four_chamber_principal_axis_ok": 100 <= four_chamber_mm <= 160,
    "t6_vertebral_body_width_mm": round(t6_body_width, 1), "t6_body_width_ok": 30 <= t6_body_width <= 50,
    "heart_centroid_LPS": cen.round(1).tolist(), "apex_LPS": apex.round(1).tolist(), "lv_base_LPS": base.round(1).tolist(),
    "apex_minus_base_direction_LPS": dirn.round(3).tolist(),
    "apex_is_left_anterior_inferior": bool(dirn[0] > 0 and dirn[1] < 0 and dirn[2] < 0),
    "long_axis_angle_from_sagittal_plane_deg": round(long_axis_from_sagittal_deg, 1),
}
(out_dir / "frame_checks.json").write_text(json.dumps(checks, indent=1))
(out_dir / "manifest.json").write_text(json.dumps({
    "frame": frame, "checks": checks,
    "calibre": {
        "files": {"atlas": "z_anatomy_heart.glb: AUTHORED atlas radii (bevel x per-point radius). THE geometry for the scenes and, "
                           "later, the X-ray and metrics (D46)",
                  "illustrative": "z_anatomy_heart_illustrative.glb: illustrative linear taper; comparison only"},
        "atlas": {"status": "ATLAS authored per-point radii (Z-Anatomy), not measured patient anatomy",
                  "method": "evaluated bevel; diameter = 2 x bevel_depth x curve point radius; measured on the exported meshes",
                  "splines": calib_atlas},
        "illustrative": {"status": "ILLUSTRATIVE calibre, comparison only", "diameters_mm_proximal_distal": TAPER_MM,
                         "method": "curve point radius = target radius / bevel radius, linear in centreline arc length from the proximal end",
                         "splines": taper}},
    "effective_ostia": ostia,
    "great_vessels": {"requested": GREAT, "missing": missing_great, "tube_settings_old_new": {n: tube_settings[n] for n in GREAT if n in tube_settings},
                      "pulmonary_trunk_refinement": pt_report.get("heart")},
    "access_routes": {"file": "z_anatomy_access_routes.glb (hidden by default in the scenes)", "requested": ACCESS, "missing": missing_access,
                      "not_in_atlas": ["common femoral artery as a separate object (the atlas 'Femoral artery' starts at the external iliac)"],
                      "continuity": gaps, "bifurcation": bifurcation,
                      "tube_settings_old_new": {n: tube_settings[n] for n in ACCESS if n in tube_settings}},
    "skin_export": {"file": "z_anatomy_skin_regions.glb (per region; welded by weld_skin.py into z_anatomy_skin.glb)",
                    "solidify_switched_off": {k: len(v) for k, v in skin_solidify.items()},
                    "why": "each region is a thin closed shell with Solidify on; the base sheet is the single body surface"},
    "objects": manifest}, indent=1))
print("EXPORTED heart", len(heart_objs), "illustrative", len(tap_objs), "access", len(access_objs), "skeleton", len(skel_objs),
      "skin regions", len(skin_objs), json.dumps(checks))
