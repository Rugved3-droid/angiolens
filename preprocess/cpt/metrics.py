"""Phase 2 view metrics. PURELY GEOMETRIC: inputs are centerline samples (LPS mm + radius) and a CArm.
Nothing here may read a rendered image or pixel buffer (guarded by tests/test_metrics.py).

Foreshortening (CONVENTIONS 5):  F = 1 - sum|dp - (dp.r)r| / sum|dp|, r = unit ray to each pair midpoint.

Overlap (spec, Phase 2):
  - every projected centerline piece (consecutive samples) of a vessel is a 2D capsule: the projected segment
    plus its projected radius, radius scaled by local magnification SID / ((p - S).d), linearly interpolated
    along the piece;
  - a target sample is overlapped if any capsule covers its projected centre;
  - INTER: capsules of the other edges of the injected tree; target samples within BIF_EXCLUSION_MM (3D) of the
    target's own bifurcation nodes are not evaluated;
  - SELF: capsules of the target itself, only pieces more than SELF_ARC_MM away in arc length;
  - O_any (used in the combined cost): fraction of samples overlapped by either, over the samples evaluated for INTER.
Combined cost = w_f * F + w_o * O_any.
"""
from __future__ import annotations

import numpy as np

from .geometry import ALPHA_RANGE_DEG, BETA_RANGE_DEG, CArm

BIF_EXCLUSION_MM = 3.0
SELF_ARC_MM = 10.0
GRID_STEP_DEG = 2.0


def _axis(lo, hi, step):
    """Grid anchored at 0 (so AP / zero tilt is always sampled), plus the exact range ends."""
    inner = np.arange(np.ceil(lo / step) * step, hi + 1e-9, step)
    return np.unique(np.r_[lo, inner, hi])


def angle_grid(step=GRID_STEP_DEG):
    return _axis(*ALPHA_RANGE_DEG, step), _axis(*BETA_RANGE_DEG, step)


def foreshortening(points: np.ndarray, source: np.ndarray) -> float:
    dp = np.diff(points, axis=0)
    r = 0.5 * (points[1:] + points[:-1]) - source
    r /= np.linalg.norm(r, axis=1, keepdims=True)
    perp = dp - np.sum(dp * r, axis=1, keepdims=True) * r
    return float(1.0 - np.linalg.norm(perp, axis=1).sum() / np.linalg.norm(dp, axis=1).sum())


def _project(carm: CArm, pts: np.ndarray):
    return carm.project(pts), carm.magnification(pts)


def _covered(q: np.ndarray, a: np.ndarray, b: np.ndarray, ra: np.ndarray, rb: np.ndarray) -> np.ndarray:
    """q (N,2) points vs capsules a->b (M,2) with radii ra->rb (M,): (N,) bool, any capsule covers."""
    if len(a) == 0 or len(q) == 0:
        return np.zeros(len(q), bool)
    ab = b - a                                                      # (M,2)
    L2 = np.maximum(np.sum(ab * ab, axis=1), 1e-12)
    t = np.clip(((q[:, None, :] - a[None]) * ab[None]).sum(-1) / L2[None], 0, 1)   # (N,M)
    d = np.linalg.norm(q[:, None, :] - (a[None] + t[..., None] * ab[None]), axis=-1)
    return np.any(d <= ra[None] + t * (rb - ra)[None], axis=1)


def view_metrics(carm: CArm, target: np.ndarray, target_bif: np.ndarray, others: list[np.ndarray]) -> dict:
    """target (N,4) ordered samples x,y,z,r; target_bif (K,3) bifurcation nodes on the target;
    others: list of (M,4) sample arrays of the other edges of the injected tree."""
    P = target[:, :3]
    q, mag = _project(carm, P)
    F = foreshortening(P, carm.source)

    evaluated = np.ones(len(P), bool)
    if len(target_bif):
        d = np.linalg.norm(P[:, None, :] - np.asarray(target_bif)[None], axis=-1).min(1)
        evaluated = d > BIF_EXCLUSION_MM

    inter = np.zeros(len(P), bool)
    for o in others:
        qo, mo = _project(carm, o[:, :3])
        ro = o[:, 3] * mo
        inter |= _covered(q, qo[:-1], qo[1:], ro[:-1], ro[1:])
    inter &= evaluated

    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    rt = target[:, 3] * mag
    mid_arc = 0.5 * (arc[1:] + arc[:-1])
    self_ = np.zeros(len(P), bool)
    for i in range(len(P)):
        far = np.abs(mid_arc - arc[i]) > SELF_ARC_MM
        if far.any():
            self_[i] = _covered(q[i:i + 1], q[:-1][far], q[1:][far], rt[:-1][far], rt[1:][far])[0]

    n_eval = max(int(evaluated.sum()), 1)
    return {"F": F,
            "O_inter": float(inter.sum() / n_eval),
            "O_self": float(self_.mean()),
            "O_any": float(((inter | self_) & evaluated).sum() / n_eval),
            "inter_mask": inter, "self_mask": self_, "evaluated": evaluated}


def combined_cost(F, O_any, w_f=1.0, w_o=1.0):
    return w_f * np.asarray(F) + w_o * np.asarray(O_any)


def angle_maps(iso, target, target_bif, others, step=GRID_STEP_DEG) -> dict:
    a, b = angle_grid(step)
    out = {k: np.zeros((len(b), len(a))) for k in ("F", "O_inter", "O_self", "O_any")}
    for j, beta in enumerate(b):
        for i, alpha in enumerate(a):
            m = view_metrics(CArm(alpha, beta, iso), target, target_bif, others)
            for k in out:
                out[k][j, i] = m[k]
    out["alpha"], out["beta"] = a, b
    return out
