"""Phase 0 sanity sheet on the Z-Anatomy atlas coronaries (D49), before any atlas X-ray reaches the browser.

    .venv\\Scripts\\python preprocess\\scripts\\phase0_atlas.py          # needs build_atlas_xray.py first

Same views, same geometry, same figure code as the ASOCA Phase 0 (phase0_case.py). The renderer is the exact CPU mesh
renderer (cpt/meshrender.py) on the closed atlas trees, with the thoracic skeleton added faintly. Expected, checked by eye:
  * RCA: a "C" in LAO 45 and an "L" in RAO 30;
  * left tree: the spider view (LAO 40 / CAUD 30) opens the LM bifurcation;
  * the spine is on the screen-LEFT of the heart in RAO 30 and on the screen-RIGHT in LAO 45.
The spine flip and "superior stays up" are also computed and written to out/phase0/atlas/checks.json (the run fails if
either is wrong). No image is mirrored or rotated anywhere.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))
from cpt.figures import save_sheet, save_single  # noqa: E402
from cpt.geometry import CArm  # noqa: E402
from cpt.glb import read_glb  # noqa: E402
from cpt.meshrender import mesh_thickness_image  # noqa: E402
from cpt.render import DetectorGrid  # noqa: E402
from cpt.views import PHASE0_VIEWS  # noqa: E402

A = ROOT / "assets" / "anatomy"
K_VESSEL, K_BONE = 0.35, 0.012           # same attenuation constants as the browser angiogram (angio.ts)


def load(name):
    g = read_glb(A / f"atlas_xray_{name}.glb")
    return g["POSITION"].astype(float), g["indices"].astype(np.int64)


def main():
    meta = json.loads((A / "atlas_xray.json").read_text())
    iso = np.array(meta["isocenter_LPS"])
    trees = {t: load(t) for t in ("left", "right")}
    VB, FB = load("bone")
    VH, FH = load("heart")
    out = ROOT / "out" / "phase0" / "atlas"
    out.mkdir(parents=True, exist_ok=True)
    grid = DetectorGrid(size_mm=250, n=500)
    footer = (f"Z-Anatomy atlas (CC BY-SA 4.0), atlas radii | SID 1000 / SOD 750 mm | isocenter = both-tree volume centroid "
              f"({', '.join(f'{x:.1f}' for x in iso)}) LPS | exact mesh path length; skeleton faint | no display flips")
    # landmarks for the automatic checks: spine = vertebral bodies T4-T8 (the skeleton GLB), heart = chamber centroid
    import trimesh
    sc = trimesh.load(A / "z_anatomy_skeleton.glb", process=False)
    spine = np.vstack([sc.geometry[sc.graph[f"Vertebra T{i}"][1]].vertices for i in range(4, 9)]).mean(0)
    heart_c = VH.mean(0)
    checks = {"isocenter_LPS": iso.tolist(), "spine_T4_T8_centroid_LPS": spine.round(1).tolist(),
              "heart_centroid_LPS": heart_c.round(1).tolist(), "views": {}}
    for tree in ("left", "right"):
        V, F = trees[tree]
        panels = []
        for a, b in PHASE0_VIEWS[tree]:
            c = CArm(a, b, iso)
            tv, sv = mesh_thickness_image(c, V, F, grid)
            tb, sbn = mesh_thickness_image(c, VB, FB, grid)
            t = tv + (K_BONE / K_VESSEL) * tb      # draw_view applies exp(-K_VESSEL t)
            title = f"ATLAS {tree.upper()} tree | {c.label}"
            save_single(out / f"{tree}_{c.label.replace(' / ', '_').replace(' ', '')}.png", t, c, grid, title, footer)
            panels.append((t, c, title))
            (sx, sy), (hx, hy) = c.project(spine)[0], c.project(heart_c)[0]
            up = c.project(iso + [0, 0, 50.0])[0][1] - c.project(iso)[0][1]
            checks["views"][f"{tree} {c.label}"] = {"spine_minus_heart_screen_x_mm": round(float(sx - hx), 1),
                                                    "superior_projects_up": bool(up > 0),
                                                    "vessel_render": sv, "bone_unpaired_pixels": sbn["unpaired_pixels"]}
            print("rendered", title, sv)
        save_sheet(out / f"{tree}_sheet.png", panels, grid, f"Z-Anatomy atlas: {tree.upper()} coronary tree", footer,
                   ncols=len(panels) if len(panels) <= 3 else 3)
    rao, lao = checks["views"]["right RAO 30"], checks["views"]["right LAO 45"]
    checks["spine_left_of_heart_in_RAO30"] = rao["spine_minus_heart_screen_x_mm"] < 0
    checks["spine_right_of_heart_in_LAO45"] = lao["spine_minus_heart_screen_x_mm"] > 0
    checks["superior_up_in_every_view"] = all(v["superior_projects_up"] for v in checks["views"].values())
    (out / "checks.json").write_text(json.dumps(checks, indent=1))
    ok = checks["spine_left_of_heart_in_RAO30"] and checks["spine_right_of_heart_in_LAO45"] and checks["superior_up_in_every_view"]
    print("CHECKS", "PASS" if ok else "FAIL", {k: checks[k] for k in ("spine_left_of_heart_in_RAO30", "spine_right_of_heart_in_LAO45",
                                                                    "superior_up_in_every_view")})
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
