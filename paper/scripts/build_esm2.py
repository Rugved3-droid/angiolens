"""ESM_2 (Online Resource 2): full verification tables and derivations, built from paper/results/ only, then converted to PDF
with Microsoft Word (paper/scripts/docx2pdf.ps1).

    .venv\\Scripts\\python paper\\scripts\\build_esm2.py
"""
import csv
import json
import subprocess
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "paper" / "results"
SUB = ROOT / "paper" / "submission"
TITLE = "AngioLens: an open-source, geometry-verified coronary angiography projection simulator for training"

d = Document()
s = d.sections[0]
s.page_height, s.page_width = Cm(29.7), Cm(21.0)
for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(s, side, Cm(2.0))
st = d.styles["Normal"]
st.font.name, st.font.size = "Times New Roman", Pt(9.5)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
st.paragraph_format.space_after = Pt(4)


def P(text, bold=False, size=None, italic=False):
    p = d.add_paragraph()
    r = p.add_run(text)
    r.bold, r.italic = bold, italic
    if size:
        r.font.size = Pt(size)
    return p


def H(text):
    h = d.add_heading(text, level=2)
    for r in h.runs:
        r.font.name, r.font.size, r.font.color.rgb = "Times New Roman", Pt(11), None


def T(caption, header, rows, src):
    P(caption, bold=True, size=9)
    t = d.add_table(rows=1 + len(rows), cols=len(header))
    t.style = d.styles["Table Grid"]
    for i, row in enumerate([header] + rows):
        for j, c in enumerate(row):
            cell = t.cell(i, j)
            cell.paragraphs[0].text = ""
            r = cell.paragraphs[0].add_run(str(c))
            r.font.size = Pt(7.5)
            r.bold = i == 0
            cell.paragraphs[0].paragraph_format.space_after = Pt(0)
    P(f"Source: {src}", italic=True, size=7.5)


def rows(path):
    return list(csv.DictReader(open(R / path, encoding="utf-8")))


def f(x, n=4):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return x
    return f"{v:.{n}g}" if abs(v) < 1e-2 and v != 0 else f"{v:.{n}f}".rstrip("0").rstrip(".") if "." in f"{v:.{n}f}" else f"{v:.{n}f}"


# ---------------- header required by the journal ----------------
P("Online Resource 2", bold=True, size=13)
P(TITLE, bold=True, size=12)
P("International Journal of Computer Assisted Radiology and Surgery")
P("Rugved Parmar, Md Fahim, Shreya P. Trivedi")
P("Corresponding author: Rugved Parmar, Department of Medicine, SUNY Downstate Health Sciences University / Kings County "
  "Hospital Center, Brooklyn, NY, USA. parmarrugved@gmail.com")
P("Content: full verification tables, the first-principles derivation used by E2, and the reproduction commands. Every value "
  "below is read from the result files named under each table (repository branch paper/ijcars-verification, folder "
  "paper/results/). AngioLens v1.1: https://github.com/Rugved3-droid/angiolens, tag v1.1, commit "
  "198c6d4da1f980cdaa301f5131ccb83ebffb5be1.", size=9)

# ---------------- S1 conventions and derivation ----------------
H("S1. Conventions and the first-principles derivation (E2)")
for t in [
    "Patient frame LPS (mm): +x patient left, +y posterior, +z superior; patient supine. Primary angle alpha: LAO positive; "
    "secondary angle beta: cranial positive (DICOM PS3.3 C.8.7.5). SID 1000 mm, source-isocenter distance 750 mm; detector "
    "250 mm, 512 pixels (0.488 mm per pixel).",
    "Derivation without the application's code. (1) At AP the detector is anterior, d0 = (0, -1, 0); the image is displayed as "
    "seen from the detector, head up, so screen right r0 = (1, 0, 0) (patient left) and screen up u0 = (0, 0, 1). (2) LAO alpha "
    "rotates the detector about z toward the patient's left: d1 = (sin a, -cos a, 0), r1 = (cos a, sin a, 0). (3) Cranial beta "
    "tilts the detector toward the head about r1: d = cos b d1 + sin b z, up = cos b z - sin b d1, r = r1. (4) Point source "
    "S = iso - 750 d, flat detector through iso + 250 d with normal d; screen x = SID (p-S).r / (p-S).d, "
    "y = SID (p-S).up / (p-S).d.",
    "Equivalence with the application's closed form: z - (z.d)d = cos b (cos b z - sin b d1), so normalize(z - (z.d)d) = up; "
    "and up x d = z x d1 = r1. Hence the application's v = normalize(z - (z.d)d), u = v x d is this rotation composition.",
    "Handedness: a letter drawn in the coronal plane (letter-right = +x, letter-up = +z) has on-screen handedness sign(cos a cos b), "
    "perspective removed: it reads normally for |alpha| < 90 deg and is edge-on at 90 deg. A mirror reverses it; an angle-sign swap "
    "does not, so swaps are detected by position.",
    "Decision rule (fixed before the first run): mask IoU >= 0.70; exactly 3 components, each centroid within 2.0 pixels of its "
    "prediction; for |alpha| < 90 deg each component matches its true glyph better than its mirror. Phantom 1 letter centres "
    "(mm from the isocenter): L (+60, -15, +25), R (-60, +20, +5), F (+5, -30, -55). Phantom 2: F moved to (+40, -25, -65), "
    "chosen analytically before rendering so that no two letters come within 5 pixels at any named view (closest gap 67 pixels).",
]:
    P(t)

# ---------------- E1 ----------------
H("S2. E1 projection agreement")
T("Table S1 E1 summary (713 poses x 3,413 centerline points)",
  ["Scope", "Path", "Poses", "Mean px", "Median px", "95th pct px", "Max px", "Max % detector width"],
  [[r["scope"], r["path"], r["n_poses"], r["mean_px"], r["median_px"], r["p95_px"], r["max_px"], r["max_pct_detector_width"]]
   for r in rows("e1/e1_summary.csv")], "e1/e1_summary.csv (e1_projection_agreement.py)")
T("Table S2 E1 per named view", ["View", "alpha", "beta", "Path", "Mean px", "Median px", "95th pct px", "Max px"],
  [[r["view"], r["alpha"], r["beta"], r["path"], r["mean_px"], r["median_px"], r["p95_px"], r["max_px"]]
   for r in rows("e1/e1_named_views.csv")], "e1/e1_named_views.csv")

# ---------------- E1b ----------------
H("S3. E1b rendered image agreement")
T("Table S3 E1b summary (GPU image vs exact CPU reference)",
  ["Scope", "Images", "r min", "MAE max mm", "Centroid shift max px", "IoU min", "Mirror L-R r max", "Mirror U-D r max", "Pass", "Mirror rejected"],
  [[r["scope"], r["n_images"], r["r_min"], r["mae_mm_max"], r["centroid_shift_px_max"], r["iou_min"], r["r_mirror_lr_max"],
    r["r_mirror_ud_max"], r["n_pass_r095_mae025"], r["n_mirror_r_below_0.6"]] for r in rows("e1b/e1b_summary.csv")],
  "e1b/e1b_summary.csv (e1b_render_agreement.py); per pose: e1b/e1b_per_pose.csv")

# ---------------- E2 ----------------
H("S4. E2 orientation phantom")
for ph, dirn in (("Phantom 1", "e2"), ("Phantom 2", "e2_v2")):
    T(f"Table S{4 if ph == 'Phantom 1' else 5} E2, {ph}: every view x render",
      ["View", "alpha", "beta", "Render", "IoU", "Components", "Max centroid err px", "IoU rule", "Position rule", "Handedness rule", "Outcome"],
      [[r["view"], r["alpha"], r["beta"], r["render"], f(r["iou"], 3), r["n_components"], f(r["max_centroid_err_px"], 2),
        r["pass_iou"], r["pass_position"], r["pass_handedness"], r["outcome"]] for r in rows(f"{dirn}/e2_tests.csv")],
      f"{dirn}/e2_tests.csv (e2_orientation.py{' --phantom=v2' if dirn == 'e2_v2' else ''})")
P("Phantom 1 failed rule (b) at LAO 45/caudal 30 because the R and F letters overlap in projection (2 components). The negative "
  "controls at that view are therefore uninformative and are excluded from the phantom-1 detection counts. Under mirrors and "
  "swaps, components match the wrong letters, so the handedness rule alone is not informative there; detections came from the "
  "IoU and position rules.", size=8.5)

# ---------------- E3 ----------------
H("S5. E3 Predict distractors")
s3 = json.loads((R / "e3" / "e3_summary.json").read_text(encoding="utf-8"))
L = s3["logic"]
T("Table S6 E3 option logic over every integer target (alpha -90..90 x beta -45..45; mirror setting off and on)",
  ["Targets", "Sets generated", "Sets valid", "Declined (|alpha|,|beta| < 5 deg)", "Declined outside that zone", "Degenerate targets in 100,000 draws"],
  [[L["targets"], L["sets"], L["ok"], L["threw"], L["threwOutsideDegenerate"], L["drawPoseDegenerate"]]], "e3/e3_summary.json :: logic")
T("Table S7 E3 pairwise similarity of binary vessel masks by pair type (612 items)",
  ["Pair type", "n", "IoU median", "IoU max", "SSIM median", "SSIM max", "Near-duplicate (5 deg rule)", "IoU >= 0.9"],
  [[k, v["iou"]["n"], f(v["iou"]["median"], 3), f(v["iou"]["max"], 3), f(v["ssim"]["median"], 3), f(v["ssim"]["max"], 3),
    v["flag_5deg"], v["flag_iou_0.9"]] for k, v in s3["by_pair_type"].items()],
  "e3/e3_summary.json :: by_pair_type (e3_distractors.py); per pair: e3/e3_pairs.csv")
P("SSIM (Wang et al. 2004; Gaussian window sigma 1.5, data range 1) lies between "
  f"{s3['ssim_all']['min']:.2f} and {s3['ssim_all']['max']:.2f} for every pair, related or not: vessel masks cover about 2% of "
  "the image, so SSIM is dominated by the shared empty background and does not discriminate. IoU is therefore the distinctness "
  "measure in the main text.", size=8.5)
T("Table S8 E3 label verification: each option's GPU vessel image vs exact references of all six hypotheses",
  ["Label", "Subset", "n", "Label best match", "Min margin r"],
  [[r["label"], r["subset"], r["n"], r["label_is_best_match"], r["margin_min"] or "(ties with an identical image)"]
   for r in rows("e3/e3_margins.csv")], "e3/e3_margins.csv (e3_margins.py)")
pr = json.loads((R / "e3" / "e3_tile_probe.json").read_text(encoding="utf-8"))
T("Table S9 E3 tile identity and the follow-up probe",
  ["Measure", "Value"],
  [["Items with correct tile byte-identical to an independent render", f"{s3['correct_tile_byte_identical']} / {s3['rendered_items']}"],
   ["Items with all four tiles byte-identical", f"{s3['all_tiles_byte_identical']} / {s3['rendered_items']}"],
   ["Probe: tiles compared / differing", f"{pr['tilesCompared']} / {pr['tilesDiffering']}"],
   ["Probe: repeat renders of the same pose differing", f"{pr['repeatRendersDiffering']} / {5 * pr['tilesCompared']}"],
   ["Probe: max grey-level difference; vessel pixels among differences",
    f"{max(abs(p['dv']) for x in pr['findings'] for p in x['pixels'])}; {sum(p['vessel'] for x in pr['findings'] for p in x['pixels'])}"]],
  "e3/e3_summary.json, e3/e3_items.csv, e3/e3_tile_probe.json (browser/e3_tile_probe.mjs)")

# ---------------- E5 ----------------
H("S6. E5 performance")
hw = json.loads((R / "e5" / "e5_hardware.json").read_text(encoding="utf-8"))
P(f"Hardware: {hw['cpu']}, {hw['cores']} cores / {hw['threads']} threads, {hw['ram_gb']} GB RAM, {hw['os']}; GPUs: "
  f"{'; '.join(hw['gpus'])}. Chromium {hw['chromium']}, Node {hw['node']}. {hw['served']}; {hw['reps']} repetitions; "
  f"rotation {hw['rotation_seconds']} s.")
T("Table S10 E5 per run (cold loads: every scene in a fresh browser context)",
  ["Config", "Rep", "GPU", "Load scene 1 ms", "Load scene 4 ms", "MB", "fps", "p95 frame ms", "Heap MB", "Chromium WS MB"],
  [[r["config"], r["rep"], r["gpu"].split("(")[1].split(",")[0] if "(" in r["gpu"] else r["gpu"], r["load_scene1_ms"],
    r["load_scene4_ms"], r["transfer_mb_scene4"], r["fps_median"], r["frame_p95_ms"], r["js_heap_mb_after_rotation"],
    r["chromium_ws_mb_after_rotation"]] for r in rows("e5/e5_runs.csv")], "e5/e5_runs.csv (browser/e5_performance.mjs)")
P("A first E5 run (paper/results/e5_v1_warm/) loaded scene 4 after scene 1 in the same browser context; it is superseded by the "
  "cold-load run above and is not used in the manuscript.", size=8.5)

# ---------------- reproduction ----------------
H("S7. Reproduction")
for t in ["git clone https://github.com/Rugved3-droid/angiolens; git checkout paper/ijcars-verification",
          "Build the git-ignored atlas assets with the repository pipeline (README), then: make paper  (or: python paper/scripts/make_paper.py)",
          "Individual experiments: paper/scripts/e1_projection_agreement.py, e1b_render_agreement.py, e2_orientation.py [--phantom=v2], "
          "e3_distractors.py, e3_margins.py, browser/e3_tile_probe.mjs, browser/e5_performance.mjs --headed=1"]:
    P(t, size=8.5)

out = SUB / "ESM_2.docx"
d.save(out)
subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "paper" / "scripts" / "docx2pdf.ps1"),
                str(out), str(SUB / "ESM_2.pdf")], check=True)
out.unlink()
print("ESM_2.pdf written")
