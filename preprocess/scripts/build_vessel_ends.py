"""Free ends of the great vessels, for the display-only end fade (D62).

    .venv\\Scripts\\python preprocess\\scripts\\build_vessel_ends.py

The atlas vessels are tubes closed by flat caps. A cap is FREE (a cut end, not a junction) when its centre lies outside every
other heart and great-vessel solid. The 3D scenes fade each free end to transparent over its last 12 mm; nothing is moved.
Writes web/public/anatomy/vessel_ends.json: {mesh name: [{"centre_LPS", "inward_LPS", "radius_mm"}]} (free ends only), plus
the junction ends for the record.
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))
from cpt.closemesh import cap_holes, merge_close, signed_volume  # noqa: E402

A_DIR = ROOT / "assets" / "anatomy"
WEB = ROOT / "web" / "public" / "anatomy"
VESSELS = ["Brachiocephalic trunk", "Left common carotid artery", "Left subclavian artery", "Superior vena cava",
           "Inferior vena cava (thoracic part)", "Left pulmonary artery", "Right pulmonary artery", "Abdominal aorta",
           "Ascending aorta", "Aortic arch", "Thoracic aorta", "Bifurcation of pulmonary trunk"]
ALWAYS_FADE = {"Superior vena cava", "Inferior vena cava (thoracic part)"}   # the root and slice views hide the atrium
JUNCTION_MM = 3.0   # a cap within this distance of another solid is a junction (the aortic root end is 2.6 mm from the LV)
OTHERS = ["Left ventricle", "Right ventricle", "Left atrium", "Right atrium", "Pulmonary trunk"]


def winding(m, p):
    """Generalised winding number of point p (1 inside a closed outward mesh, 0 outside); no spatial index needed."""
    a, b, c = (m.vertices[m.faces[:, i]] - p for i in range(3))
    la, lb, lc = (np.linalg.norm(x, axis=1) for x in (a, b, c))
    num = np.einsum("ij,ij->i", a, np.cross(b, c))
    den = la * lb * lc + np.einsum("ij,ij->i", a, b) * lc + np.einsum("ij,ij->i", b, c) * la + np.einsum("ij,ij->i", c, a) * lb
    return float(2 * np.arctan2(num, den).sum() / (4 * np.pi))


def surf_dist(m, p):
    q, _ = trimesh.sample.sample_surface_even(m, max(2000, int(m.area * 20)))
    return float(np.linalg.norm(np.vstack([q, m.vertices]) - p, axis=1).min())


def load():
    sc = trimesh.load(A_DIR / "z_anatomy_heart.glb", process=False)
    out = {}
    for n in sc.graph.nodes_geometry:
        T, g = sc.graph[n]
        out[n] = sc.geometry[g]
    return out


def solid(m):
    V, F = merge_close(m.vertices, m.faces)
    V, F, _ = cap_holes(V, F)
    if signed_volume(V, F) < 0:
        F = F[:, ::-1]
    return trimesh.Trimesh(V, F, process=False)


def caps(m):
    """The two flat end caps: the largest coplanar face groups (same normal, same plane)."""
    fn = np.round(m.face_normals, 2)
    keys, inv = np.unique(fn, axis=0, return_inverse=True)
    inv = inv.ravel()
    groups = []
    for k in range(len(keys)):
        fi = np.nonzero(inv == k)[0]
        if len(fi) < 6:
            continue
        c = m.triangles_center[fi]
        d = c @ m.face_normals[fi[0]]
        # split by plane offset (two parallel caps would share a normal only if anti-parallel ends: they do not)
        area = float(m.area_faces[fi].sum())
        centre = (c * m.area_faces[fi, None]).sum(0) / area
        if np.ptp(d) > 0.5:
            continue
        groups.append((area, centre, -m.face_normals[fi[0]]))
    groups.sort(key=lambda g: -g[0])
    return groups[:2]


def main():
    nodes = load()
    names = {n.split(".")[0] if n.startswith("Pulmonary trunk") else n: n for n in nodes}
    solids = {}
    for n in VESSELS + OTHERS:
        key = names.get(n) or next((k for k in nodes if k.startswith(n)), None)
        if key is None:
            raise SystemExit(f"missing {n}")
        solids[n] = solid(nodes[key])
    out, record = {}, {}
    for n in VESSELS:
        m = solids[n]
        ends = []
        for area, c, inward in caps(m):
            inside = [o for o, s in solids.items() if o != n and winding(s, c - 1.0 * inward) > 0.5]
            dists = {o: surf_dist(s, c) for o, s in solids.items() if o != n}
            near = [o for o, d in dists.items() if d < JUNCTION_MM]
            if n in ("Superior vena cava", "Ascending aorta"):
                print("  ", n, "end", np.round(c, 1).tolist(), "nearest", sorted((round(d, 1), o) for o, d in dists.items())[:2])
            free = not inside and not near   # the SVC's lower end stops 10.7 mm short of the right atrium: a visible cut end
            if n in ALWAYS_FADE:
                free = True
            e = {"centre_LPS": np.round(c, 3).tolist(), "inward_LPS": np.round(inward, 4).tolist(),
                 "radius_mm": round(float(np.sqrt(area / np.pi)), 2), "free": free, "inside_of": inside, "touching": near}
            ends.append(e)
        record[n] = ends
        free = [e for e in ends if e["free"]]
        if free:
            out[n] = [{k: e[k] for k in ("centre_LPS", "inward_LPS", "radius_mm")} for e in free]
        print(n, [(e["free"], e["inside_of"], e["touching"]) for e in ends])
    (WEB / "vessel_ends.json").write_text(json.dumps({"fade_mm": 18.0, "free_ends": out, "all_ends": record}, indent=1))
    print("wrote vessel_ends.json:", {k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    main()
