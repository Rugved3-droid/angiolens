"""Review figure for D52: the left tree at RAO 30 / CAUD 25, summed branch meshes (before) vs the boolean union (after).

    .venv\\Scripts\\python preprocess\\scripts\\junction_before_after.py     -> out/review/lab/junction_fix_before_after.png
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
    iso = np.array(json.loads((A / "atlas_xray.json").read_text())["isocenter_LPS"])
    carm = CArm(-30, -25, iso)
    grid = DetectorGrid(size_mm=250, n=700)
    imgs = {}
    for k, f in (("before", "atlas_xray_left_summed.glb"), ("after", "atlas_xray_left.glb")):
        g = read_glb(A / f)
        imgs[k], _ = mesh_thickness_image(carm, g["POSITION"].astype(float), g["indices"].astype(np.int64), grid)
    diff = imgs["before"] - imgs["after"]
    # zoom on the junction with the largest double count
    r, c = np.unravel_index(np.argmax(diff), diff.shape)
    h = 45
    sl = (slice(max(r - h, 0), r + h), slice(max(c - h, 0), c + h))
    I = {k: np.exp(-0.35 * v) for k, v in imgs.items()}
    fig, ax = plt.subplots(2, 3, figsize=(13, 9), layout="constrained")
    for j, k in enumerate(("before", "after")):
        ax[0, j].imshow(0.25 + 0.6 * I[k], cmap="gray", vmin=0, vmax=1)
        ax[0, j].set_title(f"{'BEFORE: branch meshes summed' if k == 'before' else 'AFTER: one unioned solid'}", fontsize=9)
        ax[0, j].add_patch(plt.Rectangle((sl[1].start, sl[0].start), 2 * h, 2 * h, fill=False, ec="#ffb000", lw=1.5))
        ax[1, j].imshow(0.25 + 0.6 * I[k][sl], cmap="gray", vmin=0, vmax=1, interpolation="nearest")
        ax[1, j].set_title(f"{k}: junction close-up (darker = longer path)", fontsize=9)
    m = ax[0, 2].imshow(diff, cmap="magma", vmin=0, vmax=max(diff.max(), 1e-6))
    ax[0, 2].set_title(f"double count removed (mm): max {diff.max():.2f}, {int((diff > 0.05).sum())} px > 0.05 mm", fontsize=9)
    fig.colorbar(m, ax=ax[0, 2], fraction=0.046)
    ax[1, 2].imshow(diff[sl], cmap="magma", vmin=0, vmax=max(diff.max(), 1e-6), interpolation="nearest")
    ax[1, 2].set_title("double count, close-up")
    for a in ax.ravel():
        a.set_xticks([]); a.set_yticks([])
    fig.suptitle("Atlas left coronary tree, RAO 30 / CAUD 25, exact path length: junctions counted once after the union (D52). "
                 "No display flips.")
    out = ROOT / "out" / "review" / "lab" / "junction_fix_before_after.png"
    fig.savefig(out, dpi=95)
    print("wrote", out, "max double count %.2f mm" % diff.max(), "after - before min %.4f" % (imgs["after"] - imgs["before"]).max())


if __name__ == "__main__":
    main()
