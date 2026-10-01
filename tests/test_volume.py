"""NRRD -> LPS loading rules (CONVENTIONS.md, section 'Patient frame')."""
import nrrd
import numpy as np
import pytest

from cpt.volume import assert_same_grid, load_nrrd_lps, translated

DIRS = np.array([[0.5, 0, 0], [0, 0.5, 0], [0, 0, 1.0]])
ORIGIN = np.array([-10.0, -20.0, -30.0])


def write(tmp_path, space, dirs=DIRS, origin=ORIGIN, name="v.nrrd"):
    data = np.zeros((4, 5, 6), np.int16)
    data[3, 1, 2] = 1
    hdr = {"space directions": dirs, "space origin": origin}
    if space is not None:
        hdr["space"] = space
    p = tmp_path / name
    nrrd.write(str(p), data, hdr, index_order="F")
    return p


def test_lps_header_identity(tmp_path):
    v = load_nrrd_lps(write(tmp_path, "left-posterior-superior"))
    np.testing.assert_allclose(v.index_to_lps([3, 1, 2]), [[-8.5, -19.5, -28.0]])
    assert v.data[3, 1, 2] == 1  # index order matches header axes


def test_ras_header_converted(tmp_path):
    v = load_nrrd_lps(write(tmp_path, "right-anterior-superior"))
    # RAS point (-8.5, -19.5, -28) is LPS (8.5, 19.5, -28)
    np.testing.assert_allclose(v.index_to_lps([3, 1, 2]), [[8.5, 19.5, -28.0]])
    assert np.linalg.det(v.affine[:3, :3]) > 0  # pure x/y sign flip of a diagonal grid


def test_oblique_directions_respected(tmp_path):
    c, s = np.cos(0.3), np.sin(0.3)
    dirs = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1.0]])
    v = load_nrrd_lps(write(tmp_path, "LPS", dirs=dirs))
    np.testing.assert_allclose(v.index_to_lps([1, 0, 0]) - v.index_to_lps([0, 0, 0]), [[c, s, 0]])


@pytest.mark.parametrize("space", [None, "scanner-xyz", "left-anterior-superior"])
def test_unknown_space_rejected(tmp_path, space):
    with pytest.raises((ValueError, KeyError)):
        load_nrrd_lps(write(tmp_path, space))


def test_roundtrip_index(tmp_path):
    v = load_nrrd_lps(write(tmp_path, "LPS"))
    ijk = np.array([[1.5, 2.25, 3.0]])
    np.testing.assert_allclose(v.lps_to_index(v.index_to_lps(ijk)), ijk)


def test_recenter_is_translation_only(tmp_path):
    v = load_nrrd_lps(write(tmp_path, "LPS"))
    t = translated(v, [5, -6, 7])
    np.testing.assert_allclose(t.affine[:3, :3], v.affine[:3, :3])
    np.testing.assert_allclose(t.index_to_lps([3, 1, 2]), v.index_to_lps([3, 1, 2]) - [5, -6, 7])


def test_grid_mismatch_detected(tmp_path):
    a = load_nrrd_lps(write(tmp_path, "LPS", name="a.nrrd"))
    b = load_nrrd_lps(write(tmp_path, "LPS", origin=ORIGIN + 1, name="b.nrrd"))
    with pytest.raises(ValueError):
        assert_same_grid(a, b)
