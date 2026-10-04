"""Scene 5 data (D53): catheter routes, engaged JL4/JR4 shapes, contrast-fill distances. Skipped without the git-ignored build."""
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "public" / "anatomy"
A = ROOT / "assets" / "anatomy"
pytestmark = pytest.mark.skipif(not (WEB / "atlas_cath.json").exists(), reason="build_atlas_cath.py output not present")


@pytest.fixture(scope="module")
def data():
    return json.loads((WEB / "atlas_cath.json").read_text())


def test_shapes_end_in_the_effective_ostium_tangent_to_the_coronary(data):
    man = json.loads((A / "manifest.json").read_text())
    for cath, key in (("JL4", "LM"), ("JR4", "RCA")):
        sh = data["shapes"][cath]
        P = np.array(sh["polyline"])
        o = np.array(man["effective_ostia"][key]["effective_ostium_LPS"])         # the manifest's target, not a copy
        t = np.array(man["effective_ostia"][key]["vessel_direction_LPS"])
        t /= np.linalg.norm(t)
        assert np.linalg.norm(P[-1] - (o + 3.0 * t)) < 0.05, cath               # tip 3 mm inside, along the coronary
        d = P[-1] - P[-4]
        assert np.degrees(np.arccos(np.dot(d / np.linalg.norm(d), t))) < 5.0, cath
        assert min(np.linalg.norm(P - o, axis=1)) < 0.5                          # it passes through the ostium
        ck = data["checks"][cath]
        assert ck["min_clearance_to_aortic_wall_mm"] >= 0.0 and ck["samples_checked"] > 100, ck
        assert np.allclose(P[0], data["ascending_top_LPS"], atol=0.05)          # starts where the route ends
        assert len(sh["straight_polyline"]) == len(sh["polyline"])               # same sampling: the morph is defined


def test_routes_are_continuous_from_puncture_to_the_ascending_aorta(data):
    for name, r in data["routes"].items():
        P = np.array(r["polyline_to_ascending_top"])
        step = np.linalg.norm(np.diff(P, axis=0), axis=1)
        assert step.max() < 1.6, name                                            # resampled at ~1 mm, no jumps
        assert np.linalg.norm(P[-1] - np.array(data["ascending_top_LPS"])) < 0.05, name
        assert P[0][2] < P[-1][2] - 200, name                                    # starts well below (femoral) / beside (radial)


def test_fill_distance_grows_along_every_branch(data):
    buf = np.fromfile(WEB / "atlas_fill.bin", "<f4")
    idx = data["fill_index"]
    assert sum(e["count"] for e in idx.values()) == len(buf)
    for tree in ("left", "right"):
        s = buf[idx[f"xray_{tree}"]["offset"]: idx[f"xray_{tree}"]["offset"] + idx[f"xray_{tree}"]["count"]]
        assert s.min() < 0.0 < s.max(), tree                                   # the buried trunk is "before" the ostium
        assert s.max() == pytest.approx(data["trees"][tree]["max_distance_mm"], abs=1.0)
    probe = json.loads((A / "inspect" / "great_vessels_probe.json").read_text())
    from scipy.spatial import cKDTree
    import trimesh
    sc = trimesh.load(A / "z_anatomy_heart.glb", process=False)
    for node, obj, i in (("RCA_branch_01", "Right coronary artery", 0), ("LAD_branch_01", "Anterior interventricular artery", 0)):
        e = idx[f"node:{node}"]
        s = buf[e["offset"]: e["offset"] + e["count"]]
        V = np.asarray(sc.geometry[sc.graph[node][1]].vertices)
        C = np.array(probe["curves"][obj]["splines"][i]["centreline"])
        k = cKDTree(C).query(V)[1]
        # vertices further along the branch's own centreline must not be "earlier" in the fill
        order = np.argsort(k)
        assert np.all(np.diff(s[order]) >= -1e-3), node
