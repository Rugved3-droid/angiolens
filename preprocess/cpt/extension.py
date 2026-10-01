"""NON-EXPERT centerline extension: semi-automatic trace of contrast vessel beyond an expert endpoint.

Kept strictly separate from the expert annotation: its own file (extension.json), its own flag in
case.json, its own render layer. Never merged into the expert lumen, graph or labels-by-default.

Method (semi-automatic = automatic proposal + mandatory human review of the overlay):
  1. ROI of EXT_ROI_MM around the expert endpoint.
  2. Large chambers excluded: opening of HU >= 200 by a 4-voxel ball, dilated 2 voxels.
     The D10 blood-pool mask is NOT used here: its split erosion hands ~1 mm vessels to the pool.
  3. Candidate = smoothed HU (sigma 0.5 voxel) >= threshold, not chamber, not bone, not expert lumen.
  4. The largest connected component touching a 2.5 mm sphere at the endpoint is skeletonized; geodesic paths
     from the skeleton point nearest the endpoint to each skeleton tip become branches. Spurs shorter
     than MIN_BRANCH_MM are dropped. Radius = in-component distance to the boundary (a lower bound).
"""
from __future__ import annotations

import networkx as nx
import numpy as np
from scipy import ndimage as ndi
from skimage.morphology import ball, skeletonize

from .centerline import build_from_paths, resample
from .volume import Volume

EXT_ROI_MM = 60.0
SEED_RADIUS_MM = 2.5
MIN_BRANCH_MM = 4.0
CHAMBER_HU = 200


def trace_extension(ct: Volume, lumen: np.ndarray, bone: np.ndarray, start: np.ndarray,
                    threshold: float) -> dict:
    sp = ct.spacing
    ijk = np.rint(ct.lps_to_index(start)[0]).astype(int)
    r = np.ceil(EXT_ROI_MM / sp).astype(int)
    lo = np.maximum(ijk - r, 0)
    hi = np.minimum(ijk + r + 1, ct.data.shape)
    S = tuple(slice(a, b) for a, b in zip(lo, hi))
    h = ct.data[S].astype(np.float32)
    chambers = ndi.binary_dilation(ndi.binary_opening(h >= CHAMBER_HU, structure=ball(4)), iterations=2)
    sm = ndi.gaussian_filter(h, 0.5)
    cand = (sm >= threshold) & (sm <= 900) & ~chambers & ~bone[S] & ~lumen[S]
    lab, _ = ndi.label(cand, structure=np.ones((3, 3, 3)))
    idx = np.argwhere(cand)
    P = ct.index_to_lps(idx + lo)
    near = np.linalg.norm(P - start, axis=1) <= SEED_RADIUS_MM
    ids = lab[tuple(idx[near].T)]
    if len(ids) == 0:
        return {"threshold": threshold, "traceable": False, "reason": "no candidate voxels at the endpoint"}
    sizes = ndi.sum(cand, lab, np.unique(ids))
    comp_id = int(np.unique(ids)[np.argmax(sizes)])          # largest component touching the seed
    comp = lab == comp_id
    edt = ndi.distance_transform_edt(comp, sampling=sp)

    sk = skeletonize(comp)
    sk_idx = np.argwhere(sk)
    if len(sk_idx) < 2:
        return {"threshold": threshold, "traceable": False, "reason": "component too small"}
    G = nx.Graph()
    key = {tuple(v): n for n, v in enumerate(sk_idx)}
    for n, v in enumerate(sk_idx):
        for d in np.argwhere(np.ones((3, 3, 3))) - 1:
            u = tuple(v + d)
            if u in key and key[u] > n:
                G.add_edge(n, key[u], w=float(np.linalg.norm(d * sp)))
    sk_lps = ct.index_to_lps(sk_idx + lo)
    root = int(np.argmin(np.linalg.norm(sk_lps - start, axis=1)))
    if root not in G:
        return {"threshold": threshold, "traceable": False, "reason": "isolated skeleton point at endpoint"}
    lengths, paths = nx.single_source_dijkstra(G, root, weight="w")
    tips = [n for n in G if G.degree(n) == 1 and n != root and lengths.get(n, 0) >= MIN_BRANCH_MM]
    branch_paths = []
    for t in sorted(tips, key=lambda n: -lengths[n]):
        nodes = paths[t]
        xyz = np.vstack([start, sk_lps[nodes]])
        rad = np.r_[edt[tuple(sk_idx[nodes[0]])], edt[tuple(sk_idx[nodes].T)]]
        branch_paths.append(np.c_[xyz, np.maximum(rad, 0.3)])
    if not branch_paths:
        return {"threshold": threshold, "traceable": False, "reason": "no branch longer than MIN_BRANCH_MM"}
    g = build_from_paths(branch_paths, ["right"] * len(branch_paths))
    hu_stats = []
    for e in g.edges:
        s = resample(e["samples"])
        v = ndi.map_coordinates(ct.data.astype(np.float32), ct.lps_to_index(s[:, :3]).T, order=1)
        L = float(np.linalg.norm(np.diff(s[:, :3], axis=0), axis=1).sum())
        hu_stats.append({"edge": e["id"], "length_mm": round(L, 1), "hu_median": round(float(np.median(v))),
                         "hu_p10": round(float(np.percentile(v, 10))), "radius_median_mm": round(float(np.median(s[:, 3])), 2),
                         "start": s[0, :3].round(1).tolist(), "end": s[-1, :3].round(1).tolist()})
    return {"threshold": threshold, "traceable": True, "graph": g, "component_voxels": int(comp.sum()),
            "component_mm3": round(float(comp.sum() * np.prod(sp)), 1), "branches": hu_stats,
            "roi_lo": lo.tolist(), "component": comp}
