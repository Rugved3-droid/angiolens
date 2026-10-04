"""D52: each atlas tree is ONE closed solid for the X-ray (boolean union), so branch junctions are not counted twice.

At three branch junctions a ray through the junction must see, through the unioned tree, exactly the length of the UNION of
the per-branch intervals (no double count), while the old summed tree sees more. Skipped without the git-ignored export.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "assets" / "anatomy"
pytestmark = pytest.mark.skipif(not (A / "atlas_xray_left.glb").exists(), reason="atlas X-ray build not present (git-ignored)")
JUNCTIONS = ["LAD_branch_02", "LCx_branch_04", "RCA_branch_02"]


def crossings(o, d, V, F):
    """All (t, exit?) where the ray o + t d (t > 0) crosses the closed mesh (V, F)."""
    v0 = V[F[:, 0]]
    e1, e2 = V[F[:, 1]] - v0, V[F[:, 2]] - v0
    h = np.cross(d, e2)
    det = e1 @ np.zeros(3) + np.einsum("ij,ij->i", e1, h)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
    s = o - v0
    u = inv * np.einsum("ij,ij->i", s, h)
    q = np.cross(s, e1)
    v = inv * (q @ d)
    t = inv * np.einsum("ij,ij->i", e2, q)
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
    n = np.cross(e1, e2)[hit]
    return t[hit], (n @ d) > 0


def path(o, d, V, F):
    t, ex = crossings(o, d, V, F)
    return float(t[ex].sum() - t[~ex].sum())


def intervals(o, d, V, F):
    t, ex = crossings(o, d, V, F)
    order = np.argsort(t)
    t, ex = t[order], ex[order]
    out, start = [], None
    for ti, e in zip(t, ex):
        if not e and start is None:
            start = ti
        elif e and start is not None:
            out.append((start, ti))
            start = None
    return out


def union_length(ivs):
    ivs = sorted(ivs)
    total, cur = 0.0, None
    for a, b in ivs:
        if cur is None or a > cur[1]:
            if cur:
                total += cur[1] - cur[0]
            cur = [a, b]
        else:
            cur[1] = max(cur[1], b)
    return total + (cur[1] - cur[0] if cur else 0.0)


@pytest.fixture(scope="module")
def trees():
    sys.path.insert(0, str(ROOT / "preprocess"))
    sys.path.insert(0, str(ROOT / "preprocess" / "scripts"))
    import build_atlas_xray as b
    from cpt.glb import read_glb
    heart = b.nodes(A / "z_anatomy_heart.glb")
    out = {}
    for tree, names in (("left", b.LEFT_WHOLE + sorted(n for n in heart if n.startswith(("LAD_branch_", "LCx_branch_")))),
                        ("right", b.RIGHT_WHOLE + sorted(n for n in heart if n.startswith("RCA_branch_")))):
        parts = []
        b.closed_union([(n, heart[n]) for n in names], tree, parts_out=parts)
        g = read_glb(A / f"atlas_xray_{tree}.glb")
        s = read_glb(A / f"atlas_xray_{tree}_summed.glb")
        out[tree] = {"parts": parts, "union": (g["POSITION"].astype(float), g["indices"].astype(np.int64)),
                     "summed": (s["POSITION"].astype(float), s["indices"].astype(np.int64))}
    return out


@pytest.mark.parametrize("branch", JUNCTIONS)
def test_junction_counted_once(trees, branch):
    man = json.loads((A / "manifest.json").read_text())
    att = next(o["attachment"] for o in man["objects"] if o["anatomical_name"] == branch and o.get("export_group") == "heart")
    assert att and att["gap_mm"] <= 0.5
    # the attachment point is exactly the cap-centre vertex of the branch tube; a ray through a shared vertex is degenerate,
    # so pass 0.04 mm beside it
    p = np.array(att["point_LPS"]) + np.array([0.023, -0.017, 0.029])
    tree = trees["right" if branch.startswith("RCA") else "left"]
    # the direction through the junction with the largest overlap among a fixed fan (deterministic)
    rng = np.random.default_rng(7)
    dirs = rng.normal(size=(60, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    best = None
    for d in dirs:
        o = p - 200 * d
        ivs = [iv for _, V, F in tree["parts"] for iv in intervals(o, d, V, F)]
        u, s = union_length(ivs), sum(b - a for a, b in ivs)
        if best is None or s - u > best[3] - best[2]:
            best = (o, d, u, s)
    o, d, u_chord, summed_parts = best
    assert summed_parts - u_chord > 0.2, f"{branch}: no overlap found at the junction (test would be vacuous)"
    through_union = path(o, d, *tree["union"])
    through_summed = path(o, d, *tree["summed"])
    assert through_union == pytest.approx(u_chord, abs=0.02), (branch, through_union, u_chord)
    assert through_summed == pytest.approx(summed_parts, abs=0.02)
    assert through_summed - through_union > 0.2
