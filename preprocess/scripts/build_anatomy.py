"""Heart, aorta and great-vessel meshes from TotalSegmentator masks of THIS patient (open 'total' task).

    python preprocess/scripts/build_anatomy.py --case Normal_12
Inputs:  data/derived/<id>/ts/seg/*.nii.gz (TotalSegmentator output on the RAS NIfTI copy of the CT)
Outputs: web/public/cases/<id>/heart.glb, aorta.glb, veins.glb (LPS mm, verbatim) + anatomy_report.json

Frame safety: every mask must come back on the CT's exact voxel grid (same shape; NIfTI affine == RAS
version of the NRRD affine); masks are then used by voxel index, so no resampling or transform is involved.

Epicardial check (assertion): signed distance from every expert coronary centerline sample to the heart surface
(+ outside, - inside). Coronaries run in epicardial fat on the surface, so most samples must lie within a few mm.
Proximal samples near the ostia sit on the aorta, so the distance to (heart OR aorta) is reported as well.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi

from cpt.case import load_case
from cpt.glb import write_glb
from cpt.mesh import mask_to_mesh, mesh_report

VEINS = ("superior_vena_cava", "inferior_vena_cava", "pulmonary_vein", "atrial_appendage_left", "brachiocephalic_trunk")
# atrial_appendage_left is part of the heart; brachiocephalic_trunk is arterial: both rendered with the "great vessels" layer
EPI_MEDIAN_MAX_MM = 4.0      # assertion: median |distance| of coronary samples to the heart-or-aorta surface
EPI_P90_MAX_MM = 8.0


def load_mask(seg_dir: Path, name: str, ct) -> np.ndarray | None:
    f = seg_dir / f"{name}.nii.gz"
    if not f.exists():
        return None
    img = nib.load(str(f))
    A_ras = np.diag([-1.0, -1.0, 1.0, 1.0]) @ ct.affine
    if img.shape != ct.data.shape or not np.allclose(img.affine, A_ras, atol=1e-3):
        raise RuntimeError(f"{name}: TotalSegmentator output is not on the CT grid (shape {img.shape}, affine\n{img.affine})")
    return np.asarray(img.dataobj) > 0


def signed_distance(mask: np.ndarray, spacing) -> np.ndarray:
    return ndi.distance_transform_edt(~mask, sampling=spacing) - ndi.distance_transform_edt(mask, sampling=spacing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="Normal_12")
    args = ap.parse_args()
    seg = ROOT / "data" / "derived" / args.case / "ts" / "seg"
    out = ROOT / "web" / "public" / "cases" / args.case
    c = load_case(args.case)
    sp = c.ct.spacing
    heart = load_mask(seg, "heart", c.ct)
    aorta = load_mask(seg, "aorta", c.ct)
    if heart is None:
        raise SystemExit("no heart mask: run TotalSegmentator first")
    veins = np.zeros_like(heart)
    present = []
    for v in VEINS:
        mk = load_mask(seg, v, c.ct)
        if mk is not None and mk.any():
            veins |= mk
            present.append(v)
    # keep the coronary lumen out of the heart/aorta meshes so the red vessels are never buried in them
    lumen_d = ndi.binary_dilation(c.lumen, iterations=1)
    meshes = {}
    # TotalSegmentator's 'total' model works at ~1.5 mm, so masks are blocky at that scale: smooth in mm, per axis
    mm = lambda s_mm: tuple(float(s_mm / x) for x in sp)
    for name, mk, smooth, target in (("heart", heart & ~lumen_d, mm(1.6), 160_000),
                                     ("aorta", aorta & ~lumen_d if aorta is not None else None, mm(1.3), 40_000),
                                     ("veins", veins & ~heart & ~lumen_d, mm(1.3), 60_000)):
        if mk is None or not mk.any():
            continue
        lab, n = ndi.label(mk)
        if n > 1:                                   # drop specks
            sizes = ndi.sum(mk, lab, range(1, n + 1))
            mk = np.isin(lab, 1 + np.flatnonzero(sizes >= 0.02 * sizes.max()))
        m = mask_to_mesh(c.ct, mk, smooth_sigma_vox=smooth, target_faces=target, taubin_iters=40)
        write_glb(out / f"{name}.glb", m.vertices, m.faces, m.vertex_normals, name=name,
                  extras={"source": "TotalSegmentator 'total' (open task) on this patient's CT"})
        meshes[name] = {**mesh_report(m), "voxels_ml": round(float(mk.sum() * np.prod(sp) / 1000), 1)}

    # ---- epicardial assertion ----
    cl = json.loads((out / "centerlines.json").read_text())
    pts = np.vstack([np.array(e["samples"])[:, :3] for e in cl["edges"]])
    tree = np.concatenate([[e["tree"]] * len(e["samples"]) for e in cl["edges"]])
    sd_heart = signed_distance(heart, sp)
    sd_ha = signed_distance(heart | (aorta if aorta is not None else False), sp)
    ijk = c.ct.lps_to_index(pts).T
    d_h = ndi.map_coordinates(sd_heart, ijk, order=1)
    d_ha = ndi.map_coordinates(sd_ha, ijk, order=1)

    # the same check against the RENDERED (smoothed) heart+aorta meshes: unsigned distance to a dense surface sampling
    from scipy.spatial import cKDTree
    import trimesh
    from cpt.glb import read_glb
    surf = []
    for nm in ("heart", "aorta"):
        if (out / f"{nm}.glb").exists():
            g = read_glb(out / f"{nm}.glb")
            surf.append(trimesh.Trimesh(g["POSITION"], g["indices"], process=False).sample(400_000))
    d_mesh = cKDTree(np.vstack(surf)).query(pts)[0] if surf else np.full(len(pts), np.nan)

    def stats(d):
        a = np.abs(d)
        return {"median_abs_mm": round(float(np.median(a)), 2), "p90_abs_mm": round(float(np.percentile(a, 90)), 2),
                "max_abs_mm": round(float(a.max()), 2), "frac_within_3mm": round(float((a <= 3).mean()), 3),
                "frac_within_5mm": round(float((a <= 5).mean()), 3), "frac_inside_heart": round(float((d < 0).mean()), 3),
                "median_signed_mm": round(float(np.median(d)), 2)}
    report = {
        "segmentation": "TotalSegmentator 2.18 'total' task (open; no license), CPU, roi_subset",
        "classes_present": ["heart", "aorta"] + present,
        "meshes": meshes,
        "coronary_to_heart_surface": {"all": stats(d_h), "left": stats(d_h[tree == "left"]), "right": stats(d_h[tree == "right"])},
        "coronary_to_heart_or_aorta_surface": {"all": stats(d_ha)},
        "coronary_to_rendered_heart_or_aorta_mesh_unsigned": {
            "median_mm": round(float(np.median(d_mesh)), 2), "p90_mm": round(float(np.percentile(d_mesh, 90)), 2),
            "max_mm": round(float(d_mesh.max()), 2), "frac_within_5mm": round(float((d_mesh <= 5).mean()), 3)},
        "assertion": {"median_abs_max_mm": EPI_MEDIAN_MAX_MM, "p90_abs_max_mm": EPI_P90_MAX_MM},
    }
    s = report["coronary_to_heart_or_aorta_surface"]["all"]
    report["assertion"]["passed"] = s["median_abs_mm"] <= EPI_MEDIAN_MAX_MM and s["p90_abs_mm"] <= EPI_P90_MAX_MM
    (out / "anatomy_report.json").write_text(json.dumps(report, indent=1))
    meta = json.loads((out / "case.json").read_text())
    for f in [f"{n}.glb" for n in meshes] + ["anatomy_report.json"]:
        if f not in meta["files"]:
            meta["files"].insert(-1, f)
    meta["anatomy"] = {k: report[k] for k in ("segmentation", "classes_present", "coronary_to_heart_or_aorta_surface",
                                              "coronary_to_rendered_heart_or_aorta_mesh_unsigned", "assertion")}
    (out / "case.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(report, indent=1))
    if not report["assertion"]["passed"]:
        raise SystemExit("EPICARDIAL ASSERTION FAILED: coronaries do not sit on the heart surface (see anatomy_report.json)")


if __name__ == "__main__":
    main()
