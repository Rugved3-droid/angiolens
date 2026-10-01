"""Surface meshes from voxel masks, in LPS mm, closed and outward-oriented.

Closedness and outward winding matter: the angiogram renderer computes per-pixel path length
from signed face depths, which is only exact for closed, consistently oriented surfaces.
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy import ndimage as ndi
from skimage.measure import marching_cubes

from .volume import Volume


def mask_to_mesh(vol: Volume, mask: np.ndarray, smooth_sigma_vox: float = 0.6,
                 target_faces: int | None = None, taubin_iters: int = 10,
                 step: int = 1) -> trimesh.Trimesh:
    """`step` > 1 meshes a block-averaged mask (coarser, still closed) instead of decimating,
    for large structures where quadric decimation would break watertightness."""
    idx = np.argwhere(mask)
    lo = np.maximum(idx.min(0) - 3, 0)
    hi = np.minimum(idx.max(0) + 4, mask.shape)
    sub = mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]].astype(np.float32)
    if step > 1:
        n = (np.array(sub.shape) // step) * step
        sub = sub[:n[0], :n[1], :n[2]].reshape(n[0] // step, step, n[1] // step, step,
                                               n[2] // step, step).mean((1, 3, 5))
    sub = np.pad(sub, 2)                                  # guarantees a closed surface
    if smooth_sigma_vox:
        sub = ndi.gaussian_filter(sub, smooth_sigma_vox)
    verts, faces, _, _ = marching_cubes(sub, level=0.5)
    # block-averaged voxel b covers fine voxels [b*step, b*step+step-1]; its centre is b*step+(step-1)/2
    verts = (verts - 2) * step + (step - 1) / 2 + lo      # back to full-volume voxel index
    m = trimesh.Trimesh(vol.index_to_lps(verts), faces, process=True)
    m.update_faces(m.nondegenerate_faces())
    m.remove_unreferenced_vertices()
    if taubin_iters:
        trimesh.smoothing.filter_taubin(m, iterations=taubin_iters)
    if target_faces and len(m.faces) > target_faces:
        m = m.simplify_quadric_decimation(face_count=target_faces)
    m.fix_normals()
    return m


def mesh_report(m: trimesh.Trimesh) -> dict:
    return {"faces": int(len(m.faces)), "vertices": int(len(m.vertices)),
            "watertight": bool(m.is_watertight), "winding_consistent": bool(m.is_winding_consistent),
            "volume_ml": round(float(m.volume) / 1000, 3) if m.is_watertight else None,
            "components": int(len(m.split(only_watertight=False)))}
