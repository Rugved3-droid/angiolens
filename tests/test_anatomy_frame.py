"""Canonical LPS atlas frame (CONVENTIONS.md section 10): handedness, landmark directions and scale."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "preprocess"))
from anatomy_frame import derive  # noqa: E402

# a synthetic body in LPS metres: (centre) per landmark
BODY = {
    "Femur.l": (0.09, 0.0, 0.50), "Femur.r": (-0.09, 0.0, 0.50), "Humerus.l": (0.17, 0.03, 1.20), "Humerus.r": (-0.17, 0.03, 1.20),
    "Kidney.l": (0.05, 0.06, 1.00), "Kidney.r": (-0.05, 0.06, 0.98),
    "Superior lobe of left lung": (0.08, 0.01, 1.28), "Superior lobe of right lung": (-0.08, 0.01, 1.28),
    "Frontal bone": (0.0, -0.06, 1.65), "Occipital bone": (0.0, 0.06, 1.62), "Parietal bone.l": (0.06, 0.0, 1.66), "Parietal bone.r": (-0.06, 0.0, 1.66),
    "Calcaneus.l": (0.10, 0.03, 0.03), "Calcaneus.r": (-0.10, 0.03, 0.03), "Talus.l": (0.10, 0.0, 0.07), "Talus.r": (-0.10, 0.0, 0.07),
    "Body of sternum": (0.0, -0.09, 1.22), **{f"Vertebra T{i}": (0.0, 0.05, 1.36 - 0.025 * i) for i in range(4, 9)},
    "Left ventricle": (0.03, -0.04, 1.18), "Right ventricle": (-0.01, -0.06, 1.18), "Left atrium": (0.01, 0.0, 1.24), "Right atrium": (-0.04, -0.02, 1.22),
}


def hierarchy(transform=np.eye(3), swap_lr=False):
    objs = []
    for n, c in BODY.items():
        if swap_lr and (n.endswith(".l") or n.endswith(".r") or "left lung" in n or "right lung" in n):
            n = n.replace(".l", ".X").replace(".r", ".l").replace(".X", ".r").replace("left", "TMP").replace("right", "left").replace("TMP", "right")
        p = transform @ np.array(c)
        h = 0.02
        objs.append({"name": n, "evaluated_geometry": {"triangles": 10, "bbox_world": [(p - h).tolist(), (p + h).tolist()]}})
    return {"objects": objs, "scale_length": 1.0, "unit_system": "METRIC", "length_unit": "CENTIMETERS"}


def test_source_already_lps_gives_identity_times_1000():
    rep, R, s, _ = derive(hierarchy())
    assert rep["handedness_ok"] and rep["snapped_to_permutation"]
    np.testing.assert_allclose(R, np.eye(3))
    assert s == 1000.0 and rep["det_rotation"] == 1.0


def test_y_up_source_is_recovered_by_one_rotation():
    # a glTF-style Y-up source: source = Rx(-90) applied to LPS (superior -> +Y, posterior -> -Z)
    T = np.array([[1, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])
    rep, R, s, _ = derive(hierarchy(T))
    assert rep["handedness_ok"]
    for name, c in BODY.items():                      # every landmark maps back to its LPS position
        np.testing.assert_allclose(R @ (T @ np.array(c)), np.array(c), atol=1e-9)
    assert np.linalg.det(R) == pytest.approx(1.0)


def test_mirrored_labels_are_rejected():
    rep, *_ = derive(hierarchy(swap_lr=True))
    assert not rep["handedness_ok"]


def test_mirrored_geometry_is_rejected():
    rep, *_ = derive(hierarchy(np.diag([-1.0, 1, 1])))   # x flipped, names unchanged: left structures now on -x
    assert not rep["handedness_ok"]


# ---------------- real export (skipped when the git-ignored assets are absent) ----------------
MAN = ROOT / "assets" / "anatomy" / "manifest.json"


@pytest.mark.skipif(not MAN.exists(), reason="Z-Anatomy export not present (git-ignored assets)")
def test_real_export_landmarks_and_scale():
    m = json.loads(MAN.read_text())
    C = {o["anatomical_name"]: np.array(o["center_LPS"]) for o in m["objects"]}
    ck = m["checks"]
    assert m["frame"]["det_rotation"] == 1.0 and m["frame"]["handedness_ok"]
    for a, b in (("Femur.l", "Femur.r"), ("Humerus.l", "Humerus.r")):
        assert C[a][0] > C[b][0] + 100, f"{a} must be patient-left (+x) of {b}"
    assert C["Vertebra T6"][1] > C["Body of sternum"][1] + 50, "vertebral bodies must be posterior (+y) to the sternum"
    assert C["Frontal bone"][2] > C["Calcaneus.l"][2] + 1200, "skull must be superior (+z) to the feet"
    assert ck["heart_long_axis_ok"], ck["heart_long_axis_mm"]
    assert ck["t6_body_width_ok"], ck["t6_vertebral_body_width_mm"]
    assert ck["apex_is_left_anterior_inferior"], ck["apex_minus_base_direction_LPS"]   # sanity only, not the definition
    for o in m["objects"]:                              # one shared transform: bbox_LPS == R*s*bbox_source (axis-aligned case)
        R = np.array(m["frame"]["matrix_source_to_LPS_mm"])
        lo, hi = np.array(o["bbox_source"])
        np.testing.assert_allclose(np.sort(np.stack([R @ lo, R @ hi]), 0), np.array(o["bbox_LPS"]), atol=0.05)
