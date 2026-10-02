"""Blender 4.2: export Z-Anatomy skeleton and heart to GLB in the canonical LPS-mm atlas frame.

    blender -b --disable-autoexec Startup.blend --python preprocess/blender/export_anatomy.py -- <frame.json> <out_dir> <provenance.json>

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
  * The heart is exported twice in one run: z_anatomy_heart.glb (atlas tubes, comparison) and z_anatomy_heart_tapered.glb
    (ILLUSTRATIVE coronary calibre via curve point radius, D43). The skin is the atlas's own "9: Regions of human body" (D44).
  * Export runs from a separate EMPTY staging scene with materials off: exporting from the Z-Anatomy scene itself stalls in
    the glTF gatherer (observed here; also reported by Anatria-3D). The viewer does its own shading.
"""
import json
import sys
from pathlib import Path

import bmesh
import bpy
import mathutils
import mathutils.kdtree

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
heart_roots = ["Heart.g", "Arteries of heart.g", "Cardiac veins.g"]
heart = [o for r in heart_roots for o in descendants(r) if has_geometry(o)]
great = [bpy.data.objects[n] for n in ("Ascending aorta", "Arch of aorta", "Pulmonary trunk", "Superior vena cava", "Inferior vena cava",
                                       "Left pulmonary artery", "Right pulmonary artery") if n in bpy.data.objects and has_geometry(bpy.data.objects[n])]
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


def export(objs, group, path):
    stage = bpy.data.scenes.new(f"__EXPORT_{group}__")      # empty staging scene: nothing of the atlas scene is walked
    made = []
    for i, o in enumerate(objs):
        orig = o.name
        ob = export_copy(o, group)
        stage.collection.objects.link(ob)
        made.append(ob)
        if o.type == "CURVE" and orig in SPLIT and len(o.data.splines) > 1:
            made.extend(export_branches(o, ob, stage, group))
        if i % 100 == 0:
            log(f"[{group}] baked {i + 1}/{len(objs)}: {ob.name}")
    vl = stage.view_layers[0]
    for ob in made:
        ob.select_set(True, view_layer=vl)
    log(f"[{group}] exporting {len(made)} objects -> {path}")
    with bpy.context.temp_override(scene=stage, view_layer=vl):
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_active_scene=True, use_selection=True,
                                  export_extras=True, export_yup=False, export_apply=False, export_animations=False,
                                  export_cameras=False, export_lights=False, export_texcoords=False, export_normals=True,
                                  export_materials="NONE")
    log(f"[{group}] done")
    return made


# ---------------- illustrative calibre (radius taper) ----------------
# Z-Anatomy coronaries are constant-width tubes (bevel_depth 0.5 mm radius). For the LOOK and for the X-ray an
# ILLUSTRATIVE calibre is applied through curve point radius (a multiplier of bevel_depth), linear in centreline arc length
# from the proximal end. Nothing is moved: only tube radius changes; centrelines, transform and evaluated export are unchanged.
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

out_dir.mkdir(parents=True, exist_ok=True)
log(f"selected heart {len(heart_set)} objects, skeleton {len(skel)} objects")
heart_names = [o.name for o in heart_set]
heart_objs = export(heart_set, "heart", out_dir / "z_anatomy_heart.glb")          # untapered: kept for comparison
chk_verts = {o.name: [tuple(v.co) for v in o.data.vertices] for o in heart_objs
             if o.name in ("Left ventricle", "Right ventricle", "Left atrium", "Right atrium")}
n_untapered = len(manifest)
cleanup(heart_objs)

taper = apply_taper()
dg = bpy.context.evaluated_depsgraph_get()
dg.update()
tap_objs = export([bpy.data.objects[n] for n in heart_names], "heart_tapered", out_dir / "z_anatomy_heart_tapered.glb")
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
for e in manifest[n_untapered:]:
    if e.get("parent_vessel") or e["anatomical_name"] in CORONARY_OBJECTS:
        e["calibre"] = "illustrative (taper via curve point radius; see manifest.calibre)"
cleanup(tap_objs)

skel_objs = export(skel, "skeleton", out_dir / "z_anatomy_skeleton.glb")
skin_objs = export(skin, "skin", out_dir / "z_anatomy_skin.glb")

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
    "calibre": {"status": "ILLUSTRATIVE calibre, not measured anatomy", "diameters_mm_proximal_distal": TAPER_MM,
                "method": "curve point radius = target radius / bevel radius, linear in centreline arc length from the proximal end",
                "files": {"tapered": "z_anatomy_heart_tapered.glb (scenes; to be used by the X-ray and metrics)",
                          "untapered": "z_anatomy_heart.glb (original constant 1.0 mm tubes; comparison only)"},
                "splines": taper},
    "objects": manifest}, indent=1))
print("EXPORTED heart", len(heart_objs), "tapered", len(tap_objs), "skeleton", len(skel_objs), "skin", len(skin_objs), json.dumps(checks))
