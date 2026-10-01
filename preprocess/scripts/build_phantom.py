"""Synthetic 'phantom' case for end-to-end tests of the browser renderer (no patient data).

    python preprocess/scripts/build_phantom.py
Writes web/public/cases/phantom/ (same layout as a real case) plus expected.json: path-length
images from the Python reference renderer for a set of poses, row 0 = top.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))

import numpy as np
from scipy.spatial import cKDTree

from cpt.centerline import build_from_paths
from cpt.geometry import CArm, SID_MM, SOD_MM
from cpt.glb import write_glb
from cpt.mesh import mask_to_mesh, mesh_report
from cpt.render import DetectorGrid, thickness_image
from cpt.synthetic import capsule_mask

ISO = np.array([12.0, -40.0, -150.0])      # deliberately off-origin
DETECTOR_MM = 250.0
PX = 128
POSES = [(0, 0), (-30, 0), (45, 0), (-30, -25), (40, 30), (-75, 40)]


def tube(a, b, r, n=200):
    t = np.linspace(0, 1, n)[:, None]
    return np.c_[a + t * (b - a), np.full(n, r)]


def main():
    out = ROOT / "web" / "public" / "cases" / "phantom"
    out.mkdir(parents=True, exist_ok=True)
    o = ISO
    left_paths = [
        np.vstack([tube(o, o + [60, 0, 0], 2.0)]),                                   # -> patient LEFT
        np.vstack([tube(o, o + [20, 0, 0], 2.0), tube(o + [20, 0, 0], o + [20, 0, 40], 1.5)[1:]]),  # -> SUPERIOR
        np.vstack([tube(o, o + [20, 0, 0], 2.0), tube(o + [20, 0, 0], o + [20, -40, -10], 1.2)[1:]]),  # -> ANTERIOR
    ]
    right_paths = [tube(o + [-30, -10, -10], o + [-30, -10, -60], 1.8)]
    spine = [(o + [-5, 85, -70], o + [-5, 85, 70], 12.0)]

    def mask_of(paths):
        segs = [(p[i, :3], p[i + 1, :3], p[i, 3]) for p in paths for i in range(0, len(p) - 1, 4)]
        segs += [(p[-1, :3], p[-1, :3], p[-1, 3]) for p in paths]
        return capsule_mask(segs, spacing=0.35)

    graph = build_from_paths(left_paths + right_paths, ["left"] * 3 + ["right"])
    (out / "centerlines.json").write_text(json.dumps(graph.to_json()))
    meshes, expected = {}, {}
    for tree, paths in (("left", left_paths), ("right", right_paths)):
        vol = mask_of(paths)
        m = mask_to_mesh(vol, vol.data > 0.5, smooth_sigma_vox=0.5, taubin_iters=0)
        E = [e for e in graph.edges if e["tree"] == tree]
        pts = np.vstack([e["samples"][:, :3] for e in E])
        ids = np.concatenate([np.full(len(e["samples"]), e["id"]) for e in E])
        _, j = cKDTree(pts).query(m.vertices)
        write_glb(out / f"lumen_{tree}.glb", m.vertices, m.faces, m.vertex_normals, ids[j].astype(np.float32))
        meshes[tree] = mesh_report(m)
        if tree == "left":
            grid = DetectorGrid(DETECTOR_MM, PX)
            for a, b in POSES:
                expected[f"{a},{b}"] = thickness_image(CArm(a, b, ISO), vol, grid).astype(np.float32).ravel().round(4).tolist()
    sv = capsule_mask(spine, spacing=0.7)
    mb = mask_to_mesh(sv, sv.data > 0.5, taubin_iters=0)
    write_glb(out / "bone.glb", mb.vertices, mb.faces, mb.vertex_normals)
    meshes["bone"] = mesh_report(mb)

    meta = {"case_id": "phantom", "frame": "LPS mm (synthetic)", "isocenter_lps_mm": ISO.tolist(),
            "c_arm": {"sid_mm": SID_MM, "sod_mm": SOD_MM, "detector_mm": DETECTOR_MM},
            "centerlines": {"source": "synthetic"}, "meshes": meshes,
            "files": ["bone.glb", "centerlines.json", "lumen_left.glb", "lumen_right.glb", "case.json"]}
    (out / "case.json").write_text(json.dumps(meta, indent=1))
    # Phase 2 metrics for the longest left edge (target), others = remaining left edges
    from cpt.metrics import angle_maps, combined_cost, view_metrics
    # use exactly what the app reads (centerlines.json, rounded to 0.001 mm)
    cl = json.loads((out / "centerlines.json").read_text())
    left_edges = [{**e, "samples": np.array(e["samples"])} for e in cl["edges"] if e["tree"] == "left"]
    tgt = max(left_edges, key=lambda e: len(e["samples"]))
    bif = np.array([cl["nodes"][i]["pos"] for i in (tgt["a"], tgt["b"]) if cl["nodes"][i]["kind"] == "bifurcation"]).reshape(-1, 3)
    others = [e["samples"] for e in left_edges if e is not tgt]
    mexp = {}
    for a, b in [(0, 0), (-30, -25), (45, 0), (40, 30)]:
        m = view_metrics(CArm(a, b, ISO), tgt["samples"], bif, others)
        mexp[f"{a},{b}"] = {k: m[k] for k in ("F", "O_inter", "O_self", "O_any")}
    maps = angle_maps(ISO, tgt["samples"], bif, others, step=2)
    cost = combined_cost(maps["F"], maps["O_any"])
    j, i = np.unravel_index(np.argmin(cost), cost.shape)
    (out / "expected.json").write_text(json.dumps({"px": PX, "detector_mm": DETECTOR_MM, "images": expected,
                                                   "metrics": {"target_edge": tgt["id"], "poses": mexp,
                                                               "optimum": [float(maps["alpha"][i]), float(maps["beta"][j]), float(cost[j, i])]}}))
    print("phantom meshes", meshes)


if __name__ == "__main__":
    main()
