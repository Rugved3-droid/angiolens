import numpy as np
import pytest

from cpt.centerline import STEP_MM, build_from_paths, resample


def line(a, b, n=200, r=1.0):
    t = np.linspace(0, 1, n)[:, None]
    p = np.asarray(a, float) + t * (np.asarray(b, float) - a)
    return np.c_[p, np.full(n, r)]


def test_resample_uniform_and_keeps_ends():
    p = line([0, 0, 0], [10, 0, 0], n=7)
    q = resample(p)
    steps = np.linalg.norm(np.diff(q[:, :3], axis=0), axis=1)
    assert np.allclose(steps, STEP_MM)
    np.testing.assert_allclose(q[[0, -1], :3], p[[0, -1], :3])


def test_y_tree_topology():
    trunk = line([0, 0, 0], [0, 0, -20])
    a = np.vstack([trunk, line([0, 0, -20], [15, 0, -35])[1:]])
    b = np.vstack([trunk, line([0, 0, -20], [-15, 0, -35])[1:]])
    g = build_from_paths([a, b], ["left", "left"])
    kinds = sorted(n["kind"] for n in g.nodes)
    assert kinds == ["bifurcation", "endpoint", "endpoint", "ostium"]
    assert len(g.edges) == 3
    bif = next(n for n in g.nodes if n["kind"] == "bifurcation")
    # the merge tolerance places the split within ~1 mm of the true bifurcation
    assert np.linalg.norm(bif["pos"] - [0, 0, -20]) < 1.5
    total = sum(np.linalg.norm(np.diff(e["samples"][:, :3], axis=0), axis=1).sum() for e in g.edges)
    expected = 20 + 2 * np.hypot(15, 15)
    assert total == pytest.approx(expected, abs=1.5)
    # graph is connected: every edge endpoint is a node, and the ostium has degree 1
    deg = np.bincount([x for e in g.edges for x in (e["a"], e["b"])], minlength=len(g.nodes))
    ost = next(n for n in g.nodes if n["kind"] == "ostium")
    assert deg[ost["id"]] == 1 and deg[bif["id"]] == 3


def test_trees_kept_separate():
    l = line([0, 0, 0], [10, 0, 0])
    r = line([0, 0, 0.5], [10, 0, 0.5])    # within merge tolerance but different tree
    g = build_from_paths([l, r], ["left", "right"])
    assert {n["tree"] for n in g.nodes if n["kind"] == "ostium"} == {"left", "right"}
    assert len(g.edges) == 2


def test_official_frame_assertion_stops_on_misaligned_points(tmp_path, monkeypatch):
    """The per-case check must raise (stop and report), never silently fall back or fit."""
    import cpt.centerline as C
    from cpt.synthetic import capsule_mask

    vol = capsule_mask([([0, 0, -100], [30, 0, -100], 2.0)], spacing=0.4)
    lumen = vol.data > 0.5
    pts_ok = np.c_[np.linspace(1, 29, 50), np.zeros(50), np.full(50, -100.0)]
    fake = {"points": None, "point_data": {"MaximumInscribedSphereRadius": np.full(50, 1.5)}, "lines": [np.arange(50)]}

    def run(points):
        fake["points"] = points - [2 * vol.affine[0, 3], 2 * vol.affine[1, 3], 0]   # file frame per D11
        monkeypatch.setattr(C, "read_vtp", lambda _: fake)
        return C.official_graph("x.vtp", vol, lumen, np.zeros_like(lumen))

    g, info = run(pts_ok)
    assert info["frame_check"]["frac_within_0p5mm"] == 1.0
    with pytest.raises(C.CenterlineFrameError):
        run(pts_ok + [0, 3.0, 0])          # 1 mm outside a 2 mm-radius tube
