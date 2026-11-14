"""Fig. 5: Predict mode. a-d: the four options of one item exactly as shown to the learner (tiles captured by
paper/scripts/browser/fig_capture.mjs from the unmodified atlas PredictMode); e: E3 pairwise IoU of binary vessel masks by pair type.
Raster: Fig5.tif at 600 dpi + PNG preview.

    .venv\\Scripts\\python paper\\scripts\\figures\\fig5_predict.py
Inputs: paper/results/raw/fig5_tiles.json + fig5_tile_<k>.rgba, paper/results/e3/e3_pairs.csv.
"""
import csv
import json

import numpy as np

from figstyle import ROOT, W_FULL, panel, plt, save_raster

R = ROOT / "paper" / "results"
meta = json.loads((R / "raw" / "fig5_tiles.json").read_text())
px = meta["px"]
NAMES = {"correct": "correct", "alpha-flip": "LAO/RAO flipped", "beta-flip": "CRAN/CAUD flipped", "both-flip": "both flipped",
         "mirror-lr": "L–R mirror", "mirror-ud": "U–D mirror"}

fig = plt.figure(figsize=(W_FULL, 4.3), layout="constrained")
top, bottom = fig.subfigures(2, 1, height_ratios=[1.0, 1.05])
tax = top.subplots(1, 4)
for k in range(4):
    ax = tax[k]
    t = np.fromfile(R / "raw" / f"fig5_tile_{k}.rgba", np.uint8).reshape(px, px, 4)[..., :3]
    ax.imshow(t, interpolation="lanczos")
    ax.set_xticks([]); ax.set_yticks([])
    panel(ax, "abcd"[k], -0.01, 1.01)

rows = list(csv.DictReader(open(R / "e3" / "e3_pairs.csv")))
types = {}
for r in rows:
    key = " vs ".join(sorted((NAMES[r["kind_a"]], NAMES[r["kind_b"]]), key=lambda s: (s != "correct", s)))
    types.setdefault(key, []).append(float(r["iou"]))
order = sorted(types, key=lambda k: (not k.startswith("correct"), -np.median(types[k])))
ax = bottom.subplots(1, 1)
bp = ax.boxplot([types[k] for k in order], orientation="horizontal", widths=0.55, patch_artist=True,
                flierprops={"marker": "x", "markersize": 2.5, "markeredgewidth": 0.5},
                medianprops={"color": "black", "linewidth": 0.9}, boxprops={"linewidth": 0.6},
                whiskerprops={"linewidth": 0.6}, capprops={"linewidth": 0.6})
for patch, k in zip(bp["boxes"], order):
    patch.set_facecolor("0.85" if k.startswith("correct") else "white")
    patch.set_hatch("" if k.startswith("correct") else "////")
ax.set_yticks(range(1, len(order) + 1), [f"{k}  (n={len(types[k])})" for k in order], fontsize=6.5)
ax.invert_yaxis()
ax.set_xlim(0, 1)
ax.set_xlabel("pairwise IoU of binary vessel masks (E3; 612 items)")
ax.axvline(float(json.loads((R / "e3" / "e3_summary.json").read_text())["tau_5deg"]["min"]), color="black", lw=0.6, ls="--")
panel(ax, "e", -0.01, 1.02)
save_raster(fig, "Fig5", 600)
print("Fig5 written")
