"""Phase 2 metrics: foreshortening, capsule overlap (inter vs self), angle maps; and the guard that metrics
are purely geometric (never read rendered pixels)."""
import ast
from pathlib import Path

import numpy as np
import pytest

from cpt.geometry import CArm
from cpt.metrics import BIF_EXCLUSION_MM, SELF_ARC_MM, angle_maps, view_metrics

ISO = np.array([0.0, 0.0, 0.0])


def tube(a, b, r=1.0, step=0.5):
    a, b = np.asarray(a, float), np.asarray(b, float)
    n = max(int(np.ceil(np.linalg.norm(b - a) / step)), 1)
    t = np.linspace(0, 1, n + 1)[:, None]
    return np.c_[a + t * (b - a), np.full(n + 1, r)]


def test_foreshortening_zero_and_one():
    tgt = tube([-10, 0, 0], [10, 0, 0])
    assert view_metrics(CArm(0, 0, ISO), tgt, np.zeros((0, 3)), [])["F"] == pytest.approx(0, abs=1e-3)
    # along the AP beam (y axis), seen end-on
    tgt2 = tube([0, -10, 0], [0, 10, 0])
    assert view_metrics(CArm(0, 0, ISO), tgt2, np.zeros((0, 3)), [])["F"] == pytest.approx(1, abs=1e-6)


def test_inter_overlap_vessel_behind_target():
    tgt = tube([-10, 0, 0], [10, 0, 0])
    behind = tube([-10, 30, 0], [10, 30, 0])            # same x-z extent, posterior: overlaps fully at AP
    m = view_metrics(CArm(0, 0, ISO), tgt, np.zeros((0, 3)), [behind])
    assert m["O_inter"] == pytest.approx(1.0)
    m = view_metrics(CArm(0, 40, ISO), tgt, np.zeros((0, 3)), [behind])   # cranial separates them
    assert m["O_inter"] == 0.0


def test_capsule_radius_uses_local_magnification():
    """A vessel 3 mm off-axis in 3D but very near the source is magnified enough to cover the target."""
    c = CArm(0, 0, ISO)                                     # AP: source posterior (+y), patient toward -y
    tgt = tube([-5, 0, 0], [5, 0, 0], r=0.1)
    near_src = c.source + np.array([0, -200.0, 0])           # 200 mm from the source: magnification 5
    mag_near = c.magnification(near_src[None])[0]
    assert mag_near == pytest.approx(5.0)
    mag_tgt = c.magnification(np.zeros((1, 3)))[0]
    dz = 2.6 / mag_near                                      # projected centre-line separation: 2.6 mm
    for r3d, expect in ((0.6, True), (0.4, False)):          # projected radius 3.0 mm vs 2.0 mm
        # same projected x-span as the target (scale x by the magnification ratio)
        k = mag_tgt / mag_near
        other = tube(near_src + [-5 * k, 0, dz], near_src + [5 * k, 0, dz], r=r3d)
        m = view_metrics(c, tgt, np.zeros((0, 3)), [other])
        assert (m["O_inter"] > 0.9) is expect, (r3d, m["O_inter"])


def test_bifurcation_exclusion_3mm():
    tgt = tube([0, 0, 0], [20, 0, 0])
    child = tube([20, 0, 0], [20, 30, 0])                  # leaves the target end node along the AP beam
    bif = np.array([[20, 0, 0]])
    m = view_metrics(CArm(0, 0, ISO), tgt, bif, [child])
    ev = m["evaluated"]
    P = tgt[:, :3]
    assert np.all(np.linalg.norm(P[~ev] - bif[0], axis=1) <= BIF_EXCLUSION_MM)
    assert not m["inter_mask"][~ev].any()
    # child projects onto the target only near x=20 at AP (end-on), which is excluded
    assert m["O_inter"] == 0.0


def test_self_overlap_only_beyond_10mm_arc():
    # a U-turn: out along +x, back along +x offset posterior (behind itself at AP)
    out = tube([0, 0, 0], [20, 0, 0])
    turn = tube([20, 0, 0], [20, 10, 0])[1:]
    back = tube([20, 10, 0], [0, 10, 0])[1:]
    tgt = np.vstack([out, turn, back])
    m = view_metrics(CArm(0, 0, ISO), tgt, np.zeros((0, 3)), [])
    assert m["O_self"] > 0.6                               # the two long legs hide each other
    # a straight vessel never self-overlaps (neighbours within 10 mm are ignored)
    m2 = view_metrics(CArm(0, 0, ISO), tube([0, 0, 0], [40, 0, 0]), np.zeros((0, 3)), [])
    assert m2["O_self"] == 0.0
    assert SELF_ARC_MM == 10.0


def test_angle_maps_grid_and_symmetry():
    tgt = tube([-10, 0, 0], [10, 0, 0])
    maps = angle_maps(ISO, tgt, np.zeros((0, 3)), [], step=10)
    assert 0 in list(maps["alpha"]) and 0 in list(maps["beta"]), "AP / zero tilt must be on the grid"
    assert maps["F"].shape == (len(maps["beta"]), len(maps["alpha"]))
    assert maps["alpha"][0] == -90 and maps["alpha"][-1] == 90 and maps["beta"][0] == -45 and maps["beta"][-1] == 45
    # an x-axis vessel is seen end-on at LAO 90 and RAO 90, fully at AP
    j0 = list(maps["beta"]).index(0)
    assert maps["F"][j0, 0] > 0.99 and maps["F"][j0, -1] > 0.99 and maps["F"][j0, 9] < 1e-3


# ---------- guard: metrics never read rendered pixels ----------

FORBIDDEN_PY = {"PIL", "matplotlib", "imageio", "cv2", "skimage.io"}
FORBIDDEN_NAMES = {"thickness_image", "angio_intensity", "imread", "readPixels", "readRenderTargetPixels"}


def test_python_metrics_are_purely_geometric():
    src = Path(__file__).resolve().parents[1] / "preprocess" / "cpt" / "metrics.py"
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in FORBIDDEN_PY, a.name
        if isinstance(node, ast.ImportFrom):
            assert node.module not in ("render", "cpt.render", "figures", "cpt.figures") and \
                (node.module or "").split(".")[0] not in FORBIDDEN_PY, node.module
            assert not (node.level and node.module in ("render", "figures")), node.module
        if isinstance(node, ast.Name):
            assert node.id not in FORBIDDEN_NAMES, node.id
