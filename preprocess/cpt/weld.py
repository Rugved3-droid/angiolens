"""Weld a surface tiled into separately-meshed regions into ONE surface with consistent normals (D48).

The Z-Anatomy skin is 240 region meshes whose seams do not share vertices: about half the seam vertices coincide, the rest
sit up to a few mm from the neighbouring region's rim (different tessellation on each side). Welding:

1. merge vertices closer than `exact_tol` (union-find);
2. snap: every rim vertex moves onto the nearest rim EDGE of a different region, if one lies within `snap_tol`
   (all rims move at once; repeated `iters` times, so two facing rims meet); then merge again;
3. orient: faces are flipped so that every edge shared by two faces is traversed in opposite directions; then each connected
   piece is turned to face outward of the closed body surface (ray parity from just in front of its largest faces). The
   input winding is NOT trusted: the atlas regions are not consistently wound;
4. normals: area-weighted vertex normals; on the remaining T-junction seams the normals of nearby rim vertices are averaged,
   so the shading is continuous across the seam.

Only rim vertices move, and only by the logged snap distance. No region is moved, rotated or scaled as a whole.
"""
from collections import deque

import numpy as np
from scipy.spatial import cKDTree


def _merge(V, tol):
    """Union-find merge of vertices within tol. Returns (labels, new vertex positions = mean of each group)."""
    parent = np.arange(len(V))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in cKDTree(V).query_pairs(tol, output_type="ndarray"):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    roots = np.array([find(i) for i in range(len(V))])
    uniq, lab = np.unique(roots, return_inverse=True)
    cnt = np.bincount(lab)
    newV = np.zeros((len(uniq), 3))
    np.add.at(newV, lab, V)
    return lab, newV / cnt[:, None]


def _clean_faces(F):
    """Drop degenerate faces and exact duplicates (same three vertices); returns faces and the keep-mask."""
    ok = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    _, first = np.unique(np.sort(F, 1), axis=0, return_index=True)
    dup = np.ones(len(F), bool)
    dup[first] = False
    ok &= ~dup
    return F[ok], ok


def boundary_edges(F):
    """Directed edges (a, b, face) used by exactly one face, regardless of direction."""
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    fi = np.tile(np.arange(len(F)), 3)
    key = np.sort(e, 1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    once = cnt[inv.ravel()] == 1
    return e[once], fi[once]


def _point_segment(P, A, B):
    AB = B - A
    t = np.clip(np.einsum("ij,ij->i", P - A, AB) / np.maximum(np.einsum("ij,ij->i", AB, AB), 1e-18), 0, 1)
    C = A + AB * t[:, None]
    return np.linalg.norm(P - C, axis=1), C


def _rim_outward(V, F, be, bf):
    """Per rim vertex: unit in-surface direction pointing OUT of its own region across the rim (away from the face interior)."""
    third = np.array([[x for x in F[f] if x != a and x != b][0] for (a, b), f in zip(be, bf)])
    A, B, C = V[be[:, 0]], V[be[:, 1]], V[third]
    t = B - A
    t = t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    w = (A + B) / 2 - C
    o = w - np.einsum("ij,ij->i", w, t)[:, None] * t
    o = o / np.maximum(np.linalg.norm(o, axis=1, keepdims=True), 1e-12)
    out = np.zeros_like(V)
    for k in (0, 1):
        np.add.at(out, be[:, k], o)
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


def _snap(V, F, face_region, snap_tol, k=12, max_angle_deg=60.0):
    """One sequential (in-place, Gauss-Seidel) snap of rim vertices onto the nearest rim edge of another region, only ACROSS the crack: the target must
    lie within max_angle_deg of the vertex's outward rim direction (or straight behind it, for overlapping rims), so a vertex
    on a genuinely open rim is never dragged along the boundary. Returns new V and displacements."""
    be, bf = boundary_edges(F)
    if not len(be):
        return V, np.zeros(len(V))
    er = face_region[bf]
    rim = np.unique(be)
    outward = _rim_outward(V, F, be, bf)
    cos_max = np.cos(np.radians(max_angle_deg))
    # rim vertex -> its regions (a merged vertex can belong to several)
    vreg = {}
    for (a, b), r in zip(be, er):
        vreg.setdefault(a, set()).add(r)
        vreg.setdefault(b, set()).add(r)
    # candidate edges through the k nearest rim vertices
    inc = {}
    for i, (a, b) in enumerate(be):
        inc.setdefault(a, []).append(i)
        inc.setdefault(b, []).append(i)
    tree = cKDTree(V[rim])
    _, nn = tree.query(V[rim], k=min(k, len(rim)))
    newV = V.copy()
    disp = np.zeros(len(V))
    for row, v in enumerate(rim):
        cand = {e for j in np.atleast_1d(nn[row]) for e in inc[rim[j]] if er[e] not in vreg[v] and v not in be[e]}
        if not cand:
            continue
        c = np.fromiter(cand, int)
        d, C = _point_segment(np.repeat(newV[v][None], len(c), 0), newV[be[c, 0]], newV[be[c, 1]])
        across = np.abs(((C - newV[v]) / np.maximum(d, 1e-12)[:, None]) @ outward[v]) >= cos_max
        ok = (d <= 1e-6) | across
        if not ok.any():
            continue
        d, C = d[ok], C[ok]
        j = int(np.argmin(d))
        if d[j] <= snap_tol:
            newV[v] = C[j]
            disp[v] = d[j]
    return newV, disp


RAY_DIRS = np.array([[0.5773, 0.5778, 0.5769], [-0.61, 0.33, 0.72], [0.27, -0.81, 0.52]])
RAY_DIRS = RAY_DIRS / np.linalg.norm(RAY_DIRS, axis=1, keepdims=True)


def _crossings(o, d, v0, e1, e2):
    """Number of triangles hit by the ray o + t d, t > 0 (Moller-Trumbore, all triangles at once)."""
    h = np.cross(d, e2)
    a = np.einsum("ij,ij->i", e1, h)
    ok = np.abs(a) > 1e-12
    f = np.zeros_like(a)
    f[ok] = 1.0 / a[ok]
    s = o - v0
    u = f * np.einsum("ij,ij->i", s, h)
    q = np.cross(s, e1)
    v = f * (q @ d)
    t = f * np.einsum("ij,ij->i", e2, q)
    return int(np.sum(ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6)))


def _outward_flip(V, F, comp, nc, samples=9, eps=0.5):
    """Per connected piece: is its current winding normal pointing INTO the closed body? Vote over its largest faces: a point
    eps mm along the normal is inside when rays from it cross the whole surface an odd number of times (3 directions)."""
    v0 = V[F[:, 0]]
    e1, e2 = V[F[:, 1]] - v0, V[F[:, 2]] - v0
    fn = np.cross(e1, e2)
    area = np.linalg.norm(fn, axis=1)
    n = fn / np.maximum(area, 1e-12)[:, None]
    flip_piece = np.zeros(nc, bool)
    votes = []
    for c in range(nc):
        idx = np.flatnonzero(comp == c)
        pick = idx[np.argsort(-area[idx])[:samples]]
        inward = 0
        for f in pick:
            p = V[F[f]].mean(0) + eps * n[f]
            inward += sum(_crossings(p, d, v0, e1, e2) % 2 for d in RAY_DIRS) >= 2
        flip_piece[c] = inward * 2 > len(pick)
        votes.append((int(len(idx)), int(inward), int(len(pick))))
    return flip_piece, votes


def _orient(F, prefer_input=True, V=None):
    """Make winding consistent across every edge shared by exactly two faces (BFS, flipping as needed). Then each connected
    piece is turned to face OUTWARD of the closed surface (when V is given), or keeps its majority input orientation.
    Returns oriented faces and stats."""
    nF = len(F)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    fi = np.tile(np.arange(nF), 3)
    key = np.sort(e, 1)
    order = np.lexsort((key[:, 1], key[:, 0]))
    ks, fs, es = key[order], fi[order], e[order]
    same = np.all(ks[1:] == ks[:-1], axis=1)
    # pairs of consecutive equal keys where the key occurs exactly twice
    start = np.flatnonzero(np.r_[True, ~same])
    counts = np.diff(np.r_[start, len(ks)])
    two = start[counts == 2]
    fa, fb = fs[two], fs[two + 1]
    # same direction on both faces -> they disagree (one must flip)
    agree = ~np.all(es[two] == es[two + 1], axis=1)
    adj = [[] for _ in range(nF)]
    for a, b, g in zip(fa, fb, agree):
        adj[a].append((b, g))
        adj[b].append((a, g))
    flip = np.zeros(nF, bool)
    comp = -np.ones(nF, int)
    nc = 0
    for s in range(nF):
        if comp[s] >= 0:
            continue
        comp[s] = nc
        q = deque([s])
        while q:
            f = q.popleft()
            for g, ok in adj[f]:
                want = flip[f] if ok else not flip[f]
                if comp[g] < 0:
                    comp[g] = nc
                    flip[g] = want
                    q.append(g)
        nc += 1
    extra = {}
    if V is not None:
        cur = F.copy()
        cur[flip] = cur[flip][:, ::-1]
        fp, votes = _outward_flip(V, cur, comp, nc)
        flip ^= fp[comp]
        big = sorted(votes, reverse=True)[:5]
        extra = {"orientation_rule": "outward by ray parity", "pieces_turned_outward": int(fp.sum()),
                 "largest_pieces_faces_inward_votes_samples": big,
                 "ambiguous_pieces": int(sum(1 for _, i, s in votes if 0 < i < s))}
    elif prefer_input:
        for c in range(nc):
            m = comp == c
            if flip[m].mean() > 0.5:
                flip[m] = ~flip[m]
    out = F.copy()
    out[flip] = out[flip][:, ::-1]
    # residual inconsistency (non-orientable or conflicting cycles)
    e2 = np.concatenate([out[:, [0, 1]], out[:, [1, 2]], out[:, [2, 0]]])[order]
    bad = int(np.sum(np.all(e2[two] == e2[two + 1], axis=1)))
    return out, {"pieces": int(nc), "faces_flipped": int(flip.sum()), "shared_edges": int(len(two)),
                 "inconsistent_shared_edges_after": bad, **extra}


def vertex_normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])     # area-weighted
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def weld(V, F, face_region, exact_tol=0.01, snap_tol=4.0, iters=3, seam_normal_radius=1.5, outward=False):
    """V (n,3) float, F (m,3) int, face_region (m,) int. outward=True: orient every piece outward of the (nearly closed)
    surface by ray parity; otherwise keep the majority input orientation. Returns dict(V, F, face_region, labels (input vertex
    -> output vertex), N, stats)."""
    V = np.asarray(V, float)
    F = np.asarray(F, np.int64)
    face_region = np.asarray(face_region)
    stats = {"input_vertices": int(len(V)), "input_faces": int(len(F))}
    rim0, _ = boundary_edges(F)
    stats["input_open_edges"] = int(len(rim0))
    lab, V1 = _merge(V, exact_tol)
    F1, ok = _clean_faces(lab[F])
    fr = face_region[ok]
    stats["after_exact_merge"] = {"vertices": int(len(V1)), "open_edges": int(len(boundary_edges(F1)[0]))}
    total = np.zeros(len(V1))
    for _ in range(iters):
        V1, d = _snap(V1, F1, fr, snap_tol)
        total += d
    lab2, V2 = _merge(V1, exact_tol * 5)
    F2, ok2 = _clean_faces(lab2[F1])
    fr2 = fr[ok2]
    moved = total[total > 0]
    stats["snap"] = {"snap_tol_mm": snap_tol, "iterations": iters, "vertices_moved": int(len(moved)),
                     "max_displacement_mm": round(float(moved.max()), 3) if len(moved) else 0.0,
                     "p99_displacement_mm": round(float(np.quantile(moved, 0.99)), 3) if len(moved) else 0.0}
    F3, ost = _orient(F2, V=V2 if outward else None)
    stats["orientation"] = ost
    N = vertex_normals(V2, F3)
    # continuous shading across T-junction seams: average rim-vertex normals within seam_normal_radius
    rim, rf = boundary_edges(F3)
    rv = np.unique(rim)
    if len(rv):
        groups = cKDTree(V2[rv]).query_ball_point(V2[rv], seam_normal_radius)
        Nr = np.array([N[rv[g]].sum(0) for g in groups])
        N[rv] = Nr / np.maximum(np.linalg.norm(Nr, axis=1, keepdims=True), 1e-12)
    # seam gaps left: rim vertices whose nearest other-region rim edge is still > 0.05 mm away but within snap_tol
    _, d_left = _snap(V2, F3, fr2, snap_tol)
    stats["result"] = {"vertices": int(len(V2)), "faces": int(len(F3)), "open_edges": int(len(rim)),
                       "rim_vertices_with_residual_gap_over_0.05mm": int(np.sum(d_left > 0.05)),
                       "max_residual_seam_gap_mm": round(float(d_left.max()), 3) if len(d_left) else 0.0}
    labels = lab2[lab]                     # input vertex -> output vertex
    return {"V": V2, "F": F3, "face_region": fr2, "labels": labels, "N": N, "stats": stats}
