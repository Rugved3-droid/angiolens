"""Blender 4.2 probe (read-only): great-vessel centrelines, coronary ostia, aortic-valve leaflets, pulmonary-trunk mesh, in LPS mm.

    blender -b --disable-autoexec --python-exit-code 1 Startup.blend --python preprocess/blender/probe_great_vessels.py -- <frame.json> <out.json>

Nothing is modified or saved. Used to plan the illustrative great-vessel calibre and the ostium-on-wall check (D46).
"""
import json
import sys
from pathlib import Path

import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
frame = json.loads(Path(argv[0]).read_text())
M = mathutils.Matrix([list(r) + [0.0] for r in frame["matrix_source_to_LPS_mm"]] + [[0, 0, 0, 1]])
dg = bpy.context.evaluated_depsgraph_get()

CURVES = ["Ascending aorta", "Aortic arch", "Thoracic aorta", "Abdominal aorta", "Superior vena cava", "Bifurcation of pulmonary trunk",
          "Left pulmonary artery", "Right pulmonary artery", "Brachiocephalic trunk", "Left common carotid artery", "Left subclavian artery",
          "Inferior vena cava (thoracic part)", "Left brachiocephalic vein", "Right brachiocephalic vein",
          "Left coronary artery", "Right coronary artery",
          # every coronary spline (D53: contrast fill by centreline distance from the effective ostium)
          "Anterior interventricular artery", "Circumflex artery of heart", "Septal branches of anterior interventricular artery",
          "Right inferolateral branch of right coronary artery",
          # catheter access routes (D47): femoral both sides, radial on the right
          "Common iliac artery.r", "Common iliac artery.l", "External iliac artery.r", "External iliac artery.l",
          "Femoral artery.r", "Femoral artery.l", "Right subclavian artery", "Axillary artery.r", "Brachial artery.r", "Radial artery.r"]
LANDMARKS = ["Vertebra L3", "Vertebra L4", "Vertebra L5", "Aortic bifurcation.g"]
MESHES = ["Pulmonary trunk", "Right coronary leaflet", "Left coronary leaflet", "Non-coronary leaflet",
          "Anterior semilunar leaflet of pulmonary valve", "Left semilunar leaflet of pulmonary valve", "Right semilunar leaflet of pulmonary valve"]


def centreline(o, sp):
    W = M @ o.matrix_world
    res = max(int(o.data.resolution_u), 2)
    pts = []
    if sp.type == "BEZIER":
        bp = list(sp.bezier_points)
        for a, b in zip(bp[:-1], bp[1:]):
            seg = mathutils.geometry.interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co, res + 1)
            pts.extend(seg if not pts else seg[1:])
        cps = [(W @ p.co)[:] for p in bp]
        rad = [p.radius for p in bp]
    else:
        pts = [mathutils.Vector(q.co[:3]) for q in sp.points]
        cps = [(W @ v)[:] for v in pts]
        rad = [q.radius for q in sp.points]
    return {"type": sp.type, "resolution_u": res, "control_points": cps, "radii": rad, "centreline": [(W @ v)[:] for v in pts]}


out = {"curves": {}, "meshes": {}}
for n in CURVES:
    o = bpy.data.objects.get(n)
    if o is None or o.type != "CURVE":
        out["curves"][n] = None
        continue
    out["curves"][n] = {"parent": o.parent.name if o.parent else None, "bevel_depth": o.data.bevel_depth,
                        "use_fill_caps": o.data.use_fill_caps, "resolution_u": o.data.resolution_u,
                        "bevel_resolution": o.data.bevel_resolution, "bevel_mode": o.data.bevel_mode,
                        "det_world": (M @ o.matrix_world).to_3x3().determinant(),
                        "splines": [centreline(o, sp) for sp in o.data.splines]}
out["landmarks"] = {}
for n in LANDMARKS:
    o = bpy.data.objects.get(n)
    if o is None:
        out["landmarks"][n] = None
        continue
    W = M @ o.matrix_world
    entry = {"origin_LPS": (W @ mathutils.Vector((0, 0, 0)))[:], "type": o.type}
    if o.type == "MESH" and len(o.data.vertices):
        zs = [(W @ v.co).z for v in o.data.vertices]
        entry["z_range_LPS"] = [min(zs), max(zs)]
    out["landmarks"][n] = entry
for n in MESHES:
    o = bpy.data.objects.get(n)
    if o is None:
        out["meshes"][n] = None
        continue
    me = o.evaluated_get(dg).to_mesh()
    W = M @ o.matrix_world
    out["meshes"][n] = {"vertices": [(W @ v.co)[:] for v in me.vertices], "faces": [list(p.vertices) for p in me.polygons]}
    o.evaluated_get(dg).to_mesh_clear()
Path(argv[1]).write_text(json.dumps(out))
print("PROBE OK", argv[1])
