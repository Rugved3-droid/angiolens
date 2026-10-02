"""Exact mesh path-length renderer (cpt/meshrender.py) against analytic chords, and its raster orientation."""
import numpy as np
import trimesh

from cpt.geometry import CArm
from cpt.meshrender import mesh_thickness_image
from cpt.render import DetectorGrid


def analytic_sphere_chord(carm, grid, c, R):
    x, y = grid.pixel_centers()
    q = carm.screen_to_lps(np.stack([x.ravel(), y.ravel()], 1))
    d = q - carm.source
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    w = c - carm.source
    b = d @ w
    dist2 = (w @ w) - b ** 2
    return (2 * np.sqrt(np.clip(R ** 2 - dist2, 0, None))).reshape(grid.n, grid.n)


def test_sphere_matches_analytic_chord_at_oblique_view():
    c, R = np.array([10.0, -5.0, 3.0]), 20.0
    s = trimesh.creation.icosphere(subdivisions=5, radius=R)
    carm = CArm(-30, -25, np.zeros(3))
    grid = DetectorGrid(size_mm=120, n=120)
    th, st = mesh_thickness_image(carm, s.vertices + c, s.faces, grid)
    ref = analytic_sphere_chord(carm, grid, c, R)
    inner = ref > 2.0                                  # away from the rim, where the polygonal sphere and a sphere differ most
    assert st["unpaired_pixels"] <= 4 and st["negative_pixels"] == 0
    assert np.abs(th - ref)[inner].max() < 0.25
    assert abs(th.max() - 2 * R) < 0.1


def test_inward_winding_gives_negative_path():
    s = trimesh.creation.icosphere(subdivisions=3, radius=10)
    carm = CArm(0, 0, np.zeros(3))
    grid = DetectorGrid(size_mm=60, n=60)
    th, _ = mesh_thickness_image(carm, s.vertices, s.faces[:, ::-1], grid)
    assert th.min() < -19


def test_patient_left_renders_right_and_superior_top_at_ap():
    """Raster orientation identical to the voxel renderer: AP, +x (patient left) right, +z (superior) top."""
    carm = CArm(0, 0, np.zeros(3))
    grid = DetectorGrid(size_mm=100, n=100)
    left = trimesh.creation.icosphere(3, 5.0)
    th, _ = mesh_thickness_image(carm, left.vertices + [25, 0, 0], left.faces, grid)
    r, cidx = np.unravel_index(np.argmax(th), th.shape)
    assert cidx > grid.n / 2 + 10 and abs(r - grid.n / 2) < 3
    th, _ = mesh_thickness_image(carm, left.vertices + [0, 0, 25], left.faces, grid)
    r, cidx = np.unravel_index(np.argmax(th), th.shape)
    assert r < grid.n / 2 - 10 and abs(cidx - grid.n / 2) < 3
