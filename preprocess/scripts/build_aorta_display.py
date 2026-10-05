"""Display-only aorta (D62): one seamless, locally smoothed solid for the 3D scenes, with the coronary origins filleted.

    .venv\\Scripts\\python preprocess\\scripts\\build_aorta_display.py            # measure, update the manifest, build
    .venv\\Scripts\\python preprocess\\scripts\\build_atlas_cath.py               # then: catheters + fill distances (new ostia)

Same precedent as the pulmonary trunk (D46): a display refinement of ONE structure, every point within 1 mm of the atlas surface,
nothing moved, rotated or scaled. The X-ray never uses this file (the aorta is not in the X-ray; the coronary solids are unchanged).

Method (a signed distance field on a 0.4 mm grid, then marching cubes):
  A   = boolean union of the four aortic segments (ascending, arch, thoracic, abdominal): removes the end-to-end seams.
  A_s = A's distance field, Gaussian-smoothed (sigma 0.8 mm) and clamped to +-1 mm of A: removes the root crease.
  C   = the coronary X-ray solids (the trees drawn in 3D). Split at the effective ostium by the tree distance s:
        C_prox (behind the ostium plane, within 9 mm: the buried trunk, wall-coloured) and C_dist (the rest, drawn as coronary).
  V   = smooth union (polynomial smin, k = 4 mm: at most k/4 = 1 mm of fillet) of A_s, C_prox and C_dist shrunk by 0.25 mm
        (so V's surface stays hidden under the drawn coronary), finally clamped to within 1 mm of A u C.
The effective ostia are re-measured where each trunk centreline leaves A_s (the smoothed wall), and written to the manifest.

Outputs: web/public/anatomy/z_anatomy_aorta_display.glb (POSITION, NORMAL, _END = mm from the free distal end) and
assets/anatomy/aorta_display.json (deviation report, ostia shift, catheter clearance on the smoothed wall).
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
from scipy import ndimage
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocess"))
from cpt.closemesh import cap_holes, merge_close, signed_volume  # noqa: E402
from cpt.glb import write_glb  # noqa: E402

A_DIR = ROOT / "assets" / "anatomy"
WEB = ROOT / "web" / "public" / "anatomy"
SEGMENTS = ["Ascending aorta", "Aortic arch", "Thoracic aorta", "Abdominal aorta"]
H = 0.4             # grid step, mm (11.9 GB machine: ~34 M voxels, peak ~2 GB)
SIGMA = 0.8         # wall smoothing, mm
K = 4.0             # smin blend width, mm (fillet adds at most K/4 = 1 mm)
SHRINK = 0.6        # C_dist shrink, mm: V dives under the drawn coronary at a steeper angle (no sawtooth crossing on its facets)
MAX_DEV = 1.0       # the rule, mm (measured both ways)
FIELD_CLAMP = 0.65  # field clamp, mm
VERTEX_CLAMP = 0.95 # per-vertex clamp after meshing, mm (the pulmonary-trunk rule, D46)
STUB_GROW = 0.4    # mm: the wall-coloured stub is this much fatter than the coronary (no near-coincident surfaces)
STUB_R = 9.0       # the buried trunk is cut by the ostium PLANE within this radius of the effective ostium, mm
FINAL_BLUR = 0.5   # mm: removes the kinks the clamp leaves in the field
BAND = 3.0          # exact distances within this band, mm
OSTIUM_KEY = {"left": "LM", "right": "RCA"}


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def heart_nodes():
    sc = trimesh.load(A_DIR / "z_anatomy_heart.glb", process=False)
    out = {}
    for n in sc.graph.nodes_geometry:
        T, g = sc.graph[n]
        assert np.allclose(T, np.eye(4)), n
        out[n] = sc.geometry[g]
    return out


def closed(m, name):
    V, F = merge_close(m.vertices, m.faces)
    V, F, st = cap_holes(V, F)
    if signed_volume(V, F) < 0:
        F = F[:, ::-1]
    if st["open_edges_after"]:
        raise SystemExit(f"{name}: still open after capping {st}")
    return V, F


def union(parts):
    import manifold3d as mf
    solids = []
    for name, V, F in parts:
        m = mf.Manifold(mf.Mesh(vert_properties=np.asarray(V, np.float32), tri_verts=np.asarray(F, np.uint32)))
        if m.status() != mf.Error.NoError:
            raise SystemExit(f"{name}: not a valid manifold ({m.status()})")
        solids.extend(m.decompose())
    u = mf.Manifold.batch_boolean(solids, mf.OpType.Add)
    mesh = u.to_mesh()
    return np.asarray(mesh.vert_properties, float)[:, :3], np.asarray(mesh.tri_verts, np.int64), len(u.decompose())


class Grid:
    def __init__(self, lo, hi):
        self.lo = np.asarray(lo, float)
        self.n = np.ceil((np.asarray(hi) - self.lo) / H).astype(int) + 1
        log("grid", self.n.tolist(), f"{np.prod(self.n) / 1e6:.1f} M voxels")

    def pts(self, idx):
        return self.lo + np.asarray(idx) * H


def occupancy(grid, V, F):
    """Inside mask by z-column parity: every triangle's crossings with the column centres (jittered off the grid lines)."""
    nx, ny, nz = grid.n
    jx, jy = 1e-4 * np.pi, 1e-4 * np.e
    hits = [[] for _ in range(nx * ny)]
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    lo = np.minimum(np.minimum(a, b), c)
    hi = np.maximum(np.maximum(a, b), c)
    i0 = np.ceil((lo[:, 0] - grid.lo[0]) / H - jx).astype(int)
    i1 = np.floor((hi[:, 0] - grid.lo[0]) / H - jx).astype(int)
    j0 = np.ceil((lo[:, 1] - grid.lo[1]) / H - jy).astype(int)
    j1 = np.floor((hi[:, 1] - grid.lo[1]) / H - jy).astype(int)
    i0, j0 = np.maximum(i0, 0), np.maximum(j0, 0)              # columns outside this grid are not needed
    i1, j1 = np.minimum(i1, nx - 1), np.minimum(j1, ny - 1)
    for t in np.nonzero((i1 >= i0) & (j1 >= j0))[0]:
        I, J = np.meshgrid(np.arange(i0[t], i1[t] + 1), np.arange(j0[t], j1[t] + 1), indexing="ij")
        px = grid.lo[0] + (I.ravel() + jx) * H
        py = grid.lo[1] + (J.ravel() + jy) * H
        # barycentric in xy
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = a[t], b[t], c[t]
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
        w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
        w2 = 1 - w0 - w1
        ok = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        z = w0 * az + w1 * bz + w2 * cz
        for ii, jj, zz in zip(I.ravel()[ok], J.ravel()[ok], z[ok]):
            hits[ii * ny + jj].append(zz)
    occ = np.zeros((nx, ny, nz), bool)
    zc = grid.lo[2] + np.arange(nz) * H
    bad = 0
    for k, hz in enumerate(hits):
        if not hz:
            continue
        hz = np.sort(hz)
        if len(hz) % 2:
            bad += 1
            hz = hz[:-1]
        col = np.zeros(nz, bool)
        for z0, z1 in zip(hz[0::2], hz[1::2]):
            col |= (zc >= z0) & (zc < z1)
        occ[k // ny, k % ny] = col
    return occ, bad


def sdf(grid, V, F, occ, samples_per_mm2=60.0):
    """Signed distance (negative inside): voxel EDT everywhere, exact (dense surface samples) within BAND of the surface."""
    di = ndimage.distance_transform_edt(occ, sampling=H).astype(np.float32)
    do = ndimage.distance_transform_edt(~occ, sampling=H).astype(np.float32)
    f = np.where(occ, -di, do)
    del di, do
    m = trimesh.Trimesh(V, F, process=False)
    n = int(m.area * samples_per_mm2)
    P, fi = trimesh.sample.sample_surface_even(m, n, radius=None)
    # keep TRUE boundary samples only: outside just beyond the face, inside just behind it. A union of end-to-end segments keeps
    # the coplanar caps as an internal double wall (inside on both sides); distances to it would read ~0 inside the solid
    N = m.face_normals[fi]

    def occ_at(p):
        ijk = np.rint((p - grid.lo) / H).astype(int)
        ok = np.all((ijk >= 0) & (ijk < grid.n), 1)
        out = np.zeros(len(p), bool)
        out[ok] = occ[tuple(ijk[ok].T)]
        return out

    keep = ~occ_at(P + 0.6 * N) & occ_at(P - 0.6 * N)
    P = P[keep]
    kd = cKDTree(P)
    band = np.nonzero(np.abs(f) < BAND)
    q = grid.pts(np.stack(band, 1))
    d, _ = kd.query(q, workers=-1)
    f[band] = np.sign(f[band]) * d.astype(np.float32)
    return f, P, int((~keep).sum())


def smin(a, b, k):
    h = np.clip(k - np.abs(a - b), 0, None) / k
    return np.minimum(a, b) - h * h * k * 0.25


def trilinear(f, grid, p):
    return ndimage.map_coordinates(f, ((np.asarray(p) - grid.lo) / H).T, order=1, mode="nearest")


def main():
    t0 = time.time()
    np.random.seed(62)                                     # surface sampling is random: reproducible builds
    heart = heart_nodes()
    man_path = A_DIR / "manifest.json"
    man = json.loads(man_path.read_text())
    cath = json.loads((WEB / "atlas_cath.json").read_text())

    # ---- A: the four aortic segments, closed and unioned ----
    parts = [(n, *closed(heart[n], n)) for n in SEGMENTS]
    VA, FA, bodies = union(parts)
    log("aorta union", len(VA), "verts", len(FA), "faces", bodies, "body")
    # ---- C: the coronary solids (what the 3D scene draws) ----
    cor = {}
    for tree in ("left", "right"):
        g = trimesh.load(WEB / f"atlas_xray_{tree}.glb", force="mesh", process=False)
        cor[tree] = (np.asarray(g.vertices, float), np.asarray(g.faces, np.int64))

    lo = VA.min(0) - 6.0
    hi = VA.max(0) + 6.0
    grid = Grid(lo, hi)
    occA, badA = occupancy(grid, VA, FA)
    log("aorta occupancy, odd columns:", badA)
    fA, PA_b, membraneA = sdf(grid, VA, FA, occA)
    log('aorta: internal double-wall samples dropped:', membraneA)
    del occA
    log("aorta sdf")
    # wall smoothing, clamped
    fAs = ndimage.gaussian_filter(fA, SIGMA / H).astype(np.float32)
    np.clip(fAs, fA - MAX_DEV, fA + MAX_DEV, out=fAs)
    log("smoothed")

    # ---- effective ostia on the smoothed wall ----
    ostia = {}
    for tree in ("left", "right"):
        key = OSTIUM_KEY[tree]
        eo = man["effective_ostia"][key]
        orig = eo.get("atlas_wall_original") or {k: eo[k] for k in ("effective_ostium_LPS", "buried_centreline_length_mm",
                                                                      "wall_normal_LPS", "angle_vessel_to_wall_normal_deg")}
        lines = cath["trees"][tree]["centrelines"]
        pe = np.array(eo["proximal_end_LPS"])
        lk = min(lines, key=lambda k: np.linalg.norm(np.array(lines[k]["points"][0]) - pe))
        P = np.array(lines[lk]["points"], float)
        s_old = np.array(lines[lk]["s_mm"], float)
        # fine resample along the trunk; first exit from the smoothed wall
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
        arc = np.concatenate([[0], np.cumsum(seg)])
        u = np.arange(0, min(arc[-1], 25.0), 0.02)
        Q = np.stack([np.interp(u, arc, P[:, i]) for i in range(3)], 1)
        val = trilinear(fAs, grid, Q)
        j = int(np.argmax(val > 0))
        if val[0] > 0 or j == 0:
            raise SystemExit(f"{key}: trunk does not start inside the smoothed wall")
        w = val[j - 1] / (val[j - 1] - val[j])
        o_new = Q[j - 1] + w * (Q[j] - Q[j - 1])
        buried_new = float(u[j - 1] + w * (u[j] - u[j - 1]))
        gx = np.array([trilinear(fAs, grid, o_new[None] + d)[0] - trilinear(fAs, grid, o_new[None] - d)[0]
                       for d in np.eye(3) * 0.2])
        nrm = gx / np.linalg.norm(gx)
        tng = Q[min(j + 10, len(Q) - 1)] - Q[max(j - 10, 0)]
        tng /= np.linalg.norm(tng)
        shift = float(np.linalg.norm(o_new - np.array(orig["effective_ostium_LPS"])))
        delta_s = buried_new - orig["buried_centreline_length_mm"]       # s_new = s_old - delta_s  (s_old: atlas wall)
        # atlas_cath.json may already carry the new ostium from an earlier run: use the shift relative to ITS buried length
        delta_from_cath = buried_new - (eo["buried_centreline_length_mm"])
        ostia[tree] = {"key": key, "o": o_new, "t": tng, "delta_from_cath": delta_from_cath}
        eo["atlas_wall_original"] = orig
        eo.update({"effective_ostium_LPS": o_new.round(3).tolist(), "buried_centreline_length_mm": round(buried_new, 2),
                   "wall_normal_LPS": nrm.round(4).tolist(), "vessel_direction_LPS": tng.round(4).tolist(),
                   "angle_vessel_to_wall_normal_deg": round(float(np.degrees(np.arccos(np.clip(np.dot(tng, nrm), -1, 1)))), 1),
                   "measured_on": "smoothed display aorta (D62): where the trunk centreline leaves the smoothed wall",
                   "shift_from_atlas_wall_mm": round(shift, 2)})
        log(f"{key}: ostium moved {shift:.2f} mm along the trunk (buried {orig['buried_centreline_length_mm']} -> {buried_new:.2f} mm)")

    # ---- C fields near the root (sub-box around both ostia) ----
    fC = np.full(grid.n, 50.0, np.float32)
    PC_b = []
    sfield = np.full(grid.n, 1e3, np.float32)            # signed distance past the ostium plane near each ostium (+big elsewhere)
    centre = (ostia["left"]["o"] + ostia["right"]["o"]) / 2
    sub_lo = np.maximum(np.floor((np.minimum(ostia["left"]["o"], ostia["right"]["o"]) - 22 - grid.lo) / H).astype(int), 0)
    sub_hi = np.minimum(np.ceil((np.maximum(ostia["left"]["o"], ostia["right"]["o"]) + 22 - grid.lo) / H).astype(int), grid.n)
    sl = tuple(slice(a, b) for a, b in zip(sub_lo, sub_hi))
    sub = Grid.__new__(Grid)
    sub.lo, sub.n = grid.lo + sub_lo * H, sub_hi - sub_lo
    for tree in ("left", "right"):
        Vc, Fc = cor[tree]
        occC, badC = occupancy(sub, Vc, Fc)
        f, Pc_b, _ = sdf(sub, Vc, Fc, occC)
        PC_b.append(Pc_b)
        fC[sl] = np.minimum(fC[sl], f)
        # the stub split: the plane through the effective ostium, normal to the trunk (the shader uses the SAME plane, so the
        # drawn coronary and the wall-coloured stub meet edge to edge)
        idx = np.stack(np.meshgrid(*[np.arange(n) for n in sub.n], indexing="ij"), -1).reshape(-1, 3)
        p = sub.pts(idx)
        o, t = ostia[tree]["o"], ostia[tree]["t"]
        near = np.linalg.norm(p - o, axis=1) < STUB_R
        sv = np.full(len(p), 1e3, np.float32)
        sv[near] = (p[near] - o) @ t
        s_sub = sfield[sl].reshape(-1)
        s_sub[near] = sv[near]
        sfield[sl] = s_sub.reshape(sub.n)
        log(f"coronary {tree}: odd columns {badC}, stub-side voxels {(near & (sv < 0)).sum()}")
    del occC
    fCprox = np.maximum(fC - STUB_GROW, sfield).astype(np.float32)   # the stub a little FATTER than the drawn tube: clear overlap
    fCdist = np.maximum(fC, -sfield).astype(np.float32)
    fV = smin(fAs, np.minimum(fCprox, fCdist + SHRINK), K).astype(np.float32)
    ref = np.minimum(fA, fC)
    np.clip(fV, ref - FIELD_CLAMP, ref + FIELD_CLAMP, out=fV)   # field-level bound (smin is not a true distance: margin)
    fV = ndimage.gaussian_filter(fV, FINAL_BLUR / H).astype(np.float32)
    np.clip(fV, ref - FIELD_CLAMP, ref + FIELD_CLAMP, out=fV)
    del fCprox, fCdist
    log("field built")

    # ---- surface ----
    from skimage.measure import marching_cubes
    verts, faces, _, _ = marching_cubes(fV, 0.0, spacing=(H, H, H))
    verts += grid.lo
    faces = faces[:, ::-1].astype(np.int64)                # outward winding (field negative inside)
    log("marching cubes", len(verts), len(faces))
    import fast_simplification
    # decimate the RAW marching-cubes surface (decimating after smoothing produced stretched fold-over faces), then smooth
    v2, f2 = fast_simplification.simplify(verts.astype(np.float32), faces.astype(np.int32), target_reduction=0.94)
    v2 = v2.astype(float)
    f2 = f2.astype(np.int64)
    # the decimator leaves unreferenced vertices at arbitrary positions: drop them (they are not drawn, but they would enter the
    # vertex clamp and the deviation samples)
    used = np.unique(f2)
    remap = np.full(len(v2), -1, np.int64)
    remap[used] = np.arange(len(used))
    v2, f2 = v2[used], remap[f2]
    # ... and a few tiny detached fragments (4-8 faces, far from the aorta): the aorta is ONE body, keep the largest component
    parts = trimesh.Trimesh(v2, f2, process=False).split(only_watertight=False)
    main_part = max(parts, key=lambda c: len(c.faces))
    dropped = sum(len(c.faces) for c in parts) - len(main_part.faces)
    v2, f2 = np.asarray(main_part.vertices, float), np.asarray(main_part.faces, np.int64)
    log(f"kept the main body; dropped {len(parts) - 1} fragments ({dropped} faces)")
    sm = trimesh.Trimesh(v2, f2, process=False)
    trimesh.smoothing.filter_taubin(sm, lamb=0.5, nu=0.53, iterations=20)   # removes marching-cubes terracing (volume-preserving)
    v2 = np.asarray(sm.vertices, float)
    if signed_volume(v2, f2) < 0:
        f2 = f2[:, ::-1]
    log("decimated", len(v2), len(f2))

    # ---- per-vertex clamp (D46 precedent): no vertex farther than VERTEX_CLAMP from the original surfaces ----
    kd_o = cKDTree(np.vstack([PA_b, np.vstack(PC_b)]))
    d0, i0 = kd_o.query(v2, workers=-1)
    Po = np.vstack([PA_b, np.vstack(PC_b)])
    over = d0 > VERTEX_CLAMP
    v2[over] = Po[i0[over]] + (v2[over] - Po[i0[over]]) * (VERTEX_CLAMP / d0[over])[:, None]
    log(f"vertex clamp: {int(over.sum())} of {len(v2)} vertices pulled to {VERTEX_CLAMP} mm (max before {d0.max():.2f} mm)")
    clamped = int(over.sum())

    # ---- deviation (both directions) ----
    mV = trimesh.Trimesh(v2, f2, process=False)
    PV, _ = trimesh.sample.sample_surface_even(mV, 400000)
    PV = np.vstack([PV, v2])
    # the ORIGINAL surfaces: boundary samples only (the union's internal double walls at the old seams are not surface)
    PA = PA_b
    PC = np.vstack(PC_b)
    kd_orig = cKDTree(np.vstack([PA, PC]))
    d_v2o, _ = kd_orig.query(PV, workers=-1)
    kd_new = cKDTree(PV)
    # original aorta -> V; aortic wall lying INSIDE a coronary solid (under the drawn coronary at the ostia) is hidden, not lost
    hidden = trilinear(fC, grid, PA) < -0.05
    PA = PA[~hidden][:: 4]
    d_a2v, _ = kd_new.query(PA, workers=-1)
    near_root = np.linalg.norm(PV - centre, axis=1) < 40
    dev = {"V_to_original_max_mm": round(float(d_v2o.max()), 3), "V_to_original_p99_mm": round(float(np.percentile(d_v2o, 99)), 3),
           "V_to_original_median_mm": round(float(np.median(d_v2o)), 3),
           "root_V_to_original_max_mm": round(float(d_v2o[near_root].max()), 3),
           "aorta_to_V_max_mm": round(float(d_a2v.max()), 3), "aorta_to_V_p99_mm": round(float(np.percentile(d_a2v, 99)), 3),
           "aorta_to_V_median_mm": round(float(np.median(d_a2v)), 3),
           "vertices_clamped": clamped,
           "aorta_samples_hidden_inside_coronary": int(hidden.sum()), "aorta_internal_double_wall_samples": membraneA,
           "note": "sample-based (about 0.13 mm spacing): includes up to ~0.07 mm of sampling error"}
    log("deviation", dev)
    # what the scene DRAWS: the display aorta plus the coronary from the effective ostium on (s >= 0, unchanged geometry).
    # Next to an ostium the nearest drawn surface to the old aortic wall can be the coronary tube itself.
    PCd = PC[trilinear(sfield, grid, PC) >= 0]
    d_a2d, _ = cKDTree(np.vstack([PV, PCd])).query(PA, workers=-1)
    dev.update({"aorta_to_displayed_max_mm": round(float(d_a2d.max()), 3),
                "aorta_to_displayed_p99_mm": round(float(np.percentile(d_a2d, 99)), 3),
                "aorta_points_over_1mm_from_V_alone": int((d_a2v > 1.0).sum()),
                "rule": "PASS needs V_to_original_max and aorta_to_displayed_max <= 1 mm (sample-based)"})
    log("displayed:", {k: dev[k] for k in ("aorta_to_displayed_max_mm", "aorta_points_over_1mm_from_V_alone")})
    far = PA[d_a2d > 1.0]
    if len(far):
        log("aorta points farther than 1 mm from the displayed surface:", len(far), "bbox", far.min(0).round(1).tolist(),
            far.max(0).round(1).tolist())
        np.savez(A_DIR / "aorta_display_debug.npz", v=v2, f=f2, far=far)
    if dev["V_to_original_max_mm"] > MAX_DEV + 0.05 or dev["aorta_to_displayed_max_mm"] > MAX_DEV + 0.05:
        raise SystemExit(f"deviation above {MAX_DEV} mm: {dev}")

    # ---- catheter clearance on the smoothed wall (JL4 / JR4 from atlas_cath.json, before the engagement zone) ----
    clear = {}
    R = cath["catheter_outer_radius_mm"]
    for cname, shp in cath["shapes"].items():
        S = np.array(shp["polyline"])
        o = ostia[shp["tree"]]["o"]
        t = ostia[shp["tree"]]["t"]
        keep = (np.einsum("ij,j->i", S - o, t) < 0) & (np.linalg.norm(S - o, axis=1) > 4.0)
        c = -trilinear(fAs, grid, S[keep]) - R               # mm from the catheter surface to the smoothed wall (+ = inside)
        clear[cname] = {"min_clearance_to_smoothed_wall_mm": round(float(c.min()), 2), "samples_checked": int(keep.sum()),
                        "tip_inside_coronary_lumen": bool(trilinear(fC, grid, S[-1:])[0] < 0)}
    log("clearance", clear)

    # ---- distal-end distance (_END) for the vessel-end fade: from the abdominal aorta's free (inferior) end ----
    ab = heart["Abdominal aorta"]
    Vab, Fab = merge_close(ab.vertices, ab.faces)
    from cpt.closemesh import boundary_loops
    loops = boundary_loops(Fab)
    if loops:
        ends = [Vab[lp].mean(0) for lp in loops]
        c_end = min(ends, key=lambda c: c[2])
    else:
        c_end = Vab[np.argmin(Vab[:, 2])]
    axis = np.array([0, 0, 1.0])
    end_d = np.clip((v2 - c_end) @ axis, 0, None).astype(np.float32)

    vn = trimesh.Trimesh(v2, f2, process=False).vertex_normals.astype(np.float32)
    out = WEB / "z_anatomy_aorta_display.glb"
    write_glb(out, v2.astype(np.float32), f2.astype(np.uint32), normals=vn, name="aorta_display", attributes={"_END": end_d})
    report = {"method": __doc__.split("Method")[1].split("Outputs")[0].strip(),
              "grid_mm": H, "sigma_mm": SIGMA, "smin_k_mm": K, "shrink_mm": SHRINK, "clamp_mm": MAX_DEV,
              "segments": SEGMENTS, "union_bodies": bodies, "vertices": int(len(v2)), "faces": int(len(f2)),
              "deviation": dev, "ostia": {ostia[t]["key"]: man["effective_ostia"][ostia[t]["key"]] for t in ostia},
              "catheter_clearance_smoothed_wall": clear, "seconds": round(time.time() - t0, 1)}
    man.setdefault("display_refinements", {})["aorta"] = {k: report[k] for k in ("grid_mm", "sigma_mm", "smin_k_mm", "clamp_mm",
                                                                                "deviation", "segments")}
    man_path.write_text(json.dumps(man, indent=1))
    (A_DIR / "aorta_display.json").write_text(json.dumps(report, indent=1))
    # the app's stub cut: the same planes (the drawn coronary starts here)
    (WEB / "aorta_display.json").write_text(json.dumps({"note": "D62 display aorta: coronary stub cut planes", "stub_cut": {
        tree: {"origin_LPS": ostia[tree]["o"].round(4).tolist(), "normal_LPS": ostia[tree]["t"].round(5).tolist(),
               "radius_mm": STUB_R, "coronary_drawn_from_mm": -2.0} for tree in ostia}}, indent=1))
    log("wrote", out.name, "and the manifest;", report["seconds"], "s")
    for c in clear.values():
        if c["min_clearance_to_smoothed_wall_mm"] < 0 or not c["tip_inside_coronary_lumen"]:
            raise SystemExit(f"catheter clearance failed on the smoothed wall: {clear}")


if __name__ == "__main__":
    main()
