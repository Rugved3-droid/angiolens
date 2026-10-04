"""Closed X-ray meshes from the Z-Anatomy export (D49), for the atlas sanity sheet and the Scene 4 X-ray pass.

    .venv\\Scripts\\python preprocess\\scripts\\build_atlas_xray.py

Reads assets/anatomy/z_anatomy_heart.glb (atlas radii) and z_anatomy_skeleton.glb, writes to assets/anatomy/ and web/public/anatomy/:
  atlas_xray_left.glb / atlas_xray_right.glb  one closed mesh per coronary tree (tube ends fan-capped, nothing moved)
  atlas_xray_heart.glb                        the four chambers, capped (faint heart silhouette)
  atlas_xray_bone.glb                         closed thoracic bones near the heart (faint skeleton)
  atlas_xray.json                             isocenter = volume centroid of both coronary trees (fixed), tree split, cap stats
Every heart uses its own coronaries: all of this is the one Z-Anatomy atlas, under its one transform.
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))
from cpt.closemesh import cap_holes, merge_close, signed_volume, volume_centroid  # noqa: E402
from cpt.glb import write_glb  # noqa: E402

A = ROOT / "assets" / "anatomy"
WEB = ROOT / "web" / "public" / "anatomy"
# split coronary objects are represented by their spline children only (the parent mesh duplicates them)
LEFT_WHOLE = ["Left coronary artery", "Septal branches of anterior interventricular artery"]
RIGHT_WHOLE = ["Right inferolateral branch of right coronary artery"]
CHAMBERS = ["Left ventricle", "Right ventricle", "Left atrium", "Right atrium"]
BONE_RADIUS_MM = 300.0      # bones whose centre lies within this distance of the isocenter


def nodes(path):
    sc = trimesh.load(path, process=False)
    out = {}
    for n in sc.graph.nodes_geometry:
        T, g = sc.graph[n]
        if not np.allclose(T, np.eye(4)):
            raise SystemExit(f"{path.name}: node {n} has a non-identity transform")
        out[n] = sc.geometry[g]
    return out


def boolean_union(parts, label):
    """One closed solid from overlapping closed parts (manifold3d). Each part must be a valid manifold; the union removes the
    double path where a branch starts inside its parent (D52).
    D55: multi-spline parts (septal branches, right inferolateral branch) hold several tubes in ONE mesh; fed as one input, their
    overlaps with the parent were not merged. Every part is therefore split into its connected tubes before the union."""
    import manifold3d as mf
    solids = []
    for name, V, F in parts:
        m = mf.Manifold(mf.Mesh(vert_properties=np.asarray(V, np.float32), tri_verts=np.asarray(F, np.uint32)))
        if m.status() != mf.Error.NoError:
            raise SystemExit(f"{label}: {name} is not a valid manifold for the union ({m.status()})")
        solids.extend(m.decompose())
    u = mf.Manifold.batch_boolean(solids, mf.OpType.Add)
    if u.status() != mf.Error.NoError:
        raise SystemExit(f"{label}: union failed ({u.status()})")
    mesh = u.to_mesh()
    V = np.asarray(mesh.vert_properties, float)[:, :3]
    F = np.asarray(mesh.tri_verts, np.int64)
    return V, F, {"parts": len(parts), "union_volume_mm3": round(float(u.volume()), 1),
                  "summed_volume_mm3": round(float(sum(s.volume() for s in solids)), 1), "genus": int(u.genus()),
                  "union_bodies": len(u.decompose())}


def closed_union(meshes, label, strict=True, parts_out=None):
    """Concatenate closed parts. strict: any mesh that stays open stops the build; otherwise it is skipped and listed.
    parts_out (list): receives (name, V, F) of every closed part, for the boolean union."""
    Vs, Fs, stats, off = [], [], [], 0
    for name, m in meshes:
        V, F = merge_close(m.vertices, m.faces)
        V, F, st = cap_holes(V, F)
        if signed_volume(V, F) < 0:
            F = F[:, ::-1]
            st["inverted"] = True
        if st["open_edges_after"]:                     # a few non-manifold edges do not break path length; open ones do
            if strict:
                raise SystemExit(f"{label}: {name} still open after capping ({st})")
            stats.append({"name": name, "skipped": True, **st})
            continue
        stats.append({"name": name, **st})
        if parts_out is not None:
            parts_out.append((name, V, F))
        Vs.append(V)
        Fs.append(F + off)
        off += len(V)
    return np.vstack(Vs), np.vstack(Fs), stats


def main():
    heart = nodes(A / "z_anatomy_heart.glb")
    left = [(n, heart[n]) for n in LEFT_WHOLE] + [(n, m) for n, m in sorted(heart.items()) if n.startswith(("LAD_branch_", "LCx_branch_"))]
    right = [(n, heart[n]) for n in RIGHT_WHOLE] + [(n, m) for n, m in sorted(heart.items()) if n.startswith("RCA_branch_")]
    pl, pr = [], []
    VLs, FLs, sl = closed_union(left, "left tree", parts_out=pl)        # summed parts: kept only for the before/after (D52)
    VRs, FRs, sr = closed_union(right, "right tree", parts_out=pr)
    # D55: floating branch tubes (separate from the ostial trunk's component) and illustrative bridges for gaps <= 3 mm
    from cpt.bridges import analyse
    probe = json.loads((A / "inspect" / "great_vessels_probe.json").read_text())
    floating = {}
    for tree, parts, root in (("left", pl, "Left coronary artery#0"), ("right", pr, "Right coronary artery#0")):
        rep, br, ntubes = analyse(parts, probe, root)
        floating[tree] = {"tubes": ntubes, "floating_components": rep}
        parts.extend(br)                                      # bridges join the union (and are drawn in 3D, see below)
        if br:
            Vb = np.vstack([V for _, V, _ in br])
            Fb = np.vstack([F + sum(len(v) for _, v, _ in br[:k]) for k, (_, _, F) in enumerate(br)])
            write_glb(A / f"atlas_bridges_{tree}.glb", Vb, Fb, name=f"atlas_bridges_{tree}", extras={"note": "illustrative bridges, D55"})
            shutil.copy(A / f"atlas_bridges_{tree}.glb", WEB / f"atlas_bridges_{tree}.glb")
        else:
            for d in (A, WEB):
                (d / f"atlas_bridges_{tree}.glb").unlink(missing_ok=True)
    VL, FL, ul = boolean_union(pl, "left tree")
    VR, FR, ur = boolean_union(pr, "right tree")
    cl, vl = volume_centroid(VL, FL)
    cr, vr = volume_centroid(VR, FR)
    iso = (cl * vl + cr * vr) / (vl + vr)
    cls_, vls = volume_centroid(VLs, FLs)
    crs, vrs = volume_centroid(VRs, FRs)
    iso_summed = (cls_ * vls + crs * vrs) / (vls + vrs)
    for name, V, F in (("left_summed", VLs, FLs), ("right_summed", VRs, FRs)):
        write_glb(A / f"atlas_xray_{name}.glb", V, F, name=f"atlas_xray_{name}", extras={"source": "Z-Anatomy", "note": "pre-union, D52"})
    VH, FH, sh = closed_union([(n, heart[n]) for n in CHAMBERS], "heart")
    skel = nodes(A / "z_anatomy_skeleton.glb")
    bones = []
    for n, m in sorted(skel.items()):
        if n.endswith(".g"):
            continue
        c = np.asarray(m.vertices).mean(0)
        if np.linalg.norm(c - iso) <= BONE_RADIUS_MM:
            bones.append((n, m))
    VB, FB, sb = closed_union(bones, "bones", strict=False)
    meta = {
        "source": "Z-Anatomy Startup.blend via z_anatomy_heart.glb (atlas radii, D46) and z_anatomy_skeleton.glb",
        "frame": "LPS mm (atlas frame, identity transform)",
        "isocenter_LPS": [round(float(x), 3) for x in iso],
        "isocenter_rule": "volume centroid of both UNIONED coronary trees (fixed; never moves with the injected tree)",
        "isocenter_before_union_LPS": [round(float(x), 3) for x in iso_summed],
        "trees": {"left": {"meshes": [s["name"] for s in sl], "volume_mm3": round(vl, 1), "centroid_LPS": cl.round(2).tolist(), "union": ul},
                  "right": {"meshes": [s["name"] for s in sr], "volume_mm3": round(vr, 1), "centroid_LPS": cr.round(2).tolist(), "union": ur}},
        "caps": {"left": sl, "right": sr, "heart": sh},
        "floating_branches": floating,
        "bones": {"radius_mm": BONE_RADIUS_MM, "used": [x["name"] for x in sb if not x.get("skipped")],
                  "skipped_not_closable": [x["name"] for x in sb if x.get("skipped")]},
        "note": "tube ends and valve rings are fan-capped from their own rim centroid; no vertex is moved (D49)",
    }
    WEB.mkdir(parents=True, exist_ok=True)
    for name, V, F in (("left", VL, FL), ("right", VR, FR), ("heart", VH, FH), ("bone", VB, FB)):
        p = A / f"atlas_xray_{name}.glb"
        write_glb(p, V, F, name=f"atlas_xray_{name}", extras={"source": "Z-Anatomy", "closed": True})
        shutil.copy(p, WEB / p.name)
    (A / "atlas_xray.json").write_text(json.dumps(meta, indent=1))
    man_p = A / "manifest.json"
    man = json.loads(man_p.read_text())
    man["illustrative_bridges"] = [{"tree": t, **c} for t, f in floating.items() for c in f["floating_components"] if c["bridge"]]
    man["floating_branches"] = floating
    man_p.write_text(json.dumps(man, indent=1))
    print("floating components:", {t: len(f["floating_components"]) for t, f in floating.items()},
          "bridges:", len(man["illustrative_bridges"]))
    shutil.copy(A / "atlas_xray.json", WEB / "atlas_xray.json")
    print(json.dumps({"isocenter_LPS": meta["isocenter_LPS"], "isocenter_before_union_LPS": meta["isocenter_before_union_LPS"],
                      "union_left": ul, "union_right": ur, "left_mm3": meta["trees"]["left"]["volume_mm3"],
                      "right_mm3": meta["trees"]["right"]["volume_mm3"], "bones_used": sum(not x.get("skipped") for x in sb), "bones_skipped": [x["name"] for x in sb if x.get("skipped")],
                      "left_meshes": len(sl), "right_meshes": len(sr)}, indent=1))


if __name__ == "__main__":
    main()
