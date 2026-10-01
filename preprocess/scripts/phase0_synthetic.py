"""Render the chiral orientation phantom at all Phase 0 views.

    python preprocess/scripts/phase0_synthetic.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))

import numpy as np

from cpt.figures import save_sheet
from cpt.geometry import CArm
from cpt.render import DetectorGrid, thickness_image
from cpt.synthetic import orientation_phantom
from cpt.views import PHASE0_VIEWS

OUT = ROOT / "out" / "phase0" / "synthetic"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    iso = np.zeros(3)
    vol, _ = orientation_phantom(iso)
    grid = DetectorGrid(size_mm=200, n=400)
    views = sorted(set(PHASE0_VIEWS["left"] + PHASE0_VIEWS["right"]))
    panels = []
    for a, b in views:
        c = CArm(a, b, iso)
        panels.append((thickness_image(c, vol, grid), c, c.label))
    save_sheet(OUT / "phantom_views.png", panels, grid,
               "Orientation phantom: trunk+ball -> patient LEFT, thick branch -> SUPERIOR, thin -> ANTERIOR",
               "Expected: AP ball right, superior branch up; RAO the anterior branch points right, "
               "LAO it points left. Glyph = projected patient L/P/S axes.")
    print("wrote", OUT / "phantom_views.png")


if __name__ == "__main__":
    main()
