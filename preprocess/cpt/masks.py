"""Bone and blood-pool masks (DECISIONS.md D10 revision).

Bone is defined positively; blood pool is what remains.
  1. Cortical seeds: HU > CORTICAL_HU, opened 1 voxel so isolated contrast speckle drops out.
  2. Cortical shell: seeds grown 2 voxels into HU > SHELL_HU.
  3. Shell components are kept only if consistent with vertebrae, sternum or ribs
     (size, location relative to the heart, cortical fraction, and thinness: a solid dense blob with
     inscribed radius > DENSE_BLOB_RADIUS_MM is undiluted contrast such as SVC inflow, never cortex).
  4. Candidates: lightly smoothed HU in [POOL_LO, POOL_HI], outside the shell and the coronary
     lumen. Cancellous bone and contrast blood overlap in HU (Normal_12: LV cavity p5-p95 121-439,
     vertebral body 104-399), and thin bridges join them, so candidates are eroded
     SPLIT_EROSION voxels, labeled, and the labels expanded back inside the candidates.
  5. Each candidate region is classified by its RIM: the fraction of its boundary that has cortex-like
     bone (raw HU > RIM_HU) or the edge of the reconstruction FOV within RIM_MM. Bone marrow sits inside a
     cortical rim (in this CT, mostly 400-700 HU, so a raw threshold is used rather than the 700 HU seeds).
     Blood vessels and chambers are bounded by wall, fat and myocardium. A vessel lying against bone
     (descending aorta on the spine) touches the rim on one side only. The FOV edge counts because the
     circular FOV cuts the posterior vertebral body open in this dataset.
     Two features, both required for bone:
       rim >= ENCLOSED_MIN  and  mean HU < MARROW_MAX_MEAN_HU  -> cancellous bone
       otherwise                                              -> blood pool
     Measured on Normal_12: vertebra rim 0.33 / 303 HU, sternum 0.13 / 313, ribs 0.18-0.21 / 292-344,
     descending aorta 0.02 / 485, LV 0.01 / 351. A well-opacified aorta lying on the spine can reach a rim of
     ~0.15 (synthetic test), which the mean-HU condition rejects.
  6. Blood pool: all pool regions >= MIN_POOL_VOX voxels, plus dense mediastinal contrast rejected in
     step 3 (e.g. undiluted SVC inflow above POOL_HI), dilated 1 voxel, never overlapping bone.
Every region >= REPORT_ML is listed in the report with its decision.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from skimage.segmentation import expand_labels

from .volume import Volume

CORTICAL_HU = 700
SHELL_HU = 400
BONE_MESH_HU = 250
POOL_LO, POOL_HI = 150, 700
POOL_SMOOTH_SIGMA_VOX = 1.0
SPLIT_EROSION = 2
ENCLOSED_MIN = 0.10
MARROW_MAX_MEAN_HU = 400
RIM_HU = 400
RIM_MM = 1.5
MIN_SHELL_ML = 0.15
DENSE_BLOB_RADIUS_MM = 4.0
MIN_POOL_VOX = 200
REPORT_ML = 0.3
OUTSIDE_FOV_HU = -1500


def _region_props(ct, lab, i, sl):
    m = lab[sl] == i
    p = ct.index_to_lps(np.array(ndi.center_of_mass(m)) + [s.start for s in sl])[0]
    return m, p


def _shell_components(ct: Volume, lumen: np.ndarray):
    hu = ct.data
    vox_ml = float(np.prod(ct.spacing)) / 1000.0
    seeds = ndi.binary_opening(hu > CORTICAL_HU, iterations=1)
    shell = (seeds | (ndi.binary_dilation(seeds, iterations=2) & (hu > SHELL_HU))) & ~lumen
    lab, n = ndi.label(shell, structure=np.ones((3, 3, 3)))
    lumen_c = ct.index_to_lps(np.argwhere(lumen)).mean(0)
    keep = np.zeros(n + 1, bool)
    reject = np.zeros(n + 1, bool)
    comps = []
    idx = np.arange(1, n + 1)
    size = ndi.sum(np.ones(hu.shape, np.float32), lab, idx) * vox_ml
    cort = ndi.mean((hu > CORTICAL_HU).astype(np.float32), lab, idx)
    for i, sl in enumerate(ndi.find_objects(lab)):
        if size[i] < MIN_SHELL_ML:
            continue                      # speckle; not reported individually
        _, p = _region_props(ct, lab, i + 1, sl)
        reasons = []
        # bone is peripheral: posterior (spine), anterior wall (sternum) or lateral wall (ribs);
        # a shell piece in the mediastinum near the coronaries is dense contrast, not bone.
        if np.linalg.norm((p - lumen_c)[:2]) < 45 and p[1] < lumen_c[1] + 35:
            reasons.append("mediastinal location")
        if cort[i] < 0.08:
            reasons.append("too little cortical bone")
        # cortex is a thin shell; a SOLID >700 HU blob is undiluted contrast (SVC/RA inflow)
        piece = lab[sl] == i + 1
        r_in = float(ndi.distance_transform_edt(np.pad(piece, 1), sampling=ct.spacing).max())
        if r_in > DENSE_BLOB_RADIUS_MM:
            reasons.append(f"solid dense blob (inscribed radius {r_in:.1f} mm): contrast")
        keep[i + 1] = not reasons
        reject[i + 1] = any(r.startswith(("mediastinal", "solid dense")) for r in reasons)
        comps.append({"ml": round(float(size[i]), 2), "centroid_lps": p.round(1).tolist(),
                      "cortical_frac": round(float(cort[i]), 2),
                      "decision": "bone shell" if not reasons else "rejected: " + ", ".join(reasons)})
    return keep[lab], comps, shell, reject[lab]


def _rim_fraction(region: np.ndarray, hu: np.ndarray, outside: np.ndarray, spacing: np.ndarray) -> float:
    """Fraction of the region's boundary voxels that have cortex-like bone (raw HU > RIM_HU, not part
    of the region) or the FOV edge within RIM_MM. Distances are in mm, so the rule is resolution-independent.
    Arrays are the region's bounding box (padded)."""
    bright = ((hu > RIM_HU) | outside) & ~region
    if not bright.any():
        return 0.0
    dist = ndi.distance_transform_edt(~bright, sampling=spacing)
    boundary = region & ndi.binary_dilation(~region)
    return float((dist[boundary] <= RIM_MM).mean()) if boundary.any() else 0.0


def bone_and_pool(ct: Volume, lumen: np.ndarray):
    """Return (bone_region, blood_pool, report)."""
    hu = ct.data
    vox_ml = float(np.prod(ct.spacing)) / 1000.0
    shell, shell_report, _, dense_contrast = _shell_components(ct, lumen)
    outside = hu <= OUTSIDE_FOV_HU

    sm = ndi.gaussian_filter(hu.astype(np.float32), POOL_SMOOTH_SIGMA_VOX)
    cand = (sm >= POOL_LO) & (sm <= POOL_HI) & ~ndi.binary_dilation(shell, iterations=1) & ~lumen
    lab, n = ndi.label(ndi.binary_erosion(cand, iterations=SPLIT_EROSION))
    lab = expand_labels(lab, distance=SPLIT_EROSION + 1) * cand

    bone_ids, pool_ids, regions = [], [], []
    idx = np.arange(1, n + 1)
    size = ndi.sum(np.ones(hu.shape, np.float32), lab, idx)
    mean_hu = ndi.mean(hu, lab, idx)
    for i, sl in enumerate(ndi.find_objects(lab)):
        if sl is None or size[i] < MIN_POOL_VOX:
            continue
        pad = int(np.ceil(RIM_MM / ct.spacing.min())) + 2
        sl = tuple(slice(max(s.start - pad, 0), s.stop + pad) for s in sl)
        m, p = _region_props(ct, lab, i + 1, sl)
        enc = _rim_fraction(m, hu[sl], outside[sl], ct.spacing)
        is_bone = enc >= ENCLOSED_MIN and mean_hu[i] < MARROW_MAX_MEAN_HU
        (bone_ids if is_bone else pool_ids).append(i + 1)
        if size[i] * vox_ml >= REPORT_ML:
            regions.append({"ml": round(float(size[i] * vox_ml), 2), "centroid_lps": p.round(0).tolist(),
                            "mean_hu": round(float(mean_hu[i])), "rim": round(enc, 2),
                            "decision": "cancellous bone" if is_bone else "blood pool"})

    bone = ndi.binary_dilation(shell, iterations=1) | np.isin(lab, bone_ids)
    bone &= ~lumen
    # dense contrast (> CORTICAL_HU, e.g. SVC inflow) rejected as bone joins the pool so the DRR
    # suppresses it too, even though it is above POOL_HI
    pool = ndi.binary_dilation(np.isin(lab, pool_ids) | dense_contrast, iterations=1) & ~bone & ~lumen
    report = {
        "params": {"CORTICAL_HU": CORTICAL_HU, "SHELL_HU": SHELL_HU, "POOL_HU": [POOL_LO, POOL_HI],
                   "smooth_sigma_vox": POOL_SMOOTH_SIGMA_VOX, "split_erosion_vox": SPLIT_EROSION,
                   "enclosed_min": ENCLOSED_MIN, "marrow_max_mean_hu": MARROW_MAX_MEAN_HU, "rim_hu": RIM_HU, "rim_mm": RIM_MM},
        "shell_components": sorted(shell_report, key=lambda d: -d["ml"]),
        "candidate_regions": sorted(regions, key=lambda d: -d["ml"]),
        "bone_ml": round(float(bone.sum() * vox_ml), 1),
        "bone_mesh_ml": round(float((bone & (hu > BONE_MESH_HU)).sum() * vox_ml), 1),
        "pool_ml": round(float(pool.sum() * vox_ml), 1),
    }
    return bone, pool, report


def bone_mesh_mask(ct: Volume, bone: np.ndarray) -> np.ndarray:
    return bone & (ct.data > BONE_MESH_HU)
