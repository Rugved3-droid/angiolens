"""E2. Orientation and handedness: a synthetic chiral phantom, expected images derived from first principles, negative controls.

    .venv\\Scripts\\python paper\\scripts\\e2_orientation.py [--gl=d3d11|swiftshader]

PHANTOM (no patient or atlas data). Three letter-shaped tube markers, stroke radius 1.5 mm, glyph 18 x 30 mm, each drawn in a
CORONAL plane (letter "right" = +x = patient LEFT, letter "up" = +z = SUPERIOR), so at AP each letter reads normally:
    "L" centred at iso + (+60, -15, +25) mm   (patient left, anterior, superior)
    "R" centred at iso + (-60, +20,  +5) mm   (patient right, posterior)
    "F" centred at iso + ( +5, -30, -55) mm   (feet side, anterior)
Every centre has three nonzero, distinct coordinates, so LAO/RAO and CRAN/CAUD swaps move every marker unless the swapped angle is 0.
Built with the same tooling as the repo's phantom (capsule mask -> marching cubes -> GLB), loaded by the classic app as a case.

EXPECTED IMAGE, DERIVED WITHOUT THE APP'S GEOMETRY CODE (cpt.geometry is not imported here). Definitions used:
  (1) Patient frame LPS: +x left, +y posterior, +z superior; patient supine.
  (2) At AP (alpha = beta = 0) the detector is ANTERIOR: d0 = (0, -1, 0). The image is displayed as seen from the detector,
      head up, so at AP patient left is screen right: r0 = (1, 0, 0), up0 = (0, 0, 1).
  (3) LAO alpha > 0 carries the detector toward the patient's LEFT about the long axis z: d1 = Rz(alpha) d0 = (sin a, -cos a, 0),
      r1 = Rz(alpha) r0 = (cos a, sin a, 0). RAO is alpha < 0.
  (4) CRANIAL beta > 0 then tilts the detector toward the HEAD, about r1: d = cos b d1 + sin b z, up = cos b z - sin b d1, r = r1.
  (5) Point source S = iso - SOD d, flat detector at iso + (SID - SOD) d, normal d; SID 1000, SOD 750 mm.
      Screen mm: x = SID (p-S).r / (p-S).d, y = SID (p-S).up / (p-S).d.  Pixel: col = x/dpx + n/2 - 1/2, row = n/2 - 1/2 - y/dpx.
  Consequence (closed form): a coronal letter's in-image handedness is sign(cos a cos b) after removing perspective, i.e. it reads
  normally for every |alpha| < 90 and is edge-on at |alpha| = 90. So handedness catches a mirror but NOT an angle-sign swap;
  marker positions catch the swaps. Both are tested.
  Expected binary mask: each stroke sampled every 0.1 mm and projected; a pixel is "vessel" if its centre lies within
  r x local magnification (SID / (p-S).d) of a projected sample.

DECISION RULE (fixed before the run). A render passes for a view iff ALL of:
  (a) mask IoU(render > 0, expected) >= 0.70;
  (b) the render has exactly 3 connected components and each, matched to the nearest expected marker, has its centroid within
      2.0 px (0.98 mm at the detector) of that marker's expected centroid;
  (c) for |alpha| < 90: each component overlaps its expected letter more than the same letter mirrored about its own centre (IoU).
NEGATIVE CONTROLS per view (each must FAIL): left-right mirrored render; LAO<->RAO swapped render (-alpha, beta);
CRAN<->CAUD swapped render (alpha, -beta); and up-down mirrored render. A swap of an angle that is 0 reproduces the same image
and is reported as not applicable (it is not a test failure; no image-based test can see it).

Writes paper/results/e2/: e2_views.csv (expected vs observed per marker), e2_tests.csv (pass/fail per view x render),
e2_derivation.csv (expected screen positions and handedness), e2_meta.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from functools import lru_cache

import numpy as np
from scipy import ndimage
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from common import NAMED_VIEWS, RAW, RESULTS, ROOT, environment

# --phantom=v2: the second phantom (TODO U7, author-approved 2026-11-14). Only the F marker moves, to (+40, -25, -65) mm, chosen
# analytically BEFORE rendering so that no two markers come within 5 px at any named view (closest gap 67 px). v1 is kept as is.
PHANTOM = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--phantom=")), "v1")
SFX = "" if PHANTOM == "v1" else f"_{PHANTOM}"
OUT = RESULTS / f"e2{SFX}"
CASE = f"e2_orient{SFX}"
CASE_DIR = ROOT / "web" / "public" / "cases" / CASE        # git-ignored, synthetic
ISO = np.array([12.0, -40.0, -150.0])                        # same off-origin isocenter as the repo phantom
SID, SOD, DET_MM, PX = 1000.0, 750.0, 250.0, 512
R_STROKE = 1.5
W, H = 18.0, 30.0
IOU_MIN, CENTROID_MAX_PX = 0.70, 2.0

# glyph strokes in letter coordinates (h: letter-right, v: letter-up), origin at the bottom-left of the glyph box
GLYPHS = {
    "L": [[(0, 0), (0, 30)], [(0, 0), (18, 0)]],
    "F": [[(0, 0), (0, 30)], [(0, 30), (18, 30)], [(0, 15), (13, 15)]],
    "R": [[(0, 0), (0, 30)], [(0, 30), (12, 30), (18, 25), (18, 20), (12, 15), (0, 15)], [(7, 15), (18, 0)]],
}
CENTRES = {"L": (60.0, -15.0, 25.0), "R": (-60.0, 20.0, 5.0), "F": (5.0, -30.0, -55.0)}
if PHANTOM == "v2":
    CENTRES["F"] = (40.0, -25.0, -65.0)


def strokes_lps(name, mirror=False):
    """Polylines (LPS mm) of a glyph centred at its marker. mirror=True flips the glyph about its own vertical centre line."""
    c = ISO + np.array(CENTRES[name])
    out = []
    for poly in GLYPHS[name]:
        P = np.array(poly, float)
        h = (W - P[:, 0]) if mirror else P[:, 0]
        out.append(np.stack([c[0] + h - W / 2, np.full(len(P), c[1]), c[2] + P[:, 1] - H / 2], axis=1))
    return out


def resample(poly, step=0.1):
    pts = [poly[0]]
    for a, b in zip(poly[:-1], poly[1:]):
        k = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        pts += [a + (b - a) * t for t in np.linspace(0, 1, k + 1)[1:]]
    return np.array(pts)


# ---------------- first-principles projection (independent of preprocess/cpt/geometry.py) ----------------
def frame(alpha, beta):
    a, b = np.radians(alpha), np.radians(beta)
    d1 = np.array([np.sin(a), -np.cos(a), 0.0])
    r1 = np.array([np.cos(a), np.sin(a), 0.0])
    z = np.array([0.0, 0.0, 1.0])
    return np.cos(b) * d1 + np.sin(b) * z, r1, np.cos(b) * z - np.sin(b) * d1     # d, right, up


def project(p, alpha, beta):
    d, r, up = frame(alpha, beta)
    S = ISO - SOD * d
    q = np.atleast_2d(p) - S
    depth = q @ d
    x, y = SID * (q @ r) / depth, SID * (q @ up) / depth
    dpx = DET_MM / PX
    return np.stack([x / dpx + PX / 2 - 0.5, PX / 2 - 0.5 - y / dpx], axis=1), SID / depth      # (col,row), magnification


@lru_cache(maxsize=None)
def _letter_mask(nm, alpha, beta, mirror):
    m = np.zeros((PX, PX), bool)
    for poly in strokes_lps(nm, mirror):
        P = resample(poly)
        cr, mag = project(P, alpha, beta)
        rad_px = R_STROKE * mag / (DET_MM / PX)
        pad = rad_px.max() + 2
        c0, r0 = np.maximum(np.floor(cr.min(0) - pad).astype(int), 0)
        c1, r1 = np.minimum(np.ceil(cr.max(0) + pad).astype(int), PX - 1)
        if c1 < c0 or r1 < r0:
            continue
        cols, rows = np.meshgrid(np.arange(c0, c1 + 1), np.arange(r0, r1 + 1))
        q = np.stack([cols.ravel(), rows.ravel()], axis=1)
        dist, j = cKDTree(cr).query(q, distance_upper_bound=pad)
        ok = np.isfinite(dist)
        hit = np.zeros(len(q), bool)
        hit[ok] = dist[ok] <= rad_px[j[ok]]
        m[r0:r1 + 1, c0:c1 + 1] |= hit.reshape(rows.shape)
    m.setflags(write=False)
    return m


def expected_mask(names, alpha, beta, mirror=False):
    m = np.zeros((PX, PX), bool)
    for nm in names:
        m |= _letter_mask(nm, int(alpha), int(beta), mirror)
    return m


# ---------------- phantom build (same tooling as preprocess/scripts/build_phantom.py) ----------------
def build_case():
    from cpt.centerline import build_from_paths
    from cpt.glb import write_glb
    from cpt.mesh import mask_to_mesh
    from cpt.synthetic import capsule_mask

    CASE_DIR.mkdir(parents=True, exist_ok=True)
    paths, trees = [], []
    for nm in CENTRES:
        for poly in strokes_lps(nm):
            P = resample(poly, 0.5)
            paths.append(np.c_[P, np.full(len(P), R_STROKE)])
            trees.append("left")
    dummy = ISO + np.array([0.0, 60.0, 80.0])                                    # right tree: a short tube, never rendered here
    paths.append(np.c_[np.stack([dummy, dummy + [0, 0, 10]]), [1.0, 1.0]])
    trees.append("right")
    graph = build_from_paths(paths, trees)
    (CASE_DIR / "centerlines.json").write_text(json.dumps(graph.to_json()))
    import trimesh
    meshes = {}
    # one small voxel grid per letter (a single grid over all three would need ~60 M voxels); capsules on the polyline corners
    groups = {"left": [[(a, b, R_STROKE) for poly in strokes_lps(nm) for a, b in zip(poly[:-1], poly[1:])] for nm in CENTRES],
              "right": [[(dummy, dummy + [0, 0, 10], 1.0)]]}
    for tree in ("left", "right"):
        parts = []
        for segs in groups[tree]:
            vol = capsule_mask(segs, spacing=0.25)
            parts.append(mask_to_mesh(vol, vol.data > 0.5, smooth_sigma_vox=0.5, taubin_iters=0))
        m = trimesh.util.concatenate(parts)                       # disjoint closed solids: exit - entry still holds
        E = [e for e in graph.edges if e["tree"] == tree]
        pts = np.vstack([e["samples"][:, :3] for e in E])
        ids = np.concatenate([np.full(len(e["samples"]), e["id"]) for e in E])
        _, j = cKDTree(pts).query(m.vertices)
        write_glb(CASE_DIR / f"lumen_{tree}.glb", m.vertices, m.faces, m.vertex_normals, ids[j].astype(np.float32))
        meshes[tree] = {"faces": int(len(m.faces)), "vertices": int(len(m.vertices))}
    sv = capsule_mask([(ISO + [0, 90, -60], ISO + [0, 90, 60], 10.0)], spacing=0.8)       # small posterior "spine" (bone.glb)
    mb = mask_to_mesh(sv, sv.data > 0.5, taubin_iters=0)
    write_glb(CASE_DIR / "bone.glb", mb.vertices, mb.faces, mb.vertex_normals)
    meta = {"case_id": CASE, "frame": "LPS mm (synthetic orientation phantom, paper E2)", "isocenter_lps_mm": ISO.tolist(),
            "c_arm": {"sid_mm": SID, "sod_mm": SOD, "detector_mm": DET_MM}, "centerlines": {"source": "synthetic"},
            "meshes": meshes, "files": ["bone.glb", "centerlines.json", "lumen_left.glb", "lumen_right.glb", "case.json"]}
    (CASE_DIR / "case.json").write_text(json.dumps(meta, indent=1))


# ---------------- test ----------------
def evaluate(img, alpha, beta):
    obs = img > 0
    exp = expected_mask(CENTRES, alpha, beta)
    iou = (obs & exp).sum() / max(1, (obs | exp).sum())
    lab, n = ndimage.label(obs, structure=np.ones((3, 3)))
    names = list(CENTRES)
    exp_c = {nm: np.argwhere(expected_mask([nm], alpha, beta))[:, ::-1].mean(0) for nm in names}
    res = {"iou": float(iou), "n_components": int(n), "marker": {}}
    ok_pos = n == 3
    ok_hand = True
    if n >= 1:
        obs_c = [np.argwhere(lab == k + 1)[:, ::-1].mean(0) for k in range(n)]
        cost = np.array([[np.linalg.norm(oc - exp_c[nm]) for nm in names] for oc in obs_c])
        ri, ci = linear_sum_assignment(cost)
        matched = {names[c]: (r, cost[r, c]) for r, c in zip(ri, ci)}
        for nm in names:
            if nm not in matched:
                ok_pos = False
                res["marker"][nm] = {"err_px": None, "hand_ok": None}
                continue
            r, err = matched[nm]
            comp = lab == r + 1
            hand = None
            if abs(alpha) < 90:
                e_true, e_mir = expected_mask([nm], alpha, beta), expected_mask([nm], alpha, beta, mirror=True)
                # compare shapes independently of position: align both expected glyphs on the component's centroid
                shift = np.round(obs_c[r] - exp_c[nm]).astype(int)
                def iou_shift(e):
                    e2 = np.roll(np.roll(e, shift[1], 0), shift[0], 1)
                    return (comp & e2).sum() / max(1, (comp | e2).sum())
                hand = bool(iou_shift(e_true) > iou_shift(e_mir))
                ok_hand &= hand
            ok_pos &= err <= CENTROID_MAX_PX
            res["marker"][nm] = {"err_px": float(err), "hand_ok": hand, "obs_c": obs_c[r].tolist(),
                                 "exp_c": exp_c[nm].tolist()}
    res["pass"] = bool(iou >= IOU_MIN and ok_pos and ok_hand)
    res["pass_iou"], res["pass_position"], res["pass_handedness"] = bool(iou >= IOU_MIN), bool(ok_pos), bool(ok_hand)
    return res


def main():
    gl = next((x.split("=", 1)[1] for x in sys.argv[1:] if x.startswith("--gl=")), "d3d11")
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if "--skip-browser" not in sys.argv:
        build_case()
    views = [(nm, int(a), int(b)) for nm, a, b, _ in NAMED_VIEWS]
    poses = sorted({(a, b) for _, a, b in views} | {(-a, b) for _, a, b in views} | {(a, -b) for _, a, b in views})
    (RAW / "e2_input.json").write_text(json.dumps({"case": CASE, "px": PX, "poses": poses, "gpu_dir": f"e2_gpu{SFX}", "meta": f"e2_gpu_meta{SFX}.json"}))
    if "--skip-browser" not in sys.argv:
        subprocess.run(["node", str(ROOT / "paper" / "scripts" / "browser" / "e2_browser.mjs"), f"--gl={gl}"], check=True)
    img = {p: np.fromfile(RAW / f"e2_gpu{SFX}" / f"{p[0]}_{p[1]}.f32", "<f4").reshape(PX, PX) for p in poses}

    der, rows, tests = [], [], []
    for name, a, b in views:
        d, r, up = frame(a, b)
        for nm in CENTRES:
            cr, mag = project(ISO + np.array(CENTRES[nm]), a, b)
            # handedness of the letter axes on screen (letter-right = +x, letter-up = +z), perspective removed
            hand = float(np.dot([1, 0, 0], r) * np.dot([0, 0, 1], up) - np.dot([1, 0, 0], up) * np.dot([0, 0, 1], r))
            der.append((name, a, b, nm, *cr[0], float(mag[0]), hand))
        renders = {"correct": img[(a, b)], "mirror_lr": img[(a, b)][:, ::-1], "swap_lao_rao": img[(-a, b)],
                   "swap_cran_caud": img[(a, -b)], "mirror_ud": img[(a, b)][::-1, :]}
        for kind, im in renders.items():
            applicable = not ((kind == "swap_lao_rao" and a == 0) or (kind == "swap_cran_caud" and b == 0))
            e = evaluate(im, a, b)
            expected_pass = kind == "correct"
            detected = (not e["pass"]) if not expected_pass else None
            tests.append({"view": name, "alpha": a, "beta": b, "render": kind, "applicable": applicable,
                          "iou": e["iou"], "n_components": e["n_components"],
                          "max_centroid_err_px": max((m["err_px"] for m in e["marker"].values() if m["err_px"] is not None), default=None),
                          "pass_iou": e["pass_iou"], "pass_position": e["pass_position"],
                          "pass_handedness": e["pass_handedness"], "test_pass": e["pass"],
                          "outcome": ("PASS" if e["pass"] else "FAIL") if expected_pass else
                                     ("n/a (identical image)" if not applicable else ("DETECTED" if detected else "MISSED"))})
            if kind == "correct":
                for nm, m in e["marker"].items():
                    rows.append((name, a, b, nm, *(m.get("exp_c") or [np.nan, np.nan]), *(m.get("obs_c") or [np.nan, np.nan]),
                                 m["err_px"], m["hand_ok"]))
    with open(OUT / "e2_derivation.csv", "w") as f:
        f.write("view,alpha,beta,marker,expected_col_px,expected_row_px,magnification,letter_handedness_det\n")
        for x in der:
            f.write(f'"{x[0]}",{x[1]},{x[2]},{x[3]},{x[4]:.3f},{x[5]:.3f},{x[6]:.4f},{x[7]:.4f}\n')
    with open(OUT / "e2_views.csv", "w") as f:
        f.write("view,alpha,beta,marker,expected_centroid_col,expected_centroid_row,observed_centroid_col,observed_centroid_row,err_px,handedness_ok\n")
        for x in rows:
            fx = lambda v: "" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.3f}"
            f.write(f'"{x[0]}",{x[1]},{x[2]},{x[3]},' + ",".join(fx(v) for v in x[4:9]) + f",{x[9]}\n")
    keys = list(tests[0].keys())
    with open(OUT / "e2_tests.csv", "w") as f:
        f.write(",".join(keys) + "\n")
        for t in tests:
            f.write(",".join(f'"{t[k]}"' if isinstance(t[k], str) else (f"{t[k]:.4f}" if isinstance(t[k], float) else str(t[k])) for k in keys) + "\n")
    summary = {}
    for kind in ("correct", "mirror_lr", "swap_lao_rao", "swap_cran_caud", "mirror_ud"):
        T = [t for t in tests if t["render"] == kind]
        A = [t for t in T if t["applicable"]]
        summary[kind] = {"views": len(T), "applicable": len(A),
                         ("passed" if kind == "correct" else "detected"): sum((t["test_pass"] if kind == "correct" else not t["test_pass"]) for t in A)}
    meta = {"phantom": PHANTOM, "centres_mm_from_iso": CENTRES, "gl": gl, "decision_rule": {"iou_min": IOU_MIN, "centroid_max_px": CENTROID_MAX_PX}, "summary": summary,
            "runtime_s": round(time.time() - t0, 1), **json.loads((RAW / f"e2_gpu_meta{SFX}.json").read_text()), **environment()}
    (OUT / "e2_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
