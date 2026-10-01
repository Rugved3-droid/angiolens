"""Phase 0 reference PNGs for one ASOCA case.

    python preprocess/scripts/phase0_case.py --case Normal_12
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))

from cpt.case import load_case, write_meta
from cpt.figures import save_sheet, save_single
from cpt.geometry import CArm
from cpt.render import DetectorGrid, crop_to_mask, thickness_image
from cpt.views import PHASE0_VIEWS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="Normal_12")
    args = ap.parse_args()
    out = ROOT / "out" / "phase0" / args.case
    case = load_case(args.case)
    meta = write_meta(case, out)
    print(json.dumps({k: meta[k] for k in ("header_space", "isocenter_lps_mm", "trees")}, indent=1))

    grid = DetectorGrid(size_mm=250, n=500)
    footer = (f"{args.case} | SID 1000 / SOD 750 mm | isocenter = both-tree lumen centroid "
              f"({', '.join(f'{x:.1f}' for x in case.isocenter)}) LPS | detector 250 mm, no display flips")
    for tree in ("left", "right"):
        mask_vol = crop_to_mask(case.ct, getattr(case, tree))
        panels = []
        for a, b in PHASE0_VIEWS[tree]:
            c = CArm(a, b, case.isocenter)
            img = thickness_image(c, mask_vol, grid)
            title = f"{tree.upper()} tree | {c.label}"
            save_single(out / f"{tree}_{c.label.replace(' / ', '_').replace(' ', '')}.png",
                        img, c, grid, title, footer)
            panels.append((img, c, title))
            print("rendered", title)
        save_sheet(out / f"{tree}_sheet.png", panels, grid, f"{args.case}: {tree.upper()} coronary tree",
                   footer, ncols=len(panels) if len(panels) <= 3 else 3)


if __name__ == "__main__":
    main()
