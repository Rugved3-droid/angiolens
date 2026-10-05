"""Per-mesh parts of a candidate (v1.1 scouting): triangles, extent, mean vertex colour, a colour-family guess.
    .venv\\Scripts\\python preprocess\\scripts\\scout_parts.py UID  -> appends "parts" to assets/candidates/_scout/inspect_<uid>.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

C = Path(__file__).resolve().parents[2] / "assets" / "candidates"


def family(rgb):
    r, g, b = rgb
    if r > 0.45 and r > 1.6 * g and r > 1.6 * b:
        return "red (artery?)"
    if b > 0.35 and b > 1.3 * r:
        return "blue (vein?)"
    if r > 0.6 and g > 0.5 and b < 0.45:
        return "yellow (fat?)"
    if r > 0.3 and r > g and r > b:
        return "red-brown (muscle?)"
    return "neutral"


for uid in sys.argv[1:]:
    sc = trimesh.load(C / uid / "model.glb", force="scene", process=False)
    parts = []
    allV = []
    for name, g in sc.dump(concatenate=False) and [(n, sc.geometry[sc.graph[n][1]]) for n in sc.graph.nodes_geometry] or []:
        T = sc.graph[name][0]
        V = trimesh.transform_points(np.asarray(g.vertices), T)
        allV.append(V)
        col = None
        vc = getattr(g.visual, "vertex_colors", None)
        if vc is not None and len(vc) == len(g.vertices) and getattr(g.visual, "kind", "") == "vertex":
            col = (np.asarray(vc)[:, :3].mean(0) / 255).round(3).tolist()
        parts.append({"node": name, "triangles": int(len(g.faces)), "extent": (V.max(0) - V.min(0)).round(3).tolist(),
                      "centre": V.mean(0).round(3).tolist(), "mean_vertex_rgb": col, "family": family(col) if col else "no vertex colour"})
    allV = np.vstack(allV)
    ext = allV.max(0) - allV.min(0)
    for p_ in parts:
        p_["extent_frac"] = round(float(max(p_["extent"]) / max(ext)), 3)
    f = C / "_scout" / f"inspect_{uid}.json"
    d = json.loads(f.read_text())
    d["parts"] = parts
    d["model_extent"] = ext.round(3).tolist()
    f.write_text(json.dumps(d, indent=1))
    fam = {}
    for p_ in parts:
        fam.setdefault(p_["family"], []).append(p_["triangles"])
    print(uid, "extent", ext.round(2), {k: (len(v), sum(v)) for k, v in fam.items()})
    for p_ in sorted(parts, key=lambda x: -x["triangles"])[:12]:
        print("   ", p_["node"][:28].ljust(28), str(p_["triangles"]).rjust(8), "extent frac", p_["extent_frac"], p_["family"], p_["mean_vertex_rgb"])
