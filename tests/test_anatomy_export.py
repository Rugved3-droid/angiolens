"""Z-Anatomy export (CONVENTIONS section 10): atlas radii and great vessels (D46), effective ostia (D46), catheter access
routes (D47), welded skin (D48). Skipped when the git-ignored export is absent."""
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
ANAT = ROOT / "assets" / "anatomy"
MAN = ANAT / "manifest.json"
pytestmark = pytest.mark.skipif(not MAN.exists(), reason="Z-Anatomy export not present (git-ignored assets)")


def _scene(name):
    import trimesh
    sc = trimesh.load(ANAT / name, process=False)
    out = {}
    for node in sc.graph.nodes_geometry:
        T, g = sc.graph[node]
        assert np.allclose(T, np.eye(4)), node
        out[node] = sc.geometry[g]
    return out


def _closed(mesh):
    """Watertight after merging coincident vertices (glTF splits vertices at normal seams)."""
    import trimesh
    m = trimesh.Trimesh(mesh.vertices, mesh.faces, process=False)
    m.merge_vertices(digits_vertex=4)
    _, c = np.unique(np.sort(m.edges, 1), axis=0, return_counts=True)
    return bool(np.all(c == 2)), m


@pytest.fixture(scope="module")
def man():
    return json.loads(MAN.read_text())


@pytest.fixture(scope="module")
def heart():
    return _scene("z_anatomy_heart.glb")


def test_main_export_keeps_atlas_radii(man):
    cal = man["calibre"]["atlas"]
    assert cal["status"].startswith("ATLAS")
    sp = cal["splines"]
    assert len(sp) == 1 + 6 + 6 + 14                       # LM stem + split LAD/LCx/RCA branches
    checked = 0
    for s in sp:
        for a, b in zip(s["authored_diameter_mm_start_end"], s["measured_diameter_mm_start_end"]):
            if a is not None and b is not None:
                assert b == pytest.approx(a, rel=0.25, abs=0.25), s
                checked += 1
    assert checked >= 40
    by = {s["node"]: s for s in sp}
    lm = by["Left coronary artery"]["measured_diameter_mm_start_end"][0]
    rca = by["RCA_branch_01"]["measured_diameter_mm_start_end"]
    assert 3.4 <= lm <= 4.4 and 3.2 <= rca[0] <= 4.4 and rca[1] <= 1.6     # atlas: LM ~4.0, RCA ~4.0 -> 0.9


def test_great_vessels_present_closed_and_root_not_narrowed(man, heart):
    gv = man["great_vessels"]
    assert gv["missing"] == []
    assert "Inferior vena cava (thoracic part)" in gv["requested"]
    for n in gv["requested"]:
        assert n in heart, n
        if n != "Pulmonary trunk":                         # tubes have closed ends (fill caps); the trunk is an open atlas mesh
            assert _closed(heart[n])[0], f"{n} is not closed"
    # the aortic root keeps the atlas's ~30 mm: it is NOT narrowed
    _, aa = _closed(heart["Ascending aorta"])
    probe = json.loads((ANAT / "inspect" / "great_vessels_probe.json").read_text())
    cl = np.array(probe["curves"]["Ascending aorta"]["splines"][0]["centreline"])
    p0, t = cl[3], cl[4] - cl[2]
    t /= np.linalg.norm(t)
    r = aa.vertices - p0
    ring = r[np.abs(r @ t) < 1.5]
    d = np.linalg.norm(ring - np.outer(ring @ t, t), axis=1)
    assert 27.0 <= 2 * np.median(d) <= 32.0
    pt = gv["pulmonary_trunk_refinement"]
    assert max(pt["max_deviation_new_to_original_mm"], pt["max_deviation_original_to_new_mm"]) <= 1.0


def test_effective_ostia_on_wall_none_floating(man, heart):
    """Independent of Blender: ray parity (numpy) on the exported, capped ascending aorta."""
    from cpt.weld import _crossings
    _, aa = _closed(heart["Ascending aorta"])
    V, F = np.asarray(aa.vertices, float), np.asarray(aa.faces)
    v0, e1, e2 = V[F[:, 0]], V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]
    dirs = np.array([[0.5773, 0.5778, 0.5769], [-0.61, 0.33, 0.72], [0.27, -0.81, 0.52]])
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)

    def inside(p):
        return sum(_crossings(np.asarray(p, float), d, v0, e1, e2) % 2 for d in dirs) >= 2

    assert set(man["effective_ostia"]) == {"LM", "RCA"}
    for k, o in man["effective_ostia"].items():
        assert o["floating"] is False and o["proximal_end_inside_wall"], k
        assert inside(o["proximal_end_LPS"]), f"{k}: proximal end must be inside the aortic wall (no floating ostium)"
        assert 0.5 <= o["proximal_end_depth_below_wall_mm"] <= 4.5, k        # buried up to 4.5 mm is acceptable (D46)
        c, t = np.array(o["effective_ostium_LPS"]), np.array(o["vessel_direction_LPS"])
        assert inside(c - 0.3 * t) and not inside(c + 0.3 * t), f"{k}: the crossing is not on the wall"


def test_access_routes_continuous_and_bifurcation(man):
    ar = man["access_routes"]
    assert ar["missing"] == []
    routes = _scene("z_anatomy_access_routes.glb")
    assert set(ar["requested"]) <= set(routes)
    for n in ar["requested"]:
        assert _closed(routes[n])[0], f"{n} is not closed"
    for g in ar["continuity"]:
        assert g["gap_to_parent_centreline_mm"] <= 0.5 and g["gap_to_parent_distal_end_mm"] <= 0.5, g
    b = ar["bifurcation"]
    end = np.array(b["abdominal_aorta_distal_end_LPS"])
    for s in b["common_iliac_starts_LPS"].values():
        assert np.linalg.norm(np.array(s) - end) <= 0.5
    l3, l4 = b["vertebra_z_range_LPS"]["Vertebra L3"], b["vertebra_z_range_LPS"]["Vertebra L4"]
    assert l4[0] <= end[2] <= l3[1], "aortic bifurcation expected at the L3-L4 level"


def test_skin_is_one_welded_surface_facing_out():
    from cpt.glb import read_glb
    g = read_glb(ANAT / "z_anatomy_skin.glb")
    V, F, N = g["POSITION"].astype(float), g["indices"].astype(np.int64), g["NORMAL"].astype(float)
    assert len(g["extras"]["region_names"]) == 240
    for k in ("_ARM", "_LEG", "_REGION"):
        assert k in g
    assert g["_ARM"].min() >= 0 and g["_ARM"].max() == 1 and g["_LEG"].max() == 1
    w = g["extras"]["weld"]
    assert w["orientation"]["inconsistent_shared_edges_after"] == 0
    # residual cracks (< snap tolerance) are allowed only as a small remainder (they sit in the folds of the auricles)
    assert w["result"]["rim_vertices_with_residual_gap_over_0.05mm"] <= 100 and w["result"]["max_residual_seam_gap_mm"] < 4.0
    assert w["snap"]["max_displacement_mm"] <= w["snap"]["snap_tol_mm"]
    _, cnt = np.unique(np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1), axis=0, return_counts=True)
    # one sheet, no overlapping shells: edges with > 2 faces only where the atlas's own auricle meshes are non-manifold (~25)
    assert np.sum(cnt > 2) <= 40, "overlapping sheets: too many edges shared by more than two faces"
    assert np.mean(cnt == 1) < 0.02, "open edges: only holes and T-junction seams"
    c = V[F].mean(1)
    trunk = g["_ARM"][F].max(1) == 0                     # the hanging arm's inner surface faces the flank (legitimately -x)
    for sel, axis, sign in [((np.abs(c[:, 0]) < 40) & (c[:, 2] > 1200) & (c[:, 2] < 1320) & (c[:, 1] < -60), 1, -1),   # sternum
                            ((np.abs(c[:, 0]) < 40) & (c[:, 2] > 1200) & (c[:, 2] < 1320) & (c[:, 1] > 60), 1, +1),    # spine
                            (trunk & (c[:, 0] > 120) & (c[:, 2] > 1050) & (c[:, 2] < 1150), 0, +1)]:                  # left flank
        f = np.flatnonzero(sel)
        assert len(f) > 50 and np.mean(sign * N[F[f]].mean(1)[:, axis] > 0) > 0.97
