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
  * Export runs from a separate EMPTY staging scene with materials off: exporting from the Z-Anatomy scene itself stalls in
    the glTF gatherer (observed here; also reported by Anatria-3D). The viewer does its own shading.
"""
import json
import sys
from pathlib import Path

import bmesh
import bpy
import mathutils

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


out_dir.mkdir(parents=True, exist_ok=True)
log(f"selected heart {len(heart_set)} objects, skeleton {len(skel)} objects")
heart_objs = export(heart_set, "heart", out_dir / "z_anatomy_heart.glb")
skel_objs = export(skel, "skeleton", out_dir / "z_anatomy_skeleton.glb")

# ---------------- scale checks with real vertices (LPS mm) ----------------
import numpy as np  # noqa: E402  (Blender ships numpy)


def verts(ob):
    return np.array([v.co[:] for v in ob.data.vertices])


by = {o.name: o for o in heart_objs + skel_objs if o.parent is None or "_branch_" not in o.name}
chamber = np.vstack([verts(by[n]) for n in ("Left ventricle", "Right ventricle", "Left atrium", "Right atrium") if n in by])
cen = chamber.mean(0)
w, V = np.linalg.eigh(np.cov((chamber - cen).T))
ax = V[:, -1]
proj = (chamber - cen) @ ax
heart_long_mm = float(proj.max() - proj.min())
lv = verts(by["Left ventricle"])
# apex = LV vertex farthest from the base (atria centroid) along the long axis
atria = np.vstack([verts(by[n]) for n in ("Left atrium", "Right atrium") if n in by]).mean(0)
dirn = ax if np.dot(lv.mean(0) - atria, ax) > 0 else -ax
apex = lv[np.argmax((lv - atria) @ dirn)]
t6 = verts(by["Vertebra T6"])
ys = t6[:, 1]
body = t6[ys <= ys.min() + 0.35 * (ys.max() - ys.min())]   # anterior 35% of the AP extent = vertebral body (+Y is posterior)
t6_body_width = float(body[:, 0].max() - body[:, 0].min())
long_axis_from_sagittal_deg = float(np.degrees(np.arcsin(abs(dirn[0]))))  # angle of the axis out of the sagittal (y-z) plane
checks = {
    "heart_long_axis_mm": round(heart_long_mm, 1), "heart_long_axis_ok": 90 <= heart_long_mm <= 140,
    "t6_vertebral_body_width_mm": round(t6_body_width, 1), "t6_body_width_ok": 30 <= t6_body_width <= 50,
    "heart_centroid_LPS": cen.round(1).tolist(), "apex_LPS": apex.round(1).tolist(),
    "apex_minus_base_direction_LPS": dirn.round(3).tolist(),
    "apex_is_left_anterior_inferior": bool(dirn[0] > 0 and dirn[1] < 0 and dirn[2] < 0),
    "long_axis_angle_from_sagittal_plane_deg": round(long_axis_from_sagittal_deg, 1),
}
(out_dir / "frame_checks.json").write_text(json.dumps(checks, indent=1))
(out_dir / "manifest.json").write_text(json.dumps({"frame": frame, "checks": checks, "objects": manifest}, indent=1))
print("EXPORTED heart", len(heart_objs), "skeleton", len(skel_objs), json.dumps(checks))
