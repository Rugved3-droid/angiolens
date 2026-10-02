"""Blender 4.2: dump EVERY object of Startup.blend (all types, not only meshes) to JSON.

    blender -b --disable-autoexec <Startup.blend> --python preprocess/blender/dump_hierarchy.py -- <out.json>

Per object: name, type, data name, parent, collections (full paths), world matrix, modifiers, curve bevel
settings, evaluated geometry (vertex/triangle counts from the depsgraph, i.e. AFTER bevel/modifiers), world
bounding box, custom properties, visibility. Plus the collection tree.
"""
import json
import sys

import bpy
import mathutils

out = sys.argv[sys.argv.index("--") + 1]
dg = bpy.context.evaluated_depsgraph_get()


def coll_paths():
    paths = {}
    def walk(c, prefix):
        p = f"{prefix}/{c.name}" if prefix else c.name
        for o in c.objects:
            paths.setdefault(o.name, []).append(p)
        for ch in c.children:
            walk(ch, p)
    walk(bpy.context.scene.collection, "")
    return paths


def tree(c):
    return {"name": c.name, "objects": len(c.objects), "children": [tree(ch) for ch in c.children]}


paths = coll_paths()
objs = []
for o in bpy.data.objects:
    rec = {
        "name": o.name, "type": o.type, "data": o.data.name if o.data else None,
        "parent": o.parent.name if o.parent else None, "parent_type": o.parent_type if o.parent else None,
        "collections": paths.get(o.name, []), "in_scene": o.name in bpy.context.scene.objects,
        "hide_viewport": o.hide_viewport, "hide_render": o.hide_render,
        "matrix_world": [list(r) for r in o.matrix_world],
        "modifiers": [m.type for m in o.modifiers],
        "custom_props": {k: str(o[k])[:200] for k in o.keys() if not k.startswith("_")},
    }
    if o.type in ("CURVE", "SURFACE", "FONT"):
        cu = o.data
        rec["curve"] = {"dimensions": getattr(cu, "dimensions", None), "bevel_depth": getattr(cu, "bevel_depth", None),
                        "bevel_mode": getattr(cu, "bevel_mode", None), "extrude": getattr(cu, "extrude", None),
                        "bevel_object": cu.bevel_object.name if getattr(cu, "bevel_object", None) else None,
                        "taper_object": cu.taper_object.name if getattr(cu, "taper_object", None) else None,
                        "splines": len(cu.splines) if hasattr(cu, "splines") else None,
                        "control_points": sum(len(s.points) + len(s.bezier_points) for s in cu.splines) if hasattr(cu, "splines") else None}
    geom = None
    if o.type in ("MESH", "CURVE", "SURFACE", "FONT", "META") and o.name in bpy.context.scene.objects:
        try:
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            if me is not None:
                me.calc_loop_triangles()
                tris = len(me.loop_triangles)
                if len(me.vertices):
                    mw = o.matrix_world
                    pts = [mw @ v.co for v in me.vertices]
                    lo = [min(p[i] for p in pts) for i in range(3)]
                    hi = [max(p[i] for p in pts) for i in range(3)]
                else:
                    lo = hi = None
                geom = {"vertices": len(me.vertices), "triangles": tris, "bbox_world": [lo, hi]}
                ev.to_mesh_clear()
        except Exception as e:
            geom = {"error": str(e)}
    rec["evaluated_geometry"] = geom
    objs.append(rec)

json.dump({"blender": bpy.app.version_string, "file": bpy.data.filepath, "scene": bpy.context.scene.name,
           "unit_system": bpy.context.scene.unit_settings.system, "scale_length": bpy.context.scene.unit_settings.scale_length,
           "length_unit": bpy.context.scene.unit_settings.length_unit,
           "collections": tree(bpy.context.scene.collection), "objects": objs}, open(out, "w"), indent=1)
print("DUMPED", len(objs), "objects")
