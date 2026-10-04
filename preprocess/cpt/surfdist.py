"""Point-to-surface distance without a spatial-index dependency (D60): exact point-triangle distance against the k triangles
whose centroids are nearest each point (scipy cKDTree). k large enough that the true nearest triangle is among them."""
import numpy as np
from scipy.spatial import cKDTree


def point_triangle_distance(P, A, B, C):
    """Exact distances from points P[i] to triangles (A[i], B[i], C[i]) (Ericson, Real-Time Collision Detection 5.1.5)."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = P - B
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = P - C
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    denom = va + vb + vc
    with np.errstate(divide="ignore", invalid="ignore"):
        v = np.where(denom != 0, vb / denom, 0)
        w = np.where(denom != 0, vc / denom, 0)
    Q = A + ab * v[:, None] + ac * w[:, None]                      # interior projection
    # regions (vertex / edge) override the interior projection
    def setq(mask, val):
        Q[mask] = val[mask]
    setq((d1 <= 0) & (d2 <= 0), A)
    setq((d3 >= 0) & (d4 <= d3), B)
    vcm = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        setq(vcm, A + ab * np.nan_to_num(d1 / (d1 - d3))[:, None])
    setq((d6 >= 0) & (d5 <= d6), C)
    vbm = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        setq(vbm, A + ac * np.nan_to_num(d2 / (d2 - d6))[:, None])
    vam = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.nan_to_num((d4 - d3) / ((d4 - d3) + (d5 - d6)))
    setq(vam, B + (C - B) * t[:, None])
    return np.linalg.norm(P - Q, axis=1)


def points_to_surface(P, V, F, k=24):
    V, F = np.asarray(V, float), np.asarray(F, np.int64)
    cen = V[F].mean(1)
    _, idx = cKDTree(cen).query(P, k=min(k, len(F)))
    idx = np.atleast_2d(idx.T).T if idx.ndim == 1 else idx
    best = np.full(len(P), np.inf)
    for j in range(idx.shape[1]):
        f = F[idx[:, j]]
        best = np.minimum(best, point_triangle_distance(P, V[f[:, 0]], V[f[:, 1]], V[f[:, 2]]))
    return best
