"""Skin weld (D48): seams close, only rim vertices move, normals end up consistent."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "preprocess"))
from cpt.weld import boundary_edges, weld  # noqa: E402


def grid(x0, x1, nx, ny, y0=0.0, y1=10.0, z=0.0):
    xs, ys = np.linspace(x0, x1, nx), np.linspace(y0, y1, ny)
    V = np.array([(x, y, z) for y in ys for x in xs], float)
    F = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            F += [(a, a + 1, a + nx + 1), (a, a + nx + 1, a + nx)]
    return V, np.array(F)


def two_regions(gap=0.0, ny_right=7, flip_right=False):
    """Two flat patches meeting at x=10; the right one is tessellated differently along the seam and may sit `gap` mm away."""
    VA, FA = grid(0, 10, 6, 5)
    VB, FB = grid(10 + gap, 20, 6, ny_right)
    if flip_right:
        FB = FB[:, ::-1]
    V = np.vstack([VA, VB])
    F = np.vstack([FA, FB + len(VA)])
    fr = np.r_[np.zeros(len(FA), int), np.ones(len(FB), int)]
    return V, F, fr


def seam_open(V, F):
    """Length of rim that is not covered by the other side: rim vertices strictly inside the strip 0 < |x - 10| ."""
    e, _ = boundary_edges(F)
    xs = V[np.unique(e)][:, 0]
    return np.sum((xs > 10 + 1e-6) & (xs < 10.5)) + np.sum((xs < 10 - 1e-6) & (xs > 9.5))


def test_coincident_seam_is_merged():
    V, F, fr = two_regions(gap=0.0, ny_right=5)          # same tessellation: every seam vertex coincides
    w = weld(V, F, fr)
    assert len(w["V"]) == len(V) - 5
    assert w["stats"]["snap"]["vertices_moved"] == 0


def test_gap_seam_is_closed_and_only_rim_moves():
    V, F, fr = two_regions(gap=0.8, ny_right=7)          # 0.8 mm crack and mismatched tessellation (T-junctions)
    w = weld(V, F, fr, snap_tol=2.0)
    assert seam_open(w["V"], w["F"]) == 0
    assert w["stats"]["result"]["max_residual_seam_gap_mm"] <= 0.05
    assert 0 < w["stats"]["snap"]["max_displacement_mm"] <= 0.8 + 1e-9
    moved = np.linalg.norm(w["V"][w["labels"]] - V, axis=1) > 1e-9
    assert np.all(np.abs(V[moved][:, 0] - 10.4) <= 0.4 + 1e-9), "only vertices on the two seam rims may move"


def test_gap_beyond_tolerance_is_left_open():
    V, F, fr = two_regions(gap=5.0)
    w = weld(V, F, fr, snap_tol=2.0)
    assert w["stats"]["snap"]["vertices_moved"] == 0


def test_flipped_region_is_reoriented_and_normals_agree():
    V, F, fr = two_regions(gap=0.0, ny_right=5, flip_right=True)
    w = weld(V, F, fr)
    assert w["stats"]["orientation"]["inconsistent_shared_edges_after"] == 0
    nz = w["N"][:, 2]
    assert np.all(np.abs(np.abs(nz) - 1) < 1e-9) and (np.all(nz > 0) or np.all(nz < 0))


def test_closed_surface_is_turned_outward():
    """A closed box tiled into two regions (top half / bottom half), every face wound INWARD: outward=True turns it around."""
    V = np.array([[x, y, z] for z in (0, 10) for y in (0, 10) for x in (0, 10)], float)
    quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]   # outward (CCW from outside)
    F = np.array([t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))])[:, ::-1]               # all reversed: inward
    fr = (V[F].mean(1)[:, 2] > 5).astype(int)
    w = weld(V, F, fr, outward=True)
    c = w["V"][w["F"]].mean(1)
    fn = np.cross(w["V"][w["F"][:, 1]] - w["V"][w["F"][:, 0]], w["V"][w["F"][:, 2]] - w["V"][w["F"][:, 0]])
    assert np.all(np.einsum("ij,ij->i", c - 5.0, fn) > 0)
    assert np.all(np.einsum("ij,ij->i", w["V"] - 5.0, w["N"]) > 0)


def test_majority_input_orientation_is_kept():
    V, F, fr = two_regions(gap=0.0, ny_right=5)
    F = F.copy()
    F[:3] = F[:3, ::-1]                                    # 3 stray faces flipped in an otherwise +z surface
    w = weld(V, F, fr)
    assert np.all(w["N"][:, 2] > 0.99)
