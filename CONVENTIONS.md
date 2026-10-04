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

## 8. Branch labels and derived segments

- **Label mode assigns BRANCH names only:** LM, LAD, D1, D2, septal, ramus, LCx, OM1, OM2, RCA, conus, RV marginal, PDA, PLB.
  Labels are per centerline edge and are never inferred.
- **Segments are derived** from the labels by fixed rules (`web/src/segments.ts`):
  - LAD prox / mid / dist: LAD start → D1 origin → D2 origin → end.
  - LCx prox / dist: LCx start → OM1 origin → end.
  - RCA prox / mid / dist: equal arc-length thirds of the labeled RCA (default), or the SCCT acute-margin wording (switchable).
    "RCA dist" is flagged when the case's distal RCA is truncated.
  - Every other labeled branch is a single whole segment.
- **Never invent.** A split exists only at the origin of a labeled side branch on its labeled parent. If the side branch is not labeled,
  the remainder stays "(unsplit)", is not mission-eligible, and a **note** says why.
- **Issues vs notes.** Label inconsistencies are **issues** and block approval: wrong tree, a gap in a branch, a side branch not on its parent,
  or out-of-order origins. Legitimate absences are **notes** and don't block it.
- **Approval.** The derived segmentation needs a human approval. The approval is bound to a hash of the branch labels plus the RCA rule, so
  any label change voids it. Before approval, metrics target the labeled branch (or the edge); after approval, they target the derived segment
  under the click (sample-level selection).
- **The non-expert extension never takes part in segmentation.**

Tests: `web/tests/segments.test.ts`, `web/e2e/segments.e2e.mjs`.

## 9. Overlap shown to the user

The only overlap displayed is the 2D capsule metric (section 7):
- a ray, or a sample dot on the angiogram, is orange if its sample is inter-vessel overlapped and pink if self-overlapped;
- culprit vessels are those whose capsules cover the target.

The Phase 1 3D ray-lumen test is kept only as a hidden diagnostic (`__cpt.diagnosticRays3D` in e2e builds).
`web/e2e/segments.e2e.mjs` checks every displayed ray colour against the capsule mask (300 rays, 0 mismatches).

## 10. Z-Anatomy canonical LPS-oriented atlas frame

This is **not** a registration to any patient (Z-Anatomy and ASOCA are different people). It only puts the whole atlas into the
projection engine's convention: +X patient left, +Y posterior, +Z superior, millimetres.

- **One transform for everything.** p_LPS = R x s x p_source_world. R is one rigid rotation and s one uniform unit scale. No translation,
  and no structure is ever individually recentred, rotated, scaled or moved to the origin.
  [`test_real_export_landmarks_and_scale`: every exported object's bbox_LPS equals R x s x bbox_source]
- **Axes are determined empirically** (`preprocess/anatomy_frame.py`), from world-space centres of the evaluated geometry:
  - LEFT = mean of (centre(X.l) - centre(X.r)) over femur, humerus, kidney and superior lung lobe. The names define anatomical left.
    The pairs agree within 14.32 degrees; the kidneys are asymmetric.
  - SUPERIOR = skull (frontal, occipital, parietals) - feet (calcanei, tali).
  - POSTERIOR = vertebrae T4-T8 - body of sternum, orthogonalised against SUPERIOR.
  - Handedness check: P x S must agree with the name-derived LEFT. Measured agreement: 1.66 degrees.
    Mirrored labels or mirrored geometry are rejected. [`test_mirrored_labels_are_rejected`, `test_mirrored_geometry_is_rejected`]
  - Snap: the empirical axes lie within 1.16 degrees of a signed axis permutation, so the exact permutation is used.
- **Result for Startup.blend:** the source world axes already ARE L, P, S. Blender +X = patient left, +Y = posterior, +Z = superior.
  R = identity; det = 1.0.
- **Units:** the scene uses METRIC with scale_length 1.0 (display unit: cm), so 1 Blender unit = 1 m and s = 1000.
  matrix_source_to_LPS_mm = diag(1000, 1000, 1000).
- **Scale checks** (with real vertices, in `assets/anatomy/frame_checks.json`):
  - T6 vertebral body width: 32.7 mm. PASS (30-50 mm).
  - PRIMARY: LV long axis 84.3 mm. PASS (70-110 mm). Apex = LV vertex farthest from the atria centroid along the four-chamber
    principal axis; base = mean of the 10% of LV vertices nearest the left-atrium centroid (mitral side).
  - SECONDARY: four-chamber principal-axis length 142.0 mm. PASS (100-160 mm). Extent of LV+RV+LA+RA vertices along their first
    principal axis (includes the atria, hence longer than the LV).
  - Both exist to catch unit errors (a metre/centimetre slip fails both by a factor of ten), not to grade anatomy (D42).
  - Apex (sanity only, not the definition of left): the apex-minus-base direction is [0.845, -0.295, -0.446], i.e. left, anterior
    and inferior. The long axis is 57.7 degrees out of the sagittal plane.
- **glTF:** vertices are baked to LPS mm and every node has an identity transform. The exporter runs with export_yup=False (no axis
  conversion). The viewer rejects any node with a non-identity transform.
- **Vessel calibre = the atlas's AUTHORED radii** (D46, correcting D43). Every Z-Anatomy vessel is a bevelled curve whose tube
  diameter is 2 x bevel depth (0.5 mm) x the per-point curve radius the atlas authors set: LM about 4.0 -> 3.6 mm, RCA trunk
  4.0 -> 0.9 mm, ascending aorta 30 -> 28 mm, SVC 21 -> 25 mm. The evaluated export always carried these radii; D43's "constant
  1.0 mm tubes" was a measurement error.
  - `z_anatomy_heart.glb` keeps them and is THE geometry for the scenes and, later, the X-ray and metrics. Exported diameters are
    measured on the meshes and tested against the authored ones (+-25%) [`test_main_export_keeps_atlas_radii`].
  - `z_anatomy_heart_illustrative.glb` (comparison only) overwrites the coronary radii with a linear taper (LM 4.5; main LAD/LCx/RCA
    3.5 -> 1.5; side branches 2.0 -> 1.0 mm). The proximal end of an ostial trunk is the endpoint nearer the ascending-aorta centreline;
    for any other spline, the end touching another coronary spline (<= 2 mm, else the export fails).
  - Never narrow the aortic root, never subdivide or reshape a centreline. Changing tessellation is allowed (finer steps along and
    around a tube, closed ends), because it moves no centreline and no radius.
- **Great vessels** (D46): ascending aorta, arch, thoracic and abdominal aorta (to the iliac bifurcation), brachiocephalic trunk, left
  common carotid, left subclavian, SVC, thoracic IVC, pulmonary trunk, its bifurcation and both pulmonary arteries (no pulmonary
  veins). Tubes are closed (fill caps) [`test_great_vessels_present_closed_and_root_not_narrowed`]. The pulmonary trunk is a coarse
  atlas mesh, refined for display only: subdivided and smoothed with every vertex kept within 1 mm of the original surface; the
  deviation is measured both ways and logged in the manifest.
- **Effective ostium** (D46): the point where a coronary centreline, walked from its ostial end, first leaves the closed
  ascending-aortic surface. It is stored in the manifest and on the LM / RCA_branch_01 nodes (glTF extras), as the future catheter
  engagement target.
  - An ostial end buried inside the wall (up to about 4.5 mm) is acceptable: the vessel visibly emerges from the aortic wall.
  - A FLOATING ostium (proximal end outside the wall) is a defect and stops the export.
  - Inside/outside is a 7-ray parity vote, cross-checked against the nearest-surface normal. A single ray can be wrong: it was for
    the LM. Re-checked independently with numpy ray parity [`test_effective_ostia_on_wall_none_floating`].
- **Catheter access routes** (D47): `z_anatomy_access_routes.glb`, hidden by default in the scenes, same rules and same single
  transform. Femoral route on both sides (common iliac -> external iliac -> femoral) and the right radial route (right subclavian ->
  axillary -> brachial -> radial; the brachiocephalic trunk is in the heart file). Continuity is checked link by link
  [`test_access_routes_continuous_and_bifurcation`].
- **Body surface** (D44, D48). The skin is Z-Anatomy's own "9: Regions of human body": 240 named surface regions in the same atlas, under the
  same single transform. Hair, nails and the flat ".g" label boards are excluded.
  - In the atlas each region is a thin closed shell (Solidify modifier, 3 mm, offset -1). The export switches Solidify off (in memory
    only), so each region is its single outer sheet.
  - `preprocess/scripts/weld_skin.py` (`cpt/weld.py`) welds the sheets into ONE mesh. It merges coincident vertices, then snaps the few
    remaining rim vertices across the crack onto the neighbouring region's rim (never along their own rim; displacement logged).
  - It then makes the winding consistent and turns every piece outward by ray parity. Normals are smooth across the seams.
  - Region names are kept in extras.region_names, with per-vertex `_REGION`, `_ARM` and `_LEG` (weights in [0, 1]). The side views
    fade the limbs by these weights [`test_skin_is_one_welded_surface_facing_out`, `tests/test_weld.py`].
- **Atlas scenes motion** (D45). Heartbeat and breathing are ONE displacement field, evaluated in the vertex shader at rest positions for
  myocardium, coronaries and veins alike, so a vessel on the surface stays on the surface. The field is a function of position only,
  and nothing is moved per object.
  - The field has a radial envelope around the heart centre (D46). It is full strength out to a radius that encloses every chamber,
    coronary and cardiac-vein vertex, so the heart moves exactly as before. It fades to zero 120 mm further out, so the abdominal
    aorta, the access routes and the limbs stay still. Still a function of position only.

## 11. Working rules (all anatomy and tooling)

- **Every heart uses ITS OWN coronaries.** Never combine anatomy across subjects: ASOCA (real patients), Z-Anatomy (atlas), Visible
  Heart Labs (specimens) each stay whole and separate. No mixing of meshes, centrelines, radii or landmarks between them.
- **Z-Anatomy: one transform for everything** (section 10). Never move, rotate or scale a single structure.
- **No anatomy data in git:** no ASOCA-derived files, no atlas exports (assets/anatomy/, web/public/anatomy/ are git-ignored). Code and
  docs only.
- **Blender:** 4.2.16 LTS, always `--disable-autoexec --python-exit-code 1`, always through `preprocess/blender/run_blender.ps1`.
  - The machine has 11.9 GB RAM, so the runner checks available memory first and refuses to start below the threshold.
  - It also logs Blender's peak working set. The full export peaks at about 6.2 GB; the read-only probe at about 3.7 GB.
- **No shell heredocs.** They have failed repeatedly here. Write scripts to files, then run them.
- **Review gates:** stop with screenshots at every gate and ask; never assume approval.

## 12. Atlas X-ray (D49, D50)

- **Closed meshes only.** Path length = sum of exits - sum of entries, so every attenuating mesh is closed and outward-wound. Open atlas
  tubes are fan-capped (holes only, no vertex moves) by `preprocess/scripts/build_atlas_xray.py` [`tests/test_closemesh.py`].
- **Isocenter** = volume centroid of both closed coronary trees, one constant (atlas_xray.json). Switching the injected tree never
  moves it. It is the C-arm rig's origin and the angiogram's isocenter.
- **Two renderers, one definition.** `cpt/meshrender.py` (exact, CPU) is the reference; `web/src/angio.ts` (GPU) is the app.
  They agree on the atlas trees at the standard views, and mirrored GPU images must fail that comparison
  [`tests/test_meshrender.py`, `web/e2e/atlas_xray.e2e.mjs`].
- **The C-arm hardware follows the projection.** Rig basis = (u, v, d) of the same CArm, at the isocenter. The detector's outer face
  and the monitor inset show the render target unchanged (texture (0,0) = the (-u, -v) corner). No display flips (section 6).
- The Phase 0 sanity sheet (`preprocess/scripts/phase0_atlas.py`) must pass before any change to the atlas X-ray. It fails the run if
  the spine does not flip sides between RAO 30 and LAO 45, or superior does not project up.
- **One solid per tree** (D52). The X-ray uses each tree's boolean UNION, so overlapping branch starts are not counted twice
  [`tests/test_atlas_union.py`]. Per-branch meshes stay for selection, labels and hover.
- **Static frame = validated frame** (D53). The optional renderer features (contrast fill window, device channel, cine field) leave the
  static image identical. With the beat off, GPU = CPU (r = 1.0000); with it on, the X-ray follows the 3D heart's SAME field
  [`web/e2e/atlas_xray.e2e.mjs`].
- **Scene 5 is illustrative.** The catheter is shaped to the anatomy (tip at the manifest's effective ostium, tangent to the
  coronary), never the reverse. Contrast fills by distance along the tree. The UI footer says "illustrative, not physics"
  [`tests/test_atlas_cath.py`].
