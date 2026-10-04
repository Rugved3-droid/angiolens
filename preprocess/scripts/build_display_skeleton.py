"""Display skeleton for the atlas scenes (D60, performance): the faint glass-body bones, simplified and merged.

    .venv\\Scripts\\python preprocess\\scripts\\build_display_skeleton.py

The skeleton is drawn at ~10-15% opacity behind glass, yet it was 702k triangles in 278 draw calls, which kept the room and
operator views under 45 fps. For DISPLAY only, every bone is simplified (fast_simplification, quadric decimation) to 25% of
its faces and the bones are merged into two meshes: trunk and limbs (the side views fade the limbs). The X-ray keeps its own
full-resolution closed bones (atlas_xray_bone.glb); nothing here is used for any measurement. No bone is moved as a whole; the
surface deviation (every original vertex to the simplified surface, cpt/surfdist.py) is written to display_skeleton.json.
"""
import json
import re
import shutil
import sys
from pathlib import Path

import fast_simplification as fs
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))
from cpt.closemesh import merge_close  # noqa: E402
from cpt.glb import write_glb  # noqa: E402
from cpt.surfdist import points_to_surface  # noqa: E402

A = ROOT / "assets" / "anatomy"
WEB = ROOT / "web" / "public" / "anatomy"
KEEP = 0.25
# the same limb rule as the viewer (atlasHero.ts LIMB_RE)
LIMB_RE = re.compile(r"humer|radius|ulna|scaphoid|lunate|triquetr|pisiform|trapezi|capitate|hamate|metacarp|phalan|sesamoid|carp|hand|"
                     r"digit|palm|thenar|forearm|antebrach|brachial|cubital|arm\b|arm\.|of arm|wrist|femur|tibia|fibula|patella|talus|"
                     r"calcane|tars|foot|thigh|leg\b|leg\.|knee|ankle|gluteal|crural|femoral|popliteal|malleol|toe", re.I)


def main():
    sc = trimesh.load(A / "z_anatomy_skeleton.glb", process=False)
    groups = {"trunk": ([], []), "limb": ([], [])}
    offs = {"trunk": 0, "limb": 0}
    devs, faces_in, faces_out = [], 0, 0
    for name in sorted(sc.graph.nodes_geometry):
        if name.endswith(".g"):
            continue                                     # the flat "SKELETAL SYSTEM" label board
        T, g = sc.graph[name]
        assert np.allclose(T, np.eye(4)), name
        m = sc.geometry[g]
        V, F = merge_close(np.asarray(m.vertices), np.asarray(m.faces))
        faces_in += len(F)
        if len(F) > 200:
            V2, F2 = fs.simplify(V.astype(np.float32), F.astype(np.int32), target_reduction=1 - KEEP)
            V2, F2 = np.asarray(V2, float), np.asarray(F2, np.int64)
        else:
            V2, F2 = V, F
        if len(F2) == 0:
            V2, F2 = V, F
        d = points_to_surface(V, V2, F2)                  # every original vertex to the simplified SURFACE
        devs.append(float(d.max()))
        faces_out += len(F2)
        key = "limb" if LIMB_RE.search(name) else "trunk"
        Vs, Fs = groups[key]
        Vs.append(V2)
        Fs.append(F2 + offs[key])
        offs[key] += len(V2)
    stats = {"faces_in": faces_in, "faces_out": faces_out, "keep": KEEP,
             "surface_deviation_mm": {"max": round(max(devs), 2), "p99": round(float(np.quantile(devs, 0.99)), 2),
                                          "median": round(float(np.median(devs)), 2)},
             "note": "display only (glass-body bones); the X-ray uses atlas_xray_bone.glb at full resolution"}
    for key, (Vs, Fs) in groups.items():
        V, F = np.vstack(Vs), np.vstack(Fs)
        N = trimesh.Trimesh(V, F, process=False).vertex_normals
        p = A / f"z_anatomy_skeleton_display_{key}.glb"
        write_glb(p, V, F, normals=N, name=f"skeleton_display_{key}", extras={"limb": key == "limb", **stats})
        shutil.copy(p, WEB / p.name)
        stats[f"{key}_faces"] = int(len(F))
    (A / "display_skeleton.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
