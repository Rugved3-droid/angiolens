"""E3. Distractor validity in Predict mode (atlas app).

    .venv\\Scripts\\python paper\\scripts\\e3_distractors.py [--rounds=300] [--gl=d3d11|swiftshader]

Predict items are generated, not stored: each round draws a target (a preset or a random pose, predict.ts drawPose) and builds
four candidates (makeCandidates). So "every item" is covered as (1) the candidate LOGIC over every integer target on the full
angle range with both mirror settings, and (2) RENDERED items: every preset target x mirror off/on, plus seeded rounds of the
real flow (answer -> C-arm moves -> next round) with the mirror toggle off and on.

Checks per rendered item
  (a) the correct tile is byte-identical to an independent render of the target pose (same renderer, same noise seed), and its
      vessel image matches the exact CPU reference (preprocess/cpt/meshrender.py) at the target pose;
  (b) the four candidates are distinct: pairwise IoU and SSIM of binary vessel masks (path length > 0). SSIM: Wang et al. 2004
      constants, Gaussian window sigma 1.5, data range 1 (skimage);
  (c) each distractor is the transformation it is labelled as: its GPU vessel image is correlated with CPU references of every
      hypothesis {correct, LAO/RAO flip, CRAN/CAUD flip, both flipped, left-right mirror, up-down mirror}; the label must be the
      best match. Margin = r(label) - best r(other hypothesis).
Near-duplicate threshold (per item, fixed before the run): a pair is flagged if its mask IoU is at least the HIGHEST IoU between
the correct view and the same view moved 5 degrees on one axis (alpha +-5 or beta +-5; CPU masks). Rationale: the app itself
treats targets within 5 degrees of 0 as producing the same image (predict.ts DEGENERATE_DEG = 5), so a pair at least as similar
as a 5 degree C-arm error is too close to count as a different answer. A fixed IoU >= 0.9 rule is reported alongside.

Writes paper/results/e3/: e3_items.csv, e3_pairs.csv, e3_labels.csv, e3_summary.json, e3_similarity.png.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from functools import lru_cache

import numpy as np
from skimage.metrics import structural_similarity

from common import RAW, RESULTS, ROOT, SEED, environment, isocenter
from cpt.geometry import ALPHA_RANGE_DEG, BETA_RANGE_DEG, CArm
from cpt.glb import read_glb
from cpt.meshrender import mesh_thickness_image
from cpt.render import DetectorGrid

OUT = RESULTS / "e3"
ANAT = ROOT / "web" / "public" / "anatomy"
FIXED_IOU = 0.9
KINDS = ["correct", "alpha-flip", "beta-flip", "both-flip", "mirror-lr", "mirror-ud"]


def corr(a, b):
    a = a - a.mean(); b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 1.0


def ssim(a, b):
    return float(structural_similarity(a.astype(float), b.astype(float), data_range=1.0, gaussian_weights=True,
                                       sigma=1.5, use_sample_covariance=False))


def main():
    args = dict(x.lstrip("-").split("=", 1) for x in sys.argv[1:] if "=" in x)
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if "--skip-browser" not in sys.argv:
        subprocess.run(["node", str(ROOT / "paper" / "scripts" / "browser" / "e3_browser.mjs"),
                        f"--rounds={args.get('rounds', 300)}", f"--seed={SEED}", f"--gl={args.get('gl', 'd3d11')}"], check=True)
    data = json.loads((RAW / "e3_items.json").read_text())
    logic = json.loads((RAW / "e3_logic.json").read_text())
    n = data["px"]
    iso = isocenter()
    assert np.allclose(iso, data["iso"], atol=1e-3)
    grid = DetectorGrid(data["detectorMm"], n)
    meshes = {t: read_glb(ANAT / f"atlas_xray_{t}.glb") for t in ("left", "right")}

    @lru_cache(maxsize=48)          # each entry is a 512x512 float64 image (2 MB); a large cache exhausted RAM on an 12 GB machine
    def cpu(tree, a, b):
        g = meshes[tree]
        th, _ = mesh_thickness_image(CArm(a, b, iso), g["POSITION"].astype(float), g["indices"].astype(np.int64), grid)
        th.setflags(write=False)
        return th

    def gpu(item_id, k):
        x = np.zeros(n * n, np.float32)
        x[np.fromfile(RAW / "e3_masks" / f"{item_id}_{k}.idx", "<i4")] = np.fromfile(RAW / "e3_masks" / f"{item_id}_{k}.val", "<f4")
        return x.reshape(n, n).astype(float)

    items_rows, pair_rows, label_rows = [], [], []
    for it in data["items"]:
        T = it["target"]; a, b, tree = T["alpha"], T["beta"], T["tree"]
        hyp = {"correct": cpu(tree, a, b), "alpha-flip": cpu(tree, -a, b), "beta-flip": cpu(tree, a, -b),
               "both-flip": cpu(tree, -a, -b)}
        hyp["mirror-lr"] = hyp["correct"][:, ::-1]
        hyp["mirror-ud"] = hyp["correct"][::-1, :]
        # 5 degree perturbation reference for the near-duplicate threshold
        pert = []
        for da, db in ((5, 0), (-5, 0), (0, 5), (0, -5)):
            if ALPHA_RANGE_DEG[0] <= a + da <= ALPHA_RANGE_DEG[1] and BETA_RANGE_DEG[0] <= b + db <= BETA_RANGE_DEG[1]:
                pert.append(iou(cpu(tree, a + da, b + db) > 0, hyp["correct"] > 0))
        tau = max(pert)
        G = [gpu(it["id"], k) for k in range(len(it["cands"]))]
        M = [g > 0 for g in G]
        kinds = [c["kind"] for c in it["cands"]]
        ci = kinds.index("correct")
        items_rows.append({"id": it["id"], "mode": it["mode"], "mirror_toggle": it["mirror"], "tree": tree, "alpha": a, "beta": b,
                           "source": T["source"], "kinds": "|".join(kinds),
                           "correct_tile_bytes_differ": it["cands"][ci]["tileBytesDiffer"],
                           "max_tile_bytes_differ_any": max(c["tileBytesDiffer"] for c in it["cands"]),
                           "correct_r_vs_cpu": corr(G[ci], hyp["correct"]), "correct_iou_vs_cpu": iou(M[ci], hyp["correct"] > 0),
                           "tau_5deg_iou": tau})
        for i in range(4):
            for j in range(i + 1, 4):
                v_iou, v_ssim = iou(M[i], M[j]), ssim(M[i], M[j])
                pair_rows.append({"id": it["id"], "mirror_toggle": it["mirror"], "alpha": a, "beta": b, "tree": tree,
                                  "kind_a": kinds[i], "kind_b": kinds[j], "with_correct": "correct" in (kinds[i], kinds[j]),
                                  "iou": v_iou, "ssim": v_ssim, "tau_5deg_iou": tau,
                                  "flag_5deg": v_iou >= tau, "flag_iou_0.9": v_iou >= FIXED_IOU})
        for k, c in enumerate(it["cands"]):
            rs = {h: corr(G[k], hyp[h]) for h in KINDS}
            best = max(rs, key=rs.get)
            others = max(v for h, v in rs.items() if h != c["kind"])
            label_rows.append({"id": it["id"], "alpha": a, "beta": b, "tree": tree, "label": c["kind"], "best_match": best,
                               "r_label": rs[c["kind"]], "margin": rs[c["kind"]] - others,
                               "second_best": max((h for h in KINDS if h != c["kind"]), key=rs.get),
                               "label_ok": best == c["kind"]})

    def write(path, rows):
        keys = list(rows[0].keys())
        with open(path, "w") as f:
            f.write(",".join(keys) + "\n")
            for r in rows:
                f.write(",".join(f"{r[k]:.6g}" if isinstance(r[k], float) else str(r[k]) for k in keys) + "\n")
    write(OUT / "e3_items.csv", items_rows)
    write(OUT / "e3_pairs.csv", pair_rows)
    write(OUT / "e3_labels.csv", label_rows)

    P = pair_rows
    def dist(sel, key):
        v = np.array([p[key] for p in sel])
        return {"n": int(len(v)), "min": float(v.min()), "median": float(np.median(v)), "p95": float(np.percentile(v, 95)),
                "max": float(v.max())} if len(v) else {"n": 0}
    by_pair = {}
    for p in P:
        by_pair.setdefault(" vs ".join(sorted((p["kind_a"], p["kind_b"]))), []).append(p)
    L = label_rows
    summary = {
        "logic": {k: logic[k] for k in ("targets", "sets", "ok", "threw", "threwOutsideDegenerate", "drawPoseDegenerate",
                                         "kindCount", "DEGENERATE_DEG")},
        "rendered_items": len(items_rows),
        "items_by_mode": {m: sum(r["mode"] == m for r in items_rows) for m in ("preset", "flow")},
        "correct_tile_byte_identical": sum(r["correct_tile_bytes_differ"] == 0 for r in items_rows),
        "all_tiles_byte_identical": sum(r["max_tile_bytes_differ_any"] == 0 for r in items_rows),
        "correct_vs_cpu_r_min": min(r["correct_r_vs_cpu"] for r in items_rows),
        "correct_vs_cpu_iou_min": min(r["correct_iou_vs_cpu"] for r in items_rows),
        "pairs": len(P),
        "iou_all": dist(P, "iou"), "ssim_all": dist(P, "ssim"),
        "iou_with_correct": dist([p for p in P if p["with_correct"]], "iou"),
        "ssim_with_correct": dist([p for p in P if p["with_correct"]], "ssim"),
        "by_pair_type": {k: {"iou": dist(v, "iou"), "ssim": dist(v, "ssim"), "flag_5deg": sum(x["flag_5deg"] for x in v),
                             "flag_iou_0.9": sum(x["flag_iou_0.9"] for x in v)} for k, v in sorted(by_pair.items())},
        "tau_5deg": dist(items_rows, "tau_5deg_iou"),
        "flagged_5deg": sum(p["flag_5deg"] for p in P), "flagged_5deg_with_correct": sum(p["flag_5deg"] and p["with_correct"] for p in P),
        "flagged_iou_0.9": sum(p["flag_iou_0.9"] for p in P),
        "labels": {"candidates": len(L), "label_is_best_match": sum(x["label_ok"] for x in L),
                   "r_label_min": min(x["r_label"] for x in L), "margin_min": min(x["margin"] for x in L),
                   "by_kind": {k: {"n": sum(x["label"] == k for x in L), "ok": sum(x["label_ok"] for x in L if x["label"] == k),
                                   "margin_min": min((x["margin"] for x in L if x["label"] == k), default=None)} for k in KINDS}},
        "runtime_s": round(time.time() - t0, 1), "chromium": data["chromium"], "seed": data["seed"], **environment(),
    }
    (OUT / "e3_summary.json").write_text(json.dumps(summary, indent=1))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 2, figsize=(6.85, 2.4), constrained_layout=True)
    types = sorted(by_pair)
    for ax, key, lab in ((axs[0], "iou", "a"), (axs[1], "ssim", "b")):
        vals = [[x[key] for x in by_pair[t]] for t in types]
        ax.boxplot(vals, vert=False, widths=0.6, flierprops={"marker": "x", "markersize": 3})
        ax.set_yticks(range(1, len(types) + 1), types if key == "iou" else [""] * len(types), fontsize=6)
        ax.set_xlabel(f"pairwise {key.upper()} of binary vessel masks", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_xlim(0, 1)
        ax.text(-0.02 if key == "ssim" else -0.75, 1.02, lab, transform=ax.transAxes, fontsize=10, fontweight="bold")
    fig.savefig(OUT / "e3_similarity.png", dpi=300)
    print(json.dumps({k: summary[k] for k in ("rendered_items", "correct_tile_byte_identical", "all_tiles_byte_identical",
                                              "correct_vs_cpu_r_min", "flagged_5deg", "flagged_5deg_with_correct",
                                              "flagged_iou_0.9", "labels")}, indent=1))


if __name__ == "__main__":
    main()
