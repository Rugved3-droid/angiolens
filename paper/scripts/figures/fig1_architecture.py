"""Fig. 1: system architecture (a) and C-arm angle conventions (b, c). Line art: Fig1.eps (vector) + Fig1.png preview.

    .venv\\Scripts\\python paper\\scripts\\figures\\fig1_architecture.py

Conventions drawn from CONVENTIONS.md sec. 1-3 and web/src/geometry.ts:9-40 (DICOM PS3.3 C.8.7.5 signs). No data values.
"""
import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon

from figstyle import W_FULL, panel, plt, save_vector

fig = plt.figure(figsize=(W_FULL, 5.0))
gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.0], hspace=0.12, wspace=0.05)
ax = fig.add_subplot(gs[0, :])
ax.set_xlim(-1, 100); ax.set_ylim(0, 44); ax.axis("off")
panel(ax, "a", 0.01, 0.97)


def box(x, y, w, h, title, body, fc="white"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.0", fc=fc, ec="black", lw=0.7))
    ax.text(x + w / 2, y + h - 1.6, title, ha="center", va="top", fontweight="bold", fontsize=8)
    ax.text(x + w / 2, y + h - 5.6, body, ha="center", va="top", fontsize=6.5, linespacing=1.3)


def arrow(p0, p1, ls="-", both=False):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="<|-|>" if both else "-|>", mutation_scale=7, lw=0.7, color="black",
                                 linestyle=ls, shrinkA=0, shrinkB=0))


# top row: the app
box(0, 25, 18.5, 16, "Anatomy", "Z-Anatomy atlas\nin LPS mm;\nclosed coronary trees")
box(21.5, 25, 18.5, 16, "C-arm geometry", "(α, β) → d, u, v\nsource, detector\nSID 1000, SOD 750")
box(43, 25, 17, 16, "GPU renderer", "WebGL path length\n(entry/exit sums)\nin the browser")
box(64, 25, 15, 16, "Angiogram", "shown as\nrendered; no\ndisplay flips")
box(83, 25, 16, 16, "Predict mode", "1 correct view\n+ 3 distractors")
arrow((18.5, 33), (21.5, 33)); arrow((40, 33), (43, 33)); arrow((60, 33), (64, 33)); arrow((79, 33), (83, 33))
# bottom row: the reference and the verification harness
box(21.5, 3, 18.5, 15, "Python twin", "same geometry,\nfloat64")
box(43, 3, 17, 15, "CPU reference", "exact ray–triangle\npath length")
box(64, 3, 35, 15, "Verification harness", "E1 projection, E1b images\nE2 phantom + negative controls\nE3 distractors, E5 performance", fc="0.94")
arrow((30.75, 25), (30.75, 18), ls="--", both=True); ax.text(31.75, 21.5, "E1", fontsize=7, va="center")
arrow((51.5, 25), (51.5, 18), ls="--", both=True); ax.text(52.5, 21.5, "E1b", fontsize=7, va="center")
arrow((60, 10.5), (64, 10.5))

# b, c: schematic C-arm positions (detector plate = filled bar; arrow = beam from source to detector)
def carm_panel(axp, letter, views, left_lab, right_lab, plane):
    axp.set_aspect("equal"); axp.axis("off"); panel(axp, letter, 0.08, 0.97)
    axp.set_xlim(-1.9, 1.9); axp.set_ylim(-1.45, 1.75)
    axp.add_patch(Circle((0, 0), 0.55, fc="0.9", ec="black", lw=0.7))
    axp.plot([0], [0], marker="+", color="black", ms=5, mew=0.6)
    axp.text(0, -0.92, plane, ha="center", va="center", fontsize=7)
    styles = {0: "-", 1: "--", 2: ":"}
    for i, (ang, lab) in enumerate(views):
        a = np.radians(ang)
        d = np.array([np.sin(a), np.cos(a)])            # page up = anterior; page right = patient left (b) / head (c)
        t = np.array([d[1], -d[0]])
        c = 1.2 * d
        plate = [c + 0.22 * t, c - 0.22 * t, c - 0.22 * t + 0.08 * d, c + 0.22 * t + 0.08 * d]
        axp.add_patch(Polygon(plate, closed=True, fc="0.3", ec="black", lw=0.5))
        axp.add_patch(FancyArrowPatch(tuple(-0.7 * d), tuple(1.16 * d), arrowstyle="-|>", mutation_scale=6, lw=0.6,
                                      color="black", linestyle=styles[i], shrinkA=0, shrinkB=0))
        axp.text(*(1.52 * d), lab, ha="center", va="center", fontsize=7.5)
    axp.annotate("", xy=(1.75, -1.25), xytext=(-1.75, -1.25), arrowprops=dict(arrowstyle="<|-|>", lw=0.6, color="black"))
    axp.text(1.75, -1.42, right_lab, ha="right", va="top", fontsize=7.5, fontweight="bold")
    axp.text(-1.75, -1.42, left_lab, ha="left", va="top", fontsize=7.5, fontweight="bold")


carm_panel(fig.add_subplot(gs[1, 0]), "b", [(0, "AP"), (40, "LAO 40"), (-30, "RAO 30")], "patient right", "patient left",
           "axial,\nseen from feet")
carm_panel(fig.add_subplot(gs[1, 1]), "c", [(0, "AP"), (30, "CRAN 30"), (-25, "CAUD 25")], "feet", "head",
           "sagittal,\nseen from left")
save_vector(fig, "Fig1")
print("Fig1 written")
