"""Phase 0 static figures. The image array is shown exactly as rendered (row 0 at top);
the orientation glyph is computed by projecting patient axes through the same CArm."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .geometry import CArm
from .render import DetectorGrid, angio_intensity

PATIENT_AXES = {"L": [1, 0, 0], "P": [0, 1, 0], "S": [0, 0, 1]}
AXIS_COLORS = {"L": "tab:red", "P": "tab:green", "S": "tab:blue"}


def draw_view(ax, img_thickness, carm: CArm, grid: DetectorGrid, title: str):
    I = angio_intensity(img_thickness)
    ax.imshow(0.25 + 0.6 * I, cmap="gray", vmin=0, vmax=1, interpolation="bilinear")
    ax.set_title(title, fontsize=10)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_xlabel("screen right = +u", fontsize=7); ax.set_ylabel("screen up = +v", fontsize=7)

    ins = ax.inset_axes([0.0, 0.0, 0.22, 0.22])
    ins.set_xlim(-1.4, 1.4); ins.set_ylim(-1.4, 1.4)
    ins.set_xticks([]); ins.set_yticks([]); ins.set_facecolor((1, 1, 1, 0.7))
    o = carm.project(carm.iso)[0]
    placed = []
    for name, vec in PATIENT_AXES.items():
        e = carm.project(carm.iso + 40.0 * np.asarray(vec, float))[0] - o
        e = e / 40.0 / (carm.sid / carm.sod)
        if np.hypot(*e) < 0.15:   # axis (nearly) along the central ray
            ins.plot(0, 0, "o", ms=4, mfc="none", mec=AXIS_COLORS[name])
            label, txt = (0.0, -1.05), f"{name} (along beam)"
        else:
            ins.annotate("", xy=e, xytext=(0, 0),
                         arrowprops=dict(arrowstyle="->", color=AXIS_COLORS[name], lw=1.5))
            label, txt = tuple(e * 1.15), name
        while any(np.hypot(label[0] - a, label[1] - b) < 0.3 for a, b in placed):
            label = (label[0], label[1] - 0.3)
        placed.append(label)
        ins.text(*label, txt, color=AXIS_COLORS[name], fontsize=7 if len(txt) > 1 else 8,
                 ha="center", va="center", weight="bold")


def save_single(path, img, carm, grid, title, footer):
    fig, ax = plt.subplots(figsize=(6, 6.4))
    draw_view(ax, img, carm, grid, title)
    fig.text(0.5, 0.01, footer, ha="center", fontsize=6.5, color="0.3")
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def save_sheet(path, panels, grid, suptitle, footer, ncols=4):
    nrows = int(np.ceil(len(panels) / ncols))
    fig, axs = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 4.7 * nrows), layout="constrained")
    for ax in np.ravel(axs)[len(panels):]:
        ax.axis("off")
    for ax, (img, carm, title) in zip(np.ravel(axs), panels):
        draw_view(ax, img, carm, grid, title)
    fig.suptitle(suptitle, fontsize=12)
    fig.supxlabel(footer, fontsize=8, color="0.3")
    fig.savefig(path, dpi=90)
    plt.close(fig)
