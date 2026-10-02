"""Reference CPU renderer for CLOSED triangle meshes: exact per-pixel path length along true source->pixel rays.

The CPU twin of the GPU angiogram (web/src/angio.ts): every ray/triangle crossing adds its distance from the source to an
EXIT sum (outward face normal along the ray) or an ENTRY sum; for a closed, outward-wound mesh the path length is
exit - entry. Unlike the GPU, nothing is dropped at silhouettes, so this is ground truth for the atlas X-ray.

Triangles are rasterised in screen space: each one is tested only against the pixels inside its projected bounding box.
Raster convention as everywhere (CONVENTIONS 4, render.DetectorGrid): row 0 = top (+v), column 0 = left (-u).
"""
from __future__ import annotations

import numpy as np

from .geometry import CArm
from .render import DetectorGrid


def mesh_thickness_image(carm: CArm, V, F, grid: DetectorGrid, chunk: int = 200_000):
    """Returns (thickness mm [n,n], stats). Stats count pixels whose entry and exit crossings do not pair up."""
    V = np.asarray(V, float)
    F = np.asarray(F, np.int64)
    S = carm.source
    u, v = carm.axes
    D = carm.detector_center
    xy = carm.project(V)                                     # (nV, 2) screen mm
    rc = grid.screen_to_pixel(xy)                            # fractional (row, col)
    tri_rc = rc[F]                                           # (nF, 3, 2)
    r0 = np.clip(np.floor(tri_rc[..., 0].min(1)).astype(int), 0, grid.n - 1)
    r1 = np.clip(np.ceil(tri_rc[..., 0].max(1)).astype(int), 0, grid.n - 1)
    c0 = np.clip(np.floor(tri_rc[..., 1].min(1)).astype(int), 0, grid.n - 1)
    c1 = np.clip(np.ceil(tri_rc[..., 1].max(1)).astype(int), 0, grid.n - 1)
    nr, nc = r1 - r0 + 1, c1 - c0 + 1
    cnt = nr * nc
    v0 = V[F[:, 0]]
    e1 = V[F[:, 1]] - v0
    e2 = V[F[:, 2]] - v0
    fn = np.cross(e1, e2)
    exit_sum = np.zeros(grid.n * grid.n)
    entry_sum = np.zeros(grid.n * grid.n)
    n_exit = np.zeros(grid.n * grid.n, np.int64)
    n_entry = np.zeros(grid.n * grid.n, np.int64)
    # process triangles in blocks so that the expanded (triangle, pixel) list stays bounded
    order = np.arange(len(F))
    csum = np.cumsum(cnt)
    starts = np.searchsorted(csum, np.arange(0, csum[-1], chunk), side="right") if len(F) else []
    bounds = list(starts) + [len(F)]
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b <= a:
            continue
        idx = order[a:b]
        k = cnt[idx]
        tri = np.repeat(idx, k)
        local = np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)
        rr = r0[tri] + local // nc[tri]
        cc = c0[tri] + local % nc[tri]
        # pixel centre -> LPS point on the detector -> ray from the source
        px = (cc + 0.5) * grid.pixel_mm - grid.size_mm / 2
        py = grid.size_mm / 2 - (rr + 0.5) * grid.pixel_mm
        q = D + px[:, None] * u + py[:, None] * v
        d = q - S
        L = np.linalg.norm(d, axis=1)
        d = d / L[:, None]
        # Moller-Trumbore
        h = np.cross(d, e2[tri])
        det = np.einsum("ij,ij->i", e1[tri], h)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = S - v0[tri]
        bu = inv * np.einsum("ij,ij->i", s, h)
        qv = np.cross(s, e1[tri])
        bv = inv * np.einsum("ij,ij->i", d, qv)
        t = inv * np.einsum("ij,ij->i", e2[tri], qv)
        hit = ok & (bu >= 0) & (bv >= 0) & (bu + bv <= 1) & (t > 0)
        pix = (rr * grid.n + cc)[hit]
        is_exit = np.einsum("ij,ij->i", fn[tri[hit]], d[hit]) > 0
        np.add.at(exit_sum, pix[is_exit], t[hit][is_exit])
        np.add.at(entry_sum, pix[~is_exit], t[hit][~is_exit])
        np.add.at(n_exit, pix[is_exit], 1)
        np.add.at(n_entry, pix[~is_exit], 1)
    th = np.where(n_exit == n_entry, exit_sum - entry_sum, 0.0)
    stats = {"pixels_hit": int(np.sum(n_exit + n_entry > 0)), "unpaired_pixels": int(np.sum(n_exit != n_entry)),
             "negative_pixels": int(np.sum(th < -1e-6))}
    return th.reshape(grid.n, grid.n), stats
