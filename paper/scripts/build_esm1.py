"""ESM_1.mp4: a trimmed copy of the AngioLens tour video with a 6 s title card (article title, journal, authors, corresponding author's affiliation
and e-mail, as IJCARS requires for every supplementary file), plus a photosensitivity check of the result.

    .venv\\Scripts\\python paper\\scripts\\build_esm1.py [--src=D:/angiolens-video/AngioLens_tour.mp4]

The source is copied to paper/results/raw first; the original in D:/angiolens-video is only read. Three segments are cut
(KEEP below; trimming only, nothing added except the title card and a 0.6 s fade-out at the end):
  178.0-184.0 s  narration "understanding this shouldn't just be something we assume. It should be measurable." (implies the
                 Predict mode measures understanding, which the paper does not claim)
  213.5-237.0 s  the "Geometry validated against an independent reference" overlay card, which shows the older 6-pose e2e numbers
                 ("six standard views - correlation r = 1.000", "mirrors r <= 0.13") that differ from this paper's E1b grid
  243.6-254.6 s  the closing tagline "From something you have to memorize to something you actually understand" and "Thank you"
                 (implies a learning benefit)
Each cut lands on a black transition or a pause in the narration (checked against narration.json and frame sheets).

Flash check (approximation of WCAG 2.x general-flash rule on the whole frame): mean relative luminance per frame (sRGB -> linear,
Rec. 709 weights) at 64x36; a "flash" is a pair of opposing luminance changes each >= 0.10 where the darker state is < 0.80;
the maximum number of flashes in any 1 s window must be <= 3. Whole-frame means can miss small flashing regions; a second pass
does the same on a 4x4 grid of tiles. Writes paper/submission/ESM_1.mp4 and paper/results/esm1_flash_check.json.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ARGS = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
SRC = Path(ARGS.get("src", "D:/angiolens-video/AngioLens_tour.mp4"))
KEEP = [(0.0, 178.0), (184.0, 213.5), (237.0, 243.6)]
FF = next(Path("D:/angiolens-video/.venv/Lib/site-packages/imageio_ffmpeg/binaries").glob("ffmpeg*.exe"))
OUT = ROOT / "paper" / "submission" / "ESM_1.mp4"
TMP = ROOT / "paper" / "results" / "raw"
TMP.mkdir(parents=True, exist_ok=True)

TITLE = "AngioLens: an open-source, geometry-verified coronary angiography projection simulator for training"
LINES = [("Online Resource 1", 44, True), ("", 20, False), (TITLE, 34, True), ("", 16, False),
         ("International Journal of Computer Assisted Radiology and Surgery", 30, False), ("", 16, False),
         ("Rugved Parmar, Md Fahim, Shreya P. Trivedi", 30, False), ("", 12, False),
         ("Corresponding author: Rugved Parmar, Department of Medicine, SUNY Downstate Health Sciences University /", 24, False),
         ("Kings County Hospital Center, Brooklyn, NY, USA. parmarrugved@gmail.com", 24, False), ("", 16, False),
         ("Narrated tour of AngioLens (app source of release v1.1-ijcars); titles and captions are a recording overlay.", 22, False),
         ("Rendered from Z-Anatomy models (CC BY-SA 4.0), derived from BodyParts3D (DBCLS)", 22, False)]


def card(path):
    im = Image.new("RGB", (1920, 1080), (16, 20, 30))
    d = ImageDraw.Draw(im)
    y = 250
    for text, size, bold in LINES:
        f = ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)
        words, line, rows = text.split(), "", []
        for w in words:
            if d.textlength(f"{line} {w}".strip(), font=f) > 1600:
                rows.append(line); line = w
            else:
                line = f"{line} {w}".strip()
        rows.append(line)
        for r in rows:
            d.text((960, y), r, font=f, fill=(235, 238, 245), anchor="ma")
            y += int(size * 1.35)
    im.save(path)


def luminance_series(video, tiles=1):
    w, h = 64, 36
    p = subprocess.run([str(FF), "-v", "error", "-i", str(video), "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, check=True)
    fr = np.frombuffer(p.stdout, np.uint8).reshape(-1, h, w, 3) / 255.0
    lin = np.where(fr <= 0.04045, fr / 12.92, ((fr + 0.055) / 1.055) ** 2.4)
    Y = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    if tiles == 1:
        return Y.mean(axis=(1, 2))[:, None]
    ty, tx = h // tiles, w // tiles
    return np.stack([Y[:, i * ty:(i + 1) * ty, j * tx:(j + 1) * tx].mean(axis=(1, 2)) for i in range(tiles) for j in range(tiles)], axis=1)


def max_flashes_per_second(L, fps):
    worst = 0
    for k in range(L.shape[1]):
        y = L[:, k]
        events, ref, direction = [], y[0], 0       # luminance extremes with >= 0.10 swings (darker state < 0.80)
        lo = hi = y[0]
        for t, v in enumerate(y):
            if direction >= 0 and v - lo >= 0.10 and min(lo, v) < 0.80:
                events.append(t); direction = -1; hi = v
            elif direction <= 0 and hi - v >= 0.10 and min(hi, v) < 0.80:
                events.append(t); direction = 1; lo = v
            lo, hi = min(lo, v), max(hi, v)
            if direction == -1:
                lo = min(lo, v) if v < hi else v
            if direction == 1:
                hi = max(hi, v) if v > lo else v
        ev = np.array(events)
        for t in ev:                                  # a flash = 2 opposing transitions
            n = ((ev >= t) & (ev < t + fps)).sum() // 2
            worst = max(worst, int(n))
    return worst


def main():
    png = TMP / "esm1_card.png"
    card(png)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    copy = TMP / "esm1_source_copy.mp4"
    shutil.copyfile(SRC, copy)                      # work on a copy; never touch the original
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
    subprocess.run([str(FF), "-y", "-v", "error", "-loop", "1", "-t", "6", "-framerate", "30", "-i", str(png),
                    "-f", "lavfi", "-t", "6", "-i", "anullsrc=channel_layout=mono:sample_rate=48000", "-i", str(copy),
                    "-filter_complex", fc, "-map", "[ov]", "-map", "[oa]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(OUT)], check=True)
    res = {"source": str(SRC), "kept_source_segments_s": KEEP,
           "cut_source_segments_s": [(178.0, 184.0), (213.5, 237.0), (243.6, 254.6)], "output": str(OUT.relative_to(ROOT)), "size_mb": round(OUT.stat().st_size / 2 ** 20, 1)}
    probe = subprocess.run([str(FF), "-hide_banner", "-i", str(OUT)], capture_output=True, text=True).stderr
    res["streams"] = [l.strip() for l in probe.splitlines() if "Stream" in l or "Duration" in l]
    res["max_flashes_per_s_whole_frame"] = max_flashes_per_second(luminance_series(OUT, 1), 30)
    res["max_flashes_per_s_4x4_tiles"] = max_flashes_per_second(luminance_series(OUT, 4), 30)
    res["pass_le_3_per_s"] = res["max_flashes_per_s_whole_frame"] <= 3 and res["max_flashes_per_s_4x4_tiles"] <= 3
    (ROOT / "paper" / "results" / "esm1_flash_check.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
