"""Gatekeeper for a supplied artist heart model (assets/heart/). Run BEFORE using it.

    python preprocess/scripts/inspect_heart_model.py assets/heart/<file>.glb|.gltf|.obj

Reports (and writes out/review/heart_model/report.json + a contact sheet):
  1. license / copyright text found IN the file (glTF asset.copyright/extras, OBJ/MTL header comments)
     and in any LICENSE/README next to it. A missing license is reported, never assumed.
  2. every mesh/node: name, vertices, faces, materials, textures, bounding size.
  3. coronary check: are the coronaries REAL GEOMETRY (separate tube meshes) or only painted texture?
     - name hints (coronary, LAD, RCA, LCx, circumflex, diagonal, marginal, artery, ...)
     - a geometric tube test per connected component: voxel-skeleton length vs. inscribed radius
       (tubes: long and thin, radius small relative to the heart, many of them branching)
     - texture hints (texture/material names mentioning vessels while no tube geometry exists)
     Verdict: GEOMETRY / TEXTURE-ONLY / UNCLEAR. TEXTURE-ONLY means stop and report to Rugved.
FBX is not readable here (no Blender on this machine): export GLB or OBJ instead.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh

VESSEL_HINT = re.compile(r"coron|\bLAD\b|\bRCA\b|LCX|circumflex|diagonal|marginal|arter|vessel|PDA|\bLM\b|ostium", re.I)
LICENSE_HINT = re.compile(r"licen[cs]e|copyright|\bCC[- ]?(0|BY)|creative commons|public domain|royalty|attribution|©", re.I)


def file_license_text(path: Path) -> list[str]:
    found = []
    if path.suffix.lower() in (".gltf", ".glb"):
        import struct
        data = path.read_bytes()
        if path.suffix.lower() == ".glb":
            jl, _ = struct.unpack_from("<II", data, 12)
            gl = json.loads(data[20:20 + jl])
        else:
            gl = json.loads(data)
        asset = gl.get("asset", {})
        for k in ("copyright", "generator", "extras"):
            if k in asset:
                found.append(f"glTF asset.{k}: {asset[k]}")
        for k in ("extras", "extensionsUsed"):
            if k in gl:
                found.append(f"glTF {k}: {gl[k]}")
    else:
        for f in [path] + sorted(path.parent.glob("*.mtl")):
            for line in f.read_text(errors="ignore").splitlines()[:200]:
                if line.startswith("#") and LICENSE_HINT.search(line):
                    found.append(f"{f.name}: {line.strip()}")
    for f in sorted(path.parent.iterdir()):
        if f.is_file() and re.search(r"licen|readme|copying|attribution|credits", f.name, re.I):
            found.append(f"{f.name}:\n" + f.read_text(errors="ignore")[:2000])
    return found


def tube_score(m: trimesh.Trimesh, pitch: float):
    """Skeleton length / mean inscribed radius of a watertight-ish component via voxelization."""
    from scipy import ndimage as ndi
    from skimage.morphology import skeletonize
    try:
        vox = m.voxelized(pitch).fill()
    except Exception:
        return None
    mat = vox.matrix
    if mat.sum() < 8:
        return None
    edt = ndi.distance_transform_edt(np.pad(mat, 1)) * pitch
    sk = skeletonize(np.pad(mat, 1))
    if sk.sum() == 0:
        return None
    radius = float(np.median(edt[sk]))
    length = float(sk.sum() * pitch)
    return {"skeleton_length": round(length, 2), "median_radius": round(radius, 3),
            "elongation": round(length / max(radius, 1e-6), 1)}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1]).resolve()
    if path.suffix.lower() == ".fbx":
        sys.exit("FBX cannot be read here (no Blender). Please export GLB or OBJ, keeping the coronaries as separate objects.")
    out = ROOT / "out" / "review" / "heart_model"
    out.mkdir(parents=True, exist_ok=True)
    scene = trimesh.load(str(path), force="scene")
    geoms = []
    for node in scene.graph.nodes_geometry:
        T, gname = scene.graph[node]
        g = scene.geometry[gname]
        if not isinstance(g, trimesh.Trimesh):
            continue
        g = g.copy()
        g.apply_transform(T)
        mat = getattr(g.visual, "material", None)
        tex = []
        if mat is not None:
            for attr in ("image", "baseColorTexture", "normalTexture", "emissiveTexture"):
                im = getattr(mat, attr, None)
                if im is not None:
                    tex.append(attr)
        geoms.append({"node": str(node), "geometry": gname, "mesh": g,
                      "material": getattr(mat, "name", None), "textures": tex})
    allv = np.vstack([g["mesh"].vertices for g in geoms])
    size = float(np.linalg.norm(allv.max(0) - allv.min(0)))
    pitch = size / 250.0
    rows, vessel_comps = [], []
    for g in geoms:
        m = g["mesh"]
        name_hit = bool(VESSEL_HINT.search(f"{g['node']} {g['geometry']} {g['material'] or ''}"))
        comps = m.split(only_watertight=False)
        # tube test on the WHOLE mesh (vessels are often built from many short pieces) and per component
        whole = tube_score(m, pitch)
        tubes = [whole] if whole and whole["elongation"] > 25 and whole["median_radius"] < 0.03 * size else []
        for c in sorted(comps, key=lambda c: -len(c.faces))[:40]:
            ts = tube_score(c, pitch)
            if ts and ts["elongation"] > 25 and ts["median_radius"] < 0.03 * size and ts != whole:
                tubes.append(ts)
        row = {"node": g["node"], "geometry": g["geometry"], "material": g["material"], "textures": g["textures"],
               "vertices": int(len(m.vertices)), "faces": int(len(m.faces)), "components": len(comps),
               "bbox_size": np.round(m.extents, 2).tolist(), "vessel_name_hint": name_hit, "tube_like_components": len(tubes),
               "tube_examples": tubes[:3]}
        rows.append(row)
        if tubes:
            vessel_comps.append(row)
    named = [r for r in rows if r["vessel_name_hint"]]
    tex_vessel = [r for r in rows if r["textures"] and re.search(r"vess|coron|arter", f"{r['material']}", re.I)]
    if vessel_comps and (named or len(vessel_comps) >= 1):
        verdict = "GEOMETRY"
    elif tex_vessel or not vessel_comps:
        verdict = "TEXTURE-ONLY" if not vessel_comps else "UNCLEAR"
    else:
        verdict = "UNCLEAR"
    report = {"file": str(path), "units_guess": "model extent %.2f (units unknown; mm if ~100-150)" % size,
              "license_text_found": file_license_text(path) or ["NONE FOUND IN OR NEXT TO THE FILE"],
              "meshes": rows, "coronary_verdict": verdict,
              "verdict_rule": "GEOMETRY = at least one mesh with long thin tube-like components; "
                              "TEXTURE-ONLY = no tube geometry (vessels only painted) -> STOP"}
    (out / "report.json").write_text(json.dumps(report, indent=1))
    # contact sheet: every mesh, vessel candidates in red
    fig = plt.figure(figsize=(12, 12))
    ax = fig.add_subplot(projection="3d")
    for g, r in zip(geoms, rows):
        v = g["mesh"].vertices[:: max(1, len(g["mesh"].vertices) // 4000)]
        ax.scatter(*v.T, s=0.5, c="red" if r["tube_like_components"] else ("orange" if r["vessel_name_hint"] else "0.6"))
    ax.set_title(f"{path.name}: red = tube-like geometry, orange = vessel-named, grey = other  | verdict {verdict}")
    fig.savefig(out / "contact.png", dpi=80)
    print(json.dumps({k: report[k] for k in ("license_text_found", "coronary_verdict", "units_guess")}, indent=1))
    for r in rows:
        print(f"  {r['geometry'][:40]:40s} faces {r['faces']:7d} comps {r['components']:4d} tubes {r['tube_like_components']:3d}"
              f" name-hint {r['vessel_name_hint']!s:5s} material {r['material']}")


if __name__ == "__main__":
    main()
