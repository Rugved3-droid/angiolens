"""Scene 5 data (D53): catheter routes, engaged JL4/JR4 shapes, and contrast-fill distances. ILLUSTRATIVE, not physics.

    .venv\\Scripts\\python preprocess\\scripts\\build_atlas_cath.py     (after export_anatomy, the probe and build_atlas_xray)

Inputs: assets/anatomy/inspect/great_vessels_probe.json (evaluated centrelines + authored radii of the aorta, access routes and
every coronary spline), manifest.json (effective ostia, D46), the X-ray solids and z_anatomy_heart.glb.
Outputs (web/public/anatomy/, git-ignored):
  atlas_cath.json   routes (femoral_right, radial_right) from the puncture to the aortic root, the engaged shapes (JL4 -> LM,
                    JR4 -> RCA), straight "pre-shape" configurations for the morph, the reflux point, checks
  atlas_fill.bin    float32 per-vertex distance from the effective ostium along the coronary tree (mm), for the X-ray solids
                    and every 3D coronary node; atlas_cath.json["fill_index"] gives offset / count / first vertex per key
Nothing anatomical is moved: the catheter is shaped to fit the vessels, never the other way round.
"""
import heapq
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))
from cpt.glb import read_glb  # noqa: E402

A = ROOT / "assets" / "anatomy"
WEB = ROOT / "web" / "public" / "anatomy"
CATH_R = 1.0                 # 6F catheter: 2 mm outer diameter
TIP_IN_MM = 3.0              # engagement depth of the tip inside the coronary, along its initial direction
N_SHAPE = 160                # samples of the shaped (and the straight) root segment, for the morph

TREES = {
    "left": [("Left coronary artery", "LM"), ("Anterior interventricular artery", "LAD"), ("Circumflex artery of heart", "LCx"),
             ("Septal branches of anterior interventricular artery", "SEPTAL")],
    "right": [("Right coronary artery", "RCA"), ("Right inferolateral branch of right coronary artery", "RIL")],
}
ROOT_SPLINE = {"left": ("Left coronary artery", 0), "right": ("Right coronary artery", 0)}
OSTIUM_KEY = {"left": "LM", "right": "RCA"}


def P(probe, name, i=0):
    s = probe["curves"][name]["splines"][i]
    return np.array(s["centreline"], float)


def radius_along(probe, name, i=0):
    """Authored tube radius (mm) at every centreline sample (linear between control points)."""
    c = probe["curves"][name]
    s = c["splines"][i]
    r = np.array(s["radii"], float) * c["bevel_depth"] * 1000.0
    n = len(s["centreline"])
    k = np.linspace(0, len(r) - 1, n)
    return np.interp(k, np.arange(len(r)), r)


def arclen(Q):
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]


def resample(Q, step=1.0):
    s = arclen(Q)
    t = np.arange(0, s[-1], step)
    t = np.r_[t, s[-1]]
    return np.stack([np.interp(t, s, Q[:, k]) for k in range(3)], 1)


def nearest_on(Q, p):
    best = (1e18, 0, 0.0)
    for i in range(len(Q) - 1):
        a, b = Q[i], Q[i + 1]
        t = np.clip(np.dot(p - a, b - a) / max(np.dot(b - a, b - a), 1e-12), 0, 1)
        d = np.linalg.norm(p - (a + t * (b - a)))
        if d < best[0]:
            best = (d, i, t)
    return best


def catmull_rom(pts, n):
    """Centripetal Catmull-Rom through the points (end tangents by reflection), n samples."""
    pts = np.asarray(pts, float)
    ext = np.vstack([2 * pts[0] - pts[1], pts, 2 * pts[-1] - pts[-2]])
    seg = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1:i + 3]
        t0 = 0.0
        t1 = t0 + np.linalg.norm(p1 - p0) ** 0.5
        t2 = t1 + np.linalg.norm(p2 - p1) ** 0.5
        t3 = t2 + np.linalg.norm(p3 - p2) ** 0.5
        for t in np.linspace(t1, t2, 40, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            seg.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    seg.append(pts[-1])
    Q = np.array(seg)
    s = arclen(Q)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, Q[:, k]) for k in range(3)], 1)


# ---------------- coronary tree distances (contrast fill) ----------------
def tree_distances(probe, man, tree):
    """Graph of every spline's samples; each non-root spline joins at its end nearest another spline (gap recorded and
    added to the path). Distance 0 = the effective ostium (the buried part of the trunk is negative)."""
    splines = []
    for obj, tag in TREES[tree]:
        for i, _ in enumerate(probe["curves"][obj]["splines"]):
            splines.append({"obj": obj, "tag": tag, "i": i, "P": P(probe, obj, i)})
    off = np.cumsum([0] + [len(s["P"]) for s in splines])
    X = np.vstack([s["P"] for s in splines])
    adj = [[] for _ in range(len(X))]
    for k, s in enumerate(splines):
        for j in range(len(s["P"]) - 1):
            a, b = off[k] + j, off[k] + j + 1
            w = float(np.linalg.norm(X[a] - X[b]))
            adj[a].append((b, w)); adj[b].append((a, w))
    root_obj, root_i = ROOT_SPLINE[tree]
    root_k = next(k for k, s in enumerate(splines) if s["obj"] == root_obj and s["i"] == root_i)
    # grow from the root (Prim-like): each step joins the unconnected spline whose END lies nearest the connected tree, so no
    # island can form
    joins = []
    connected = {root_k}
    while len(connected) < len(splines):
        best = None
        for k, s in enumerate(splines):
            if k in connected:
                continue
            for end, idx in (("start", off[k]), ("end", off[k + 1] - 1)):
                for k2 in connected:
                    d, seg, t = nearest_on(splines[k2]["P"], X[idx])
                    if best is None or d < best[0]:
                        best = (d, k, idx, off[k2] + seg + (1 if t > 0.5 else 0), end, k2)
        d, k, a, b, end, k2 = best
        adj[a].append((b, d)); adj[b].append((a, d))
        connected.add(k)
        joins.append({"spline": f"{splines[k]['obj']}#{splines[k]['i']}", "joins": f"{splines[k2]['obj']}#{splines[k2]['i']}",
                      "at_end": end, "gap_mm": round(d, 2)})
    # Dijkstra from the root spline's ostial end
    o = np.array(man["effective_ostia"][OSTIUM_KEY[tree]]["effective_ostium_LPS"])
    src = off[root_k]
    dist = np.full(len(X), np.inf)
    dist[src] = 0.0
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, w in adj[u]:
            if d + w < dist[v]:
                dist[v] = d + w
                heapq.heappush(pq, (d + w, v))
    buried = man["effective_ostia"][OSTIUM_KEY[tree]]["buried_centreline_length_mm"]
    dist -= buried                                  # 0 at the effective ostium
    assert np.isfinite(dist).all(), f"{tree}: unreachable spline samples"
    keyed = {f"{s['obj']}#{s['i']}": (off[k], off[k + 1]) for k, s in enumerate(splines)}
    return X, dist, keyed, joins, o


def main():
    probe = json.loads((A / "inspect" / "great_vessels_probe.json").read_text())
    man = json.loads((A / "manifest.json").read_text())
    import trimesh
    sc = trimesh.load(A / "z_anatomy_heart.glb", process=False)
    heart = {n: np.asarray(sc.geometry[sc.graph[n][1]].vertices) for n in sc.graph.nodes_geometry}
    fill_arrays, fill_index, off = [], {}, 0

    def add(key, values, first):
        nonlocal off
        values = np.asarray(values, np.float32)
        fill_arrays.append(values)
        fill_index[key] = {"offset": off, "count": int(len(values)), "first_vertex": [round(float(x), 3) for x in first]}
        off += len(values)

    trees_out = {}
    for tree in ("left", "right"):
        X, dist, keyed, joins, o = tree_distances(probe, man, tree)
        kd = cKDTree(X)
        g = read_glb(WEB / f"atlas_xray_{tree}.glb")
        V = g["POSITION"].astype(float)
        add(f"xray_{tree}", dist[kd.query(V)[1]], V[0])
        trees_out[tree] = {"joins": joins, "max_distance_mm": round(float(dist.max()), 1)}
        # 3D nodes: each branch node takes its distances from its OWN spline (no bleeding across a junction)
        for node, Vn in heart.items():
            tag = None
            for obj, t in TREES[tree]:
                if node == obj:
                    tag = (obj, None)
            for pfx, obj in (("LAD", "Anterior interventricular artery"), ("LCx", "Circumflex artery of heart"), ("RCA", "Right coronary artery")):
                if node.startswith(pfx + "_branch_") and any(obj == o2 for o2, _ in TREES[tree]):
                    tag = (obj, int(node.split("_")[-1]) - 1)
            if tag is None:
                continue
            obj, i = tag
            if i is None:
                rows = np.concatenate([np.arange(*keyed[k]) for k in keyed if k.startswith(obj + "#")])
            else:
                rows = np.arange(*keyed[f"{obj}#{i}"])
            add(f"node:{node}", dist[rows][cKDTree(X[rows]).query(Vn)[1]], Vn[0])

    # ---------------- routes (puncture -> ascending aorta), right femoral and right radial ----------------
    asc = P(probe, "Ascending aorta")          # root (start) -> top (end)
    arch = P(probe, "Aortic arch")             # ascending end -> descending start
    def rev(name):
        return P(probe, name)[::-1]
    fem = P(probe, "Femoral artery.r")         # proximal (start) -> distal
    s_f = arclen(fem)
    k0 = np.searchsorted(s_f, 40.0)            # puncture 40 mm below the femoral artery's start: the common femoral segment
    femoral = np.vstack([fem[:k0 + 1][::-1], rev("External iliac artery.r")[1:], rev("Common iliac artery.r")[1:],
                         rev("Abdominal aorta")[1:], rev("Thoracic aorta")[1:], rev("Aortic arch")[1:]])
    rad = P(probe, "Radial artery.r")          # elbow (start) -> wrist (end)
    s_r = arclen(rad)
    k1 = np.searchsorted(s_r, s_r[-1] - 30.0)  # puncture 30 mm above the radial artery's distal end (the wrist)
    bct = P(probe, "Brachiocephalic trunk")    # arch origin (start) -> bifurcation (end)
    d_a, seg, t = nearest_on(arch, bct[0])
    arch_from_bct = np.vstack([arch[:seg + 1][::-1]])
    radial = np.vstack([rad[:k1 + 1][::-1], rev("Brachial artery.r")[1:], rev("Axillary artery.r")[1:],
                        rev("Right subclavian artery")[1:], bct[::-1][1:], arch_from_bct])
    routes = {}
    for name, R in (("femoral_right", femoral), ("radial_right", radial)):
        R = resample(R, 1.0)
        routes[name] = {"polyline_to_ascending_top": R.round(3).tolist(), "length_mm": round(float(arclen(R)[-1]), 1),
                        "puncture_LPS": R[0].round(2).tolist()}

    # ---------------- engaged shapes in the root (JL4 -> LM, JR4 -> RCA) and the straight pre-shape ----------------
    top = asc[-1]
    a_ax = (asc[-1] - asc[0]) / np.linalg.norm(asc[-1] - asc[0])
    r_asc = radius_along(probe, "Ascending aorta")
    r_arch = radius_along(probe, "Aortic arch")
    wall = [(asc, r_asc), (arch, r_arch)]

    def lumen_clearance(p):
        """mm from the catheter SURFACE to the aortic wall (positive = inside, clear)."""
        best = -1e9
        for C, Rr in wall:
            d, i, t = nearest_on(C, p)
            r = Rr[i] + (Rr[min(i + 1, len(Rr) - 1)] - Rr[i]) * t
            best = max(best, r - d - CATH_R)
        return best

    def on_axis(p):
        """Point on the ascending centreline at the axial level of p."""
        s = np.dot(p - asc[0], a_ax)
        return asc[0] + a_ax * s

    shapes, checks = {}, {}
    for cath, key, tree in (("JL4", "LM", "left"), ("JR4", "RCA", "right")):
        eo = man["effective_ostia"][key]
        o = np.array(eo["effective_ostium_LPS"])
        t = np.array(eo["vessel_direction_LPS"]); t /= np.linalg.norm(t)
        n = np.array(eo["wall_normal_LPS"])
        n_perp = n - np.dot(n, a_ax) * a_ax; n_perp /= np.linalg.norm(n_perp)
        R_o = float(np.interp(np.dot(o - asc[0], a_ax), arclen(asc), r_asc))
        if cath == "JL4":
            # down the ascending aorta, the primary curve rests on the CONTRALATERAL wall below the ostium, the tip turns up
            # and across into the left main
            q1 = on_axis(top - 0.45 * (top - o)) - 0.30 * R_o * n_perp
            heel_level = max(np.dot(o - asc[0], a_ax) - 9.0, 5.0)              # stays above the valve (root start + 5 mm)
            q2 = asc[0] + a_ax * heel_level - 0.55 * R_o * n_perp
            q3 = o - 8.0 * t - 2.5 * n                                        # approach from inside the lumen
        else:
            # JR4: down the ascending aorta near its axis, then the ~90 degree secondary curve swings the tip into the RCA
            q1 = on_axis(top - 0.4 * (top - o)) - 0.15 * R_o * n_perp
            q2 = on_axis(o + 9.0 * a_ax) - 0.20 * R_o * n_perp
            q3 = o - 7.0 * t - 1.5 * n
        pts = [top, q1, q2, q3, o - 2.0 * t, o, o + TIP_IN_MM * t]           # last ~5 mm coaxial with the coronary
        S = catmull_rom(pts, N_SHAPE)
        tip_dir = (S[-1] - S[-4]) / np.linalg.norm(S[-1] - S[-4])
        dist_to_o = np.linalg.norm(S - o, axis=1)
        ENGAGE_MM = 4.0                                                       # the tip seats in the ostium: not a wall clash
        inside = [lumen_clearance(p) for p, d in zip(S, dist_to_o) if np.dot(p - o, t) < 0 and d > ENGAGE_MM]
        # straight pre-shape: the catheter on the ascending centreline, from the top down to the ostium's level
        straight = np.stack([np.linspace(0, 1, N_SHAPE)] * 3, 1) * (on_axis(o) - top) + top
        shapes[cath] = {"target": key, "tree": tree, "polyline": S.round(3).tolist(), "straight_polyline": straight.round(3).tolist(),
                        "effective_ostium_LPS": o.round(3).tolist(), "coronary_direction_LPS": t.round(4).tolist(),
                        "reflux_point_LPS": (o - 4.0 * t).round(3).tolist(), "control_points_LPS": np.array(pts).round(2).tolist()}
        checks[cath] = {"tip_at_ostium_plus_mm": TIP_IN_MM, "tip_tangent_angle_to_coronary_deg": round(float(np.degrees(np.arccos(np.clip(np.dot(tip_dir, t), -1, 1)))), 2),
                        "min_clearance_to_aortic_wall_mm": round(float(min(inside)), 2), "samples_checked": len(inside)}
        if checks[cath]["tip_tangent_angle_to_coronary_deg"] > 5.0 or checks[cath]["min_clearance_to_aortic_wall_mm"] < 0.0:
            raise SystemExit(f"{cath}: shape check failed {checks[cath]}")
    for name in routes:
        routes[name]["min_clearance_mm"] = None   # routes ride the centreline (illustrative)

    data = {"note": "ILLUSTRATIVE catheter and contrast, not physics (D53)", "catheter_outer_radius_mm": CATH_R,
            "routes": routes, "shapes": shapes, "checks": checks, "trees": trees_out,
            "ascending_top_LPS": top.round(3).tolist(), "fill_index": fill_index}
    WEB.mkdir(parents=True, exist_ok=True)
    np.concatenate(fill_arrays).astype("<f4").tofile(WEB / "atlas_fill.bin")
    (WEB / "atlas_cath.json").write_text(json.dumps(data))
    shutil.copy(WEB / "atlas_cath.json", A / "atlas_cath.json")
    print(json.dumps({"checks": checks, "routes": {k: v["length_mm"] for k, v in routes.items()},
                      "trees": {k: {"max_distance_mm": v["max_distance_mm"], "joins_with_gap": [j for j in v["joins"] if j["gap_mm"] > 0.5]}
                                for k, v in trees_out.items()}, "fill_keys": len(fill_index)}, indent=1))


if __name__ == "__main__":
    main()
