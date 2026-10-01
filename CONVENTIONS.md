# Geometry conventions

Every rule below is enforced by a unit test (named in brackets). If an image looks wrong,
trace it back to the geometry. **Images are never mirrored or rotated at the display stage.**

## 1. Patient frame (LPS)

- +x = patient **left**, +y = **posterior**, +z = **superior**. Patient supine.
- voxel (i,j,k) → LPS: `p = origin + i·dir_i + j·dir_j + k·dir_k`, taken only from the NRRD header
  (`space`, `space directions`, `space origin`). [`test_lps_header_identity`, `test_oblique_directions_respected`]
- A header declaring RAS is converted by negating x and y of the directions and the origin.
  [`test_ras_header_converted`]
- A header with no `space`, or any other space, is rejected. Nothing is guessed. [`test_unknown_space_rejected`]
- CT and annotation must be on the same grid. [`test_grid_mismatch_detected`]
- Recentering is a pure translation; the linear part is never touched. [`test_recenter_is_translation_only`]

## 2. C-arm angles

- DICOM positioner convention. Primary α: LAO +, RAO −, α ∈ [−90, 90].
  Secondary β: cranial +, caudal −, β ∈ [−45, 45]. Out-of-range angles raise. [`test_out_of_range_angles_rejected`]
- Detector direction from the isocenter: `d(α,β) = (sinα·cosβ, −cosα·cosβ, sinβ)`.
  - At AP the detector is anterior. [`test_ap_detector_is_anterior`]
  - Increasing α moves the detector toward patient left. [`test_increasing_alpha_moves_detector_to_patient_left`]
  - Cranial (β > 0) moves the detector superior. [`test_beta_sign_moves_detector_cranial`]
- Readout: `RAO 30 / CAUD 20`; a zero component is omitted (`LAO 45`, `AP`). [`test_view_label`]

## 3. Source, detector, screen

- SID = 1000 mm, SOD = 750 mm.
- Isocenter: one constant per case, the centroid of all lumen voxels of **both** trees.
  Switching the injected tree never moves it. `CArm.table_offset` (default 0) is reserved for table pan.
  [`test_isocenter_is_only_translation`]
- Source `S = iso − SOD·d`. Detector center `D = iso + (SID − SOD)·d`. The detector plane has normal d.
  [`test_source_and_detector_positions`]
- Screen up `v = normalize(z − (z·d)·d)`; screen right `u = v × d`. Hence `u × v = d`: the image is
  viewed from the detector side, looking back toward the source. [`test_frame_orthonormal_right_handed`]
- Projection: intersect ray S→p with the detector plane to get q; screen = ((q−D)·u, (q−D)·v) in
  detector mm. Since u, v ⊥ d, this equals using the isocenter as the origin. [`test_screen_roundtrip`]
- Local magnification: `SID / ((p − S)·d)`; at the isocenter it is 4/3.

Required behaviors:

| Rule | Test |
|---|---|
| AP: +x projects screen right (u = (1,0,0)) | `test_ap_screen_right_is_patient_left` |
| RAO 30: the spine projects left of the heart centroid | `test_rao30_spine_projects_left_of_heart` |
| LAO 45: the spine projects right of the heart centroid | `test_lao45_spine_projects_right_of_heart` |
| Cranial/caudal: superior stays up (whole α×β grid) | `test_superior_points_stay_up` |

## 4. Image raster

- Row 0 is the top of the screen (+v); column 0 is the left (−u). This is the only screen→array
  mapping in the codebase (`DetectorGrid`). [`test_pixel_mapping_roundtrip`]
- The renderer agrees with point projection. [`test_render_matches_point_projection`]
- Patient left renders right at AP, and superior renders top. Posterior renders left in RAO 30 and right in LAO 45.
  [`test_ap_patient_left_renders_right`, `test_ap_superior_renders_top`, `test_superior_renders_top_cran_caud`,
  `test_rao30_posterior_renders_left`, `test_lao45_posterior_renders_right`]

## 5. Foreshortening

For consecutive samples, let Δp be the step and r the unit ray from S to the pair midpoint:
`F = 1 − Σ|Δp − (Δp·r)·r| / Σ|Δp|`.

- F = 0 for a segment perpendicular to its local ray, on and off the central ray.
  [`test_foreshortening_zero_on_central_ray`, `test_foreshortening_zero_perpendicular_to_local_ray_off_axis`]
- F = 1 for a segment along its ray. [`test_foreshortening_one_along_ray`]
- F = 1 − sin 45° for a segment at 45° to its ray. [`test_foreshortening_45_degrees`]

## 6. Browser (Phase 1)

- **World frame = LPS mm, verbatim.** GLB vertices are written by `cpt/glb.py` with no axis conversion. glTF's nominal +Y-up is
  deliberately ignored, and the loader rejects any non-identity node transform. The observer camera uses `up = +z` (superior).
  [`test_glb_roundtrip_verbatim`]
- **TypeScript geometry = Python geometry.** `web/src/geometry.ts` reimplements sections 2–5. It is tested against the same rules and
  against `web/tests/fixtures/geometry.json`, which Python generates (8 poses × 25 points, agreement to 1e-9 mm).
- **Angiogram clip matrix.** `CArm.clipMatrix(W)` gives NDC x = (q·u)/(W/2) and NDC y = (q·v)/(W/2), so +u is right and +v is up by
  construction (`clip matrix equals point projection` test). The matrix is mirror-handed (u × v = d points at the viewer), so
  **no renderer may use triangle winding or gl_FrontFacing**. Entry and exit come from world-space face normals.
- **Render-target orientation.** WebGL rows start at the bottom: texture uv (0,0) is the (−u, −v) corner. The left panel blits the texture
  unchanged. The detector ghost plate's corners are D ± (W/2)u ± (W/2)v with exactly that uv. Seen from the patient/source side, the ghost
  therefore appears mirrored, which is physically correct: you are looking at the back of the detector.
- **End-to-end check.** `web/e2e/phantom.e2e.mjs` renders a chiral phantom in headless Chromium. The GPU path-length image must match the
  Python reference renderer (r > 0.95, mean |error| < 0.25 mm), and its left-right and up-down mirror images must both fail that comparison.
- **Overlay drawing** (selection, rays, glyph) uses `CArm.project` plus `screenToPixel` (row 0 = top). Picking uses the inverse
  mapping. [`detector raster` test, `interaction.e2e.mjs`]

## 7. View metrics (Phase 2)

Implemented twice, `preprocess/cpt/metrics.py` (reference) and `web/src/metrics.ts`. They are equal on Python fixtures and in the browser
(`tests/test_metrics.py`, `web/tests/metrics.test.ts`, `web/e2e/metrics.e2e.mjs`).

- **Purely geometric.** Inputs are centerline samples (LPS mm + radius) and a C-arm pose. No metric, map or score may read a
  rendered image. Guarded by source scans of metrics.py, and of metrics.ts plus everything it imports, for any rendering/pixel
  module or call. The guard is mutation-tested. [`test_python_metrics_are_purely_geometric`, `guard: metrics are purely geometric`]
- **Foreshortening** F follows section 5, evaluated over the target's ordered samples.
- **Capsules.** Each piece between consecutive projected samples is a 2D capsule. Its radius is r x local magnification SID / ((p - S).d),
  linearly interpolated along the piece. A target sample is overlapped if any capsule covers its projected centre.
  [`test_capsule_radius_uses_local_magnification`]
- **Inter-vessel overlap** O_inter: capsules from the other edges of the injected tree. Target samples within 3 mm (3D) of the
  target's own bifurcation nodes are not evaluated. [`test_bifurcation_exclusion_3mm`, `test_inter_overlap_vessel_behind_target`]
- **Self-overlap** O_self: the target's own capsules, but only pieces more than 10 mm away in arc length.
  [`test_self_overlap_only_beyond_10mm_arc`]
- **Combined cost** = w_F.F + w_O.O_any. O_any is the fraction of evaluated samples overlapped by either kind.
- **Angle grid.** 2-degree steps anchored at 0 (so AP and zero tilt are always sampled), plus the exact range ends:
  alpha -90..90 (91 values), beta -45, -44, ..., 44, 45 (47 values). Maps are stored [beta][alpha]. In the UI, alpha runs left (RAO)
  to right (LAO) and beta bottom (CAU) to top (CRA). [`test_angle_maps_grid_and_symmetry`, `2 degree grid is anchored at 0`]
