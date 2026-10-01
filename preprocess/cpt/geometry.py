"""C-arm projection geometry in the LPS patient frame.

Every rule here is stated in CONVENTIONS.md and pinned by tests/test_geometry.py.
Nothing in this module (or anywhere downstream) may mirror or rotate an image to
"fix" its appearance; if a projection looks wrong, the bug is in the geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SID_MM = 1000.0
SOD_MM = 750.0
ALPHA_RANGE_DEG = (-90.0, 90.0)   # primary: LAO +, RAO -
BETA_RANGE_DEG = (-45.0, 45.0)    # secondary: cranial +, caudal -
Z_SUPERIOR = np.array([0.0, 0.0, 1.0])


def detector_direction(alpha_deg: float, beta_deg: float) -> np.ndarray:
    """Unit vector from isocenter toward the detector: (sin a cos b, -cos a cos b, sin b)."""
    a, b = np.radians(alpha_deg), np.radians(beta_deg)
    return np.array([np.sin(a) * np.cos(b), -np.cos(a) * np.cos(b), np.sin(b)])


def screen_axes(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Screen right u and screen up v for detector direction d.

    v = normalize(z - (z.d) d);  u = v x d.  Then u x v = d, i.e. the image is
    viewed from the detector side looking back at the source.
    """
    v = Z_SUPERIOR - (Z_SUPERIOR @ d) * d
    n = np.linalg.norm(v)
    if n < 1e-9:
        raise ValueError("screen up undefined: detector direction parallel to z")
    v = v / n
    u = np.cross(v, d)
    return u, v


def view_label(alpha_deg: float, beta_deg: float) -> str:
    """Cath-lab style readout, e.g. 'RAO 30 / CAUD 20'. Zero components are omitted."""
    a, b = round(alpha_deg), round(beta_deg)
    primary = "AP" if a == 0 else f"{'LAO' if a > 0 else 'RAO'} {abs(a)}"
    if b == 0:
        return primary
    return f"{primary} / {'CRAN' if b > 0 else 'CAUD'} {abs(b)}"


@dataclass(frozen=True)
class CArm:
    """A C-arm pose. All points are LPS mm in the patient frame.

    The isocenter is a single constant per case; `table_offset` is reserved for
    a later table-pan feature and is added to it.
    """
    alpha_deg: float
    beta_deg: float
    isocenter: np.ndarray
    table_offset: np.ndarray = field(default_factory=lambda: np.zeros(3))
    sid: float = SID_MM
    sod: float = SOD_MM

    def __post_init__(self):
        lo, hi = ALPHA_RANGE_DEG
        if not lo <= self.alpha_deg <= hi:
            raise ValueError(f"alpha {self.alpha_deg} outside {ALPHA_RANGE_DEG}")
        lo, hi = BETA_RANGE_DEG
        if not lo <= self.beta_deg <= hi:
            raise ValueError(f"beta {self.beta_deg} outside {BETA_RANGE_DEG}")
        object.__setattr__(self, "isocenter", np.asarray(self.isocenter, float))
        object.__setattr__(self, "table_offset", np.asarray(self.table_offset, float))

    @property
    def iso(self) -> np.ndarray:
        return self.isocenter + self.table_offset

    @property
    def d(self) -> np.ndarray:
        return detector_direction(self.alpha_deg, self.beta_deg)

    @property
    def axes(self) -> tuple[np.ndarray, np.ndarray]:
        return screen_axes(self.d)

    @property
    def source(self) -> np.ndarray:
        return self.iso - self.sod * self.d

    @property
    def detector_center(self) -> np.ndarray:
        return self.iso + (self.sid - self.sod) * self.d

    @property
    def label(self) -> str:
        return view_label(self.alpha_deg, self.beta_deg)

    def magnification(self, points) -> np.ndarray:
        """Local magnification SID / ((p - S).d)."""
        p = np.atleast_2d(np.asarray(points, float))
        return self.sid / ((p - self.source) @ self.d)

    def detector_hits(self, points) -> np.ndarray:
        """Intersection q of ray S->p with the detector plane, LPS mm, shape (N,3)."""
        p = np.atleast_2d(np.asarray(points, float))
        S = self.source
        depth = (p - S) @ self.d
        if np.any(depth <= 0):
            raise ValueError("point at or behind the source plane")
        t = self.sid / depth
        return S + t[:, None] * (p - S)

    def project(self, points) -> np.ndarray:
        """Screen coordinates (q.u, q.v) in detector mm, origin at the central ray, shape (N,2)."""
        q = self.detector_hits(points) - self.detector_center
        u, v = self.axes
        return np.stack([q @ u, q @ v], axis=1)

    def screen_to_lps(self, xy) -> np.ndarray:
        """Inverse of project() on the detector plane: screen mm -> LPS point on the detector."""
        xy = np.atleast_2d(np.asarray(xy, float))
        u, v = self.axes
        return self.detector_center + xy[:, :1] * u + xy[:, 1:2] * v


def foreshortening(points, source) -> float:
    """F = 1 - sum|dp - (dp.r) r| / sum|dp|, r = unit ray from source to each pair midpoint.

    0 = segment fully in view (perpendicular to its rays); 1 = seen end-on.
    """
    p = np.asarray(points, float)
    if len(p) < 2:
        raise ValueError("need at least two samples")
    dp = np.diff(p, axis=0)
    mid = 0.5 * (p[1:] + p[:-1])
    r = mid - np.asarray(source, float)
    r /= np.linalg.norm(r, axis=1, keepdims=True)
    perp = dp - np.sum(dp * r, axis=1, keepdims=True) * r
    total = np.linalg.norm(dp, axis=1).sum()
    if total == 0:
        raise ValueError("zero-length segment")
    return float(1.0 - np.linalg.norm(perp, axis=1).sum() / total)
