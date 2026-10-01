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

# ---------------- Phase 2 metrics fixtures (synthetic vessels only) ----------------
from cpt.metrics import angle_maps, view_metrics  # noqa: E402


def tube(a, b, r, step=0.5):
    a, b = np.asarray(a, float), np.asarray(b, float)
    n = max(int(np.ceil(np.linalg.norm(b - a) / step)), 1)
    t = np.linspace(0, 1, n + 1)[:, None]
    return np.c_[a + t * (b - a), np.full(n + 1, r)]


miso = np.array([5.0, -3.0, -100.0])
target = np.vstack([tube(miso + [-20, 0, 0], miso + [10, 0, 5], 1.4), tube(miso + [10, 0, 5], miso + [25, 12, -10], 1.1)[1:],
                    tube(miso + [25, 12, -10], miso + [5, 20, -12], 0.9)[1:]])          # bends back: self-overlap possible
bif = np.array([miso + [10, 0, 5]])
others = [tube(miso + [10, 0, 5], miso + [12, -25, 20], 1.0), tube(miso + [-20, 0, 0], miso + [-5, 30, -20], 1.6),
          tube(miso + [0, 25, 10], miso + [30, 25, -20], 1.2)]
mcases = []
for a, b in [(0, 0), (-30, -25), (45, -30), (40, 30), (-90, 45), (17, -9)]:
    m = view_metrics(CArm(a, b, miso), target, bif, others)
    mcases.append({"alpha": a, "beta": b, **{k: m[k] for k in ("F", "O_inter", "O_self", "O_any")},
                   "inter_mask": m["inter_mask"].astype(int).tolist(), "self_mask": m["self_mask"].astype(int).tolist()})
maps = angle_maps(miso, target, bif, others, step=10)
mout = ROOT / "web" / "tests" / "fixtures" / "metrics.json"
mout.write_text(json.dumps({"isocenter": miso.tolist(), "target": target.round(6).tolist(), "bif": bif.tolist(),
                            "others": [o.round(6).tolist() for o in others], "cases": mcases,
                            "maps10": {"alpha": maps["alpha"].tolist(), "beta": maps["beta"].tolist(),
                                       **{k: maps[k].round(10).tolist() for k in ("F", "O_inter", "O_self", "O_any")}}}))
print("wrote", mout)
