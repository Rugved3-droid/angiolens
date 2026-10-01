"""Artery-vs-vein checks for the non-expert RCA extension (review aid; decides nothing by itself).

    python preprocess/scripts/extension_checks.py --case Normal_12
Writes out/review/<id>/extension_checks.png and extension_checks.json.
  1 taper     FWHM lumen diameter and peak HU along the trace (same method on the expert distal RCA as calibration)
  2 CS        rough coronary-sinus segmentation, minimum distance trace -> CS
  3 HU        trace centerline HU vs CS/GCV core vs expert arteries of similar radius
  4 junction  zoomed straightened reformat at the annotation end, centerline HU minimum, lumen count
  5 branches  side branches off the trace at lower local thresholds (inside a 6 mm tube)
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage as ndi
from skimage.morphology import ball, skeletonize

from cpt.case import load_case
from cpt.centerline import resample
from cpt.masks import bone_and_pool

# Coronary sinus: oblique enhanced tube between RA side and LV at z ~ -144, picked on crux slices.
# The seed snaps to the brightest smoothed voxel within 4 mm. Grown at >= CS_HU: at 230 HU it merges with
# the LV (76 mL); at 250 HU it is a 0.5 mL tube.
CS_SEED = np.array([18.0, 31.0, -144.0])
CS_BOX = (np.array([-25.0, -5.0, -165.0]), np.array([55.0, 55.0, -115.0]))
CS_HU = 250


def frames(p):
    t = np.gradient(p, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    n = np.cross(t, [0, 0, 1.0])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    return t, n, np.cross(t, n)


def cross_sections(ct, p, half=4.0, step=0.1):
    """(N, M, M) HU cross-sections perpendicular to the path (trilinear)."""
    _, n, b = frames(p)
    g = np.arange(-half, half + step / 2, step)
    U, V = np.meshgrid(g, g, indexing="ij")
    pts = p[:, None, None, :] + U[None, ..., None] * n[:, None, None, :] + V[None, ..., None] * b[:, None, None, :]
    vals = ndi.map_coordinates(ct.data.astype(np.float32), ct.lps_to_index(pts.reshape(-1, 3)).T, order=1)
    return vals.reshape(len(p), len(g), len(g)), g


def fwhm_diameter(xs, g, step=0.1):
    """Equivalent diameter of the half-max region containing the centre; peak within 1 mm of centre."""
    c = len(g) // 2
    r = np.hypot(*np.meshgrid(g, g, indexing="ij"))
    d, peak = [], []
    for x in xs:
        pk = x[r <= 1.0].max()
        bg = np.median(x[(r >= 3.0) & (r <= 4.0)])
        half = (pk + bg) / 2
        lab, _ = ndi.label(x >= half)
        cen = np.unravel_index(np.argmax(np.where(r <= 1.0, x, -1e9)), x.shape)
        area = (lab == lab[cen]).sum() * step * step if lab[cen] else 0.0
        d.append(2 * np.sqrt(area / np.pi))
        peak.append(pk)
    return np.array(d), np.array(peak)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="Normal_12")
    args = ap.parse_args()
    case_dir = ROOT / "web" / "public" / "cases" / args.case
    out = ROOT / "out" / "review" / args.case
    c = load_case(args.case)
    hu = c.ct.data.astype(np.float32)
    sp = c.ct.spacing
    ext = json.loads((case_dir / "extension.json").read_text())
    cl = json.loads((case_dir / "centerlines.json").read_text())
    T = resample(np.array(ext["edges"][0]["samples"]), 0.25)
    exp_edge = next(e for e in cl["edges"] if e["id"] == ext["provenance"]["from_expert_edge"])
    E = resample(np.array(exp_edge["samples"]), 0.25)
    res = {}

    # ---- 1 taper ----
    xsT, g = cross_sections(c.ct, T[:, :3])
    dT, pkT = fwhm_diameter(xsT, g)
    Ed = E[-int(20 / 0.25):]                                   # last 20 mm of expert RCA
    xsE, _ = cross_sections(c.ct, Ed[:, :3])
    dE, pkE = fwhm_diameter(xsE, g)
    sT = np.arange(len(T)) * 0.25
    sE = np.arange(len(Ed)) * 0.25
    ok = (sT > 2) & (sT < sT[-1] - 2)                          # avoid the ends
    slope_d = np.polyfit(sT[ok], dT[ok], 1)[0] * 10
    slope_hu = np.polyfit(sT[ok], pkT[ok], 1)[0] * 10
    slope_dE = np.polyfit(sE, dE, 1)[0] * 10
    thirds = [dT[ok][i * ok.sum() // 3:(i + 1) * ok.sum() // 3].mean() for i in range(3)]
    res["1_taper"] = {
        "trace_fwhm_diameter_mm_by_third(RCA end -> crux)": [round(float(x), 2) for x in thirds],
        "trace_diameter_slope_mm_per_10mm": round(float(slope_d), 3),
        "trace_peak_hu_slope_per_10mm": round(float(slope_hu), 1),
        "expert_distal_RCA_fwhm_mean_mm": round(float(dE.mean()), 2),
        "expert_distal_RCA_MIS_diameter_mean_mm": round(float(2 * Ed[:, 3].mean()), 2),
        "expert_distal_RCA_slope_mm_per_10mm": round(float(slope_dE), 3),
    }

    # ---- 2 coronary sinus ----
    lo_i = np.maximum(np.floor(c.ct.lps_to_index(CS_BOX[0])[0]).astype(int), 0)
    hi_i = np.minimum(np.ceil(c.ct.lps_to_index(CS_BOX[1])[0]).astype(int) + 1, hu.shape)
    B = tuple(slice(a, b) for a, b in zip(lo_i, hi_i))
    smB = ndi.gaussian_filter(hu[B], 0.7 / sp)
    P0 = c.ct.index_to_lps(lo_i)[0]
    grid_pts = np.argwhere(np.ones(smB.shape, bool)).reshape(smB.shape + (3,)) * sp + P0
    near = np.linalg.norm(grid_pts - CS_SEED, axis=-1) <= 4.0
    seed = np.unravel_index(np.argmax(np.where(near, smB, -1e9)), smB.shape)
    lab, _ = ndi.label((smB >= CS_HU) & ~c.lumen[B])
    cs = lab == lab[seed]
    cs_pts = np.argwhere(cs) * sp + P0
    cs_edt = ndi.distance_transform_edt(cs, sampling=sp)
    dist_to_cs = ndi.distance_transform_edt(~cs, sampling=sp)
    dT_cs = ndi.map_coordinates(dist_to_cs, ((T[:, :3] - P0) / sp).T, order=1, cval=99)
    res["2_coronary_sinus"] = {
        "method": f"seed snapped to brightest within 4 mm of {CS_SEED.tolist()}, smoothed HU >= {CS_HU} (230 merges into LV)",
        "cs_volume_ml": round(float(cs.sum() * np.prod(sp) / 1000), 2),
        "cs_max_inscribed_radius_mm": round(float(cs_edt.max()), 1),
        "cs_extent_lps": [cs_pts.min(0).round(0).tolist(), cs_pts.max(0).round(0).tolist()] if len(cs_pts) else None,
        "min_distance_trace_to_cs_mm": round(float(dT_cs.min()), 2),
        "distance_crux_end_to_cs_mm": round(float(dT_cs[-1]), 2),
        "arc_mm_of_closest_approach": round(float(sT[np.argmin(dT_cs)]), 1),
        "trace_length_mm": round(float(sT[-1]), 1),
    }

    # ---- 3 HU fingerprint ----
    huT = ndi.map_coordinates(hu, c.ct.lps_to_index(T[:, :3]).T, order=1)
    cs_core = hu[B][cs & (cs_edt >= 1.5)]
    art = []
    for e in cl["edges"]:
        s = resample(np.array(e["samples"]), 0.25)
        sel = (s[:, 3] >= 0.45) & (s[:, 3] <= 0.8)
        if sel.any():
            art.append(ndi.map_coordinates(hu, c.ct.lps_to_index(s[sel, :3]).T, order=1))
    art = np.concatenate(art) if art else np.array([np.nan])
    res["3_hu"] = {"trace_centerline_median": round(float(np.median(huT))),
                   "cs_gcv_core_median": round(float(np.median(cs_core))) if cs_core.size else None,
                   "expert_arteries_radius_0.45-0.8mm_centerline_median": round(float(np.median(art))),
                   "expert_arteries_n_samples": int(len(art))}

    # ---- 4 junction ----
    path = np.vstack([E[-int(8 / 0.25):], T[1:int(8 / 0.25)]])
    jx = int(8 / 0.25) - 1
    _, n, b = frames(path[:, :3])
    off = np.arange(-3, 3.05, 0.05)
    crops = []
    for ax_ in (n, b):
        pts = path[:, None, :3] + off[None, :, None] * ax_[:, None, :]
        crops.append(ndi.map_coordinates(hu, c.ct.lps_to_index(pts.reshape(-1, 3)).T, order=1).reshape(len(path), len(off)))
    on = ndi.map_coordinates(hu, c.ct.lps_to_index(path[:, :3]).T, order=1)
    sj = (np.arange(len(path)) - jx) * 0.25
    win = np.abs(sj) <= 3
    # lumen count at junction cross-sections: local maxima above half-max within 2.5 mm
    xsJ, gJ = cross_sections(c.ct, path[jx - 4:jx + 9, :3], half=3.0, step=0.1)
    counts = []
    for x in xsJ:
        r = np.hypot(*np.meshgrid(gJ, gJ, indexing="ij"))
        bg = np.median(x[r >= 2.5])
        half = (x[r <= 1].max() + bg) / 2
        lab_, k = ndi.label((x >= half) & (r <= 2.5))
        counts.append(int(k))
    res["4_junction"] = {"centerline_hu_min_within_3mm": round(float(on[win].min())),
                         "centerline_hu_at_junction": round(float(on[jx])),
                         "fat_plane(<0 HU on centerline)": bool(on[win].min() < 0),
                         "lumens_in_cross_sections_-1..+2mm": counts}

    # ---- 5 side branches ----
    ijk = np.rint(c.ct.lps_to_index(T[len(T) // 2, :3])[0]).astype(int)
    r = np.ceil(35 / sp).astype(int)
    lo2 = np.maximum(ijk - r, 0)
    hi2 = np.minimum(ijk + r + 1, hu.shape)
    S2 = tuple(slice(a, b) for a, b in zip(lo2, hi2))
    h2 = hu[S2]
    P2 = c.ct.index_to_lps(lo2)[0]
    tube_d = np.full(h2.shape, 99.0)
    tube_mask = np.zeros(h2.shape, bool)
    ti = np.rint((T[:, :3] - P2) / sp).astype(int)
    tube_mask[tuple(ti.T)] = True
    tube_d = ndi.distance_transform_edt(~tube_mask, sampling=sp)
    chambers = ndi.binary_dilation(ndi.binary_opening(h2 >= 200, structure=ball(4)), iterations=2)
    bone, _, _ = bone_and_pool(c.ct, c.lumen)
    csS2 = np.zeros(h2.shape, bool)
    # map CS mask into S2 coordinates
    cs_full = np.zeros(hu.shape, bool)
    cs_full[B] = cs
    csS2 = ndi.binary_dilation(cs_full[S2], iterations=2)
    sm2 = ndi.gaussian_filter(h2, 0.5)
    branches = {}
    for thr in (215, 200, 185):
        cand2 = (sm2 >= thr) & (sm2 <= 900) & (tube_d <= 6.0) & ~chambers & ~bone[S2] & ~c.lumen[S2] & ~csS2
        lab2, _ = ndi.label(cand2, structure=np.ones((3, 3, 3)))
        ids = np.unique(lab2[tuple(ti.T)])
        ids = ids[ids > 0]
        comp = np.isin(lab2, ids)
        sk = skeletonize(comp)
        # side-branch voxels: skeleton farther than 1.5 mm from the trace centerline
        side = sk & (tube_d > 1.5)
        sl, k = ndi.label(side, structure=np.ones((3, 3, 3)))
        found = []
        for j in range(1, k + 1):
            pts = np.argwhere(sl == j) * sp + P2
            if len(pts) < 2:
                continue
            L = float(np.linalg.norm(pts.max(0) - pts.min(0)))
            if L < 3.0:
                continue
            near = pts[np.argmin(tube_d[sl == j])]
            far = pts[np.argmax(tube_d[sl == j])]
            arc = float(sT[np.argmin(np.linalg.norm(T[:, :3] - near, axis=1))])
            found.append({"arc_mm": round(arc, 1), "extent_mm": round(L, 1), "tip_lps": far.round(1).tolist(),
                          "direction_lps": np.round((far - near) / max(np.linalg.norm(far - near), 1e-6), 2).tolist()})
        branches[str(thr)] = found
    res["5_side_branches_within_6mm_tube"] = branches
    (out / "extension_checks.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))

    # ---- figure ----
    fig = plt.figure(figsize=(24, 15), layout="constrained")
    gs = fig.add_gridspec(3, 4)
    ax = fig.add_subplot(gs[0, 0:2])
    ax.plot(sT, dT, color="tab:red", alpha=0.35)
    ax.plot(sT, ndi.uniform_filter1d(dT, 9), color="tab:red", lw=2, label="trace FWHM diameter (2 mm mean)")
    ax.plot(sE - sE[-1], dE, color="tab:blue", lw=1.5, label="expert distal RCA FWHM diameter (calibration)")
    ax.plot(sE - sE[-1], 2 * Ed[:, 3], "b--", lw=1, label="expert distal RCA 2 x MIS radius")
    ax.axvline(0, color="y", ls="--")
    ax.set_xlabel("arc length from the annotation end (mm) -> toward crux"); ax.set_ylabel("diameter (mm)")
    ax2 = ax.twinx()
    ax2.plot(sT, ndi.uniform_filter1d(pkT, 9), color="k", lw=1, label="trace peak HU")
    ax2.set_ylabel("peak HU (black)")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title(f"1 taper: diameter slope {slope_d:+.2f} mm/10 mm (negative = tapers toward crux)")

    ax = fig.add_subplot(gs[0, 2:4])
    zc = T[-1, 2]
    k0, k1 = [int(round(c.ct.lps_to_index([0, 0, z])[0, 2])) for z in (zc - 8, zc + 14)]
    lo, hi = c.ct.bounds_lps()
    ax.imshow(np.clip(hu[:, :, k0:k1], -100, 450).max(2).T, cmap="gray", vmin=-50, vmax=420, origin="lower",
              extent=[lo[0], hi[0], lo[1], hi[1]])
    if len(cs_pts):
        csm = cs.any(2).T
        rgba = np.zeros(csm.shape + (4,)); rgba[csm] = (0.2, 0.6, 1.0, 0.35)
        e0 = c.ct.index_to_lps(lo_i)[0]; e1 = c.ct.index_to_lps(hi_i - 1)[0]
        ax.imshow(rgba, origin="lower", extent=[e0[0], e1[0], e0[1], e1[1]])
    ax.plot(T[:, 0], T[:, 1], "r-", lw=2, label="trace")
    ax.plot(*T[-1, :2], "ro", ms=8)
    ax.plot(E[-80:, 0], E[-80:, 1], "c-", lw=2, label="expert RCA")
    ax.set_xlim(-30, 55); ax.set_ylim(-15, 50)
    ax.legend(fontsize=8)
    ax.set_title(f"2 CS (blue, rough): trace min distance {res['2_coronary_sinus']['min_distance_trace_to_cs_mm']} mm, "
                 f"crux end {res['2_coronary_sinus']['distance_crux_end_to_cs_mm']} mm")

    ax = fig.add_subplot(gs[1, 0])
    data = [huT, cs_core if cs_core.size else [np.nan], art]
    ax.boxplot(data, showfliers=False)
    ax.set_xticks([1, 2, 3], ["trace\ncenterline", "CS/GCV\ncore", "expert arteries\nr 0.45-0.8 mm"])
    ax.set_ylabel("HU")
    ax.set_title("3 HU fingerprint")

    for j, (crop, name) in enumerate(zip(crops, ("plane 1", "plane 2"))):
        ax = fig.add_subplot(gs[1, 1 + j])
        ax.imshow(crop.T, cmap="gray", vmin=-100, vmax=600, aspect="auto", extent=[sj[0], sj[-1], off[-1], off[0]])
        ax.axvline(0, color="y", ls="--")
        ax.set_xlabel("mm from annotation end (left: expert, right: trace)"); ax.set_ylabel("mm from centerline")
        ax.set_title(f"4 junction zoom, {name} (HU -100..600)")
    ax = fig.add_subplot(gs[1, 3])
    ax.plot(sj, on, "k")
    ax.axvline(0, color="y", ls="--"); ax.axhline(0, color="tab:orange", ls=":", label="fat (< 0 HU)")
    ax.set_xlabel("mm from annotation end"); ax.set_ylabel("centerline HU"); ax.legend(fontsize=8)
    ax.set_title(f"4 centerline HU: min {res['4_junction']['centerline_hu_min_within_3mm']} within 3 mm")

    ax = fig.add_subplot(gs[2, 0:2])
    ax.axis("off")
    lines = ["5 side branches off the trace (skeleton > 1.5 mm from it, >= 3 mm, inside a 6 mm tube, CS excluded):"]
    for thr, f in branches.items():
        lines.append(f"  {thr} HU: {len(f)} candidate(s)")
        for b_ in f:
            lines.append(f"     at arc {b_['arc_mm']} mm, extent {b_['extent_mm']} mm, direction {b_['direction_lps']}, tip {b_['tip_lps']}")
    ax.text(0, 1, "\n".join(lines), va="top", family="monospace", fontsize=10)
    ax = fig.add_subplot(gs[2, 2:4])
    ax.axis("off")
    ax.text(0, 1, json.dumps({k: res[k] for k in ("1_taper", "3_hu", "4_junction")}, indent=1), va="top",
            family="monospace", fontsize=9)
    fig.suptitle(f"{args.case}: is the non-expert RCA extension an artery?  (review aid; extension stays OFF)", fontsize=14)
    fig.savefig(out / "extension_checks.png", dpi=70)
    print("wrote", out / "extension_checks.png")


if __name__ == "__main__":
    main()
