"""Shared figure style for IJCARS: Arial 8 pt, lines >= 0.5 pt, 174 mm (single-column) width, RGB, grayscale-safe."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
FIG = ROOT / "paper" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
MM = 1 / 25.4
W_FULL = 174 * MM
W_HALF = 84 * MM

plt.rcParams.update({
    "font.family": "Arial", "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 8,
    "ytick.labelsize": 8, "legend.fontsize": 8, "axes.linewidth": 0.6, "lines.linewidth": 1.0, "xtick.major.width": 0.6,
    "ytick.major.width": 0.6, "ps.fonttype": 42, "pdf.fonttype": 42, "savefig.facecolor": "white",
})


def panel(ax, letter, x=-0.02, y=1.02):
    ax.text(x, y, letter, transform=ax.transAxes, fontsize=10, fontweight="bold", va="bottom", ha="right")


def save_raster(fig, name, dpi):
    """TIFF (RGB, 8 bit/channel, LZW) at the IJCARS resolution + a PNG preview for the manuscript body."""
    from PIL import Image
    png = FIG / f"{name}.png"
    fig.savefig(png, dpi=dpi)
    Image.open(png).convert("RGB").save(FIG / f"{name}.tif", compression="tiff_lzw", dpi=(dpi, dpi))
    return png


def save_vector(fig, name):
    """EPS (vector, preferred by Springer for line art) + a 1200 dpi TIFF fallback (Springer's line-art resolution) + PNG preview."""
    fig.savefig(FIG / f"{name}.eps")
    save_raster(fig, name, 1200)
    fig.savefig(FIG / f"{name}.png", dpi=600)
