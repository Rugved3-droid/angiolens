"""Free-floating coronary branch tubes and illustrative bridges (D55).

Some atlas side-branch tubes (septal, right inferolateral) end a little short of their parent: in the X-ray union they are separate
bodies. This module finds every such component, measures its surface gap to the main tree, and for gaps <= max_gap builds a
short closed tube (an ILLUSTRATIVE bridge) from the branch's proximal centreline end to the nearest point of the parent's
centreline, with the branch's own authored origin radius. Existing geometry is never moved.
"""
from __future__ import annotations

import numpy as np

SPLIT_OBJECT = {"LAD": "Anterior interventricular artery", "LCx": "Circumflex artery of heart", "RCA": "Right coronary artery"}


def spline_of_part(name):
    """Part name -> (object, spline index or None = all splines of the object)."""
    for tag, obj in SPLIT_OBJECT.items():
        if name.startswith(tag + "_branch_"):
            return obj, int(name.split("_")[-1]) - 1
    return name, None


def centreline(probe, obj, i):
    s = probe["curves"][obj]["splines"][i]
    C = np.array(s["centreline"], float)
    r = np.array(s["radii"], float) * probe["curves"][obj]["bevel_depth"] * 1000.0
    rr = np.interp(np.linspace(0, len(r) - 1, len(C)), np.arange(len(r)), r)
    return C, rr


def pieces(parts, probe):
    """Split multi-spline parts into single tubes (connected pieces) and label each with its spline."""
    import manifold3d as mf
    out = []
    for name, V, F in parts:
        m = mf.Manifold(mf.Mesh(vert_properties=np.asarray(V, np.float32), tri_verts=np.asarray(F, np.uint32)))
        obj, idx = spline_of_part(name)
        cands = [idx] if idx is not None else list(range(len(probe["curves"][obj]["splines"])))
        lines = {i: centreline(probe, obj, i) for i in cands}
        for p in m.decompose():
            Vp = np.asarray(p.to_mesh().vert_properties, float)[:, :3]
            best = min(cands, key=lambda i: np.mean(np.min(np.linalg.norm(Vp[::7, None] - lines[i][0][None, ::2], axis=2), axis=1)))
            C, r = lines[best]
            out.append({"key": f"{obj}#{best}", "part": name, "solid": p, "C": C, "r": r})
    return out


def components(ps, touch=0.01):
    n = len(ps)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    gap = np.full((n, n), np.inf)
    for i in range(n):
        for j in range(i + 1, n):
            g = ps[i]["solid"].min_gap(ps[j]["solid"], 25.0)
            gap[i, j] = gap[j, i] = g
            if g <= touch:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values()), gap


def nearest_on(C, p):
    best = (1e18, None)
    for a, b in zip(C[:-1], C[1:]):
        t = np.clip(np.dot(p - a, b - a) / max(np.dot(b - a, b - a), 1e-12), 0, 1)
        q = a + t * (b - a)
        d = np.linalg.norm(p - q)
        if d < best[0]:
            best = (d, q)
    return best


def tube(P, Q, r, sections=12):
    """Closed cylinder P -> Q (outward winding)."""
    import trimesh
    m = trimesh.creation.cylinder(radius=r, segment=np.array([P, Q]), sections=sections)
    return np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)


def analyse(parts, probe, root_key, max_gap=3.0):
    """Report of floating components (relative to the component holding root_key) and bridges for gaps <= max_gap."""
    ps = pieces(parts, probe)
    groups, gap = components(ps)
    main = next(g for g in groups if any(ps[i]["key"] == root_key for i in g))
    report, bridges = [], []
    for g in groups:
        if g is main:
            continue
        a, b = min(((i, j) for i in g for j in main), key=lambda ij: gap[ij])
        pa, pb = ps[a], ps[b]
        # the floating tube's proximal end: its centreline end nearer the parent's centreline
        ends = [(nearest_on(pb["C"], pa["C"][0])[0], 0), (nearest_on(pb["C"], pa["C"][-1])[0], -1)]
        _, e = min(ends)
        P = pa["C"][e]
        d, Q = nearest_on(pb["C"], P)
        r = float(pa["r"][e])
        item = {"branch": pa["key"], "part": pa["part"], "tubes_in_component": [ps[i]["key"] for i in g], "parent": pb["key"],
                "surface_gap_mm": round(float(gap[a, b]), 3), "centreline_gap_mm": round(float(d), 3)}
        if gap[a, b] <= max_gap:
            V, F = tube(P, Q, r)
            item["bridge"] = {"from_LPS": P.round(3).tolist(), "to_LPS": Q.round(3).tolist(), "radius_mm": round(r, 3),
                              "length_mm": round(float(np.linalg.norm(Q - P)), 3), "note": "illustrative bridge"}
            bridges.append((f"bridge:{pa['key']}", V, F))
        else:
            item["bridge"] = None
        report.append(item)
    return report, bridges, len(ps)
