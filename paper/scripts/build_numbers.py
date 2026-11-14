"""Collect every number the manuscript quotes, from the result files only, with its source (file + field/row).

    .venv\\Scripts\\python paper\\scripts\\build_numbers.py

Writes paper/results/numbers.json: {key: {"value": raw, "text": formatted as printed, "source": "file :: field"}}.
The manuscript template (paper/manuscript/*.md) may only print numbers through {{key}} placeholders that resolve here;
paper/scripts/build_manuscript.py fails on any unknown key, and paper/AUDIT.md is generated from the keys actually used.
"""
from __future__ import annotations

import csv
import json

import numpy as np

from common import RESULTS

N = {}


def put(key, value, text, source):
    N[key] = {"value": value, "text": text, "source": source}


def rows(path):
    return list(csv.DictReader(open(RESULTS / path, encoding="utf-8")))


def js(path):
    return json.loads((RESULTS / path).read_text(encoding="utf-8"))


def sci(x, d=1):
    m, e = f"{x:.{d}e}".split("e")
    return f"{m} × 10^{str(int(e)).replace('-', '−')}^"   # ^...^ = superscript; true minus sign


# ---------------- E1 ----------------
m1 = js("e1/e1_meta.json")
put("e1_grid_poses", m1["n_grid_poses"], f"{m1['n_grid_poses']}", "e1/e1_meta.json :: n_grid_poses")
put("e1_named", m1["n_named_views"], f"{m1['n_named_views']}", "e1/e1_meta.json :: n_named_views")
put("e1_poses_total", m1["n_grid_poses"] + m1["n_named_views"], f"{m1['n_grid_poses'] + m1['n_named_views']}", "e1/e1_meta.json :: n_grid_poses + n_named_views")
put("e1_points", m1["n_points"], f"{m1['n_points']:,}", "e1/e1_meta.json :: n_points")
put("pixel_mm", m1["pixel_mm"], f"{m1['pixel_mm']:.3f}", "e1/e1_meta.json :: pixel_mm")
s1 = {(r["scope"], r["path"]): r for r in rows("e1/e1_summary.csv")}
for path in ("overlay", "vertex"):
    r = s1[("grid_5deg", path)]
    put(f"e1_{path}_max_px", float(r["max_px"]), sci(float(r["max_px"])), f"e1/e1_summary.csv :: grid_5deg,{path},max_px")
    put(f"e1_{path}_median_px", float(r["median_px"]), sci(float(r["median_px"])), f"e1/e1_summary.csv :: grid_5deg,{path},median_px")
    put(f"e1_{path}_p95_px", float(r["p95_px"]), sci(float(r["p95_px"])), f"e1/e1_summary.csv :: grid_5deg,{path},p95_px")
    put(f"e1_{path}_max_pct", float(r["max_pct_detector_width"]), sci(float(r["max_pct_detector_width"])),
        f"e1/e1_summary.csv :: grid_5deg,{path},max_pct_detector_width")
v = float(s1[("grid_5deg", "vertex")]["max_px"]) * m1["pixel_mm"] * 1000
put("e1_vertex_max_um", v, f"{v:.2f}", "e1/e1_summary.csv vertex max_px x e1_meta pixel_mm x 1000 (um at the detector)")

# ---------------- E1b ----------------
p1b = rows("e1b/e1b_per_pose.csv")
m1b = js("e1b/e1b_meta.json")
put("e1b_images", len(p1b), f"{len(p1b):,}", "e1b/e1b_per_pose.csv :: row count")
for key, col, fmt, agg in (("e1b_r_min", "r", "{:.5f}", min), ("e1b_mae_max", "mae_mm", "{:.4f}", max),
                           ("e1b_centroid_max", "centroid_shift_px", "{:.3f}", max), ("e1b_iou_min", "mask_iou", "{:.4f}", min),
                           ("e1b_mirror_lr_max", "r_mirror_lr", "{:.3f}", max), ("e1b_mirror_ud_max", "r_mirror_ud", "{:.3f}", max)):
    x = agg(float(r[col]) for r in p1b)
    put(key, x, fmt.format(x), f"e1b/e1b_per_pose.csv :: {agg.__name__}({col})")
npass = sum(float(r["r"]) > 0.95 and float(r["mae_mm"]) < 0.25 for r in p1b)
put("e1b_pass", npass, f"{npass:,}", "e1b/e1b_per_pose.csv :: count(r > 0.95 and mae_mm < 0.25)")
nsens = sum(float(r["r_mirror_lr"]) < 0.6 and float(r["r_mirror_ud"]) < 0.6 for r in p1b)
put("e1b_mirror_rejected", nsens, f"{nsens:,}", "e1b/e1b_per_pose.csv :: count(r_mirror_lr < 0.6 and r_mirror_ud < 0.6)")
worst = max(p1b, key=lambda r: float(r["r_mirror_lr"]))
put("e1b_mirror_lr_worst_pose", f"{worst['tree']} {worst['alpha']},{worst['beta']}",
    f"{'RAO' if int(worst['alpha']) < 0 else 'LAO'} {abs(int(worst['alpha']))} / {'CRAN' if int(worst['beta']) > 0 else 'CAUD'} {abs(int(worst['beta']))}",
    "e1b/e1b_per_pose.csv :: argmax(r_mirror_lr)")
put("e1b_gpu", m1b["gpu"], "Intel UHD Graphics" if "Intel" in m1b["gpu"] else m1b["gpu"], "e1b/e1b_meta.json :: gpu")
put("chromium", m1b["chromium"], m1b["chromium"], "e1b/e1b_meta.json :: chromium")

# ---------------- E2 (v1 and v2) ----------------
for ph, d in (("v1", "e2"), ("v2", "e2_v2")):
    t = rows(f"{d}/e2_tests.csv")
    meta = js(f"{d}/e2_meta.json")["summary"]
    put(f"e2_{ph}_pass", meta["correct"]["passed"], f"{meta['correct']['passed']}", f"{d}/e2_meta.json :: summary.correct.passed")
    put(f"e2_{ph}_views", meta["correct"]["views"], f"{meta['correct']['views']}", f"{d}/e2_meta.json :: summary.correct.views")
    for k in ("mirror_lr", "swap_lao_rao", "swap_cran_caud", "mirror_ud"):
        put(f"e2_{ph}_{k}_det", meta[k]["detected"], f"{meta[k]['detected']}", f"{d}/e2_meta.json :: summary.{k}.detected")
        put(f"e2_{ph}_{k}_app", meta[k]["applicable"], f"{meta[k]['applicable']}", f"{d}/e2_meta.json :: summary.{k}.applicable")
    corr = [r for r in t if r["render"] == "correct" and r["test_pass"] == "True"]
    put(f"e2_{ph}_iou_min", min(float(r["iou"]) for r in corr), f"{min(float(r['iou']) for r in corr):.3f}",
        f"{d}/e2_tests.csv :: min(iou) over passing correct renders")
    me = max(float(r["max_centroid_err_px"]) for r in corr)
    put(f"e2_{ph}_err_max_px", me, f"{me:.2f}", f"{d}/e2_tests.csv :: max(max_centroid_err_px) over passing correct renders")
    put(f"e2_{ph}_err_max_mm", me * m1["pixel_mm"], f"{me * m1['pixel_mm']:.2f}", f"{d}/e2_tests.csv max_centroid_err_px x pixel_mm")
    neg = [float(r["iou"]) for r in t if r["render"] != "correct" and r["applicable"] == "True"
           and not (ph == "v1" and "classic" in r["view"])]
    put(f"e2_{ph}_neg_iou_max", max(neg), f"{max(neg):.3f}", f"{d}/e2_tests.csv :: max(iou) over applicable negative controls"
        + (" (v1: excluding the classic spider view)" if ph == "v1" else ""))
    if ph == "v1":
        cs = [r for r in t if r["render"] == "correct" and "classic" in r["view"]][0]
        put("e2_v1_overlap_iou", float(cs["iou"]), f"{float(cs['iou']):.3f}", "e2/e2_tests.csv :: classic spider, correct, iou")
        put("e2_v1_overlap_components", int(cs["n_components"]), cs["n_components"], "e2/e2_tests.csv :: classic spider, correct, n_components")
hand = [r for r in rows("e2_v2/e2_views.csv") if r["handedness_ok"] in ("True", "False")]
put("e2_v2_hand_ok", sum(r["handedness_ok"] == "True" for r in hand), f"{sum(r['handedness_ok'] == 'True' for r in hand)}",
    "e2_v2/e2_views.csv :: count(handedness_ok == True)")
put("e2_v2_hand_n", len(hand), f"{len(hand)}", "e2_v2/e2_views.csv :: count(handedness_ok in True/False)")

# ---------------- E3 ----------------
s3 = js("e3/e3_summary.json")
L = s3["logic"]
put("e3_logic_sets", L["sets"], f"{L['sets']:,}", "e3/e3_summary.json :: logic.sets")
put("e3_logic_ok", L["ok"], f"{L['ok']:,}", "e3/e3_summary.json :: logic.ok")
put("e3_logic_targets", L["targets"], f"{L['targets']:,}", "e3/e3_summary.json :: logic.targets")
put("e3_logic_threw", L["threw"], f"{L['threw']}", "e3/e3_summary.json :: logic.threw")
put("e3_draws_degenerate", L["drawPoseDegenerate"], f"{L['drawPoseDegenerate']}", "e3/e3_summary.json :: logic.drawPoseDegenerate")
put("e3_items", s3["rendered_items"], f"{s3['rendered_items']}", "e3/e3_summary.json :: rendered_items")
put("e3_flow_rounds", s3["items_by_mode"]["flow"], f"{s3['items_by_mode']['flow']}", "e3/e3_summary.json :: items_by_mode.flow")
put("e3_preset_items", s3["items_by_mode"]["preset"], f"{s3['items_by_mode']['preset']}", "e3/e3_summary.json :: items_by_mode.preset")
put("e3_candidates", s3["labels"]["candidates"], f"{s3['labels']['candidates']:,}", "e3/e3_summary.json :: labels.candidates")
put("e3_label_ok", s3["labels"]["label_is_best_match"], f"{s3['labels']['label_is_best_match']:,}", "e3/e3_summary.json :: labels.label_is_best_match")
put("e3_r_label_min", s3["labels"]["r_label_min"], f"{s3['labels']['r_label_min']:.5f}", "e3/e3_summary.json :: labels.r_label_min")
mg = [float(r["margin_min"]) for r in rows("e3/e3_margins.csv") if r["margin_min"]]
put("e3_margin_min", min(mg), f"{min(mg):.2f}", "e3/e3_margins.csv :: min(margin_min) over all_hypotheses_distinct")
put("e3_pairs", s3["pairs"], f"{s3['pairs']:,}", "e3/e3_summary.json :: pairs")
for k in ("median", "p95", "max"):
    put(f"e3_iou_{k}", s3["iou_all"][k], f"{s3['iou_all'][k]:.3f}", f"e3/e3_summary.json :: iou_all.{k}")
put("e3_ssim_min", s3["ssim_all"]["min"], f"{s3['ssim_all']['min']:.2f}", "e3/e3_summary.json :: ssim_all.min")
put("e3_ssim_max", s3["ssim_all"]["max"], f"{s3['ssim_all']['max']:.2f}", "e3/e3_summary.json :: ssim_all.max")
put("e3_tau_min", s3["tau_5deg"]["min"], f"{s3['tau_5deg']['min']:.3f}", "e3/e3_summary.json :: tau_5deg.min")
put("e3_tau_max", s3["tau_5deg"]["max"], f"{s3['tau_5deg']['max']:.3f}", "e3/e3_summary.json :: tau_5deg.max")
put("e3_tau_median", s3["tau_5deg"]["median"], f"{s3['tau_5deg']['median']:.3f}", "e3/e3_summary.json :: tau_5deg.median")
put("e3_flagged", s3["flagged_5deg"], f"{s3['flagged_5deg']}", "e3/e3_summary.json :: flagged_5deg")
put("e3_flagged_09", s3["flagged_iou_0.9"], f"{s3['flagged_iou_0.9']}", "e3/e3_summary.json :: flagged_iou_0.9")
gap = min(float(r["tau_5deg_iou"]) - float(r["iou"]) for r in rows("e3/e3_pairs.csv"))
put("e3_tau_gap_min", gap, f"{gap:.3f}", "e3/e3_pairs.csv :: min(tau_5deg_iou - iou) over all pairs")
put("e3_tiles_identical_correct", s3["correct_tile_byte_identical"], f"{s3['correct_tile_byte_identical']}", "e3/e3_summary.json :: correct_tile_byte_identical")
put("e3_tiles_identical_all", s3["all_tiles_byte_identical"], f"{s3['all_tiles_byte_identical']}", "e3/e3_summary.json :: all_tiles_byte_identical")
it = rows("e3/e3_items.csv")
diff = [int(r["max_tile_bytes_differ_any"]) for r in it if int(r["max_tile_bytes_differ_any"]) > 0]
put("e3_tile_diff_items", len(diff), f"{len(diff)}", "e3/e3_items.csv :: count(max_tile_bytes_differ_any > 0)")
put("e3_tile_diff_min_bytes", min(diff), f"{min(diff)}", "e3/e3_items.csv :: min(max_tile_bytes_differ_any > 0)")
put("e3_tile_diff_max_bytes", max(diff), f"{max(diff)}", "e3/e3_items.csv :: max(max_tile_bytes_differ_any)")
put("e3_correct_iou_cpu_min", s3["correct_vs_cpu_iou_min"], f"{s3['correct_vs_cpu_iou_min']:.4f}", "e3/e3_summary.json :: correct_vs_cpu_iou_min")
pr = js("e3/e3_tile_probe.json")
put("probe_tiles", pr["tilesCompared"], f"{pr['tilesCompared']:,}", "e3/e3_tile_probe.json :: tilesCompared")
put("probe_tiles_diff", pr["tilesDiffering"], f"{pr['tilesDiffering']}", "e3/e3_tile_probe.json :: tilesDiffering")
put("probe_repeats", 5 * pr["tilesCompared"], f"{5 * pr['tilesCompared']:,}", "e3/e3_tile_probe.json :: 5 x tilesCompared (5 repeat renders per tile)")
put("probe_repeats_diff", pr["repeatRendersDiffering"], f"{pr['repeatRendersDiffering']}", "e3/e3_tile_probe.json :: repeatRendersDiffering")
dv = max(abs(p["dv"]) for f in pr["findings"] for p in f["pixels"])
put("probe_max_dv", dv, f"{dv}", "e3/e3_tile_probe.json :: max |dv| over findings.pixels")
vess = sum(p["vessel"] for f in pr["findings"] for p in f["pixels"])
put("probe_vessel_px", vess, f"{vess}", "e3/e3_tile_probe.json :: count(pixels.vessel) over findings")

# ---------------- E5 ----------------
s5 = {r["config"]: r for r in rows("e5/e5_summary.csv")}
hw = js("e5/e5_hardware.json")
runs = rows("e5/e5_runs.csv")
for cfg, short in (("headless_gpu_d3d11", "igpu"), ("headless_swiftshader_cpu", "sw"), ("headed_discrete_gpu_d3d11", "dgpu")):
    if cfg not in s5:
        continue
    r = s5[cfg]
    for col, fmt in (("load_scene1_ms", "{:,.0f}"), ("load_scene4_ms", "{:,.0f}"), ("fps_median", "{:.1f}"), ("frame_p95_ms", "{:.1f}"),
                     ("js_heap_mb_after_rotation", "{:.1f}"), ("chromium_ws_mb_after_rotation", "{:,.0f}"), ("transfer_mb_scene4", "{:.0f}")):
        for stat in ("median", "min", "max"):
            x = float(r[f"{col}_{stat}"])
            put(f"e5_{short}_{col}_{stat}", x, fmt.format(x), f"e5/e5_summary.csv :: {cfg},{col}_{stat}")
    for col in ("load_scene1_ms", "load_scene4_ms"):
        x = float(r[f"{col}_median"]) / 1000
        put(f"e5_{short}_{col}_s", x, f"{x:.1f}", f"e5/e5_summary.csv :: {cfg},{col}_median / 1000")
    g = sorted({x["gpu"] for x in runs if x["config"] == cfg})
    put(f"e5_{short}_gpu", g, "; ".join(g), f"e5/e5_runs.csv :: gpu for {cfg}")
put("hw_cpu", hw["cpu"], hw["cpu"].replace("(R)", "").replace("(TM)", "").replace(" CPU", ""), "e5/e5_hardware.json :: cpu")
put("hw_ram", hw["ram_gb"], f"{hw['ram_gb']:.0f}", "e5/e5_hardware.json :: ram_gb")
put("hw_os", hw["os"], "Windows 11", "e5/e5_hardware.json :: os")
put("e5_reps", hw["reps"], f"{hw['reps']}", "e5/e5_hardware.json :: reps")
put("e5_seconds", hw["rotation_seconds"], f"{hw['rotation_seconds']}", "e5/e5_hardware.json :: rotation_seconds")

# ---------------- Fig. 5 tile order ----------------
NM = {"correct": "correct", "alpha-flip": "LAO/RAO reversed", "beta-flip": "cranial/caudal reversed", "both-flip": "both reversed",
      "mirror-lr": "left-right mirror", "mirror-ud": "up-down mirror"}
f5 = json.loads((RESULTS / "raw" / "fig5_tiles.json").read_text())
order = ", ".join(f"{'abcd'[k]} {NM[c['kind']]}" for k, c in enumerate(f5["cands"]))
put("fig5_order", [c["kind"] for c in f5["cands"]], order, "results/raw/fig5_tiles.json :: cands[].kind (written by fig_capture.mjs)")

# ---------------- repository facts ----------------
put("tests_pytest", 393, "393", "paper/inventory.md sec. 4 (npm run verify log, 2026-11-14): pytest 393 passed")
put("tests_vitest", 65, "65", "paper/inventory.md sec. 4: vitest 65 passed")
put("tests_e2e", 11, "11", "paper/inventory.md sec. 4: 11 browser suites")

(RESULTS / "numbers.json").write_text(json.dumps(N, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print(f"{len(N)} numbers written to paper/results/numbers.json")
