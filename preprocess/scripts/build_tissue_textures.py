"""Tissue textures for the display (v1.1 item 3b): Blender's baked tiles -> web textures, heights -> tangent-space normal maps.

    .venv\\Scripts\\python preprocess\\scripts\\build_tissue_textures.py

Reads assets/textures/*.png (preprocess/blender/bake_tissue_textures.py). Normals come from the height maps with wrap-around
central differences (np.roll), so they stay exactly seamless like the tiles. Writes web/public/anatomy/textures/ (git-ignored;
JPEG for colour, PNG for normal and roughness) and out/review/v1_1_peel/textures_tiled.png (each map tiled 2x2: seam check).
"""
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "assets" / "textures"
DST = ROOT / "web" / "public" / "anatomy" / "textures"
REV = ROOT / "out" / "review" / "v1_1_peel"
STRENGTH = {"myo": 1.1, "cor": 0.8, "fat": 2.0}            # height (0-1) -> slope scale


def normal_from_height(h, k):
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * k
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * k
    n = np.stack([-gx, gy, np.ones_like(h)], -1)              # +y up in tangent space (image rows grow downward)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return ((n * 0.5 + 0.5) * 255).round().astype(np.uint8)


def main():
    DST.mkdir(parents=True, exist_ok=True)
    REV.mkdir(parents=True, exist_ok=True)
    tiles = []
    for name in ["myo_albedo", "myo_rough", "fat_albedo", "fat_rough"]:
        im = Image.open(SRC / f"{name}.png").convert("RGB")
        if name.endswith("albedo"):
            im.save(DST / f"{name}.jpg", quality=92)
        else:
            im.convert("L").save(DST / f"{name}.png")
        tiles.append((name, im))
    for key in ["myo", "cor", "fat"]:
        h = np.asarray(Image.open(SRC / f"{key}_height.png").convert("L"), np.float32) / 255.0
        h = h * (1024 / h.shape[0])                            # per-pixel slope at the 1024 reference size
        n = Image.fromarray(normal_from_height(h, STRENGTH[key] * h.shape[0] / 64))
        n.save(DST / f"{key}_normal.png")
        tiles.append((f"{key}_normal", n))
    # v1.1 packed maps (one texture per tissue: 3 triplanar taps instead of 9): RG = normal xy, B = roughness,
    # A = colour variation (albedo luminance around its mean, 0.5 = the material colour)
    for key, rough, alb in [("myo", "myo_rough", "myo_albedo"), ("fat", "fat_rough", "fat_albedo"), ("cor", None, None)]:
        n = np.asarray(Image.open(DST / f"{key}_normal.png").convert("RGB"), np.uint8)
        R = np.asarray(Image.open(SRC / f"{rough}.png").convert("L"), np.uint8) if rough else np.full(n.shape[:2], 100, np.uint8)
        if alb:
            L = np.asarray(Image.open(SRC / f"{alb}.png").convert("L"), np.float32)
            Avar = np.clip(128 + (L - L.mean()) / max(L.std(), 1e-3) * 38, 0, 255).astype(np.uint8)
        else:
            Avar = np.full(n.shape[:2], 128, np.uint8)
        Image.fromarray(np.dstack([n[..., 0], n[..., 1], R, Avar]), "RGBA").save(DST / f"{key}_pack.png")
    # seam check: every map tiled 2x2 at 256 px per tile
    s = 256
    sheet = Image.new("RGB", (len(tiles) * 2 * s, 2 * s))
    for i, (name, im) in enumerate(tiles):
        t = im.convert("RGB").resize((s, s))
        for dx in (0, 1):
            for dy in (0, 1):
                sheet.paste(t, (i * 2 * s + dx * s, dy * s))
    sheet.save(REV / "textures_tiled.png")
    print("wrote", sorted(p.name for p in DST.iterdir()))


if __name__ == "__main__":
    main()
