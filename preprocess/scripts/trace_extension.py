"""Trace a NON-EXPERT extension beyond an expert endpoint and build its review overlay.

    python preprocess/scripts/trace_extension.py --case Normal_12 --edge 1 --threshold 230
Writes web/public/cases/<id>/extension.json (separate layer) and sets case.json["non_expert_extension"].
The layer stays default-OFF until --approve is passed after reviewing out/review/<id>/extension_overlay.png.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage as ndi

from cpt.case import load_case
from cpt.centerline import resample
from cpt.extension import trace_extension
from cpt.geometry import CArm
from cpt.masks import bone_and_pool
from cpt.render import DetectorGrid

EXT_ID_OFFSET = 1000
ATTEMPT_THRESHOLDS = (250, 230, 210, 200)


def cpr(ct, path, half_mm=8.0, step=0.25):
    """Straightened reformats along `path` in two orthogonal planes, plus HU on the path."""
    p = resample(path, step)[:, :3]
    t = np.gradient(p, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    n = np.cross(t, [0, 0, 1.0])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    b = np.cross(t, n)
    off = np.arange(-half_mm, half_mm + step, step)
    vol = ct.data.astype(np.float32)
    out = []
    for ax in (n, b):
        pts = p[:, None, :] + off[None, :, None] * ax[:, None, :]
        out.append(ndi.map_coordinates(vol, ct.lps_to_index(pts.reshape(-1, 3)).T, order=1).reshape(len(p), len(off)))
    on = ndi.map_coordinates(vol, ct.lps_to_index(p).T, order=1)
    return out, on, off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="Normal_12")
    ap.add_argument("--edge", type=int, default=1, help="expert edge whose distal end is extended")
    ap.add_argument("--threshold", type=float, default=230)
    ap.add_argument("--approve", action="store_true", help="mark reviewed: layer default ON in the app")
    args = ap.parse_args()
    case_dir = ROOT / "web" / "public" / "cases" / args.case
    out = ROOT / "out" / "review" / args.case
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((case_dir / "case.json").read_text())
    cl = json.loads((case_dir / "centerlines.json").read_text())

    if args.approve:
        ext = meta.get("non_expert_extension")
        if not ext:
            sys.exit("no extension to approve; run without --approve first")
        ext.update(status="reviewed and approved by Rugved", default_visible=True, approved=str(date.today()))
        (case_dir / "case.json").write_text(json.dumps(meta, indent=1))
        print("approved; layer default ON")
        return

    c = load_case(args.case)
    bone, _, _ = bone_and_pool(c.ct, c.lumen)
    expert = next(e for e in cl["edges"] if e["id"] == args.edge)
    S = np.array(expert["samples"])
    start = S[-1, :3]

    attempts = {}
    for thr in sorted(set(ATTEMPT_THRESHOLDS) | {args.threshold}, reverse=True):
        r = trace_extension(c.ct, c.lumen, bone, start, thr)
        attempts[thr] = r
        summary = {k: v for k, v in r.items() if k not in ("graph", "component", "roi_lo")}
        print(f"threshold {thr}: {json.dumps(summary)}")
    chosen = attempts[args.threshold]
    if not chosen["traceable"]:
        sys.exit(f"not traceable at {args.threshold}: {chosen['reason']}")
    g = chosen["graph"]

    # ---- separate layer file ----
    end_node = expert["b"]
    edges = []
    for e in g.edges:
        edges.append({"id": EXT_ID_OFFSET + e["id"], "tree": "right", "non_expert": True,
                      "attached_to_expert_node": end_node if e["a"] == 0 else None,
                      "a": EXT_ID_OFFSET + e["a"], "b": EXT_ID_OFFSET + e["b"],
                      "length_mm": round(float(np.linalg.norm(np.diff(e["samples"][:, :3], axis=0), axis=1).sum()), 2),
                      "samples": np.round(resample(e["samples"]), 3).tolist()})
    nodes = [{"id": EXT_ID_OFFSET + n["id"], "kind": n["kind"] if n["id"] else "attachment", "tree": "right",
              "pos": np.round(n["pos"], 3).tolist()} for n in g.nodes]
    layer = {
        "case_id": args.case, "non_expert": True,
        "provenance": {"method": "semi-automatic contrast-component trace (cpt/extension.py)",
                       "threshold_hu": args.threshold, "from_expert_edge": args.edge, "from_point": start.round(3).tolist(),
                       "created": str(date.today()), "attempts": {str(k): v.get("branches", v.get("reason")) for k, v in attempts.items()}},
        "caveats": ["NOT part of the expert ASOCA annotation",
                    "radius is the in-component distance to the boundary (lower bound, partial-volume limited)",
                    "artery vs accompanying vein not distinguishable automatically; human review required"],
        "nodes": nodes, "edges": edges,
    }
    (case_dir / "extension.json").write_text(json.dumps(layer))
    # closed tube mesh for rendering, starting where the path leaves the expert lumen (no double counting)
    from cpt.glb import write_glb
    from cpt.mesh import mask_to_mesh
    from cpt.synthetic import capsule_mask
    lumen_d = ndi.distance_transform_edt(~c.lumen, sampling=c.ct.spacing)
    segs = []
    for e in g.edges:
        s_ = resample(e["samples"], 0.25)
        outside = ndi.map_coordinates(lumen_d, c.ct.lps_to_index(s_[:, :3]).T, order=1) > 0.3
        s_ = s_[np.argmax(outside):] if outside.any() else s_[:0]
        segs += [(s_[i, :3], s_[i + 1, :3], s_[i, 3]) for i in range(len(s_) - 1)]
    tube = capsule_mask(segs, spacing=0.12)
    m = mask_to_mesh(tube, tube.data > 0.5, smooth_sigma_vox=0.8, target_faces=20000, taubin_iters=0)
    write_glb(case_dir / "extension.glb", m.vertices, m.faces, m.vertex_normals,
              np.full(len(m.vertices), EXT_ID_OFFSET, np.float32), name="non_expert_extension",
              extras={"non_expert": True})
    print("extension mesh watertight", m.is_watertight, "faces", len(m.faces))
    meta["non_expert_extension"] = {"file": "extension.json", "status": "PENDING REVIEW", "default_visible": False,
                                    "edges": [e["id"] for e in edges], "threshold_hu": args.threshold,
                                    "total_length_mm": round(sum(e["length_mm"] for e in edges), 1)}
    for f in ("extension.json", "extension.glb"):
        if f not in meta["files"]:
            meta["files"].insert(-1, f)
    (case_dir / "case.json").write_text(json.dumps(meta, indent=1))

    # ---- review overlay ----
    rca = [np.array(e["samples"]) for e in cl["edges"] if e["tree"] == "right"]
    ext_main = max((e["samples"] for e in g.edges), key=len)
    fig = plt.figure(figsize=(24, 15), layout="constrained")
    gs = fig.add_gridspec(3, 4)
    grid = DetectorGrid(250, 500)
    colors = {250: "#888888", 230: "#ff2d2d", 210: "#ff9a2d", 200: "#ffd02d"}
    for k, (a, b) in enumerate([(45, 0), (-30, 0), (30, 20), (0, -30)]):
        ax = fig.add_subplot(gs[0, k])
        cm = CArm(a, b, c.isocenter)
        ax.set_facecolor("#e8e8e8")
        for s in rca:
            rc = grid.screen_to_pixel(cm.project(s[:, :3]))
            ax.plot(rc[:, 1], rc[:, 0], color="#1f4fbf", lw=3, solid_capstyle="round")
        for thr, r in sorted(attempts.items()):
            if not r["traceable"]:
                continue
            for e in r["graph"].edges:
                rc = grid.screen_to_pixel(cm.project(e["samples"][:, :3]))
                ax.plot(rc[:, 1], rc[:, 0], ls="--" if thr == args.threshold else ":", color=colors.get(thr, "k"),
                        lw=2.5 if thr == args.threshold else 1.5, label=f"extension @{thr} HU" if e["id"] == 0 else None)
        rc = grid.screen_to_pixel(cm.project(start))
        ax.plot(rc[0, 1], rc[0, 0], "kx", ms=10, mew=2)
        ax.set_xlim(60, 380); ax.set_ylim(420, 100); ax.set_aspect("equal")
        ax.set_title(f"{cm.label}: RCA expert (blue) + extension (dashed)")
        ax.set_xticks([]); ax.set_yticks([])
        if k == 0:
            ax.legend(fontsize=8, loc="upper right")

    # slab MIP (axial) around the extension
    ax = fig.add_subplot(gs[1, 0:2])
    zs = ext_main[:, 2]
    k0, k1 = [int(round(c.ct.lps_to_index([0, 0, z])[0, 2])) for z in (zs.min() - 6, zs.max() + 6)]
    lo, hi = c.ct.bounds_lps()
    mip = np.clip(c.ct.data[:, :, k0:k1 + 1], -200, 700).max(2).T
    ax.imshow(mip, cmap="gray", vmin=-100, vmax=600, origin="lower", extent=[lo[0], hi[0], lo[1], hi[1]])
    for s in rca:
        ax.plot(s[:, 0], s[:, 1], color="#4f8fff", lw=1.5)
    for e in g.edges:
        ax.plot(e["samples"][:, 0], e["samples"][:, 1], "--", color="#ff2d2d", lw=2)
    ax.plot(*start[:2], "yx", ms=10, mew=2)
    ax.set_xlim(start[0] - 35, start[0] + 45); ax.set_ylim(start[1] - 30, start[1] + 40)
    ax.set_title(f"axial slab MIP z {zs.min() - 6:.0f}..{zs.max() + 6:.0f} (x right = patient LEFT, y up = POSTERIOR); x = expert RCA end")

    # straightened CPR: last 40 mm of expert RCA + main extension branch
    s_exp = resample(S)[:, :]
    s_exp = s_exp[np.r_[0, np.cumsum(np.linalg.norm(np.diff(s_exp[:, :3], axis=0), axis=1))] >=
                  np.linalg.norm(np.diff(s_exp[:, :3], axis=0), axis=1).sum() - 40]
    path = np.vstack([s_exp, ext_main[1:]])
    (img_n, img_b), on, off = cpr(c.ct, path)
    junction = len(resample(s_exp, 0.25)) - 1
    L = np.arange(len(on)) * 0.25
    for j, (img, name) in enumerate([(img_n, "plane 1"), (img_b, "plane 2 (orthogonal)")]):
        ax = fig.add_subplot(gs[1, 2 + j])
        ax.imshow(img.T, cmap="gray", vmin=-100, vmax=650, aspect="auto", extent=[0, L[-1], off[-1], off[0]])
        ax.axvline(L[junction], color="y", ls="--")
        ax.set_title(f"straightened CPR, {name}; yellow = end of expert annotation")
        ax.set_xlabel("arc length (mm)"); ax.set_ylabel("mm from centerline")
    ax = fig.add_subplot(gs[2, 0:2])
    ax.plot(L, on, color="k", lw=1)
    ax.plot(L, ndi.uniform_filter1d(on, 9), color="tab:red", lw=2, label="HU on centerline (2 mm mean)")
    ax.axvline(L[junction], color="y", ls="--", label="end of expert annotation")
    ax.axhline(args.threshold, color="tab:red", ls=":", label=f"trace threshold {args.threshold} HU")
    ax.set_xlabel("arc length (mm)"); ax.set_ylabel("HU"); ax.legend()
    ax2 = ax.twinx()
    rp = resample(path, 0.25)[:, 3]
    ax2.plot(L[:len(rp)], rp, color="tab:blue", lw=1.5)
    ax2.set_ylabel("radius (mm): expert MIS radius, then extension lower bound", color="tab:blue")
    ax.set_title("HU and caliber along the path")
    ax = fig.add_subplot(gs[2, 2:4])
    ax.axis("off")
    lines = [f"Threshold attempts from expert edge {args.edge} end {start.round(1).tolist()}:"]
    for thr, r in sorted(attempts.items(), reverse=True):
        if r["traceable"]:
            leak = " (LEAKS into a large network: rejected)" if r["component_mm3"] > 200 else ""
            lines.append(f"  {thr} HU: {len(r['branches'])} branch(es), component {r['component_mm3']} mm3{leak}")
            for bdesc in sorted(r["branches"], key=lambda b: -b["length_mm"])[:3]:
                lines.append(f"     {bdesc['length_mm']} mm, median HU {bdesc['hu_median']}, "
                             f"radius {bdesc['radius_median_mm']} mm, ends {bdesc['end']}")
        else:
            lines.append(f"  {thr} HU: not traceable ({r['reason']})")
    lines += ["", f"Chosen layer: {args.threshold} HU (dashed red). NON-EXPERT. Default OFF until approved.",
              "Artery vs accompanying vein cannot be decided automatically."]
    ax.text(0, 1, "\n".join(lines), va="top", family="monospace", fontsize=10)
    fig.suptitle(f"{args.case}: non-expert distal RCA extension, REVIEW BEFORE ENABLING", fontsize=14)
    fig.savefig(out / "extension_overlay.png", dpi=70)
    print("wrote", out / "extension_overlay.png")


if __name__ == "__main__":
    main()
