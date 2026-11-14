"""E1b. Rendered-image agreement: the app's GPU angiogram (web/src/angio.ts) vs the exact CPU mesh renderer (preprocess/cpt/meshrender.py).

    .venv\\Scripts\\python paper\\scripts\\e1b_render_agreement.py [--gl=d3d11|swiftshader]

E1 compares point projections; this compares the IMAGES that reach the screen, so rasterisation, the float32 clip matrix,
the entry/exit path-length accumulation and the GL row flip are all inside the comparison.
Poses: the 5 degree grid of E1 plus the named views, each for the left and the right atlas tree (vessel path length only).
Per pose: Pearson r, mean |error| over pixels where either image is nonzero (the e2e suites' metric), path-length-weighted
centroid shift (px), binary-mask IoU (path length > 0), and r of the left-right and up-down MIRRORED GPU image against the
CPU image (the comparison must be able to tell a mirrored render).

Writes paper/results/e1b/: e1b_per_pose.csv, e1b_summary.csv, e1b_meta.json.  Raw images: paper/results/raw/ (git-ignored).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import numpy as np

from common import (DETECTOR_MM, DETECTOR_PX, NAMED_VIEWS, RAW, RESULTS, ROOT, angle_grid, environment, isocenter)
from cpt.geometry import CArm
from cpt.glb import read_glb
from cpt.meshrender import mesh_thickness_image
from cpt.render import DetectorGrid

OUT = RESULTS / "e1b"
ANAT = ROOT / "web" / "public" / "anatomy"


def corr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum()))


def centroid(img):
    r, c = np.indices(img.shape)
    w = img.sum()
    return np.array([(c * img).sum() / w, (r * img).sum() / w])


def main():
    gl = next((x.split("=", 1)[1] for x in sys.argv[1:] if x.startswith("--gl=")), "d3d11")
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    a, b = angle_grid(5)
    angles = [(int(x), int(y)) for y in b for x in a]
    angles += [(int(al), int(be)) for _, al, be, _ in NAMED_VIEWS if (int(al), int(be)) not in angles]
    poses = [(t, al, be) for t in ("left", "right") for al, be in angles]
    (RAW / "e1b_input.json").write_text(json.dumps({"poses": poses}))
    t0 = time.time()
    subprocess.run(["node", str(ROOT / "paper" / "scripts" / "browser" / "e1b_gpu.mjs"), f"--gl={gl}"], check=True)
    gmeta = json.loads((RAW / "e1b_gpu_meta.json").read_text())
    assert gmeta["px"] == DETECTOR_PX and gmeta["detectorMm"] == DETECTOR_MM, gmeta
    iso = isocenter()
    assert np.allclose(iso, gmeta["iso"], atol=1e-3), (iso, gmeta["iso"])
    rep = {(p["tree"], p["alpha"], p["beta"]): p["repaired"] for p in gmeta["poses"]}
    grid = DetectorGrid(DETECTOR_MM, DETECTOR_PX)
    meshes = {t: read_glb(ANAT / f"atlas_xray_{t}.glb") for t in ("left", "right")}
    n = DETECTOR_PX
    rows = []
    for tree, al, be in poses:
        g = meshes[tree]
        cpu, st = mesh_thickness_image(CArm(al, be, iso), g["POSITION"].astype(float), g["indices"].astype(np.int64), grid)
        gpu = np.zeros(n * n, np.float32)
        idx = np.fromfile(RAW / "e1b_gpu" / f"{tree}_{al}_{be}.idx", "<i4")
        gpu[idx] = np.fromfile(RAW / "e1b_gpu" / f"{tree}_{al}_{be}.val", "<f4")
        gpu = gpu.reshape(n, n).astype(float)
        union = (cpu > 0) | (gpu > 0)
        inter = (cpu > 0) & (gpu > 0)
        rows.append({
            "tree": tree, "alpha": al, "beta": be,
            "r": corr(gpu, cpu), "mae_mm": float(np.abs(gpu - cpu)[union].mean()),
            "centroid_shift_px": float(np.linalg.norm(centroid(gpu) - centroid(cpu))),
            "mask_iou": float(inter.sum() / union.sum()),
            "r_mirror_lr": corr(gpu[:, ::-1], cpu), "r_mirror_ud": corr(gpu[::-1, :], cpu),
            "cpu_pixels_hit": int((cpu > 0).sum()), "gpu_pixels_hit": int((gpu > 0).sum()),
            "gpu_repaired_px": rep[(tree, al, be)], "cpu_unpaired_px": st["unpaired_pixels"],
            "named": next((nm for nm, x, y, _ in NAMED_VIEWS if (x, y) == (al, be)), ""),
        })
    keys = list(rows[0].keys())
    with open(OUT / "e1b_per_pose.csv", "w") as f:
        f.write(",".join(keys) + "\n")
        for r in rows:
            f.write(",".join(f'"{r[k]}"' if isinstance(r[k], str) else (f"{r[k]:.6g}" if isinstance(r[k], float) else str(r[k])) for k in keys) + "\n")

    # the e2e acceptance rule (web/e2e/atlas_xray.e2e.mjs): r > 0.95, mae < 0.25 mm, mirrored r < 0.6
    def summ(sel, scope):
        R = np.array([r["r"] for r in sel]); M = np.array([r["mae_mm"] for r in sel])
        C = np.array([r["centroid_shift_px"] for r in sel]); I = np.array([r["mask_iou"] for r in sel])
        LR = np.array([r["r_mirror_lr"] for r in sel]); UD = np.array([r["r_mirror_ud"] for r in sel])
        ok = (R > 0.95) & (M < 0.25)
        sens = (LR < 0.6) & (UD < 0.6)
        return [scope, len(sel), f"{R.min():.4f}", f"{np.median(R):.4f}", f"{M.max():.4f}", f"{np.median(M):.4f}",
                f"{C.max():.3f}", f"{np.median(C):.3f}", f"{I.min():.4f}", f"{np.median(I):.4f}",
                f"{LR.max():.3f}", f"{UD.max():.3f}", int(ok.sum()), int(sens.sum())]
    hdr = ["scope", "n_images", "r_min", "r_median", "mae_mm_max", "mae_mm_median", "centroid_shift_px_max",
           "centroid_shift_px_median", "iou_min", "iou_median", "r_mirror_lr_max", "r_mirror_ud_max",
           "n_pass_r095_mae025", "n_mirror_r_below_0.6"]
    with open(OUT / "e1b_summary.csv", "w") as f:
        f.write(",".join(hdr) + "\n")
        grid_set = {(int(x), int(y)) for y in b for x in a}
        for tree in ("left", "right", "both"):
            sel = [r for r in rows if tree in ("both", r["tree"])]
            f.write(",".join(map(str, summ([r for r in sel if (r["alpha"], r["beta"]) in grid_set], f"grid_5deg_{tree}"))) + "\n")
            f.write(",".join(map(str, summ([r for r in sel if r["named"]], f"named_{tree}"))) + "\n")
    meta = {"gl_backend": gl, "gpu": gmeta["gpu"], "chromium": gmeta["chromium"], "n_images": len(rows),
            "runtime_s": round(time.time() - t0, 1), **environment()}
    (OUT / "e1b_meta.json").write_text(json.dumps(meta, indent=1))
    print(open(OUT / "e1b_summary.csv").read())


if __name__ == "__main__":
    main()
