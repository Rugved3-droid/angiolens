"""E3 label margins, excluding hypotheses that are the SAME image as the label at that target.

    .venv\\Scripts\\python paper\\scripts\\e3_margins.py        (reads paper/results/e3/e3_labels.csv)

e3_distractors.py scores each candidate against all six hypotheses. When beta = 0, the "CRAN/CAUD flip" hypothesis (alpha, -0) is
the correct image itself, and "both flipped" is the LAO/RAO flip, so those labels tie at margin 0 with an identical image. The app
never offers such a flip (predict.ts replaces it with a mirror). The margin is therefore reported over targets with alpha != 0 and
beta != 0, where all six hypotheses are distinct images. Items with beta = 0 are counted separately; every label there was still
the best match (label_ok).
Writes paper/results/e3/e3_margins.csv.
"""
import csv

from common import RESULTS

rows = list(csv.DictReader(open(RESULTS / "e3" / "e3_labels.csv")))
out = {}
for r in rows:
    distinct = float(r["alpha"]) != 0 and float(r["beta"]) != 0
    k = (r["label"], "all_hypotheses_distinct" if distinct else "beta_or_alpha_zero")
    o = out.setdefault(k, {"n": 0, "ok": 0, "margin_min": None})
    o["n"] += 1
    o["ok"] += r["label_ok"] == "True"
    if distinct:
        m = float(r["margin"])
        o["margin_min"] = m if o["margin_min"] is None else min(o["margin_min"], m)
with open(RESULTS / "e3" / "e3_margins.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["label", "subset", "n", "label_is_best_match", "margin_min"])
    for (lab, sub), o in sorted(out.items()):
        w.writerow([lab, sub, o["n"], o["ok"], "" if o["margin_min"] is None else f"{o['margin_min']:.4f}"])
print(open(RESULTS / "e3" / "e3_margins.csv").read())
