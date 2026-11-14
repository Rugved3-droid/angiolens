"""`make paper`: regenerate every result, figure and submission file of the IJCARS paper, in order, one GPU job at a time.

    .venv\\Scripts\\python paper\\scripts\\make_paper.py [--skip=e1,e1b,...] [--no-headed]

Prerequisites (git-ignored, built by the repository's own pipeline; see README "Reproducing the paper"):
web/public/anatomy/ (atlas X-ray meshes), assets/anatomy/inspect/great_vessels_probe.json (atlas centerlines),
web/dist/ (npm run build, for E5), Microsoft Word (docx -> PDF for ESM_2), and the tour video for ESM_1.
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PY = sys.executable
skip = {s for a in sys.argv[1:] if a.startswith("--skip=") for s in a[7:].split(",")}
steps = [
    ("e1", [PY, "e1_projection_agreement.py"]),
    ("e1b", [PY, "e1b_render_agreement.py"]),
    ("e2", [PY, "e2_orientation.py"]),
    ("e2v2", [PY, "e2_orientation.py", "--phantom=v2"]),
    ("e3", [PY, "e3_distractors.py", "--rounds=300"]),
    ("e3m", [PY, "e3_margins.py"]),
    ("probe", ["node", "browser/e3_tile_probe.mjs"]),
    ("e5", ["node", "browser/e5_performance.mjs", "--reps=5", "--seconds=10"] + ([] if "--no-headed" in sys.argv else ["--headed=1"])),
    ("capture", ["node", "browser/fig_capture.mjs"]),
    ("fig1", [PY, "figures/fig1_architecture.py"]),
    ("fig2", [PY, "figures/fig2_views.py"]),
    ("fig3", [PY, "figures/fig3_agreement.py"]),
    ("fig4", [PY, "figures/fig4_phantom.py"]),
    ("fig5", [PY, "figures/fig5_predict.py"]),
    ("numbers", [PY, "build_numbers.py"]),
    ("draft", [PY, "build_manuscript.py", "--src=paper/manuscript/draft_v1.md", "--out=paper/manuscript/build/draft_v1.docx"]),
    ("manuscript", [PY, "build_manuscript.py"]),
    ("frontmatter", [PY, "build_frontmatter.py"]),
    ("esm1", [PY, "build_esm1.py"]),
    ("esm2", [PY, "build_esm2.py"]),
    ("audit", [PY, "build_audit.py"]),
]
for name, cmd in steps:
    if name in skip:
        print(f"- {name}: skipped")
        continue
    print(f"== {name}", flush=True)
    subprocess.run(cmd, check=True, cwd=HERE if not cmd[1].startswith("--") else ROOT)
sub = ROOT / "paper" / "submission"
for src, dst in (("Fig1.eps", "Fig1.eps"), ("Fig2.tif", "Fig2.tif"), ("Fig3.tif", "Fig3.tif"), ("Fig4.tif", "Fig4.tif"), ("Fig5.tif", "Fig5.tif")):
    shutil.copy2(ROOT / "paper" / "figures" / src, sub / dst)
print("paper/submission/ rebuilt")
