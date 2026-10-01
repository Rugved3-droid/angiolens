"""Bone vs blood-pool review figure: 5 axial levels, plus the per-region decision report.

    python preprocess/scripts/review_masks.py --case Normal_12
Writes out/review/<case>/masks_overlay.png and masks_report.json. Review before the DRR uses the masks.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from cpt.case import load_case
from cpt.masks import bone_and_pool

COLORS = {"bone": (1.0, 0.85, 0.0), "pool": (0.9, 0.1, 0.1), "lumen": (0.0, 1.0, 0.3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="Normal_12")
    ap.add_argument("--levels", default="-75,-100,-125,-150,-175")
    args = ap.parse_args()
    out = ROOT / "out" / "review" / args.case
    out.mkdir(parents=True, exist_ok=True)

    c = load_case(args.case)
    bone, pool, report = bone_and_pool(c.ct, c.lumen)
    (out / "masks_report.json").write_text(json.dumps(report, indent=1))
    np.savez_compressed(out / "masks.npz", bone=bone, pool=pool)

    lo, hi = c.ct.bounds_lps()
    ext = [lo[0], hi[0], lo[1], hi[1]]
    zs = [float(z) for z in args.levels.split(",")]
    fig, axs = plt.subplots(2, len(zs), figsize=(6 * len(zs), 12.5), layout="constrained")
    for col, z in enumerate(zs):
        k = int(round(c.ct.lps_to_index([0, 0, z])[0, 2]))
        sl = c.ct.data[:, :, k].T
        for row, show in enumerate([False, True]):
            a = axs[row, col]
            a.imshow(sl, cmap="gray", vmin=-200, vmax=900, origin="lower", extent=ext)
            if show:
                for name, m in (("pool", pool), ("bone", bone), ("lumen", c.lumen)):
                    rgba = np.zeros(sl.shape + (4,))
                    rgba[m[:, :, k].T] = COLORS[name] + (0.45,)
                    a.imshow(rgba, origin="lower", extent=ext)
            a.set_title(f"z = {z:.0f} mm" + ("  overlay" if show else "  CT only"))
            a.set_xlabel("x (+ = patient LEFT)")
            a.set_ylabel("y (+ = POSTERIOR)")
    fig.suptitle(f"{args.case}: bone (yellow), blood pool (red), coronary lumen (green).  "
                 f"bone {report['bone_ml']} mL, pool {report['pool_ml']} mL.  "
                 "Axes are LPS mm as labeled (posterior is UP in these plots).", fontsize=13)
    fig.savefig(out / "masks_overlay.png", dpi=60)
    print("wrote", out / "masks_overlay.png")


if __name__ == "__main__":
    main()
