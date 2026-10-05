"""Before / after figure of the aortic root (D62) from the review shots in out/review/v1_1/.

    .venv\\Scripts\\python preprocess\\scripts\\root_before_after.py   -> out/review/v1_1/root_before_after.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

D = Path(__file__).resolve().parents[2] / "out" / "review" / "v1_1"
ROWS = [  # (before, after, crop box in the source image, row title)
    ("before_1920_s1_root.png", "1920_s1_root.png", (560, 60, 1520, 760), "Aortic root close-up (Heart scene)"),
    ("before_zoom_lm.png", "zoom_lm.png", (200, 60, 1080, 700), "Left main origin, extreme close-up (45 mm)"),
    ("before_1280_s5_root.png", "1280_s5_root.png", (330, 60, 1010, 560), "Engaged: glass aorta, JL4 in the left main"),
]
W = 900
cells = []
for b, a, box, title in ROWS:
    ib, ia = (Image.open(D / f).convert("RGB").crop(box) for f in (b, a))
    h = round(W * ib.height / ib.width)
    cells.append((ib.resize((W, h), Image.LANCZOS), ia.resize((W, h), Image.LANCZOS), title))
pad, head = 16, 44
H = sum(c[0].height + head for c in cells) + pad * (len(cells) + 1) + 40
out = Image.new("RGB", (2 * W + 3 * pad, H), (16, 21, 29))
g = ImageDraw.Draw(out)
try:
    font = ImageFont.truetype("segoeui.ttf", 22)
    small = ImageFont.truetype("segoeui.ttf", 18)
except OSError:
    font = small = ImageFont.load_default()
g.text((pad, 10), "BEFORE (v1.0-rc1)", fill=(200, 208, 218), font=font)
g.text((2 * pad + W, 10), "AFTER (v1.0: display aorta, D62)", fill=(200, 208, 218), font=font)
y = 40 + pad
for ib, ia, title in cells:
    g.text((pad, y + 8), title, fill=(160, 170, 182), font=small)
    out.paste(ib, (pad, y + head))
    out.paste(ia, (2 * pad + W, y + head))
    y += head + ib.height + pad
out.save(D / "root_before_after.png")
print("wrote", D / "root_before_after.png", out.size)
