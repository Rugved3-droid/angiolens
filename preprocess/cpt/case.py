"""Per-case loading: CT + lumen annotation in LPS, left/right tree split, fixed isocenter."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

from .volume import Volume, assert_same_grid, load_nrrd_lps

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw"


@dataclass
class Case:
    case_id: str
    ct: Volume
    lumen: np.ndarray           # bool, both trees
    left: np.ndarray            # bool
    right: np.ndarray           # bool
    isocenter: np.ndarray       # LPS mm, constant for the case
    split_report: dict

    def tree_volume(self, which: str) -> Volume:
        m = {"left": self.left, "right": self.right, "both": self.lumen}[which]
        return Volume(data=m, affine=self.ct.affine, source_space=self.ct.source_space)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def split_trees(vol: Volume, lumen: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Two 26-connected components -> (left, right).

    Assignment needs two independent anatomical criteria to agree: the left tree is
    the larger lumen volume AND has the more patient-left (+x) centroid. If they
    disagree, or there are not exactly two components, refuse and ask.
    """
    lab, n = ndi.label(lumen, structure=np.ones((3, 3, 3)))
    if n != 2:
        raise ValueError(f"expected 2 lumen components, found {n}; needs manual review")
    comps = []
    for i in (1, 2):
        idx = np.argwhere(lab == i)
        p = vol.index_to_lps(idx)
        top = p[p[:, 2].argmax()]
        comps.append({"label": i, "voxels": int(len(idx)),
                      "volume_mm3": float(len(idx) * np.prod(vol.spacing)),
                      "centroid_lps": p.mean(0).round(2).tolist(),
                      "most_superior_point_lps": top.round(2).tolist()})
    by_size = max(comps, key=lambda c: c["voxels"])
    by_x = max(comps, key=lambda c: c["centroid_lps"][0])
    if by_size is not by_x:
        raise ValueError(f"left/right criteria disagree: {comps}; needs manual review")
    left_label = by_size["label"]
    report = {"left": next(c for c in comps if c["label"] == left_label),
              "right": next(c for c in comps if c["label"] != left_label),
              "rule": "left = larger AND more +x centroid (both must agree)"}
    return lab == left_label, (lab > 0) & (lab != left_label), report


def load_case(case_id: str) -> Case:
    d = RAW / case_id
    ct = load_nrrd_lps(d / f"CTCA_{case_id}.nrrd")
    ann = load_nrrd_lps(d / f"Annotation_{case_id}.nrrd")
    assert_same_grid(ct, ann)
    lumen = ann.data > 0
    left, right, report = split_trees(ct, lumen)
    iso = ct.index_to_lps(np.argwhere(lumen)).mean(0)
    return Case(case_id, ct, lumen, left, right, iso, report)


def write_meta(case: Case, out: Path) -> dict:
    d = RAW / case.case_id
    meta = {
        "case_id": case.case_id,
        "source": "ASOCA (Gharleghi et al. 2022), extracted unmodified from D:/ASOCADataAccess.zip",
        "files": {p.name: sha256(p) for p in sorted(d.glob("*.nrrd"))},
        "header_space": case.ct.source_space,
        "affine_voxel_to_lps": case.ct.affine.round(6).tolist(),
        "shape": list(case.ct.data.shape),
        "bounds_lps_mm": [b.round(2).tolist() for b in case.ct.bounds_lps()],
        "isocenter_lps_mm": case.isocenter.round(3).tolist(),
        "isocenter_rule": "centroid of all lumen voxels of both trees; constant per case",
        "trees": case.split_report,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "case_meta.json").write_text(json.dumps(meta, indent=2))
    return meta
