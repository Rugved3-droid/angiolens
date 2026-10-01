"""Build all browser assets for one case into web/public/cases/<id>/.

    python preprocess/scripts/build_case.py --case Normal_12
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))

import numpy as np
from scipy.spatial import cKDTree

from cpt.case import RAW, load_case, sha256
from cpt.centerline import official_graph, skeleton_graph
from cpt.geometry import SID_MM, SOD_MM
from cpt.glb import write_glb
from cpt.masks import bone_and_pool, bone_mesh_mask, review_status
from cpt.mesh import mask_to_mesh, mesh_report

DETECTOR_MM = 250.0


def coverage_vs_skeleton(case, graph) -> dict:
    from skan import Skeleton
    from skimage.morphology import skeletonize
    pts = np.vstack([e["samples"][:, :3] for e in graph.edges])
    sk = Skeleton(skeletonize(case.lumen), spacing=1)
    tree = cKDTree(pts)
    missing = []
    for i in range(sk.n_paths):
        c = case.ct.index_to_lps(sk.path_coordinates(i))
        d, _ = tree.query(c)
        if np.median(d) > 2.0:
            L = float(np.linalg.norm(np.diff(c, axis=0), axis=1).sum())
            missing.append({"length_mm": round(L, 1), "centroid_lps": c.mean(0).round(1).tolist()})
    skp = case.ct.index_to_lps(np.argwhere(skeletonize(case.lumen)))
    d_off, _ = cKDTree(skp).query(pts)
    return {"skeleton_branches_not_in_graph": sorted(missing, key=lambda m: -m["length_mm"]),
            "graph_samples_far_from_skeleton_frac": round(float((d_off > 2).mean()), 4)}


def edge_ids_for(mesh, graph, tree):
    E = [e for e in graph.edges if e["tree"] == tree]
    pts = np.vstack([e["samples"][:, :3] for e in E])
    ids = np.concatenate([np.full(len(e["samples"]), e["id"]) for e in E])
    _, j = cKDTree(pts).query(mesh.vertices)
    return ids[j].astype(np.float32)


def dominance_block(graph, info) -> dict:
    """Facts for the dominance question; the assessment string is from the 2026-09-30 CT review."""
    return {
        "annotated_paths": info["paths"],
        "assessment": ("Not left-dominant. Annotated RCA ends at (-9.6, 0.8, -162.8), ~10-20 mm short of the "
                       "estimated crux (x 0-10, y 20-30, z -150..-160; +/-10 mm). In the CT a contrast-filled, "
                       "unannotated vessel (~1.2 mm diameter, >=250 HU) continues ~33 mm from the RCA end along the "
                       "posterior AV groove to ~(14, 21, -149), i.e. to the crux: likely RIGHT-dominant with the "
                       "distal RCA/PDA not in the expert annotation. LCx (path 5) ends high in the posterior AV "
                       "groove at (44.4, 38.5, -121.3), ~30 mm left of and ~30 mm above the crux; its CT "
                       "continuation runs superiorly (likely great cardiac vein), not to the crux."),
        "status": "indeterminate",
        "status_note": ("2026-09-30 Rugved: indeterminate until the non-expert RCA extension is shown to be artery "
                        "(see DECISIONS D12/D20, out/review/Normal_12/extension_checks.png)"),
        "teaching_note": "PDA/PLB are absent from this case's annotation; they cannot be labeled or injected.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="Normal_12")
    args = ap.parse_args()
    t0 = time.time()
    out = ROOT / "web" / "public" / "cases" / args.case
    out.mkdir(parents=True, exist_ok=True)
    case = load_case(args.case)
    print(f"loaded {time.time() - t0:.0f}s")

    bone, pool, mask_report = bone_and_pool(case.ct, case.lumen)
    print(f"masks {time.time() - t0:.0f}s; review gate: {review_status(args.case, ROOT / 'reviews')['status']}")

    vtp = RAW / args.case / f"Centerlines_{args.case}.vtp"
    if vtp.exists():
        # raises CenterlineFrameError (build stops) unless 100% of points are inside the expert lumen
        graph, cl_info = official_graph(vtp, case.ct, case.left, case.right)
    else:
        print("no official centerlines: skeleton fallback (graph source recorded in case.json)")
        graph, cl_info = skeleton_graph(case.ct, case.left, case.right, pool), {"frame_check": None, "paths": []}
    cov = coverage_vs_skeleton(case, graph)
    (out / "centerlines.json").write_text(json.dumps(graph.to_json()))
    print(f"centerlines ({graph.source}) {time.time() - t0:.0f}s")

    meshes = {}
    for tree, target in (("left", 120_000), ("right", 60_000)):
        m = mask_to_mesh(case.ct, getattr(case, tree), target_faces=target)
        write_glb(out / f"lumen_{tree}.glb", m.vertices, m.faces, m.vertex_normals,
                  edge_ids_for(m, graph, tree), name=f"lumen_{tree}")
        meshes[f"lumen_{tree}"] = mesh_report(m)
    mb = mask_to_mesh(case.ct, bone_mesh_mask(case.ct, bone), smooth_sigma_vox=0.6, step=2,
                      taubin_iters=5)
    write_glb(out / "bone.glb", mb.vertices, mb.faces, mb.vertex_normals, name="bone")
    meshes["bone"] = mesh_report(mb)
    print(f"meshes {time.time() - t0:.0f}s", meshes)

    lo, hi = case.ct.bounds_lps()
    meta = {
        "case_id": args.case,
        "frame": "LPS mm (+x patient left, +y posterior, +z superior); all assets verbatim, no recentering",
        "isocenter_lps_mm": case.isocenter.round(3).tolist(),
        "c_arm": {"sid_mm": SID_MM, "sod_mm": SOD_MM, "detector_mm": DETECTOR_MM},
        "ct_bounds_lps_mm": [lo.round(2).tolist(), hi.round(2).tolist()],
        "inputs_sha256": {p.name: sha256(p) for p in sorted((RAW / args.case).iterdir())},
        "trees": case.split_report,
        "dominance": dominance_block(graph, cl_info),
        "centerlines": {"source": graph.source, "frame_check": cl_info["frame_check"], "coverage": cov,
                        "n_nodes": len(graph.nodes), "n_edges": len(graph.edges)},
        "masks": {**{k: mask_report[k] for k in ("params", "bone_ml", "bone_mesh_ml", "pool_ml")},
                  "review": review_status(args.case, ROOT / "reviews")["status"]},
        "meshes": meshes,
        "annotation": json.loads((ROOT / "reviews" / f"{args.case}.json").read_text()).get("annotation", {})
        if (ROOT / "reviews" / f"{args.case}.json").exists() else {},
        "files": sorted(p.name for p in out.iterdir() if p.name != "case.json") + ["case.json"],
    }
    # the non-expert extension is a separate, separately-reviewed layer: carry its flag over a rebuild
    old = out / "case.json"
    if (out / "extension.json").exists() and old.exists():
        prev = json.loads(old.read_text()).get("non_expert_extension")
        if prev:
            meta["non_expert_extension"] = prev
    (out / "case.json").write_text(json.dumps(meta, indent=1))
    index = ROOT / "web" / "public" / "cases" / "index.json"
    ids = sorted({*json.loads(index.read_text())["cases"], args.case}) if index.exists() else [args.case]
    index.write_text(json.dumps({"cases": ids}, indent=1))
    total = sum(p.stat().st_size for p in out.iterdir())
    print(f"done {time.time() - t0:.0f}s; {total / 1e6:.1f} MB in {out}")


if __name__ == "__main__":
    main()
