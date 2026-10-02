"""Reference path-length images of the atlas trees for the browser check web/e2e/atlas_xray.e2e.mjs (D50).

    .venv\\Scripts\\python preprocess\\scripts\\atlas_xray_fixtures.py

Exact CPU mesh renderer (cpt/meshrender.py) on the same closed meshes the browser loads, on the browser's pixel grid
(512 px over 250 mm; row 0 = top). Written to web/public/anatomy/ (git-ignored): float32, little endian, row-major.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))
from cpt.geometry import CArm  # noqa: E402
from cpt.glb import read_glb  # noqa: E402
from cpt.meshrender import mesh_thickness_image  # noqa: E402
from cpt.render import DetectorGrid  # noqa: E402

WEB = ROOT / "web" / "public" / "anatomy"
POSES = [("left", 0, 0), ("left", -30, 0), ("left", 45, 0), ("left", -30, -25), ("left", 40, -30), ("right", 45, 0)]


def main():
    iso = np.array(json.loads((WEB / "atlas_xray.json").read_text())["isocenter_LPS"])
    grid = DetectorGrid(size_mm=250, n=512)
    index = []
    for tree, a, b in POSES:
        g = read_glb(WEB / f"atlas_xray_{tree}.glb")
        th, st = mesh_thickness_image(CArm(a, b, iso), g["POSITION"].astype(float), g["indices"].astype(np.int64), grid)
        name = f"xray_ref_{tree}_{a}_{b}.bin"
        th.astype("<f4").tofile(WEB / name)
        index.append({"tree": tree, "alpha": a, "beta": b, "file": name, "px": grid.n, "detector_mm": grid.size_mm, **st})
        print(name, st)
    (WEB / "xray_ref_index.json").write_text(json.dumps(index, indent=1))


if __name__ == "__main__":
    main()
