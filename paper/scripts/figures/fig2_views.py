"""Fig. 2: the same atlas anatomy at four named views; each panel = 3D scene seen from behind the detector (left) beside the
rendered angiogram (right), cropped from the app's Scene 4 split view (screenshots by paper/scripts/browser/fig_capture.mjs).
Crops only (no edits to pixels): the 3D half is cropped to the heart; the detector image is cropped to its own square, which
removes the app's caption text below it. Combination figure: Fig2.tif at 600 dpi + PNG preview.

    .venv\\Scripts\\python paper\\scripts\\figures\\fig2_views.py
"""
import numpy as np
from PIL import Image

from figstyle import ROOT, W_FULL, panel, plt, save_raster

RAW = ROOT / "paper" / "results" / "raw"
VIEWS = ["raocaud", "spider", "rao30", "lao45"]


def crops(path):
    im = np.asarray(Image.open(path).convert("RGB"))
    h, w, _ = im.shape
    left = im[:, : w // 2]
    right = im[:, w // 2:]
    # detector square: the bright (grey) region of the right half
    bright = right.mean(axis=2) > 90
    rows = np.where(bright.mean(axis=1) > 0.5)[0]            # caption text rows are mostly dark: excluded
    cols = np.where(bright[rows].mean(axis=0) > 0.5)[0]
    y0, y1, x0, x1 = rows.min(), rows.max(), cols.min(), cols.max()
    det = right[y0:y1 + 1, x0:x1 + 1]
    side = det.shape[0]
    cx = left.shape[1] // 2
    l3d = left[max(0, (h - side) // 2): (h - side) // 2 + side, max(0, cx - side // 2): cx - side // 2 + side]
    return l3d, det


fig, axs = plt.subplots(2, 2, figsize=(W_FULL, W_FULL * 0.53), constrained_layout=True)
for ax, v, lab in zip(axs.ravel(), VIEWS, "abcd"):
    l3d, det = crops(RAW / f"fig2_{v}.png")
    det = np.asarray(Image.fromarray(det).resize((l3d.shape[1], l3d.shape[0]), Image.LANCZOS))
    gap = np.full((l3d.shape[0], 12, 3), 255, np.uint8)
    ax.imshow(np.concatenate([l3d, gap, det], axis=1))
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    panel(ax, lab, -0.005, 1.01)
save_raster(fig, "Fig2", 600)
print("Fig2 written")
