"""Close open triangle meshes for path-length rendering (the X-ray needs closed, outward-wound meshes).

Only HOLES are added (a fan of triangles from each boundary loop's centroid); no existing vertex moves. Each cap triangle
runs along its rim edge in the opposite direction to the face that owns the edge, so the winding stays consistent.
"""
from __future__ import annotations

import numpy as np


def merge_close(V, F, digits=4):
    """Merge vertices equal to `digits` decimals (glTF splits vertices at normal seams)."""
    key = np.round(np.asarray(V, float), digits)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.ravel()
    newV = np.zeros((len(uniq), 3))
    np.add.at(newV, inv, V)
    newV /= np.bincount(inv)[:, None]
    F2 = inv[np.asarray(F)]
    ok = (F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])
    return newV, F2[ok]


def boundary_loops(F):
    """Directed boundary edges (as owned by their face) chained into loops."""
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(e, 1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    b = e[cnt[inv.ravel()] == 1]
    nxt = {}
    for a, c in b:
        nxt.setdefault(int(a), []).append(int(c))
    loops, used = [], set()
    for a, c in b:
        if (int(a), int(c)) in used:
            continue
        loop = [int(a)]
        cur, prev = int(c), int(a)
        used.add((prev, cur))
        while cur != loop[0] and len(loop) < len(b) + 1:
            loop.append(cur)
            cand = [x for x in nxt.get(cur, []) if (cur, x) not in used]
            if not cand:
                break
            prev, cur = cur, cand[0]
            used.add((prev, cur))
        loops.append(loop)
    return loops


def cap_holes(V, F):
    """Returns (V, F, stats): every boundary loop fan-capped from its centroid."""
    V = np.asarray(V, float)
    F = np.asarray(F, np.int64)
    loops = boundary_loops(F)
    newV, newF = [V], [F]
    n = len(V)
    for lp in loops:
        c = V[lp].mean(0)
        newV.append(c[None])
        k = len(lp)
        # owned edge a->b; cap triangle b->a->c runs it the other way
        tri = np.array([[lp[(i + 1) % k], lp[i], n] for i in range(k)])
        newF.append(tri)
        n += 1
    V2, F2 = np.vstack(newV), np.vstack(newF)
    _, cnt = np.unique(np.sort(np.concatenate([F2[:, [0, 1]], F2[:, [1, 2]], F2[:, [2, 0]]]), 1), axis=0, return_counts=True)
    vol = signed_volume(V2, F2)
    return V2, F2, {"holes_capped": len(loops), "loop_sizes": sorted({len(lp) for lp in loops}),
                    "open_edges_after": int((cnt == 1).sum()), "nonmanifold_edges_after": int((cnt > 2).sum()),
                    "signed_volume_mm3": round(float(vol), 1)}


def signed_volume(V, F):
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def volume_centroid(V, F):
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    w = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    return (w[:, None] * (a + b + c) / 4.0).sum(0) / w.sum(), float(w.sum())
