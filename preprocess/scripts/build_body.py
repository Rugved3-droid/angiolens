"""Fit the CC0 MakeHuman base mesh around this patient's heart (APPROXIMATE, for context only).

    python preprocess/scripts/build_body.py --case Normal_12
Writes web/public/cases/<id>/body.glb (LPS mm, verbatim) and body_fit.json.

Source: assets_src/makehuman/base.obj, MakeHuman base mesh, explicitly CC0 (Sept 2020; header of the file).
Only the "body" group is used (helper/joint geometry dropped).

Axes (verified from the mesh's own joint helpers, not assumed): MakeHuman +X = character's LEFT
(joint-l-elbow x = +3.13), +Y = up (head), +Z = anterior (eyes at z +1.25 vs head centre +0.16); units dm.
Supine patient in LPS: x = X, y = -Z, z = Y (a proper rotation, det +1; no mirroring).

Fit (uniform scale + translation only; every number reported in body_fit.json):
  x: body midline -> CT midline (mean x of the sternum and vertebral-body bone regions)
  z: body "heart level" = mean clavicle-joint height - HEART_BELOW_CLAVICLE_MM -> CT heart centroid z
  y: body anterior skin at heart level -> CT anterior skin at heart level (first HU > -300 from the front)
  scale: 1.0 unless the CT vertebral bodies would stick out of the body's back; then the smallest scale
         that leaves BACK_MARGIN_MM of soft tissue behind them.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))

import numpy as np
import trimesh
from scipy import ndimage as ndi

from cpt.case import load_case
from cpt.glb import write_glb
from cpt.masks import bone_and_pool

HEART_BELOW_CLAVICLE_MM = 110.0
BACK_MARGIN_MM = 25.0
MH_TO_LPS = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # rows: x=X, y=-Z, z=Y


def read_obj(path):
    V, faces, groups, cur = [], [], {}, None
    for line in open(path, encoding="utf-8"):
        if line.startswith("v "):
            V.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("g "):
            cur = line.split(None, 1)[1].strip()
        elif line.startswith("f ") and cur:
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            groups.setdefault(cur, []).append(idx)
    return np.array(V), groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="Normal_12")
    ap.add_argument("--heart-centroid", type=float, nargs=3, default=None,
                    help="LPS mm; default = heart.glb centroid if present, else coronary lumen centroid")
    args = ap.parse_args()
    out = ROOT / "web" / "public" / "cases" / args.case
    V, groups = read_obj(ROOT / "assets_src" / "makehuman" / "base.obj")
    assert np.linalg.det(MH_TO_LPS) > 0
    jl = V[np.unique(np.concatenate(groups["joint-l-elbow"]))].mean(0)
    assert jl[0] > 0, "MakeHuman +X must be the character's left"

    tris = []
    for f in groups["body"]:
        tris += [[f[0], f[k], f[k + 1]] for k in range(1, len(f) - 1)]
    m = trimesh.Trimesh(V, np.array(tris), process=True)
    m.remove_unreferenced_vertices()
    P = (m.vertices * 100.0) @ MH_TO_LPS.T                      # dm -> mm, MakeHuman -> LPS
    clav = np.vstack([V[np.unique(np.concatenate(groups[g]))] for g in ("joint-l-clavicle", "joint-r-clavicle")]).mean(0)
    clav_z = (clav * 100.0 @ MH_TO_LPS.T)[2]

    case = load_case(args.case)
    ct = case.ct
    bone, _, rep = bone_and_pool(ct, case.lumen)
    lab, n = ndi.label(bone)
    sizes = ndi.sum(bone, lab, range(1, n + 1))
    big = np.argsort(-sizes)[:6] + 1
    bone_pts = ct.index_to_lps(np.argwhere(np.isin(lab, big)))
    mid_x = float(np.median(bone_pts[:, 0]))
    vert = bone_pts[bone_pts[:, 1] > 30]                       # posterior bone (vertebral bodies)
    if args.heart_centroid:
        heart_c = np.array(args.heart_centroid)
    elif (out / "heart.glb").exists():
        from cpt.glb import read_glb
        heart_c = read_glb(out / "heart.glb")["POSITION"].mean(0)
    else:
        heart_c = case.isocenter
    # CT anterior skin at heart level (x within 20 mm of midline): first voxel with HU > -300 from the front
    k = int(round(ct.lps_to_index([0, 0, heart_c[2]])[0, 2]))
    i0, i1 = [int(round(ct.lps_to_index([mid_x + d, 0, 0])[0, 0])) for d in (-20, 20)]
    col = ct.data[i0:i1, :, k] > -300
    first = [np.argmax(c) for c in col if c.any()]
    ct_skin_y = float(ct.index_to_lps([0, np.median(first), 0])[0, 1])

    def placed(scale):
        Q = P * scale
        heart_level_z = (clav_z - HEART_BELOW_CLAVICLE_MM) * scale
        band = np.abs(Q[:, 2] - heart_level_z) < 15
        front = Q[band & (np.abs(Q[:, 0]) < 30), 1].min()
        back = Q[band & (np.abs(Q[:, 0]) < 30), 1].max()
        t = np.array([mid_x, ct_skin_y - front, heart_c[2] - heart_level_z])
        return Q + t, back + t[1], t

    scale = 1.0
    vert_back = float(np.percentile(vert[:, 1], 99)) if len(vert) else -np.inf
    for s in np.arange(1.0, 1.6, 0.01):
        Q, back_y, t = placed(s)
        scale = s
        if back_y >= vert_back + BACK_MARGIN_MM:
            break
    Q, back_y, t = placed(scale)
    body = trimesh.Trimesh(Q, m.faces, process=False)
    body.fix_normals()
    write_glb(out / "body.glb", body.vertices, body.faces, body.vertex_normals, name="body",
              extras={"source": "MakeHuman base mesh (CC0, Sept 2020)", "approximate_fit": True})
    fit = {
        "approximate": True,
        "source": "MakeHuman base.obj 'body' group, CC0 (https://github.com/makehumancommunity/makehuman)",
        "axes": "x=X(left), y=-Z(anterior->-y), z=Y(up); verified from joint helpers; det +1",
        "scale": round(float(scale), 3),
        "height_mm": round(float(np.ptp(Q[:, 2])), 0),
        "translation_mm": np.round(t, 1).tolist(),
        "ct_midline_x": round(mid_x, 1),
        "ct_anterior_skin_y_at_heart_level": round(ct_skin_y, 1),
        "heart_centroid_lps": np.round(heart_c, 1).tolist(),
        "heart_level_rule": f"clavicle joints - {HEART_BELOW_CLAVICLE_MM} mm",
        "body_back_y_at_heart_level": round(float(back_y), 1),
        "ct_vertebral_posterior_y_p99": round(vert_back, 1),
        "soft_tissue_behind_vertebrae_mm": round(float(back_y - vert_back), 1),
        "faces": int(len(body.faces)),
    }
    (out / "body_fit.json").write_text(json.dumps(fit, indent=1))
    meta = json.loads((out / "case.json").read_text())
    for f in ("body.glb", "body_fit.json"):
        if f not in meta["files"]:
            meta["files"].insert(-1, f)
    meta["body_fit"] = fit
    (out / "case.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(fit, indent=1))


if __name__ == "__main__":
    main()
