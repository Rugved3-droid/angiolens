"""Shared inputs for the paper's verification experiments (paper/scripts/e*.py).

Everything here is READ from the repository or its git-ignored atlas assets; nothing is tuned.
  * Named views: the values the apps ship (web/src/atlasHero.ts CARM_VIEWS, web/src/main.ts PRESETS).
  * Centerlines: Z-Anatomy coronary splines as evaluated by Blender (assets/anatomy/inspect/great_vessels_probe.json),
    LPS mm (CONVENTIONS sec. 10). Git-ignored (CC BY-SA 4.0 atlas data); regenerate with preprocess/blender/probe_great_vessels.py.
  * Isocenter and detector: web/public/anatomy/atlas_xray.json and web/src/cathLab.ts (detectorMm = 250, 512 px).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper"
RESULTS = PAPER / "results"
RAW = RESULTS / "raw"            # git-ignored: atlas-derived binaries (renders, masks)
sys.path.insert(0, str(ROOT / "preprocess"))

PROBE = ROOT / "assets" / "anatomy" / "inspect" / "great_vessels_probe.json"
XRAY_JSON = ROOT / "web" / "public" / "anatomy" / "atlas_xray.json"
DETECTOR_MM = 250.0              # web/src/cathLab.ts:65
DETECTOR_PX = 512                # web/src/cathLab.ts:99
SEED = 20261114                  # fixed seed for every randomised step

# (name, alpha LAO+, beta CRAN+, source in the code). The prompt's seven named views, with the values the apps use.
NAMED_VIEWS = [
    ("RAO caudal", -30, -25, "atlasHero.ts:927 raocaud; main.ts:25"),
    ("RAO cranial", -30, 30, "main.ts:26"),
    ("AP cranial", 0, 35, "main.ts:27"),
    ("AP caudal", 0, -30, "main.ts:29"),
    ("LAO cranial", 40, 30, "main.ts:28"),
    ("LAO caudal (spider)", 40, -30, "atlasHero.ts:928 spider (atlas app)"),
    ("LAO caudal (spider, classic)", 45, -30, "main.ts:29 'LAO caudal (spider)' (classic CT app)"),
    ("Left lateral", 90, 0, "alpha range end, geometry.ts:9"),
    ("RAO 30", -30, 0, "atlasHero.ts:925; main.ts:32"),
    ("LAO 45", 45, 0, "atlasHero.ts:926; main.ts:31"),
]

LEFT_CURVES = ["Left coronary artery", "Anterior interventricular artery", "Circumflex artery of heart",
               "Septal branches of anterior interventricular artery"]
RIGHT_CURVES = ["Right coronary artery", "Right inferolateral branch of right coronary artery"]


def angle_grid(step=5):
    """LAO/RAO -90..90 x CRAN/CAUD -45..45 in `step` degree steps (both ends included)."""
    a = np.arange(-90, 91, step)
    b = np.arange(-45, 46, step)
    return a, b


def isocenter() -> np.ndarray:
    return np.array(json.loads(XRAY_JSON.read_text())["isocenter_LPS"], float)


def centerlines():
    """List of (tree, curve, spline index, (n,3) LPS mm) for every atlas coronary spline."""
    p = json.loads(PROBE.read_text())
    out = []
    for tree, names in (("left", LEFT_CURVES), ("right", RIGHT_CURVES)):
        for n in names:
            for i, s in enumerate(p["curves"][n]["splines"]):
                out.append((tree, n, i, np.array(s["centreline"], float)))
    return out


def all_points() -> np.ndarray:
    return np.vstack([c[3] for c in centerlines()])


def environment() -> dict:
    import platform
    return {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()}
