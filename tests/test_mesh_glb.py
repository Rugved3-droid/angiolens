import numpy as np

from cpt.glb import read_glb, write_glb
from cpt.mesh import mask_to_mesh, mesh_report
from cpt.synthetic import capsule_mask


def test_glb_roundtrip_verbatim(tmp_path):
    v = np.array([[10.5, -20.25, -150.0], [11, -20, -150], [10, -19, -149]], np.float32)
    f = np.array([[0, 1, 2]])
    e = np.array([3, 3, 7], np.float32)
    write_glb(tmp_path / "t.glb", v, f, normals=np.tile([0, 0, 1.0], (3, 1)), edge_id=e)
    g = read_glb(tmp_path / "t.glb")
    np.testing.assert_array_equal(g["POSITION"], v)   # no axis conversion, bit-exact
    np.testing.assert_array_equal(g["indices"], f)
    np.testing.assert_array_equal(g["_EDGE_ID"], e)
    assert g["extras"]["frame"] == "LPS"


def test_mask_mesh_closed_outward_and_in_place():
    vol = capsule_mask([([0, 0, -100], [30, 0, -100], 3.0)], spacing=0.4)
    m = mesh_report_and_mesh(vol)
    assert m.is_watertight and m.is_winding_consistent and m.volume > 0
    # volume close to the analytic capsule, position unchanged (pure LPS, no recentering)
    expected = np.pi * 9 * 30 + 4 / 3 * np.pi * 27
    assert abs(m.volume - expected) / expected < 0.08
    np.testing.assert_allclose(m.bounds, [[-3, -3, -103], [33, 3, -97]], atol=0.5)


def mesh_report_and_mesh(vol):
    m = mask_to_mesh(vol, vol.data > 0.5, target_faces=4000)
    r = mesh_report(m)
    assert r["components"] == 1
    return m


def test_block_averaged_mesh_stays_in_place_and_closed():
    vol = capsule_mask([([0, 0, -100], [30, 0, -100], 3.0)], spacing=0.4)
    m = mask_to_mesh(vol, vol.data > 0.5, step=2)
    assert m.is_watertight and m.volume > 0
    np.testing.assert_allclose(m.bounds, [[-3, -3, -103], [33, 3, -97]], atol=0.8)
