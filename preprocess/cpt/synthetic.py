"""Synthetic voxel phantoms in LPS for geometry tests and the synthetic PNG renderer."""
from __future__ import annotations

import numpy as np

from .volume import Volume


def capsule_mask(segments, spacing: float = 0.5, margin: float = 3.0) -> Volume:
    """Voxelise capsules [(p0, p1, radius), ...] given in LPS mm onto an axis-aligned LPS grid."""
    segs = [(np.asarray(a, float), np.asarray(b, float), float(r)) for a, b, r in segments]
    pts = np.array([p for a, b, r in segs for p in (a - r, a + r, b - r, b + r)])
    lo = pts.min(0) - margin
    hi = pts.max(0) + margin
    shape = np.ceil((hi - lo) / spacing).astype(int) + 1
    axes = [lo[i] + spacing * np.arange(shape[i]) for i in range(3)]
    X, Y, Z = np.meshgrid(*axes, indexing="ij")
    P = np.stack([X, Y, Z], -1)
    mask = np.zeros(shape, bool)
    for a, b, r in segs:
        ab = b - a
        L2 = ab @ ab
        t = np.clip(((P - a) @ ab) / L2, 0, 1) if L2 > 0 else np.zeros(shape)
        dist = np.linalg.norm(P - (a + t[..., None] * ab), axis=-1)
        mask |= dist <= r
    A = np.eye(4)
    A[:3, :3] *= spacing
    A[:3, 3] = lo
    return Volume(data=mask.astype(np.float32), affine=A, source_space="LPS (synthetic)")


def orientation_phantom(iso) -> tuple[Volume, dict]:
    """A deliberately chiral 'tree' rooted at iso so a mirrored or rotated render is obvious.

    trunk  -> +x (patient LEFT), 60 mm, r 2.0, ending in a 5 mm ball
    branch -> +z (SUPERIOR),     40 mm, r 1.5
    branch -> -y (ANTERIOR),     40 mm, r 1.0
    """
    iso = np.asarray(iso, float)
    parts = {
        "left_trunk": (iso, iso + [60, 0, 0], 2.0),
        "left_ball": (iso + [60, 0, 0], iso + [60, 0, 0], 5.0),
        "superior_branch": (iso, iso + [0, 0, 40], 1.5),
        "anterior_branch": (iso, iso + [0, -40, 0], 1.0),
    }
    return capsule_mask(parts.values()), parts
