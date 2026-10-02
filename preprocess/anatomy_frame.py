"""Canonical LPS-oriented atlas frame for Z-Anatomy, derived EMPIRICALLY from named landmarks.

This is NOT registration to any patient. It only puts the whole atlas into the projection engine's axis convention
(+X patient left, +Y posterior, +Z superior, millimetres) with ONE rigid rotation and ONE uniform unit scale.
No structure is ever recentred, rotated or scaled on its own.

    python preprocess/anatomy_frame.py assets/anatomy/inspect/hierarchy.json  -> assets/anatomy/frame.json

Landmarks (world-space centres of the EVALUATED geometry, from dump_hierarchy.py):
  LEFT      = mean over bilateral pairs of (centre(X.l) - centre(X.r)): femur, humerus, kidney, superior lung lobe
              (the ".l"/".r" and "left"/"right" in the names define anatomical left; pairs must agree)
  POSTERIOR = centre(thoracic vertebrae T4-T8) - centre(body of sternum)   (same level)
  SUPERIOR  = centre(skull: frontal, occipital, parietals) - centre(feet: calcanei, tali)
Gram-Schmidt from SUPERIOR (longest baseline), then POSTERIOR, then LEFT is *checked*, not constructed:
  the left/right landmarks must agree with L = P x S (handedness), otherwise the frame is rejected.
If the empirical axes are within SNAP_DEG of a signed axis permutation, the exact permutation is used.
Unit scale: the single factor that makes a Blender unit a millimetre (from the scene unit settings), then checked:
  heart long axis 90-140 mm and mid-thoracic vertebral body width 30-50 mm, else FAIL.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

SNAP_DEG = 3.0
PAIRS = [("Femur.l", "Femur.r"), ("Humerus.l", "Humerus.r"), ("Kidney.l", "Kidney.r"),
         ("Superior lobe of left lung", "Superior lobe of right lung")]
SKULL = ["Frontal bone", "Occipital bone", "Parietal bone.l", "Parietal bone.r"]
FEET = ["Calcaneus.l", "Calcaneus.r", "Talus.l", "Talus.r"]
STERNUM = ["Body of sternum"]
MID_T = [f"Vertebra T{i}" for i in range(4, 9)]
HEART = ["Left ventricle", "Right ventricle", "Left atrium", "Right atrium"]


def centres(H):
    c = {}
    for o in H["objects"]:
        g = o.get("evaluated_geometry") or {}
        bb = g.get("bbox_world")
        if g.get("triangles") and bb and bb[0] is not None:
            c[o["name"]] = (np.array(bb[0]) + np.array(bb[1])) / 2, np.array(bb[0]), np.array(bb[1])
    return c


def unit(v):
    return v / np.linalg.norm(v)


def angle(a, b):
    return float(np.degrees(np.arccos(np.clip(np.dot(unit(a), unit(b)), -1, 1))))


def derive(H, vertices_of=None):
    C = centres(H)
    need = sum(PAIRS, ()) + tuple(SKULL + FEET + STERNUM + MID_T + HEART)
    missing = [n for n in need if n not in C]
    if missing:
        raise SystemExit(f"missing landmarks: {missing}")
    mean = lambda names: np.mean([C[n][0] for n in names], axis=0)
    pair_vecs = {a: C[a][0] - C[b][0] for a, b in PAIRS}
    left_emp = unit(np.mean([unit(v) for v in pair_vecs.values()], axis=0))
    pair_spread = max(angle(v, left_emp) for v in pair_vecs.values())
    sup_emp = unit(mean(SKULL) - mean(FEET))
    post_raw = mean(MID_T) - mean(STERNUM)
    # Gram-Schmidt: S, then P orthogonal to S; L is CHECKED against P x S
    S = sup_emp
    P = unit(post_raw - np.dot(post_raw, S) * S)
    L = np.cross(P, S)
    handed_ok = np.dot(L, left_emp) > 0.9
    R = np.stack([L, P, S])                               # rows: LPS axes expressed in source coordinates
    # snap to an exact signed permutation if close
    snapped = np.zeros((3, 3))
    for i in range(3):
        j = int(np.argmax(np.abs(R[i])))
        snapped[i, j] = np.sign(R[i, j])
    snap_dev = max(angle(R[i], snapped[i]) for i in range(3))
    is_perm = abs(abs(np.linalg.det(snapped)) - 1) < 1e-9 and len({int(np.argmax(np.abs(r))) for r in snapped}) == 3
    use = snapped if (is_perm and snap_dev <= SNAP_DEG) else R
    # unit scale from the scene settings: 1 Blender unit = scale_length metres
    mm_per_unit = 1000.0 * float(H.get("scale_length", 1.0))
    # scale checks
    heart_pts = np.vstack([np.stack([C[n][1], C[n][2]]) for n in HEART])
    heart_bbox_extent_mm = (heart_pts.max(0) - heart_pts.min(0)) * mm_per_unit
    report = {
        "source_units": {"unit_system": H.get("unit_system"), "scale_length": H.get("scale_length"),
                         "length_unit_display": H.get("length_unit"), "mm_per_blender_unit": mm_per_unit},
        "empirical_axes_in_source": {"left": left_emp.round(5).tolist(), "superior": sup_emp.round(5).tolist(),
                                     "posterior_raw": unit(post_raw).round(5).tolist()},
        "left_pairs_max_spread_deg": round(pair_spread, 2),
        "left_from_pairs_vs_PxS_deg": round(angle(left_emp, L), 2),
        "handedness_ok": bool(handed_ok),
        "snap_deviation_deg": round(snap_dev, 2), "snapped_to_permutation": bool(use is snapped),
        "rotation_rows_LPS_in_source": use.round(6).tolist(),
        "matrix_source_to_LPS_mm": (use * mm_per_unit).round(6).tolist(),
        "det_rotation": round(float(np.linalg.det(use)), 6),
        "heart_bbox_extent_mm_source_axes": heart_bbox_extent_mm.round(1).tolist(),
    }
    return report, use, mm_per_unit, C


def main():
    hj = Path(sys.argv[1])
    H = json.loads(hj.read_text())
    rep, R, s, C = derive(H)
    if not rep["handedness_ok"]:
        raise SystemExit("FRAME REJECTED: named left/right structures disagree with posterior x superior (mirrored source or labels)")
    if rep["left_pairs_max_spread_deg"] > 25:
        raise SystemExit(f"FRAME REJECTED: bilateral pairs disagree by {rep['left_pairs_max_spread_deg']} deg")
    out = hj.parent.parent / "frame.json"
    out.write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
