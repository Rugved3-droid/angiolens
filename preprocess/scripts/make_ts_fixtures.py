"""Cross-language fixtures: Python geometry outputs for synthetic points (no patient data).

    python preprocess/scripts/make_ts_fixtures.py   -> web/tests/fixtures/geometry.json
The TypeScript tests must reproduce these numbers.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))

import numpy as np

from cpt.geometry import CArm, foreshortening

rng = np.random.default_rng(42)
iso = np.array([25.237, -3.285, -106.703])
points = iso + rng.uniform(-90, 90, size=(25, 3))
cases = []
for a, b in [(0, 0), (-30, 0), (45, 0), (-30, -25), (40, -30), (-90, 45), (90, -45), (17.5, 33.3)]:
    c = CArm(a, b, iso)
    u, v = c.axes
    seg = points[:6]
    cases.append({
        "alpha": a, "beta": b, "d": c.d.tolist(), "u": u.tolist(), "v": v.tolist(),
        "source": c.source.tolist(), "detector_center": c.detector_center.tolist(),
        "screen": c.project(points).tolist(), "magnification": c.magnification(points).tolist(),
        "foreshortening_first6": foreshortening(seg, c.source), "label": c.label,
    })
out = ROOT / "web" / "tests" / "fixtures" / "geometry.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"isocenter": iso.tolist(), "points": points.tolist(), "cases": cases}, indent=1))
print("wrote", out)
