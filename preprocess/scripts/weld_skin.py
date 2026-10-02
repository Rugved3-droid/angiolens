"""Weld the Z-Anatomy skin regions into ONE surface (D48).

    .venv\\Scripts\\python preprocess\\scripts\\weld_skin.py          # assets/anatomy/z_anatomy_skin_regions.glb -> z_anatomy_skin.glb

Input: the per-region skin GLB written by export_anatomy.py (240 regions, LPS mm, identity node transforms).
Output: one mesh with
  * POSITION / NORMAL (consistent orientation, smooth across the seams),
  * _ARM, _LEG: per-vertex weights in [0, 1] (1 = arm / leg region; seam vertices get the mean of the regions they join),
    used by the side views to fade the limbs,
  * _REGION: index into extras.region_names (the region a vertex came from; for a merged seam vertex, the first one).
The weld statistics are written into assets/anatomy/manifest.json under "skin_weld".
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))
from cpt.glb import write_glb  # noqa: E402
from cpt.weld import weld  # noqa: E402

ARM = {"Deltoid region", "Anterior region of arm", "Posterior region of arm", "Lateral bicipital groove", "Medial bicipital groove",
       "Anterior region of elbow", "Posterior region of elbow", "Cubital fossa", "Anterior region of forearm", "Posterior region of forearm",
       "Lateral border of forearm", "Medial border of forearm", "Radial foveola", "Anterior region of wrist", "Posterior region of wrist",
       "Dorsum of hand", "Palm", "Dorsal surfaces of digits of hand", "Palmar surfaces of digits of hand"}
LEG = {"Anterior region of thigh", "Posterior region of thigh", "Anterior region of knee", "Posterior region of knee", "Popliteal fossa",
       "Anterior region of leg", "Posterior region of leg", "Anterior region of ankle", "Lateral malleolus", "Medial malleolus",
       "Lateral retromalleolar region", "Medial retromalleolar region", "Dorsum of foot", "Sole", "Heel region", "Lateral border of foot",
       "Medial border of foot", "Lateral part of longitudinal arch of foot", "Medial part of longitudinal arch of foot",
       "Distal transverse arch of foot", "Proximal transverse arch of foot", "Metatarsal region", "Hallucial eminence",
       "Dorsal surfaces of digits of foot", "Plantar surfaces of digits of foot"}


def base(n):
    return re.sub(r"\.(l|r)$", "", n)


def load_regions(path):
    sc = trimesh.load(path, process=False)
    names, Vs, Fs, fr, vr = [], [], [], [], []
    off = 0
    for i, node in enumerate(sorted(sc.graph.nodes_geometry)):
        T, g = sc.graph[node]
        if not np.allclose(T, np.eye(4)):
            raise SystemExit(f"skin region {node} has a non-identity transform")
        m = sc.geometry[g]
        names.append(node)
        Vs.append(np.asarray(m.vertices, float))
        Fs.append(np.asarray(m.faces, np.int64) + off)
        fr.append(np.full(len(m.faces), i))
        vr.append(np.full(len(m.vertices), i))
        off += len(m.vertices)
    return names, np.vstack(Vs), np.vstack(Fs), np.concatenate(fr), np.concatenate(vr)


def main():
    src = ROOT / "assets" / "anatomy" / "z_anatomy_skin_regions.glb"
    dst = ROOT / "assets" / "anatomy" / "z_anatomy_skin.glb"
    names, V, F, fr, vr = load_regions(src)
    w = weld(V, F, fr, outward=True)
    lab = w["labels"]
    n = len(w["V"])
    arm_in = np.array([base(names[r]) in ARM for r in vr], float)
    leg_in = np.array([base(names[r]) in LEG for r in vr], float)
    cnt = np.bincount(lab, minlength=n)
    arm = np.bincount(lab, arm_in, n) / np.maximum(cnt, 1)
    leg = np.bincount(lab, leg_in, n) / np.maximum(cnt, 1)
    region = np.full(n, -1.0)
    for i in range(len(lab) - 1, -1, -1):          # first source region wins
        region[lab[i]] = vr[i]
    used = sorted({base(x) for x in names})
    unknown_limbs = sorted((ARM | LEG) - set(used))
    if unknown_limbs:
        raise SystemExit(f"limb region names not found in the skin: {unknown_limbs}")
    stats = w["stats"]
    stats["regions"] = len(names)
    stats["arm_regions"] = sorted(ARM)
    stats["leg_regions"] = sorted(LEG)
    stats["arm_vertices"] = int((arm > 0).sum())
    stats["leg_vertices"] = int((leg > 0).sum())
    extras = {"anatomical_name": "Skin (welded body surface)", "source": "Z-Anatomy '9: Regions of human body' (D44, D48)",
              "region_names": names, "weld": stats}
    write_glb(dst, w["V"], w["F"], normals=w["N"], name="Skin (welded body surface)", extras=extras,
              attributes={"_ARM": arm, "_LEG": leg, "_REGION": region})
    man_p = ROOT / "assets" / "anatomy" / "manifest.json"
    man = json.loads(man_p.read_text())
    man["skin_weld"] = {"file": "z_anatomy_skin.glb", "input": "z_anatomy_skin_regions.glb", **stats}
    man_p.write_text(json.dumps(man, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
