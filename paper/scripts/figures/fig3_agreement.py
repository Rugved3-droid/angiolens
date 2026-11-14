"""Fig. 3: E1 + E1b agreement over the 5-degree angle grid. Raster (heatmaps + labels): Fig3.tif at 600 dpi + PNG preview.

    .venv\\Scripts\\python paper\\scripts\\figures\\fig3_agreement.py
Inputs: paper/results/e1/e1_per_pose.csv (vertex_max_px), paper/results/e1b/e1b_per_pose.csv (centroid_shift_px, r_mirror_lr).
"""
import csv

import numpy as np

from figstyle import ROOT, W_FULL, panel, plt, save_raster

R = ROOT / "paper" / "results"
A = np.arange(-90, 91, 5)
B = np.arange(-45, 46, 5)


def grid(rows, key, agg=max):
    M = np.full((len(B), len(A)), np.nan)
    for r in rows:
        a, b = int(float(r["alpha"])), int(float(r["beta"]))
        if a in A and b in B:
            i, j = list(B).index(b), list(A).index(a)
            v = float(r[key])
            M[i, j] = v if np.isnan(M[i, j]) else agg(M[i, j], v)
    return M


e1 = list(csv.DictReader(open(R / "e1" / "e1_per_pose.csv")))
e1b = [r for r in csv.DictReader(open(R / "e1b" / "e1b_per_pose.csv"))]
panels = [
    ("a", grid(e1, "vertex_max_px"), "E1: max projection\ndiscrepancy (px × $10^{-4}$)", 1e4, "viridis"),
    ("b", grid(e1b, "centroid_shift_px"), "E1b: max centroid\nshift (px × $10^{-3}$)", 1e3, "viridis"),
    ("c", grid(e1b, "r_mirror_lr"), "E1b: r of mirrored GPU\nimage vs reference", 1, "cividis"),
]
fig, axs = plt.subplots(1, 3, figsize=(W_FULL, 2.35), constrained_layout=True)
named = [(-30, -25), (-30, 30), (0, 35), (0, -30), (40, 30), (40, -30), (45, -30), (90, 0), (-30, 0), (45, 0)]
for ax, (lab, M, cbl, sc, cmap) in zip(axs, panels):
    im = ax.imshow(M * sc, origin="lower", extent=[A[0] - 2.5, A[-1] + 2.5, B[0] - 2.5, B[-1] + 2.5], aspect="auto", cmap=cmap)
    ax.set_xlabel("RAO (−) / LAO (+), deg")
    ax.set_ylabel("CAUD (−) / CRAN (+), deg")
    ax.set_xticks([-90, -45, 0, 45, 90]); ax.set_yticks([-45, 0, 45])
    for a, b in named:
        ax.plot(a, b, marker="o", mfc="none", mec="white", ms=4, mew=0.9)
        ax.plot(a, b, marker="o", mfc="none", mec="black", ms=5.5, mew=0.4)
    cb = fig.colorbar(im, ax=ax, shrink=0.9)
    cb.set_label(cbl, fontsize=7); cb.ax.tick_params(labelsize=7)
    panel(ax, lab, -0.12, 1.02)
save_raster(fig, "Fig3", 600)
print("Fig3 written")
