"""Display aorta and vessel-end fade (D62): the 1 mm rule, the re-measured ostia, catheter clearance on the smoothed wall.
Skipped without the git-ignored build (build_aorta_display.py, build_vessel_ends.py)."""
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "public" / "anatomy"
A = ROOT / "assets" / "anatomy"
pytestmark = pytest.mark.skipif(not (A / "aorta_display.json").exists(), reason="build_aorta_display.py output not present")


@pytest.fixture(scope="module")
def rep():
    return json.loads((A / "aorta_display.json").read_text())


def test_display_surface_within_1mm_both_ways(rep):
    d = rep["deviation"]
    # sample-based measurement; the rule is 1 mm (D46 precedent), the per-vertex clamp is 0.95 mm
    assert d["V_to_original_max_mm"] <= 1.0
    assert d["aorta_to_displayed_max_mm"] <= 1.0


def test_one_seamless_aorta(rep):
    assert rep["union_bodies"] == 1
    assert rep["segments"] == ["Ascending aorta", "Aortic arch", "Thoracic aorta", "Abdominal aorta"]


def test_ostia_remeasured_on_the_smoothed_wall_and_barely_moved():
    man = json.loads((A / "manifest.json").read_text())
    for key in ("LM", "RCA"):
        eo = man["effective_ostia"][key]
        assert "smoothed display aorta" in eo["measured_on"]
        assert eo["shift_from_atlas_wall_mm"] < 1.0
        orig = np.array(eo["atlas_wall_original"]["effective_ostium_LPS"])
        assert np.linalg.norm(np.array(eo["effective_ostium_LPS"]) - orig) < 1.0


def test_catheters_clear_the_smoothed_wall_and_engage(rep):
    for cath, c in rep["catheter_clearance_smoothed_wall"].items():
        assert c["min_clearance_to_smoothed_wall_mm"] >= 0.0, cath
        assert c["tip_inside_coronary_lumen"], cath


def test_app_stub_cut_matches_the_manifest_ostia():
    app = json.loads((WEB / "aorta_display.json").read_text())["stub_cut"]
    man = json.loads((A / "manifest.json").read_text())["effective_ostia"]
    for tree, key in (("left", "LM"), ("right", "RCA")):
        assert np.allclose(app[tree]["origin_LPS"], man[key]["effective_ostium_LPS"], atol=1e-3)
        assert app[tree]["coronary_drawn_from_mm"] < 0           # the drawn coronary starts INSIDE the wall-coloured stub


@pytest.mark.skipif(not (WEB / "vessel_ends.json").exists(), reason="build_vessel_ends.py output not present")
def test_vessel_ends_fade_only_cut_ends():
    ends = json.loads((WEB / "vessel_ends.json").read_text())
    free = ends["free_ends"]
    for n in ("Brachiocephalic trunk", "Left common carotid artery", "Left subclavian artery", "Left pulmonary artery",
              "Right pulmonary artery", "Abdominal aorta"):
        assert len(free.get(n, [])) == 1, n                      # one cut end each; the other end joins a structure
    assert "Ascending aorta" not in free                         # the root sits on the LV: never faded
    assert len(free["Superior vena cava"]) == 2                  # both cava ends: the root and slice views hide the right atrium
    assert len(free["Inferior vena cava (thoracic part)"]) == 2
