"""Reference CPU renderer: per-pixel path length through a voxel mask along true source->pixel rays.

Used for Phase 0 PNGs and as ground truth for the later GPU renderers. Raster convention
(CONVENTIONS.md 'Image raster'): row 0 is the top of the screen (+v), column 0 the left
(-u). That is the only screen->array mapping; no flips anywhere else.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import map_coordinates

from .geometry import CArm
from .volume import Volume


@dataclass(frozen=True)
class DetectorGrid:
    size_mm: float = 250.0
    n: int = 500

    @property
    def pixel_mm(self) -> float:
        return self.size_mm / self.n

    def pixel_centers(self) -> tuple[np.ndarray, np.ndarray]:
        """Screen (x, y) mm of every pixel, each shape (n, n), indexed [row, col]."""
        c = (np.arange(self.n) + 0.5) * self.pixel_mm - self.size_mm / 2
        x = np.broadcast_to(c[None, :], (self.n, self.n))
        y = np.broadcast_to(-c[:, None], (self.n, self.n))
        return x, y

    def screen_to_pixel(self, xy) -> np.ndarray:
        """Screen mm -> fractional (row, col)."""
        xy = np.atleast_2d(np.asarray(xy, float))
        col = (xy[:, 0] + self.size_mm / 2) / self.pixel_mm - 0.5
        row = (self.size_mm / 2 - xy[:, 1]) / self.pixel_mm - 0.5
        return np.stack([row, col], axis=1)


def crop_to_mask(vol: Volume, mask: np.ndarray, margin: int = 2) -> Volume:
    idx = np.argwhere(mask)
    lo = np.maximum(idx.min(0) - margin, 0)
    hi = np.minimum(idx.max(0) + margin + 1, mask.shape)
    sub = mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]].astype(np.float32)
    A = vol.affine.copy()
    A[:3, 3] = vol.index_to_lps(lo)[0]
    return Volume(data=sub, affine=A, source_space=vol.source_space)


def thickness_image(carm: CArm, mask_vol: Volume, grid: DetectorGrid,
                    step_mm: float = 0.2, chunk: int = 4000) -> np.ndarray:
    """Path length (mm) through `mask_vol` (float 0..1, trilinear) for every detector pixel."""
    x, y = grid.pixel_centers()
    q = carm.screen_to_lps(np.stack([x.ravel(), y.ravel()], 1))
    S = carm.source
    dirs = q - S
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)

    lo, hi = mask_vol.bounds_lps()
    with np.errstate(divide="ignore", invalid="ignore"):
        t_a = (lo - S) / dirs
        t_b = (hi - S) / dirs
    t0 = np.nanmax(np.minimum(t_a, t_b), axis=1)
    t1 = np.nanmin(np.maximum(t_a, t_b), axis=1)
    hit = np.flatnonzero(t1 > t0)

    inv = np.linalg.inv(mask_vol.affine[:3, :3])
    org = mask_vol.affine[:3, 3]
    out = np.zeros(len(q), np.float64)
    for s in range(0, len(hit), chunk):
        r = hit[s:s + chunk]
        k = np.arange(int(np.ceil((t1[r] - t0[r]).max() / step_mm)) + 1)
        t = t0[r, None] + (k[None, :] + 0.5) * step_mm
        valid = t < t1[r, None]
        pts = S + t[..., None] * dirs[r, None, :]
        ijk = (pts - org) @ inv.T
        vals = map_coordinates(mask_vol.data, ijk.reshape(-1, 3).T, order=1, cval=0.0)
        out[r] = (vals.reshape(t.shape) * valid).sum(1) * step_mm
    return out.reshape(grid.n, grid.n)


def angio_intensity(thickness_mm: np.ndarray, k_per_mm: float = 0.35) -> np.ndarray:
    """I = exp(-k t): 1 = unattenuated (bright), contrast-filled lumen dark."""
    return np.exp(-k_per_mm * thickness_mm)
