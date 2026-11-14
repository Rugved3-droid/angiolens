"""Fig. 4: E2 orientation phantom. GPU renders (path length, dark = more) with the first-principles expected outline (dashed).
Raster: Fig4.tif at 600 dpi + PNG preview.

    .venv\\Scripts\\python paper\\scripts\\figures\\fig4_phantom.py
Inputs: paper/results/raw/e2_gpu*/ (GPU images written by e2_orientation.py, synthetic phantom only), expected masks from
paper/scripts/e2_orientation.py (independent derivation).
"""
import sys

import numpy as np

from figstyle import ROOT, W_FULL, panel, plt, save_raster

sys.path.insert(0, str(ROOT / "paper" / "scripts"))
import e2_orientation as e2  # noqa: E402

RAW = ROOT / "paper" / "results" / "raw"
PX = e2.PX
V1_F = (5.0, -30.0, -55.0)
V2_F = (40.0, -25.0, -65.0)


def img(phantom, a, b):
    d = "e2_gpu" if phantom == "v1" else "e2_gpu_v2"
    return np.fromfile(RAW / d / f"{a}_{b}.f32", "<f4").reshape(PX, PX)


def expected(phantom, a, b):
    e2.CENTRES["F"] = V1_F if phantom == "v1" else V2_F
    e2._letter_mask.cache_clear()
    return e2.expected_mask(list(e2.CENTRES), a, b)


# (panel, phantom, rendered pose, expected-for pose, flip, label used in the caption)
P = [("a", "v2", (40, -30), (40, -30), None), ("b", "v2", (40, -30), (40, -30), "lr"), ("c", "v2", (-40, -30), (40, -30), None),
     ("d", "v2", (40, 30), (40, -30), None), ("e", "v1", (45, -30), (45, -30), None), ("f", "v2", (45, -30), (45, -30), None)]
fig, axs = plt.subplots(2, 3, figsize=(W_FULL, W_FULL * 2 / 3 * 0.92), constrained_layout=True)
r0, r1, c0, c1 = 30, 512, 30, 482                                     # crop to the markers (same crop for every panel)
for ax, (lab, ph, pose, exp_pose, flip) in zip(axs.ravel(), P):
    im = img(ph, *pose)
    if flip == "lr":
        im = im[:, ::-1]
    E = expected(ph, *exp_pose)
    ax.imshow(-im[r0:r1, c0:c1], cmap="gray", vmin=-max(1e-6, float(im.max())), vmax=0, interpolation="nearest")
    ax.contour(E[r0:r1, c0:c1].astype(float), levels=[0.5], colors=["#c2410c"], linewidths=0.6, linestyles="--")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(0.5)
    panel(ax, lab, -0.01, 1.01)
save_raster(fig, "Fig4", 600)
print("Fig4 written")
