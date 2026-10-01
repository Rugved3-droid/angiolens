"""Image raster rules (CONVENTIONS.md 'Image raster'): +u -> right columns, +v -> top rows."""
import numpy as np
import pytest

from cpt.geometry import CArm
from cpt.render import DetectorGrid, thickness_image
from cpt.synthetic import capsule_mask

ISO = np.array([5.0, -10.0, -120.0])
GRID = DetectorGrid(size_mm=200, n=200)


def blob_centroid(alpha, beta, offset, r=4.0):
    p = ISO + np.asarray(offset, float)
    img = thickness_image(CArm(alpha, beta, ISO), capsule_mask([(p, p, r)]), GRID)
    rows, cols = np.indices(img.shape)
    w = img / img.sum()
    return (rows * w).sum(), (cols * w).sum(), img


def test_ap_patient_left_renders_right():
    row, col, _ = blob_centroid(0, 0, [40, 0, 0])
    assert col > GRID.n / 2 + 10 and abs(row - (GRID.n / 2 - 0.5)) < 1


def test_ap_superior_renders_top():
    row, col, _ = blob_centroid(0, 0, [0, 0, 40])
    assert row < GRID.n / 2 - 10


@pytest.mark.parametrize("beta", [-30, 0, 30])
def test_superior_renders_top_cran_caud(beta):
    row, _, _ = blob_centroid(-30, beta, [0, 0, 40])
    assert row < GRID.n / 2 - 10


def test_rao30_posterior_renders_left():
    _, col, _ = blob_centroid(-30, 0, [0, 60, 0])
    assert col < GRID.n / 2 - 10


def test_lao45_posterior_renders_right():
    _, col, _ = blob_centroid(45, 0, [0, 60, 0])
    assert col > GRID.n / 2 + 10


def test_render_matches_point_projection():
    off = np.array([25.0, -15.0, 30.0])
    c = CArm(35, -20, ISO)
    row, col, _ = blob_centroid(35, -20, off)
    expect = GRID.screen_to_pixel(c.project(ISO + off))[0]
    assert np.hypot(row - expect[0], col - expect[1]) < 0.5


def test_sphere_thickness_on_central_ray():
    _, _, img = blob_centroid(0, 0, [0, 0, 0], r=5.0)
    assert img.max() == pytest.approx(10.0, abs=0.6)   # 2r, voxelised at 0.5 mm


def test_pixel_mapping_roundtrip():
    x, y = GRID.pixel_centers()
    rc = GRID.screen_to_pixel(np.stack([x.ravel(), y.ravel()], 1))
    rows, cols = np.indices(x.shape)
    np.testing.assert_allclose(rc[:, 0], rows.ravel(), atol=1e-9)
    np.testing.assert_allclose(rc[:, 1], cols.ravel(), atol=1e-9)
