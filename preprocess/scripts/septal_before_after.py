"""Review figure for D55: a septal-branch origin, the D52 union (multi-tube parts fed whole) vs the per-tube union.

    .venv\\Scripts\\python preprocess\\scripts\\septal_before_after.py   (needs atlas_xray_left_D52.glb kept from the D52 build)
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))
from cpt.geometry import CArm  # noqa: E402
from cpt.glb import read_glb  # noqa: E402
from cpt.meshrender import mesh_thickness_image  # noqa: E402
from cpt.render import DetectorGrid  # noqa: E402

A = ROOT / "assets" / "anatomy"


def main():
    meta = json.loads((A / "atlas_xray.json").read_text())
    iso = np.array(meta["isocenter_LPS"])
    probe = json.loads((A / "inspect" / "great_vessels_probe.json").read_text())
    carm = CArm(-30, 0, iso)                                        # RAO 30: the septals run in the image plane
    grid = DetectorGrid(size_mm=250, n=800)
    img = {}
    for k, f in (("before", "atlas_xray_left_D52.glb"), ("after", "atlas_xray_left.glb")):
        g = read_glb(A / f)
        img[k], _ = mesh_thickness_image(carm, g["POSITION"].astype(float), g["indices"].astype(np.int64), grid)
    diff = img["before"] - img["after"]
    # crop at the septal origin with the largest change
    sep = [np.array(s["centreline"][0]) for s in probe["curves"]["Septal branches of anterior interventricular artery"]["splines"]]
    rc = [grid.screen_to_pixel(carm.project(p))[0] for p in sep]
    vals = [diff[int(round(r)) - 6:int(round(r)) + 7, int(round(c)) - 6:int(round(c)) + 7].max() for r, c in rc]
    k = int(np.argmax(vals))
    r, c = (int(round(x)) for x in rc[k])
    h = 40
    sl = (slice(r - h, r + h), slice(c - h, c + h))
    fig, ax = plt.subplots(1, 3, figsize=(13, 4.8), layout="constrained")
    for j, key in enumerate(("before", "after")):
        ax[j].imshow(0.25 + 0.6 * np.exp(-0.35 * img[key][sl]), cmap="gray", vmin=0, vmax=1, interpolation="nearest")
        ax[j].set_title(f"{'BEFORE (D52 union, septal tubes fed as one mesh)' if key == 'before' else 'AFTER (per-tube union, D55)'}", fontsize=9)
    m = ax[2].imshow(diff[sl], cmap="magma", vmin=0, vmax=max(diff[sl].max(), 1e-6), interpolation="nearest")
    ax[2].set_title(f"double path removed at septal #{k} origin: max {diff[sl].max():.2f} mm", fontsize=9)
    fig.colorbar(m, ax=ax[2], fraction=0.046)
    for a in ax:
        a.set_xticks([]); a.set_yticks([])
    fig.suptitle("Left tree, RAO 30, exact path length, crop at a septal origin (no tube was floating; no bridge needed). No display flips.",
                 fontsize=10)
    out = ROOT / "out" / "review" / "lab" / "septal_before_after.png"
    fig.savefig(out, dpi=100)
    print("wrote", out, "septal", k, "max removed %.3f mm in crop, %.3f mm whole image" % (diff[sl].max(), diff.max()),
          "after > before anywhere: %.4f" % (-diff).max())


if __name__ == "__main__":
    main()
