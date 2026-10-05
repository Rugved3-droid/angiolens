"""Peel-mode display parts (v1.1 item 3; feature flag "peel"; display only, never in the X-ray).

    .venv\\Scripts\\python preprocess\\scripts\\build_peel_parts.py

1. EPICARDIAL FAT (illustrative): a layer on the epicardium along the main coronaries (centreline radius >= MIN_R), in their
   grooves. At the vessel the fat rises to the vessel's own height above the epicardium + COVER_FRAC of its radius (the atlas
   vessels often float a little), so every vessel is partly embedded; it tapers to nothing at radius + SPREAD_MM to the side; a smooth noise field (sigma NOISE_SIGMA) makes the surface lobulated.
   Built as a signed distance field (the heart = boolean union of the four chambers), marching cubes, decimation, smoothing.
2. ATRIAL APPENDAGES: the atlas has none as separate objects. Each atrium's triangles are split by GEODESIC distance (Dijkstra
   on the mesh edges) from the atrium vertex nearest the ostium its appendage covers: the left appendage over the left main,
   the right one over the right coronary origin (seed: the middle of the atrial wall within 8 mm of the tree's first 30 mm).
   Whole triangles only: no vertex is moved.
Writes web/public/anatomy/peel_*.glb and assets/anatomy/peel_parts.json (sizes, seeds, thresholds).
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))
sys.path.insert(0, str(ROOT / "preprocess" / "scripts"))
from cpt.glb import write_glb  # noqa: E402
import build_aorta_display as bad  # noqa: E402  (grid, occupancy, distance field, union, closing)

A_DIR = ROOT / "assets" / "anatomy"
WEB = ROOT / "web" / "public" / "anatomy"
CHAMBERS = ["Left ventricle", "Right ventricle", "Left atrium", "Right atrium"]
MIN_R = 0.8          # mm: vessels this thick or more get fat (the main arteries in their grooves)
COVER_FRAC = 0.15    # fat surface this fraction of the radius above the vessel centre: the vessel is about two thirds embedded
SPREAD_MM = 3.5      # lateral reach beyond the vessel radius
MIN_THICK = 1.8      # mm: the cushion stands at least this high above the epicardium
NOISE_MM = 0.3       # lobule relief amplitude
NOISE_SIGMA = 1.4    # mm
H = 0.6              # grid, mm
COVER_DIST_MM = 16.0 # atrial wall this close to the first 30 mm of a tree belongs to the peelable appendage
APPENDAGE_MM = {"Left atrium": ("LM", 40.0), "Right atrium": ("RCA", 30.0)}


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def centreline_points(cath):
    P, R = [], []
    for tree in ("left", "right"):
        for line in cath["trees"][tree]["centrelines"].values():
            pts = np.array(line["points"], float)
            rad = np.array(line["radius_mm"], float) if np.ndim(line["radius_mm"]) else np.full(len(pts), float(line["radius_mm"]))
            for a, b, ra, rb in zip(pts[:-1], pts[1:], rad[:-1], rad[1:]):
                n = max(1, int(np.ceil(np.linalg.norm(b - a) / 0.4)))
                t = np.linspace(0, 1, n, endpoint=False)[:, None]
                P.append(a + (b - a) * t)
                R.append(ra + (rb - ra) * t[:, 0])
    P, R = np.vstack(P), np.concatenate(R)
    keep = R >= MIN_R
    return P[keep], R[keep]


def round_cone(p, a, b, r1, r2):
    """Exact signed distance to a round cone (spheres at a, b with radii r1, r2 and their tangent cone), vectorized."""
    ba = b - a
    l2 = np.einsum("ij,ij->i", ba, ba)
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / np.maximum(l2, 1e-9)
    pa = p - a
    y = np.einsum("ij,ij->i", pa, ba)
    z = y - l2
    xv = pa * l2[:, None] - ba * y[:, None]
    x2 = np.einsum("ij,ij->i", xv, xv)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    out = np.empty(len(p))
    c1 = np.sign(z) * a2 * z2 > k
    c2 = np.sign(y) * a2 * y2 < k
    out[c1] = np.sqrt(x2[c1] + z2[c1]) * il2[c1] - r2[c1]
    m2 = c2 & ~c1
    out[m2] = np.sqrt(x2[m2] + y2[m2]) * il2[m2] - r1[m2]
    m3 = ~c1 & ~c2
    out[m3] = (np.sqrt(x2[m3] * a2[m3] * il2[m3]) + y[m3] * rr[m3]) * il2[m3] - r1[m3]
    return out


def build_fat(heart, cath, rep):
    parts = [(n, *bad.closed(heart[n], n)) for n in CHAMBERS]
    VH, FH, bodies = bad.union(parts)
    log("heart union", len(FH), "faces", bodies, "bodies")
    P, R = centreline_points(cath)
    log("fat follows", len(P), "centreline samples with radius >=", MIN_R)
    bad.H = H
    lo = np.minimum(VH.min(0), P.min(0)) - 12
    hi = np.maximum(VH.max(0), P.max(0)) + 12
    grid = bad.Grid(lo, hi)
    occ, odd = bad.occupancy(grid, VH, FH)
    fH, _, _ = bad.sdf(grid, VH, FH, occ)
    del occ
    # each vessel sample's height above the epicardium (the atlas vessels often float a little) and its outward normal
    hc = np.clip(bad.trilinear(fH, grid, P), 0.0, 4.0)
    gx = np.stack([bad.trilinear(fH, grid, P + e) - bad.trilinear(fH, grid, P - e) for e in np.eye(3) * 0.6], 1)
    nC = gx / np.maximum(np.linalg.norm(gx, axis=1, keepdims=True), 1e-6)
    # per vessel sample a ROUND CONE (Quilez's exact SDF): top sphere just over the vessel (COVER_FRAC of the radius above its
    # centre), base sphere on the epicardium below it (radius + SPREAD_MM). The smooth union of the K nearest cones gives a
    # continuous cushion that fills the groove under the vessel and leaves it partly embedded.
    A = P + nC * (COVER_FRAC * R)[:, None] * 0.0                # top centre = the vessel centre
    ra = R * (1.0 + COVER_FRAC)
    B = P - nC * (hc + 0.8)[:, None]                            # base centre, just under the epicardium
    rb = R + SPREAD_MM
    band = np.nonzero((fH > -2.0) & (fH < 7.0))
    q = grid.pts(np.stack(band, 1))
    K = 8
    dk, ik = cKDTree(P).query(q, k=K, distance_upper_bound=MIN_R + SPREAD_MM + 8, workers=-1)
    vals = np.full(len(q), 10.0, np.float32)
    acc = np.zeros(len(q))                                      # exponential smooth-min accumulator
    KS = 1.6                                                    # mm: smooth-union width
    for k in range(K):
        ok = np.isfinite(dk[:, k])
        if not ok.any():
            continue
        idx = ik[ok, k]
        d = round_cone(q[ok], A[idx], B[idx], ra[idx], rb[idx])
        acc[ok] += np.exp(-d / KS)
    has = acc > 0
    vals[has] = (-KS * np.log(acc[has])).astype(np.float32)
    vals = np.maximum(vals, -fH[band] - 0.3)                    # nothing inside the myocardium
    field = np.full(grid.n, 10.0, np.float32)
    field[band] = vals
    del fH
    rng = np.random.default_rng(3)
    noise = ndimage.gaussian_filter(rng.standard_normal(grid.n).astype(np.float32), NOISE_SIGMA / H)
    noise /= noise.std() + 1e-9
    field = ndimage.gaussian_filter(field, 0.4 / H) + NOISE_MM * noise
    from skimage.measure import marching_cubes
    v, f, _, _ = marching_cubes(field, 0.0, spacing=(H, H, H))
    v += grid.lo
    f = f[:, ::-1].astype(np.int64)
    import fast_simplification
    v, f = fast_simplification.simplify(v.astype(np.float32), f.astype(np.int32), target_reduction=0.85)
    v = np.asarray(v, float); f = np.asarray(f, np.int64)
    # the decimator leaves a few stretched fold-over triangles (long spikes): drop any triangle with an edge over 4 mm
    el = np.max([np.linalg.norm(v[f[:, i]] - v[f[:, (i + 1) % 3]], axis=1) for i in range(3)], axis=0)
    f = f[el < 4.0]
    log(f"fat: dropped {int((el >= 4.0).sum())} stretched triangles")
    m = trimesh.Trimesh(v, f, process=True)
    parts = [c for c in m.split(only_watertight=False) if len(c.faces) > 300]
    m = trimesh.util.concatenate(parts)
    trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=0.53, iterations=10)
    # after smoothing: a few badly connected vertices diverge (spikes up to ~200 mm); drop every triangle with an edge > 4 mm
    # and keep the pieces that remain large
    V, Fm = np.asarray(m.vertices), np.asarray(m.faces)
    el = np.max([np.linalg.norm(V[Fm[:, i]] - V[Fm[:, (i + 1) % 3]], axis=1) for i in range(3)], axis=0)
    m = trimesh.Trimesh(V, Fm[el < 4.0], process=True)
    m = trimesh.util.concatenate([c for c in m.split(only_watertight=False) if len(c.faces) > 300])
    log(f"fat: {int((el >= 4.0).sum())} spiked triangles removed after smoothing")
    rep["fat"] = {"faces": int(len(m.faces)), "pieces": len(parts), "min_vessel_radius_mm": MIN_R, "cover_frac_of_radius": COVER_FRAC,
                  "spread_mm": SPREAD_MM, "noise_mm": NOISE_MM, "grid_mm": H, "area_cm2": round(float(m.area) / 100, 1)}
    write_glb(WEB / "peel_fat.glb", m.vertices.astype(np.float32), m.faces.astype(np.uint32),
              normals=m.vertex_normals.astype(np.float32), name="Epicardial fat (illustrative)")
    log("fat", rep["fat"])


def split_atrium(name, g, man, rep, cath):
    key, mm = APPENDAGE_MM[name]
    o = np.array(man["effective_ostia"][key]["effective_ostium_LPS"])
    V = np.asarray(g.vertices, float)
    F = np.asarray(g.faces, np.int64)
    N = np.asarray(g.vertex_normals, np.float32)
    # merge coincident vertices for the graph (glTF splits them at normal seams), keep the original arrays for output
    key_v = np.round(V, 4)
    _, inv = np.unique(key_v, axis=0, return_inverse=True)
    inv = inv.ravel()
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    a, b = inv[e[:, 0]], inv[e[:, 1]]
    nU = inv.max() + 1
    Vu = np.zeros((nU, 3)); Vu[inv] = V
    wts = np.linalg.norm(Vu[a] - Vu[b], axis=1)
    G = coo_matrix((np.r_[wts, wts], (np.r_[a, b], np.r_[b, a])), shape=(nU, nU)).tocsr()
    # seed: the middle of the atrial wall that lies over the first 30 mm of this tree (the appendage covers the origin);
    # the atlas atrium vertex nearest the ostium itself sits on the atrium's body, not on its appendage
    tree = "left" if key == "LM" else "right"
    Pc = np.vstack([np.array(l["points"], float) for l in cath["trees"][tree]["centrelines"].values()])
    Pc = Pc[np.linalg.norm(Pc - o, axis=1) < 30.0]
    dv, _ = cKDTree(Pc).query(Vu)
    over = dv < 8.0
    target = Vu[over].mean(0) if over.sum() >= 10 else o
    seed = int(np.argmin(np.linalg.norm(Vu - target, axis=1)))
    dist = dijkstra(G, indices=seed, limit=mm + 1)
    # the appendage = the geodesic disc around the seed PLUS all atrial wall that lies over the tree's origin (within
    # COVER_DIST_MM of its first 30 mm): in this atlas the left atrium wraps over the left main, and that wall is what hides it
    inside_v = (dist[inv] <= mm) | (dv[inv] < COVER_DIST_MM)
    tri_in = inside_v[F].all(1)
    out = {}
    for label, sel in (("appendage", tri_in), ("body", ~tri_in)):
        Fi = F[sel]
        used = np.unique(Fi)
        remap = np.full(len(V), -1, np.int64); remap[used] = np.arange(len(used))
        out[label] = (V[used].astype(np.float32), remap[Fi].astype(np.uint32), N[used])
    side = "left" if name.startswith("Left") else "right"
    write_glb(WEB / f"peel_{side}_appendage.glb", *out["appendage"][:2], normals=out["appendage"][2],
              name=f"{'Left' if side == 'left' else 'Right'} atrial appendage")
    write_glb(WEB / f"peel_{side}_atrium_body.glb", *out["body"][:2], normals=out["body"][2], name=f"{name} (body)")
    rep[f"{side}_appendage"] = {"atrium": name, "seed_near": key, "seed_LPS": Vu[seed].round(2).tolist(), "geodesic_mm": mm,
                                "faces": int(tri_in.sum()), "body_faces": int((~tri_in).sum()), "vertices_moved": 0}
    log(f"{name}: appendage {int(tri_in.sum())} of {len(F)} triangles (geodesic {mm} mm from the wall over the {key} origin)")


def main():
    heart = bad.heart_nodes()
    man = json.loads((A_DIR / "manifest.json").read_text())
    cath = json.loads((WEB / "atlas_cath.json").read_text())
    rep = {"note": "display only (feature flag peel); never in the X-ray"}
    for name in APPENDAGE_MM:
        split_atrium(name, heart[name], man, rep, cath)
    build_fat(heart, cath, rep)
    (A_DIR / "peel_parts.json").write_text(json.dumps(rep, indent=1))
    log("wrote peel_*.glb and peel_parts.json")


if __name__ == "__main__":
    main()
