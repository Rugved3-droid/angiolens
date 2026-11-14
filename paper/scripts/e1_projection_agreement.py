"""E1. Projection geometry agreement: browser (web/src/geometry.ts in Chromium) vs the Python reference (preprocess/cpt/geometry.py).

    .venv\\Scripts\\python paper\\scripts\\e1_projection_agreement.py

Poses: LAO/RAO -90..90 x CRAN/CAUD -45..45 in 5 degree steps (37 x 19 = 703), plus the named views (common.NAMED_VIEWS).
Points: every evaluated Z-Anatomy coronary centerline sample (both trees), LPS mm, the app's isocenter.
Reference: CArm.project -> DetectorGrid(250 mm, 512 px).screen_to_pixel, float64.
Browser:   'overlay' = CArm.project + screenToPixel (float64); 'vertex' = clipMatrix in float32 (the GPU vertex path).
Discrepancy = Euclidean 2D distance at the detector, in pixels and in % of detector width.

Writes paper/results/e1/: e1_per_pose.csv, e1_named_views.csv, e1_summary.csv, e1_heatmap.png, e1_meta.json.
"""
from __future__ import annotations

import json
import subprocess
import time

import numpy as np

from common import (DETECTOR_MM, DETECTOR_PX, NAMED_VIEWS, RAW, RESULTS, ROOT, all_points, angle_grid, environment,
                    isocenter)
from cpt.geometry import CArm
from cpt.render import DetectorGrid

OUT = RESULTS / "e1"


def stats(e):
    return {"mean": float(e.mean()), "median": float(np.median(e)), "p95": float(np.percentile(e, 95)), "max": float(e.max())}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    iso = isocenter()
    pts = all_points()
    a, b = angle_grid(5)
    grid_poses = [(int(x), int(y)) for y in b for x in a]
    named = [(int(al), int(be)) for _, al, be, _ in NAMED_VIEWS]
    poses = grid_poses + named
    (RAW / "e1_input.json").write_text(json.dumps({"poses": poses, "points": pts.tolist(), "iso": iso.tolist(),
                                                     "detector_mm": DETECTOR_MM, "detector_px": DETECTOR_PX}))
    t0 = time.time()
    subprocess.run(["node", str(ROOT / "paper" / "scripts" / "browser" / "e1_browser.mjs")], check=True)
    br = np.fromfile(RAW / "e1_browser.bin", "<f8").reshape(len(poses), len(pts), 4)

    g = DetectorGrid(DETECTOR_MM, DETECTOR_PX)
    px_mm = DETECTOR_MM / DETECTOR_PX
    rows, per = [], {}
    for k, (al, be) in enumerate(poses):
        rc = g.screen_to_pixel(CArm(al, be, iso).project(pts))          # (row, col)
        ref = np.stack([rc[:, 1], rc[:, 0]], axis=1)                     # (col, row)
        e_over = np.linalg.norm(br[k, :, 0:2] - ref, axis=1)
        e_vert = np.linalg.norm(br[k, :, 2:4] - ref, axis=1)
        inside = np.all((ref >= -0.5) & (ref <= DETECTOR_PX - 0.5), axis=1)
        per[(al, be)] = (e_over, e_vert)
        if k < len(grid_poses):
            rows.append((al, be, *[stats(e_over)[s] for s in ("mean", "median", "p95", "max")],
                         *[stats(e_vert)[s] for s in ("mean", "median", "p95", "max")], int(inside.sum())))
    hdr = ("alpha,beta,overlay_mean_px,overlay_median_px,overlay_p95_px,overlay_max_px,"
           "vertex_mean_px,vertex_median_px,vertex_p95_px,vertex_max_px,points_on_detector")
    np.savetxt(OUT / "e1_per_pose.csv", np.array(rows), delimiter=",", header=hdr, comments="", fmt="%.6g")

    def line(name, e_list):
        e = np.concatenate(e_list)
        s = stats(e)
        return [name] + [f"{s[x]:.3e}" for x in ("mean", "median", "p95", "max")] + [f"{100 * s['max'] * px_mm / DETECTOR_MM:.3e}"]

    with open(OUT / "e1_named_views.csv", "w") as f:
        f.write("view,alpha,beta,path,mean_px,median_px,p95_px,max_px,max_pct_detector_width\n")
        for (name, al, be, _), (a2, b2) in zip(NAMED_VIEWS, named):
            for j, path in enumerate(("overlay", "vertex")):
                f.write(f'"{name}",{al},{be},{path},' + ",".join(line("", [per[(a2, b2)][j]])[1:]) + "\n")
    with open(OUT / "e1_summary.csv", "w") as f:
        f.write("scope,path,n_poses,n_points_per_pose,mean_px,median_px,p95_px,max_px,max_pct_detector_width\n")
        for scope, keys in (("grid_5deg", grid_poses), ("named_views", named)):
            for j, path in enumerate(("overlay", "vertex")):
                f.write(f"{scope},{path},{len(set(keys))},{len(pts)}," + ",".join(line("", [per[k][j] for k in keys])[1:]) + "\n")

    # heatmap: max discrepancy per pose, vertex (float32 GPU) path, log10 px
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    M = np.array([[per[(int(x), int(y))][1].max() for x in a] for y in b])
    O = np.array([[per[(int(x), int(y))][0].max() for x in a] for y in b])
    fig, axs = plt.subplots(1, 2, figsize=(6.85, 2.6), constrained_layout=True)
    for ax, Z, ttl in ((axs[0], O, "a"), (axs[1], M, "b")):
        im = ax.imshow(np.log10(np.maximum(Z, 1e-16)), origin="lower", extent=[a[0] - 2.5, a[-1] + 2.5, b[0] - 2.5, b[-1] + 2.5],
                       aspect="auto", cmap="viridis")
        ax.set_xlabel("primary angle (deg; RAO < 0 < LAO)", fontsize=8)
        ax.set_ylabel("secondary angle (deg; CAUD < 0 < CRAN)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.text(-0.18, 1.02, ttl, transform=ax.transAxes, fontsize=10, fontweight="bold")
        for _, al, be, _ in NAMED_VIEWS:
            ax.plot(al, be, marker="o", mfc="none", mec="white", ms=4, mew=0.8)
        cb = fig.colorbar(im, ax=ax)
        cb.set_label("log10 max discrepancy (px)", fontsize=7)
        cb.ax.tick_params(labelsize=7)
    fig.savefig(OUT / "e1_heatmap.png", dpi=300)

    meta = {"n_grid_poses": len(grid_poses), "n_named_views": len(named), "n_points": int(len(pts)),
            "isocenter_LPS": iso.tolist(), "detector_mm": DETECTOR_MM, "detector_px": DETECTOR_PX, "pixel_mm": px_mm,
            "runtime_s": round(time.time() - t0, 1), **environment(),
            **json.loads((RAW / "e1_browser_meta.json").read_text())}
    (OUT / "e1_meta.json").write_text(json.dumps(meta, indent=1))
    print(open(OUT / "e1_summary.csv").read())


if __name__ == "__main__":
    main()
