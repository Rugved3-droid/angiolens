"""Capping open tubes for the X-ray (cpt/closemesh.py, D49): holes closed, nothing moved, outward winding kept."""
import numpy as np
import trimesh

from cpt.closemesh import cap_holes, merge_close, signed_volume, volume_centroid


def open_tube(r=2.0, h=20.0, n=12):
    m = trimesh.creation.cylinder(radius=r, height=h, sections=n)
    keep = np.abs(m.face_normals[:, 2]) < 0.5           # drop both end caps: an open tube, outward winding
    return np.asarray(m.vertices), np.asarray(m.faces)[keep]


def test_open_tube_is_capped_closed_and_outward():
    V, F = open_tube()
    V2, F2, st = cap_holes(*merge_close(V, F))
    assert st["holes_capped"] == 2 and st["open_edges_after"] == 0 and st["nonmanifold_edges_after"] == 0
    assert np.allclose(V2[: len(merge_close(V, F)[0])], merge_close(V, F)[0]), "existing vertices must not move"
    vol = signed_volume(V2, F2)
    assert vol > 0 and abs(vol - np.pi * 4 * 20 * np.sin(2 * np.pi / 12) * 12 / (2 * np.pi)) < 1.0   # 12-gon prism volume


def test_volume_centroid_of_offset_tube():
    V, F = open_tube()
    V2, F2, _ = cap_holes(*merge_close(V + [5.0, -3.0, 7.0], F))
    c, vol = volume_centroid(V2, F2)
    assert np.allclose(c, [5.0, -3.0, 7.0], atol=1e-6) and vol > 0
