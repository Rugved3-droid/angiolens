"""ESM_1.mp4 for Medical Science Educator: a trimmed copy of D:/angiolens-video/AngioLens_tour.mp4 with an MSE title card.

Reuses the card renderer and photosensitivity check of paper/scripts/build_esm1.py (the IJCARS version), with:
  * an MSE title card (journal, current author list; no IJCARS wording);
  * one extra cut: 205.95-213.5 s (the expanded "Your record" panel with the demo answers, "5/11 correct (45%)", opens at 206.0 s, plus ("So instead of just getting a score, the learner can actually see which axis they're
    consistently getting backwards.") which joins the existing 213.5-237.0 cut. Cut point is the pause after "...logged
    by type." (word ends 205.98 s, next word 206.62 s, narration.json).
The original video is only read. Called by build_package.py when the source video is present; otherwise the committed
submission/MSE_Innovation/ESM_1.mp4 is kept.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "paper/scripts"))
import build_esm1 as E  # noqa: E402  (main() is guarded; importing runs nothing)

SRC = Path("D:/angiolens-video/AngioLens_tour.mp4")
OUT = ROOT / "submission/MSE_Innovation/ESM_1.mp4"
TMP = ROOT / "paper/results/raw"
KEEP = [(0.0, 178.0), (184.0, 205.95), (237.0, 243.6)]
CUT = [(178.0, 184.0), (205.95, 237.0), (243.6, 254.6)]
TITLE = "AngioLens: an open-source, browser-based simulator that makes coronary angiography projections visible and testable"
E.LINES = [("Online Resource 1", 44, True), ("", 20, False), (TITLE, 34, True), ("", 16, False),
           ("Medical Science Educator", 30, False), ("", 16, False),
           ("Rugved Parmar, Md Fahim, Adam Budzikowski", 30, False), ("", 12, False),
           ("Corresponding author: Rugved Parmar, Internal Medicine, SUNY Downstate Health Sciences University /", 24, False),
           ("Kings County Hospital, Brooklyn, NY, USA. parmarrugved@gmail.com", 24, False), ("", 16, False),
           ("Narrated tour of AngioLens (release v1.1-ijcars); titles and captions are a recording overlay.", 22, False),
           ("Rendered from Z-Anatomy models (CC BY-SA 4.0), derived from BodyParts3D (DBCLS)", 22, False)]


def build():
    if not SRC.exists():
        print(f"ESM: source {SRC} not found; keeping the committed {OUT.name}")
        return None
    TMP.mkdir(parents=True, exist_ok=True)
    png, copy = TMP / "mse_esm1_card.png", TMP / "mse_esm1_source_copy.mp4"
    E.card(png)
    shutil.copyfile(SRC, copy)
    parts, labels = [], []
    for i, (a, b) in enumerate(KEEP):
        fade = f",afade=t=in:d=0.04,afade=t=out:st={b - a - 0.04:.2f}:d=0.04"
        parts.append(f"[2:v]trim={a}:{b},setpts=PTS-STARTPTS,format=yuv420p,setsar=1[v{i}];"
                     f"[2:a]atrim={a}:{b},asetpts=PTS-STARTPTS{fade}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    total = sum(b - a for a, b in KEEP) + 6
    fc = (";".join(parts) + ";[0:v]format=yuv420p,setsar=1[c];"
          + f"[c][1:a]{''.join(labels)}concat=n={len(KEEP) + 1}:v=1:a=1[cv][ca];"
          + f"[cv]fade=t=out:st={total - 0.6:.2f}:d=0.6[ov];[ca]afade=t=out:st={total - 0.6:.2f}:d=0.6[oa]")
    subprocess.run([str(E.FF), "-y", "-v", "error", "-loop", "1", "-t", "6", "-framerate", "30", "-i", str(png),
                    "-f", "lavfi", "-t", "6", "-i", "anullsrc=channel_layout=mono:sample_rate=48000", "-i", str(copy),
                    "-filter_complex", fc, "-map", "[ov]", "-map", "[oa]", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                    str(OUT)], check=True)
    res = {"source": str(SRC), "kept_source_segments_s": KEEP, "cut_source_segments_s": CUT,
           "duration_s": round(total, 1), "size_mb": round(OUT.stat().st_size / 2 ** 20, 1),
           "max_flashes_per_s_whole_frame": E.max_flashes_per_second(E.luminance_series(OUT, 1), 30),
           "max_flashes_per_s_4x4_tiles": E.max_flashes_per_second(E.luminance_series(OUT, 4), 30)}
    res["pass_le_3_per_s"] = res["max_flashes_per_s_whole_frame"] <= 3 and res["max_flashes_per_s_4x4_tiles"] <= 3
    (ROOT / "paper/mse/esm1_check.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    print(json.dumps(build(), indent=1))
