"""NRRD loading into the LPS patient frame.

voxel (i,j,k) -> LPS:  p = origin + i*dir_i + j*dir_j + k*dir_k, taken from the
header only. A RAS-declared header is converted by negating x and y of both the
directions and the origin. Any other space is rejected. Recentering is a pure
translation and never touches the linear part.
"""
from __future__ import annotations

from dataclasses import dataclass

import nrrd
import numpy as np

LPS_NAMES = {"left-posterior-superior", "lps"}
RAS_NAMES = {"right-anterior-superior", "ras"}
RAS_TO_LPS = np.diag([-1.0, -1.0, 1.0])


@dataclass
class Volume:
    data: np.ndarray        # indexed [i, j, k] in header axis order
    affine: np.ndarray      # 4x4 voxel index -> LPS mm
    source_space: str       # space as declared in the header

    @property
    def spacing(self) -> np.ndarray:
        return np.linalg.norm(self.affine[:3, :3], axis=0)

    def index_to_lps(self, ijk) -> np.ndarray:
        ijk = np.atleast_2d(np.asarray(ijk, float))
        return ijk @ self.affine[:3, :3].T + self.affine[:3, 3]

    def lps_to_index(self, p) -> np.ndarray:
        p = np.atleast_2d(np.asarray(p, float))
        inv = np.linalg.inv(self.affine[:3, :3])
        return (p - self.affine[:3, 3]) @ inv.T

    def bounds_lps(self) -> tuple[np.ndarray, np.ndarray]:
        n = np.array(self.data.shape) - 1
        corners = np.array([[a, b, c] for a in (0, n[0]) for b in (0, n[1]) for c in (0, n[2])])
        pts = self.index_to_lps(corners)
        return pts.min(0), pts.max(0)


def affine_from_header(hdr: dict) -> tuple[np.ndarray, str]:
    space = hdr.get("space")
    if space is None:
        raise ValueError("NRRD header has no 'space' field; refusing to guess the patient frame")
    s = space.strip().lower()
    dirs = np.asarray(hdr["space directions"], float)   # rows = per-axis vectors
    if dirs.shape != (3, 3) or not np.all(np.isfinite(dirs)):
        raise ValueError(f"unexpected 'space directions': {dirs}")
    origin = np.asarray(hdr.get("space origin", np.zeros(3)), float)
    lin = dirs.T                                       # columns = per-axis vectors
    if s in LPS_NAMES:
        pass
    elif s in RAS_NAMES:
        lin = RAS_TO_LPS @ lin
        origin = RAS_TO_LPS @ origin
    else:
        raise ValueError(f"unsupported NRRD space '{space}'")
    A = np.eye(4)
    A[:3, :3] = lin
    A[:3, 3] = origin
    return A, space


def load_nrrd_lps(path) -> Volume:
    data, hdr = nrrd.read(str(path), index_order="F")
    A, space = affine_from_header(hdr)
    return Volume(data=data, affine=A, source_space=space)


def translated(vol: Volume, offset) -> Volume:
    """Shift the frame by `offset` mm (p' = p - offset). Translation only."""
    A = vol.affine.copy()
    A[:3, 3] = A[:3, 3] - np.asarray(offset, float)
    return Volume(data=vol.data, affine=A, source_space=vol.source_space)


def assert_same_grid(a: Volume, b: Volume, tol: float = 1e-4) -> None:
    if a.data.shape != b.data.shape or not np.allclose(a.affine, b.affine, atol=tol):
        raise ValueError("CT and annotation are not on the same voxel grid")
