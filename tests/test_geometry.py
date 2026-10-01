"""One test (or more) per rule in CONVENTIONS.md, section 'C-arm geometry'."""
import numpy as np
import pytest

from cpt.geometry import CArm, detector_direction, foreshortening, screen_axes, view_label

ISO = np.array([12.0, -40.0, -150.0])  # deliberately not the origin
# Synthetic anatomy relative to the heart centroid (= isocenter here). The spine is
# posterior and, because the heart sits left of midline, slightly to the patient's right.
SPINE_MIDLINE = ISO + np.array([0.0, 90.0, 0.0])
SPINE_REALISTIC = ISO + np.array([-25.0, 90.0, 0.0])


def screen_x(carm, p):
    return carm.project(p)[0, 0]


# --- AP ---------------------------------------------------------------------------------

def test_ap_detector_is_anterior():
    np.testing.assert_allclose(detector_direction(0, 0), [0, -1, 0], atol=1e-12)


def test_ap_screen_right_is_patient_left():
    u, v = screen_axes(detector_direction(0, 0))
    np.testing.assert_allclose(u, [1, 0, 0], atol=1e-12)
    np.testing.assert_allclose(v, [0, 0, 1], atol=1e-12)
    c = CArm(0, 0, ISO)
    assert screen_x(c, ISO + [20, 0, 0]) > 0
    assert screen_x(c, ISO + [-20, 0, 0]) < 0


# --- Spine side -------------------------------------------------------------------------

@pytest.mark.parametrize("spine", [SPINE_MIDLINE, SPINE_REALISTIC])
def test_rao30_spine_projects_left_of_heart(spine):
    c = CArm(-30, 0, ISO)
    assert screen_x(c, spine) < screen_x(c, ISO)


@pytest.mark.parametrize("spine", [SPINE_MIDLINE, SPINE_REALISTIC])
def test_lao45_spine_projects_right_of_heart(spine):
    c = CArm(45, 0, ISO)
    assert screen_x(c, spine) > screen_x(c, ISO)


# --- Cranial / caudal keep superior up -------------------------------------------------

@pytest.mark.parametrize("alpha", range(-90, 91, 15))
@pytest.mark.parametrize("beta", range(-45, 46, 15))
def test_superior_points_stay_up(alpha, beta):
    rng = np.random.default_rng(0)
    c = CArm(alpha, beta, ISO)
    base = ISO + rng.uniform(-80, 80, size=(50, 3))
    up = base + [0, 0, 30.0]
    assert np.all(c.project(up)[:, 1] > c.project(base)[:, 1])
    _, v = c.axes
    assert v[2] > 0


# --- Alpha direction --------------------------------------------------------------------

@pytest.mark.parametrize("beta", [-45, 0, 30])
def test_increasing_alpha_moves_detector_to_patient_left(beta):
    xs = [CArm(a, beta, ISO).detector_center[0] for a in range(-90, 91, 5)]
    assert np.all(np.diff(xs) > 0)
    assert CArm(90, beta, ISO).detector_center[0] > ISO[0]


def test_beta_sign_moves_detector_cranial():
    assert detector_direction(0, 30)[2] > 0
    assert detector_direction(0, -30)[2] < 0


# --- Foreshortening ---------------------------------------------------------------------

def test_foreshortening_zero_on_central_ray():
    c = CArm(-30, -25, ISO)
    u, _ = c.axes
    seg = np.array([ISO - 0.5 * u, ISO + 0.5 * u])
    assert foreshortening(seg, c.source) == pytest.approx(0.0, abs=1e-12)


def test_foreshortening_zero_perpendicular_to_local_ray_off_axis():
    c = CArm(40, -30, ISO)
    mid = ISO + np.array([35.0, -20.0, 25.0])
    r = (mid - c.source) / np.linalg.norm(mid - c.source)
    t = np.cross(r, [0, 0, 1.0]); t /= np.linalg.norm(t)
    seg = np.array([mid - 0.5 * t, mid + 0.5 * t])
    assert foreshortening(seg, c.source) == pytest.approx(0.0, abs=1e-12)


def test_foreshortening_one_along_ray():
    c = CArm(45, 20, ISO)
    p = ISO + np.array([10.0, 5.0, -15.0])
    r = (p - c.source) / np.linalg.norm(p - c.source)
    seg = p + np.linspace(0, 20, 41)[:, None] * r
    assert foreshortening(seg, c.source) == pytest.approx(1.0, abs=1e-9)


def test_foreshortening_45_degrees():
    c = CArm(0, 0, ISO)
    u, _ = c.axes
    seg = np.array([ISO - 0.05 * (u + c.d), ISO + 0.05 * (u + c.d)])
    assert foreshortening(seg, c.source) == pytest.approx(1 - np.sqrt(0.5), abs=1e-9)


# --- Frame invariants -------------------------------------------------------------------

@pytest.mark.parametrize("alpha", range(-90, 91, 10))
@pytest.mark.parametrize("beta", range(-45, 46, 9))
def test_frame_orthonormal_right_handed(alpha, beta):
    d = detector_direction(alpha, beta)
    u, v = screen_axes(d)
    M = np.stack([u, v, d])
    np.testing.assert_allclose(M @ M.T, np.eye(3), atol=1e-12)
    np.testing.assert_allclose(np.cross(u, v), d, atol=1e-12)


def test_source_and_detector_positions():
    c = CArm(-30, 20, ISO)
    assert np.linalg.norm(c.source - c.iso) == pytest.approx(750.0)
    assert np.linalg.norm(c.detector_center - c.source) == pytest.approx(1000.0)
    np.testing.assert_allclose(c.project(ISO), [[0, 0]], atol=1e-9)
    assert c.magnification(ISO)[0] == pytest.approx(1000 / 750)


def test_screen_roundtrip():
    c = CArm(35, -20, ISO)
    xy = np.array([[12.5, -40.0], [-80.0, 3.0]])
    np.testing.assert_allclose(c.project(c.screen_to_lps(xy)), xy, atol=1e-9)


def test_isocenter_is_only_translation():
    p = ISO + np.array([[10.0, -20, 30], [-5, 7, 2]])
    a = CArm(25, -15, ISO).project(p)
    b = CArm(25, -15, ISO + 100).project(p + 100)
    np.testing.assert_allclose(a, b, atol=1e-9)


def test_out_of_range_angles_rejected():
    with pytest.raises(ValueError):
        CArm(91, 0, ISO)
    with pytest.raises(ValueError):
        CArm(0, -46, ISO)


@pytest.mark.parametrize("a,b,s", [(0, 0, "AP"), (-30, -20, "RAO 30 / CAUD 20"),
                                   (45, 0, "LAO 45"), (0, 30, "AP / CRAN 30")])
def test_view_label(a, b, s):
    assert view_label(a, b) == s
