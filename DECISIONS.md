# Decisions log

Newest at the bottom. Status: DECIDED (by Rugved), DEFAULT (my call, open to change), OPEN (needs Rugved).

## 2026-09-30 (Phase 0)

**D1 Location.** DECIDED. `D:\coronary-projection-trainer\`, its own git repo. A Python venv in `.venv`,
with versions pinned in `requirements.txt` (system Python 3.12; not the stEVE conda env).

**D2 Data source.** DECIDED. `D:\coronav\data\anatomy\` holds only VMR 0066 (CoroNav-processed), so it is not used.
The original ASOCA distribution is `D:\ASOCADataAccess.zip` (8.3 GB, dataset's own
`ASOCADataAccess/Normal/{CTCA,Annotations,Centerlines,SurfaceMeshes}` layout). `Normal_12` CTCA and its
annotation were **extracted (read-only) from that zip** into `data/raw/Normal_12/` and renamed
`CTCA_Normal_12.nrrd` and `Annotation_Normal_12.nrrd`. Byte content is unchanged; the SHA-256 of each file is in
`out/phase0/Normal_12/case_meta.json`. Nothing in the CoroNav or stEVE folders was moved or modified. No CoroNav or stEVE meshes or centerlines are used.
Headers: `space: left-posterior-superior`, identity directions (0.369, 0.369, 0.625 mm), gzip, both files on the same grid.
The CT is int32 HU; outside the circular reconstruction FOV it is padded at −3024.

**D3 Uninjected tree in the DRR.** DECIDED. Every voxel in the expert lumen segmentation (both trees,
dilated ~1 voxel) is set to soft-tissue HU (~40), on top of the blood-pool mask. Only the
selected tree is added back as contrast. (To implement in Phase 1.5.)

**D4 Isocenter.** DECIDED. One fixed point per case: the centroid of all lumen voxels of both trees.
For Normal_12 it is (25.2, −3.3, −106.7) mm LPS. `CArm.table_offset` is reserved for table pan.

**D5 Left/right split.** DEFAULT. The annotation must have exactly two 26-connected components. Left = the larger
one AND the one with the more patient-left centroid; if these disagree, loading stops for manual review.
Normal_12 left: 1670 mm³, centroid x +42. Right: 690 mm³, centroid x −15, y −22 (anterior).
This names *trees* only, never branches (branch labels come from Label mode).

**D6 Spine in FOV.** DECIDED (marker rule) / measured. In Normal_12 the vertebral bodies are present through the whole
z range (−193 to −65 mm, ~129 mm) at y ≈ +45…+90 mm. The circular reconstruction FOV
clips the posterior elements. So no approximate spine marker is needed for this case; the rule still applies to
future cases with sparse vertebral bone.

**D7 Image raster and viewing side.** DEFAULT (follows from the spec). Row 0 = +v (top), column 0 = −u.
Because u × v = d, the image is viewed from the detector side. This is the standard angiographic view
(AP: patient left on screen right).

**D8 Phase 0 renderer.** DEFAULT. The CPU reference renderer integrates path length through the expert voxel
annotation along true source→pixel rays (trilinear, 0.2 mm steps), I = exp(−0.35·t). The detector is 250 mm and 500 px.
It deliberately does not use a mesh, so it is an independent ground truth for the Phase 1 mesh and GPU renderers.

**D9 View readout.** DEFAULT. A zero component is omitted: `LAO 45`, not `LAO 45 / 0`. AP is `AP`.

**D10 Blood-pool mask as specified leaks into the spine.** OPEN. Rule: 200–700 HU, the component containing the aortic root.
In Normal_12 that component (443 mL) also contains the vertebral bodies (cancellous bone around 200–300 HU touches
the contrast-filled descending aorta). That would erase the spine from the bone mesh and from the DRR.
With a 1-voxel opening before connectivity, the spine separates (pool 289 mL). However, the FOV ends at
z = −65, below the arch, so the descending aorta is then a *separate* component and would be classed as "bone"
(HU > 250) and stay opacified in the DRR. Needs a decision before Phase 1 (bone mesh) and 1.5 (DRR).
→ Superseded by D10 (revised) below.

## 2026-09-30 (Phase 0 review → Phase 1)

**D10 (revised): bone defined positively; blood pool = what remains.** DECIDED (approach, by Rugved) / DEFAULT (parameters).
`preprocess/cpt/masks.py`:
- Cortical seeds (> 700 HU, opened 1 voxel) are grown 2 voxels into > 400 HU to form a shell.
- Shell pieces are kept by location, cortical fraction and thinness.
- Smoothed 150–700 HU candidates are split by a 2-voxel erosion and classified one region at a time:
  **cancellous bone** if (fraction of boundary with raw HU > 400 or the FOV edge within 1.5 mm) ≥ 0.10 **and** mean HU < 400;
  otherwise **blood pool**.

Iterations on Normal_12, and why each was dropped:
- connectivity from the aortic root: swallowed the spine;
- opening plus root seed: the descending aorta became "bone" (the FOV ends below the arch);
- per-slice hole filling: the vertebral cortex is open where the circular FOV cuts it;
- boundary-near-shell in voxel units: a synthetic aorta lying on the spine scored like bone;
- angular rays: fatty marrow pockets, and cortex mostly below 700 HU in this scan.

Measured (rim / mean HU):
- vertebra 0.33 / 303, sternum 0.13 / 313, ribs 0.18–0.21 / 292–344 → bone;
- descending aorta 0.02 / 485, LV 0.01 / 351 → pool.

Result: bone 165 mL, pool 457 mL. Residual: about 2 mL of anterior costal-cartilage fragments (each ≤ 0.6 mL) are classed as pool. The last
~2 mm of bone at the FOV edge lands in neither mask and keeps its own HU.

**SVC check:** in Normal_12 the SVC and right heart are barely opacified (RV median 129 HU), so no dense-contrast seeds occur. Two rules guard other
cases. A shell piece in a mediastinal location, or a solid blob (inscribed radius > 4 mm), is rejected as contrast and added to the pool, so
inflow above 700 HU is suppressed too. Both are pinned by `tests/test_masks.py`.

Review figure: `out/review/Normal_12/masks_overlay.png`; per-region decisions: `masks_report.json`.

**D11 Official ASOCA centerlines are primary.** DECIDED.
- **Frame:** the .vtp points sit in a frame offset from the CT header by P_vtp = p_lps − 2·(ox, oy, 0): the origin's x/y were written with the
  RAS sign while the axes stayed LPS. This pure translation is derived from the header, not fitted. After it, all 7,445 points lie inside
  the expert lumen (mean 0.0004 mm, max 0.27 mm). Every mirror alternative is off by 15–17 mm, and a free translation refinement converges to (0,0,0).
- **Coverage:** 0.1% of official samples are more than 2 mm from my skeleton. My skeleton has 3 spurs the official set lacks: 7.3 mm at the distal
  RCA end, plus 4.0 and 2.6 mm (bulges). The skeleton graph is kept as a fallback, used if the frame check fails.
- **Graph:** the 6 ostium→endpoint paths are merged (1 mm tolerance) into 12 nodes and 10 edges, resampled every 0.5 mm with radius.

**D12 Dominance (Normal_12).** PENDING Rugved. Neither the annotated RCA nor the annotated LCx reaches the crux.
- **Annotated RCA:** 114.6 mm, ending at (−9.6, 0.8, −162.8). That is about 10–20 mm short of the estimated crux (x 0–10, y 20–30,
  z −150…−160, ±10 mm). In the CT, an unannotated ~1.2 mm, ≥ 250 HU vessel continues about 33 mm along the posterior AV groove to ~(14, 21, −149).
- **LCx:** 78.6 mm from the ostium (62.1 mm past the LM bifurcation), ending high in the posterior AV groove at (44.4, 38.5, −121.3).
  Its CT continuation runs superiorly, most likely the great cardiac vein.
- **Reading:** not left-dominant. Probably right-dominant, with the distal RCA/PDA missing from the expert annotation.

Recorded in `case.json → dominance`. Figure: `out/review/dominance_check.png`.

**D13 Segment = centerline-graph edge.** DEFAULT. Selection, rays and labels work per edge. One name may cover several edges.
Names never come from geometry.

**D14 Meshes.** DEFAULT.
- **Lumen:** marching cubes on the padded expert mask (σ 0.6 voxel), then Taubin smoothing and quadric decimation. Both trees are watertight and
  single-component (left 1.58 mL, right 0.65 mL, vs 1.67 / 0.69 mL in voxels).
- **Bone:** decimation broke watertightness. Instead, marching cubes runs on a 2×-block-averaged mask with no decimation (watertight, 320k faces).
- Each lumen vertex stores its nearest edge id (`_EDGE_ID`). Case assets total 9.1 MB.

**D15 Angiogram path length.** DEFAULT.
- **Accumulation:** order-independent. (|x−S| − SOD) goes into separate entry and exit sums, each with a counter (float32 render target;
  a half-float fallback is reported in the status bar).
- **Silhouette repair:** at silhouettes the rasterizer occasionally drops one crossing of a pair. Those pixels have unequal counts and are filled
  from valid 4-neighbors (0–4 pixels per 128² phantom view).
- **Display:** I = 0.78·exp(−0.35·t_vessel − 0.012·t_bone), 3×3 binomial blur, noise ±0.0175. Detector 250 mm, 512 px.

**D16 Label storage.** DEFAULT (static app, no backend). Labels autosave to browser localStorage, and can be exported or imported as `labels.json`.
A `labels.json` placed in `web/public/cases/<id>/` loads when nothing is stored locally. The file carries an edge signature, so stale labels are
flagged after a centerline rebuild.

**D17 Presets.** DEFAULT (adjust freely). A preset also sets the injection for its tree.
- Left tree: RAO 30/CAUD 25, RAO 30/CRAN 30, AP/CRAN 35, LAO 40/CRAN 30, LAO 45/CAUD 30 (spider), AP/CAUD 30.
- RCA: LAO 45, RAO 30, LAO 30/CRAN 20.

**D18 Selecting a non-injected vessel** (by clicking it in 3D) highlights it in 3D and tells you to switch injection; it does not switch injection itself.

**D19 Observer framing.** "Frame patient" looks from beside the beam (along +u, slightly superior), so the detector plate never sits between the
observer and the heart. "Frame C-arm" shows the whole C-arm. Neither changes the projection.

## 2026-09-30 (Phase 1 review, item 1)

**D20 Non-expert distal RCA extension.** DECIDED (separate layer, by Rugved) / PENDING REVIEW (content).
`cpt/extension.py` and `scripts/trace_extension.py`. The trace starts at the expert RCA end (edge 1, node 1) and takes the
largest component of smoothed HU ≥ T that touches a 2.5 mm seed sphere. It excludes chambers (opening of ≥ 200 HU by a 4-voxel ball), bone and the expert lumen. The D10 pool mask is
not used here: its split erosion assigns ~1 mm vessels to the pool. The component is then skeletonized into geodesic branches.

| Threshold | Result |
|---|---|
| 250 HU | fragments only |
| **230 HU** | **one unbranched 36 mm vessel (median 300 HU, radius ≥ 0.5 mm) to (12.5, 17.7, −151.2), at the estimated crux** |
| 210 / 200 HU | leaks into a 1.4–1.7 mL network reaching the left AV groove (venous); rejected |

**No PDA/PLB is traceable** without leaking. HU steps from ~480 to ~300 exactly at the expert end, with no gap: consistent with a
narrowing artery under partial volume, but the accompanying small cardiac vein cannot be excluded automatically.

Storage:
- Own file: `extension.json` (`non_expert: true`, provenance, caveats, edge ids ≥ 1000), plus a closed tube mesh, `extension.glb`.
- Own flag: `case.json → non_expert_extension` (status, `default_visible`). `build_case.py` carries the flag over rebuilds.
- Never merged into `centerlines.json`, the expert lumen meshes or the label signature.

In the app: separate toggle, violet tinted tube plus dashed centerline in 3D, dashed overlay in the angiogram, and a "[NON-EXPERT trace]" tag on selection.
It is included in rays and overlap only while visible. The layer stays **default OFF** until
`trace_extension.py --approve` after review of `out/review/Normal_12/extension_overlay.png`.

**D20 update: extension NOT approved (Rugved's rule: approve only if the evidence clearly favours artery).** `scripts/extension_checks.py`,
`out/review/Normal_12/extension_checks.png` / `.json`:
1. Taper: FWHM diameter is flat, 1.42 / 1.50 / 1.48 mm by thirds (slope +0.004 mm per 10 mm). Uninformative: this is at the CT
   resolution floor (calibration: expert distal RCA FWHM 1.96 mm vs official MIS diameter 1.82 mm). Peak HU falls 11.8 HU per 10 mm toward the crux.
2. Coronary sinus (rough; seed snapped near (18, 31, −144), ≥ 250 HU; at 230 HU it merges into the LV): 0.53 mL tube, max radius 3.2 mm, (9, 25, −148)..(25, 41, −132).
   The trace never touches it: minimum distance 9.6 mm, at the crux end. (Favours artery, weakly.)
3. HU: trace centerline median 301, against CS core 306 and expert arteries of radius 0.45–0.8 mm at 412 (n = 284). **Matches the vein, not same-size arteries.**
4. Junction: single lumen in all 13 cross-sections from −1 to +2 mm, and no fat plane (centerline minimum 177 HU at +1.5 mm). But there is an abrupt
   480 → ~300 HU step exactly at the annotation end, plus a dip. Consistent with contact of two vessels or an abrupt caliber change; not decisive.
   (The bright vertical line at 0 mm in reformat plane 2 is a reformat artifact where the path direction changes.)
5. Side branches at 215 HU: one 5 mm candidate at the crux end heading superiorly (0, 0.19, 0.98), compatible with an AV nodal artery
   *or* a venous tributary. At 185 HU, 8 candidates (noise or myocardium).

Verdict: mixed, leaning venous. The layer stays default OFF with status "NOT APPROVED". Dominance in `case.json` = **indeterminate**.
For future cases, pick one whose expert annotation reaches the crux and the PDA.

## 2026-09-30 (Phase 2)

**D21 Masks are tuned to Normal_12; review gate.** DECIDED (Rugved). The D10 rule and all its thresholds were tuned on Normal_12 only
and will not be tuned further. For every future case:
- the mask overlay (`review_masks.py`) is a **mandatory review gate**;
- **TotalSegmentator** is the preferred route over writing new heuristics.

Enforced in code:
- `review_masks.py --approve "<note>"` writes `reviews/<case>.json` (committed; no patient data).
- The approval is bound to a fingerprint of every mask parameter, so changing any parameter voids it.
- `build_case.py` records the gate status in `case.json`.
- `masks.require_reviewed_masks()` is the hard gate the DRR builder must call. [`test_review_gate`]

Normal_12 is approved (params `2db75c09eb796651`).

**D22 Centerline frame check is a per-case assertion.** DECIDED (Rugved). `official_graph()` raises `CenterlineFrameError` unless 100% of
official points lie within 0.5 mm of a lumen voxel after the header-derived translation.
- The build stops and reports.
- There is no silent skeleton fallback, and no transform is ever fitted.
- The skeleton graph is used only when a case has no official centerline file, and its source is recorded.

[`test_official_frame_assertion_stops_on_misaligned_points`]

**D23 Angiogram pixel fill: suspected root cause.** Kept (Rugved).
- **Measured** on the phantom (6 poses, 6 repaired pixels): every repaired pixel had an even total crossing count with unequal entry and exit
  counts, and none had an odd count.
- **Meaning:** the rasterizer never drops a crossing. Instead, some face's entry/exit classification is wrong.
- **Suspected cause:** near-degenerate (sliver) marching-cubes triangles whose float32 face normals point the wrong way, so a grazing exit is
  counted as an entry.
- **Possible proper fix (not done):** compute flat normals in float64 in Python, or remove slivers before export.
- The phantom e2e reports the repaired-pixel classification. Metrics never read pixels (see D24).

**D24 Phase 2 metric choices.** DEFAULT.
- **O in the cost** is O_any (inter or self), over the samples evaluated for inter.
- **Target** is the selected edge. If the edge is labeled, it is the contiguous chain of edges sharing that label: a simple path, otherwise the
  connected part, with a note.
- **"Other vessels"** are the injected tree's expert edges. The non-expert extension is included only while its toggle is on, as for rays.
- **Two overlap measures coexist.** Phase 1 ray culprits test in 3D (a ray within a vessel's radius); Phase 2 capsule overlap tests in 2D. They
  answer different questions and can disagree at the margin. The capsule metric is the scored one.
- **Heatmaps:**
  - single-hue blue ramp, low values dark so they recede into the dark surface;
  - the colour scale tops out at a "nice" value just above each map's maximum, shown on the legend;
  - hover shows the view and value, and a click moves the C-arm;
  - crosshair = current view, ring = map optimum (Explore mode; Mission mode will hide it).
- **Performance:** a full 2-degree map (4,277 poses) for an 80 mm segment takes about 0.6 s in a Web Worker, using a uniform-grid capsule index.
  The index gives the same masks as brute force (tested).

**D25 Phase order changed.** DECIDED (Rugved). Phase 1.5 (DRR/volume rendering) is skipped for now. The order is Phase 2, then Phase 3
(Mission + Guess); the DRR comes after Phase 3.

## 2026-10-01 (pre-Phase 3: items A, B, C)

**D26 Branch labels, derived segments, approval.** DECIDED (Rugved), implementation DEFAULT. Label mode now uses branch names; segment names are
derived (see CONVENTIONS 8).
- **RCA split:** Rugved specified "thirds per SCCT". SCCT's wording actually splits at the acute margin, so both are implemented: equal thirds
  is the default and the acute-margin rule is a switch. The approval records which rule was used.
- **RCA truncation:** `reviews/Normal_12.json → annotation.rca_distal_truncated = true` is copied into `case.json`, and "RCA dist" carries the flag.
- **Missing side branches** (for example, no D2 present) are notes, not blocking issues. Otherwise a case lacking a branch could never be approved.
- **Labels file version 2.** It holds the branch labels plus `segments_approval` (labels hash, RCA rule, date). A version 1 file
  (segment names) is rejected with a message; none existed.

**D27 One overlap definition in the display.** DECIDED (Rugved). The 3D rays and the sample dots are coloured from the capsule metric
(orange = inter, pink = self), and culprits come from the covering capsules (`interBy`). The 3D ray-lumen check is no longer displayed;
it stays as an internal diagnostic. Rays are now cast from the metric target (the derived segment once approved), not from the raw edge.

**D28 Heatmap scale floors.** DECIDED (Rugved).
- Per-map scaling keeps a floor: foreshortening and both overlap maps never scale below 20%; the combined cost never below 20% of (w_F + w_O),
  which is my extension of the rule to the cost map.
- A "fixed 0–100%" toggle uses the full range.
- The rule is a pure function, `scaleTop()`, with unit tests.
- Note: a straight segment seen end-on reaches 100% foreshortening and 100% self-overlap somewhere on the grid, so on many maps the per-map top is
  legitimately 100%.

## 2026-10-01 (RCA rule correction; Phase 3 Predict)

**D29 RCA split rule: correction of D26.** DECIDED (Rugved). SCCT splits the RCA at the acute margin, not in thirds. The rule is now automatic:
- **RV marginal labeled and originating on the RCA:** the SCCT acute-margin rule. Prox = ostium to half-way to the RV marginal origin, mid = to that
  origin, dist = beyond.
- **Otherwise:** equal arc-length thirds. All three RCA segments carry the flag "approximate (thirds)" and are **not mission-eligible**, and a note
  asks for the RV marginal to be labeled.

The manual RCA-rule switch from D26 is removed. The approval records the rule actually used (`acute-margin` / `approximate-thirds`), so an
approval given under thirds is voided once an RV marginal is labeled.

**D30 Phase order revised again.** DECIDED (Rugved): Predict (new core of Phase 3) → Mission + Guess (missions only on fully derived
segments) → phone as detector (/remote) → DRR.

**D31 PREDICT mode.** DECIDED (Rugved), details DEFAULT.
- **Candidates:** correct, −alpha, −beta and both flipped. A toggle swaps "both flipped" for an L-R mirror of the correct view.
- **Degenerate flips:** a flip that would reproduce the same image (|alpha| or |beta| < 5 degrees, e.g. AP cranial or LAO 45) is replaced by an L-R or U-D
  mirror, so the four candidates are always distinct.
- **No target near (0, 0).** Only three distinct images exist there; `makeCandidates` refuses it, and `drawPose` cannot produce it.
- **Mirrored images:** they exist only as deliberate wrong answers. They are built by an explicit pixel flip in `predictUI.ts`, marked as
  distractor-only. No correct or displayed view is ever mirrored.
- **Pose draws:**
  - 50% one of the 9 standard presets (with its injection tree), 50% random.
  - Random poses: alpha in ±[10, 70], beta in ±[10, 40], random tree.
  - Every target is at least 15 degrees (between detector directions) from the previous pose; the previous target is the next start.
- **Tiles:** all four use the same noise seed, so noise is never a cue. Bone stays visible as a legitimate cue. No overlays.
- **During a question** the C-arm controls are locked (sliders, presets, arrow keys), so the answer cannot be found by moving there.
  Keys: A-D to pick, Enter for the next view.
- **After the pick** the correct and the chosen tile are marked, each tile is named, and the C-arm animates from the previous pose to the
  target (1.4 s, angles interpolated). The 3D panel and the angiogram follow the animation.
- **Tracking:** answers are stored per viewer in localStorage, which is enough for a personal tool. The summary shows accuracy and the last 20,
  errors per distractor type with the number of times each was offered (so the rates are fair), and accuracy by target side (LAO/RAO/CRAN/CAUD).
- **Whole-vessel level:** no labels or segments are used.
- **Tests:** `web/tests/predict.test.ts` (candidates, degenerate cases, draws, summary) and `web/e2e/predict.e2e.mjs`. In the e2e, the correct tile's
  darkness correlates with the target's independently computed path-length image at r 0.45-0.61, versus about 0 for its mirror. The mirror
  distractor is an exact pixel flip, and the C-arm ends at the target.

## 2026-10-01 (presentation pivot, Step 1: hero scene)

**D32 Simple, explanatory presentation by default.** DECIDED (Rugved). The geometry engine, X-ray rendering, metrics and Predict are unchanged.
- **Simple view (default):** one full-window hero scene, a standard-view menu, two angle sliders and a one-line caption. No numbers, heatmaps
  or labels.
- **"Advanced" (header):** brings back every existing panel and mode.
- e2e test builds (`?e2e`) default to Advanced so the existing tests are unaffected; `?simple=1` forces the hero.

**D33 Heart from this patient's CT (TotalSegmentator).** DECIDED.
- **Package:** TotalSegmentator 2.18.0 (code: Apache 2.0), CPU torch 2.14, in its own venv (`.venv-ts`, git-ignored).
- **Licensing** (from the package source, `map_to_binary.commercial_models`): the tasks that REQUIRE a license (free for non-commercial use,
  by application) include `heartchambers_highres` (myocardium + 4 chambers + aorta + pulmonary artery), `coronary_arteries` and
  `aortic_sinuses`. **None of these was used.** Rugved decides whether to obtain a license for `heartchambers_highres`.
- **Used:** the open `total` task with roi_subset heart, aorta, superior/inferior vena cava, pulmonary vein, left atrial appendage and
  brachiocephalic trunk. The trunk is absent because the CT field of view ends below the arch. `total` gives the heart as ONE label (outer
  envelope), not separate chambers/myocardium, and has no pulmonary trunk.
- **Offline:** the weights were downloaded once into `.totalseg/` (git-ignored). Usage statistics are disabled in its config
  (`send_usage_stats: false`). The CT never leaves the machine.
- **Frame:** the CT was written to NIfTI with its RAS affine (diag(-1,-1,1) x the NRRD LPS affine). Every returned mask is asserted to lie on the
  CT's exact voxel grid, then used by voxel index (no resampling).
- **Meshes:** smoothed per axis in mm (heart sigma 1.6 mm, aorta/veins 1.3 mm; the model works at ~1.5 mm, so masks are blocky), Taubin x40,
  decimated. All watertight, in LPS.
- **Epicardial assertion** (`build_anatomy.py`, stored in `case.json -> anatomy`). Coronary centerline samples vs the heart(+aorta) mask surface:
  median 2.20 mm (outside; epicardial fat), p90 4.37 mm, max 7.58 mm, 95.6% within 5 mm, 7.7% just inside. Against the rendered meshes:
  median 2.55 mm, p90 4.83 mm. Thresholds: median <= 4 mm, p90 <= 8 mm. PASSED.
- No stock heart model is used anywhere.

**D34 Body model.** DECIDED.
- **Source:** MakeHuman base mesh (`assets_src/makehuman/base.obj`, from github.com/makehumancommunity/makehuman). It is **CC0**: the file header says
  "This asset was explicitly released as CC0 in september 2020", and the MakeHuman FAQ says "the base mesh [is] considered graphical assets,
  covered by CC0". Only the `body` group is used.
- **Axes:** verified from the mesh's own joint helpers (+X = character's left, +Y up, +Z anterior). Mapped to supine LPS by x = X, y = -Z, z = Y
  (det +1, no mirroring).
- **Fit (APPROXIMATE, labeled as such in `body_fit.json`):** uniform scale 1.05 (1.75 m) plus a translation.
  - Midline goes to the CT bone midline; the anterior chest skin at heart level goes to the CT anterior skin (y -74.6 mm).
  - Heart level = clavicle joints - 110 mm, aligned to the TotalSegmentator heart centroid.
  - Caveat: the CT field of view cuts off the spinous processes, so the body's back (y +119 mm at heart level) may be somewhat too shallow.
- **Rendering:** fresnel "glass" skin; breathing is a ~3 mm chest/upper-abdomen swell at 15 breaths/min, on the skin only. The heart and
  coronaries do not move, because the X-ray geometry is static.

**D35 Room, C-arm, beam.**
- **All in the LPS frame.** The room's "up" is -y (anterior, for a supine patient), so the floor is toward +y. At AP the detector is above the
  chest and the tube under the table, as in a real lab.
- **C-arm:** generic and unbranded, built in code: arc, tube, collimator, detector and stand. It is posed every frame from the SAME CArm basis
  (u, v, d) as the X-ray rendering, so it cannot drift from the projection. The arc lies in the (d, v) plane and bulges toward the head end.
- **Detector:** the live angiogram is on its OUTER face, seen from outside with u right and v up (correct orientation). From the tube side it would be
  mirrored.
- **Beam:** a translucent additive pyramid from the focal spot to the detector corners.
- **Pose changes** from the view menu animate (1.6 s, ease in/out).

**D36 Views and readability.**
- **Coronaries:** glossy saturated red (emissive). Where they are hidden behind the heart, a faint red ghost shows through (GreaterDepth pass).
  The non-injected tree is dimmed, as in the Advanced 3D panel.
- **Myocardium:** warm muscle tone. **Aorta:** ivory. **Great veins:** blue (illustration convention).
- **Heart close-up:** anterior view with the head up; C-arm and table hidden.
- **Beam view:** side-on to the beam, from the room-up side.
- **Split view:** the heart seen from the DETECTOR side with screen-up = v, so it is laid out like the angiogram next to it.
- Review renders use real-GPU headless Chromium (ANGLE/D3D11). SwiftShader was too slow for the physical materials.

## 2026-10-01 (revised anatomy plan: Z-Anatomy provenance and frame; NOT connected to the C-arm)

**D37 Source and tools.**
- **Z-Anatomy:** https://github.com/Z-Anatomy/Models-of-human-anatomy (the old "Z-Anatomy/The-blend" repository redirects here),
  commit ad876c0, Z-Anatomy.zip -> Startup.blend (file date 2023-05-02).
  SHA-256: zip e0296885..., blend 9f08a17e..., License.txt 196b66b5... (full values in assets/anatomy/LICENSE.txt and provenance.json).
- **License:** CC BY-SA 4.0, verified from the downloaded License.txt. BodyParts3D underneath is CC BY-SA 2.1 Japan. Full attribution is in
  assets/anatomy/LICENSE.txt. The bundle also contains CC BY-NC(-SA) parts (inner ear, kidney model). Those are not exported; the kidneys are
  read only as left/right landmarks.
- **Blender 4.2.16 LTS:** the official portable build. blender.org's CDN answered 403 to scripted downloads (including winget), so the same file
  was fetched from official mirrors and verified against Blender's published SHA-256 (checksum files identical on two mirrors). It runs with
  --disable-autoexec (the file's z-anatomy.py is never executed) and --python-exit-code 1 (it quits on any script error).
- All anatomy assets are git-ignored (assets/anatomy/, web/public/anatomy/).

**D38 Hierarchy findings** (`assets/anatomy/inspect/hierarchy.json`, all 7,184 objects of every type).
- **Coronaries are bevelled CURVE objects.** The named coronary objects are: Left coronary artery (a short LM stem: 1 spline, 3 control points),
  Anterior interventricular artery (LAD, 6 splines), Septal branches of anterior interventricular artery (6), Circumflex artery of heart (LCx, 6),
  Right coronary artery (14), and Right inferolateral branch of right coronary artery (8).
- **No named PDA, diagonals, obtuse marginals, ramus, conus, RV/acute marginal, or SA/AV nodal branches.** Side branches exist only as unnamed
  splines inside the LAD, LCx and RCA objects. Nothing is inferred from shape (`assets/anatomy/CORONARY_REPORT.md`).
- **Chambers are separate meshes** (left/right atrium and ventricle, valves, papillary muscles). The `.g`/`.j` objects are zero-geometry
  markers; there is no "Heart" mesh.
- **Anomaly:** one cardiac-vein curve is named literally "????????" (a non-ASCII name lost in the source). It is reported, not guessed.
- **Anatria-3D (reference only), checked against our file:**
  - Confirmed: coronaries are curves; zero-geometry markers; export from the atlas scene stalls (observed here too, so the export uses an
    empty staging scene with materials off).
  - Not matching: their "Bonus collection/Cardiovascular system/Heart" path is empty in this file.

**D39 Export** (`preprocess/blender/export_anatomy.py`).
- **Files:** z_anatomy_heart.glb (34 structures + 26 spline branches) and z_anatomy_skeleton.glb (278 bones/cartilages).
- **Transform:** one shared matrix for all of them; curves converted from EVALUATED geometry (the depsgraph, bevel applied); identity node
  transforms; export_yup=False.
- **Names:** original names are node names and are also kept in extras (anatomical_name, source_*).
- **Manifest:** assets/anatomy/manifest.json, per object.
- **Spline branches** (Rugved): each spline of the LAD, LCx and RCA is also a child node <VESSEL>_branch_NN. Each is evaluated exactly like its
  parent, never moved, and carries no clinical name.
  - The manifest records parent vessel, spline index, spline type, evaluated length, endpoints and attachment (which end, to what, gap).
  - 25 of 26 branches attach with a 0.0 mm gap. RCA_branch_01 is the RCA trunk; its proximal end is the ostium.
  - A first rule mis-recorded the ostium as "attached" to the nearest spline 21 mm away. That is now fixed: anything beyond 2 mm counts as the
    ostium, in both the script and the manifest (recorded in manifest post_fixes).
- **Verification:** all 312 exported objects satisfy bbox_LPS = R x s x bbox_source.
- **Debug viewer:** web/anatomy.html (temporary, not connected to the C-arm), with screenshots in out/review/anatomy/.

**D40 Scale check failure: heart long axis 142.0 mm > 140 mm.** OPEN (Rugved).
- The measurement is the four-chamber extent along the first principal axis, so it includes the atria.
- For information, the LV long axis (base to apex) is 84.3 mm.
- The threshold and the test are unchanged; the test fails until the definition or the threshold is decided.

**D41 Visible Heart Labs candidates.** Heart0088 and Heart0063 Coronary Arteries (Sketchfab, VisibleHeartLabs).
- **License:** CC BY-NC 4.0, verified via the public Sketchfab API.
- **Download:** needs a logged-in account (HTTP 401), so it was not attempted (MANUAL_DOWNLOAD_REQUIRED).
- **Content:** coronary arteries only; no same-ID whole-heart model was found in public searches.
- Per Rugved (2026-10-01) they are SKIPPED: under the rule "every heart uses its own coronaries", a coronary-only model cannot be the hero heart.

## 2026-10-01 (Scenes 1 and 2 on the Z-Anatomy hero heart; still NOT connected to the C-arm)

**D42 Scale checks redefined** (Rugved: "my spec was ambiguous, not a real failure").
- PRIMARY: LV long axis, base to apex, 70-110 mm. Measured 84.3 mm: PASS.
- SECONDARY: four-chamber principal-axis length, 100-160 mm. Measured 142.0 mm: PASS.
- Both exist to catch unit errors. This replaces the single 90-140 mm "heart long axis" check (D40, now closed).
- Definitions are in CONVENTIONS section 10 and frame_checks.json; tests in tests/test_anatomy_frame.py.

**D43 Z-Anatomy is the hero heart (Rugved). Illustrative coronary calibre.** CORRECTED by D46: the premise below ("constant
1.0 mm atlas tubes") was wrong. The atlas authors per-point radii, and the main export now keeps them. The taper survives only as the
comparison file z_anatomy_heart_illustrative.glb; z_anatomy_heart_tapered.glb is deleted.
- **Taper:** the constant 1.0 mm atlas tubes are re-exported with curve point radius, linear in arc length from the proximal end:
  LM 4.5 mm; main LAD/LCx/RCA 3.5 -> 1.5 mm; side branches 2.0 -> 1.0 mm.
- **Which spline is "main":** spline 0 of the LAD, LCx and RCA objects. Each one attaches to the LM (LAD, LCx) or starts at the aortic root
  (RCA). All 41 splines of the 6 coronary objects are tapered: the LM, the 3 split vessels, the septal branches and the right inferolateral
  branch.
- **Proximal ends:** every spline's proximal end was found by attachment (gap <= 2 mm) or, for ostial trunks, by distance to the
  ascending-aorta centreline (RCA 12.7 vs 63.9 mm; LM 11.5 vs 18.5 mm). All 41 came out as the spline "start".
- **Measured on the exported meshes:** main splines about 3.3-3.4 -> 1.6 mm, side branches about 1.95 -> 1.02 mm.
- **Files:** the export runs once and writes both z_anatomy_heart.glb (untapered, comparison) and z_anatomy_heart_tapered.glb (used).
  The manifest records method, targets, measurements and "ILLUSTRATIVE calibre"; the UI footer says "vessel calibre is illustrative".
- **For later:** the X-ray and metrics are to use the tapered geometry when the atlas is connected (not yet).

**D44 Body surface from the same atlas.**
- Z-Anatomy contains a skin: "9: Regions of human body", the body surface tiled into named regions (pectoral, presternal, mammary, ...).
- 240 region meshes are exported with the same single transform (z_anatomy_skin.glb). Excluded: hair, nail plates, perionyx, eyebrows,
  eyelashes, and "Regions of human body.g", a flat board beside the body.
- No other body model is used.
- The region seams show faintly as lines in the glass shading; this is left as is. REVERSED by D48 (Rugved): the regions are now welded
  into one surface.

**D45 Atlas scenes** (web/atlas.html, src/atlasHero.ts; e2e: atlas_shots.mjs, atlas_label.e2e.mjs).
- **Scene 1, the heart:** PBR materials. Ventricles deep muscle red, atria lighter and browner. Coronaries saturated red with clearcoat
  gloss. Cardiac veins dark blue, with a toggle. Studio lighting: environment light plus key, rim and fill lights that travel with the
  camera. Free orbit; hover names; no numbers.
- **Not shown:** valves and papillary muscles (internal). The atlas's great vessels (aorta, SVC, pulmonary arteries) are schematic 1 mm
  centreline curves and are hidden; whether to give them an illustrative calibre too is OPEN (Rugved). CORRECTED by D46: they were never
  1 mm; they carry the atlas's own radii (ascending aorta 30 mm). They are now shown.
- **Heartbeat:** about 64 per minute; ventricles squeeze radially and the base descends, with an atrial kick before systole. Breathing is a
  4.6 s cycle that lowers the heart, swells the chest skin and lifts the anterior chest wall.
- **Shared field:** all of it is the one position-only displacement field (CONVENTIONS section 10).
- **Scene 2, the heart in the patient:**
  - Glass skin with Fresnel edge glow; faint bones; the opaque heart inside.
  - "Heart in the patient" is a smooth pull-out that fades the body in.
  - Views: Front, Left side, Right side, From the feet, From the head. Each is a smooth camera move with a one-line caption.
  - In the side views the arms fade out. The axial views cut the body with a section plane 125 mm below or above the heart centre,
    so the camera does not have to look through the legs or the head.
  - Every caption was checked against the camera basis (e.g. from the feet with anterior up, patient left is screen right).
- **Shaders:** every program is precompiled at load, so the pull-out does not stall.
- **Label mode:** click any of the 26 branch nodes and pick D1/D2/OM1/PDA/PLB/acute marginal/conus/... from fixed lists.
  - Labels are saved in localStorage and can be exported and imported as atlas_branch_labels.json (version 1). An optional default can
    be shipped at web/public/anatomy/.
  - Veins hide while labelling, since their blue clashes with the LAD colour family.
  - It does not block the scenes. Unlabeled branches show "<vessel> (branch not yet named)" on hover.
- **Recording:** made inside the page. MediaRecorder captures a 2D composite of the WebGL canvas, the background and the caption.
  Playwright's screencast dropped most transition frames, while the page itself runs at 27-60 fps.

## 2026-10-02 (atlas corrections: authored radii, great vessels, effective ostia, access routes, welded skin)

**D46 Atlas radii are THE calibre; great vessels; effective ostium.** DECIDED (Rugved), details DEFAULT.
- **Correction of D43 and D45.** Z-Anatomy's vessels are bevelled curves with AUTHORED per-point radii: diameter = 2 x 0.5 mm bevel x the
  point radius. The evaluated export always carried them; the earlier "constant 1.0 mm tubes" / "1 mm schematic great vessels" claims
  were measurement errors. Measured on the old untapered file: ascending aorta 30.0 mm, LM 3.98 mm, RCA trunk 3.63 -> 1.21 mm,
  SVC 21.3 mm. The manifest even recorded the authored ranges (previous_point_radii_range).
- **Files.** `z_anatomy_heart.glb` keeps the atlas radii and is THE geometry for the scenes and, later, the X-ray and metrics. The D43
  taper survives only as `z_anatomy_heart_illustrative.glb` (comparison). `z_anatomy_heart_tapered.glb` is deleted.
  - Exported diameters are measured and tested against the authored ones (+-25%), for the LM stem and all 26 split branches.
  - The UI footer now reads "vessel sizes are the atlas's own, not a patient's".
- **The aortic root is NOT narrowed** (Rugved: a 23-25 mm root is anatomically wrong). It keeps the atlas's ~30 mm. The earlier
  "<= 1 mm ostium" rule was too strict and is dropped, together with the planned Bezier subdivision and root narrowing.
- **Effective ostium** = where the coronary centreline, walked from its ostial end, first leaves the closed (capped) ascending-aortic
  surface. A buried ostial end (up to ~4.5 mm) is fine: the vessel visibly emerges from the wall. Only a FLOATING ostium is a defect,
  and it stops the export. Result:
  - LM: proximal end 3.38 mm inside the wall. It runs 7.5 mm before emerging, leaving the wall at 75 degrees to its normal (shallow).
  - RCA: proximal end 2.08 mm inside, emerging after 2.25 mm at 23 degrees.
  - Neither floats. The points are stored in the manifest and on the LM / RCA_branch_01 nodes as the future catheter engagement target.
  - Inside/outside is a 7-ray parity vote plus a nearest-normal cross-check, because a single ray gave a false "floating LM" on the
    first run. Verified again without Blender in tests/test_anatomy_export.py.
- **Great vessels shown:**
  - aorta: ascending, arch, thoracic and abdominal, down to the iliac bifurcation;
  - arch branches: brachiocephalic trunk, left common carotid, left subclavian;
  - venae cavae: SVC and thoracic IVC (the IVC was missing from the first list by mistake; its real name is "Inferior vena cava
    (thoracic part)");
  - pulmonary arteries: trunk, bifurcation, left and right. No pulmonary veins (Rugved).
  - The old list asked for "Arch of aorta" and "Inferior vena cava", which do not exist in the file, so the arch was never exported.
- **Tessellation, display only:** tubes go from 12 to 24 steps per Bezier segment and from bevel resolution 4 to 12, with closed ends
  (fill caps). No centreline, radius or placement changes.
- **Pulmonary trunk** (a coarse 138-vertex atlas mesh): 2x linear subdivision, 10x Laplacian smoothing of interior vertices, every vertex
  clamped to within 1 mm of its starting point on the original surface; rims fixed. Measured deviation: 0.52 mm (new -> original) and
  0.61 mm (original -> new); no vertex needed clamping (Rugved: target <= 1 mm; never moved as a whole).
- **Viewer:**
  - Materials: aorta and arch branches in a softer arterial red than the coronaries (so the coronaries read where they leave the
    wall); venae cavae blue; pulmonary arteries violet.
  - New Scene 1 view "Aortic root": the camera looks along the mean of the two ostial wall normals, lifted toward the head, 165 mm
    away. On the way in, the atria (their appendages cover both ostia), the pulmonary arteries and the cardiac veins fade out, and
    the ventricles become a ghost (22% opacity), so the right-ventricular outflow tract no longer hides the root. A first version
    that only hid the pulmonary arteries showed neither ostium.
  - Visible and NOT fixed (atlas geometry, untouched): a crease on the root above the LM, and a faint seam line where the ascending
    aorta meets the arch (two capped tubes end to end).
  - The heartbeat field got a radial envelope (CONVENTIONS section 10), so the far aorta does not swing with the heartbeat.

**D47 Catheter access routes** (for Scene 5; exported once now). DECIDED (Rugved), details DEFAULT.
- `z_anatomy_access_routes.glb`, same atlas radii, same single transform, same tessellation and caps. Hidden by default in the scenes;
  the review shot uses `?routes`.
- **Femoral (both sides):** common iliac (18 -> 12 mm) -> external iliac (12 -> 9.3 mm) -> femoral (9.3 mm, 357 mm long).
  - The atlas has NO separate common femoral object. Its "Femoral artery" starts at the end of the external iliac and runs down the
    thigh, so the common femoral is its proximal part.
- **Radial (right):** brachiocephalic trunk (heart file) -> right subclavian (9 -> 5 mm) -> axillary (5) -> brachial (5 -> 4) -> radial (4 -> 2.2 mm).
- **Continuity:** every link (and the aortic chain: ascending -> arch -> thoracic -> abdominal) meets its parent's distal end with a
  0.00 mm gap. No gaps.
- **Aortic bifurcation:** the abdominal aorta ends exactly where both common iliacs start, at z = 1030.6 mm. The atlas's own label
  "Aortic bifurcation" sits at the same height (z = 1030.2). Level: L3 spans z 1021-1066 mm and L4 spans 994-1036 mm, so the bifurcation
  is at the L3/L4 junction, upper L4.
- The common iliacs start at 18 mm, the abdominal aorta's own end calibre. That is the atlas's value, kept as is.

**D48 Welded skin (reverses the "seams left as is" of D44).** DECIDED (Rugved), method DEFAULT.
- **Finding:** in the atlas, 200 of the 240 skin regions carry a Solidify modifier (3 mm, offset -1). Evaluated, each region is a thin
  CLOSED SHELL (outer + inner sheet with opposite normals).
  - That is why half of all skin normals pointed inward, and why neighbouring shells overlapped (3-4 faces per edge).
  - The export now switches Solidify off (in memory; the file is never saved), so each region is its single outer sheet.
- **Weld** (`preprocess/cpt/weld.py`, run by `preprocess/scripts/weld_skin.py`):
  - exact merge at 0.01 mm;
  - then rim vertices snap ACROSS the crack onto the neighbouring region's rim, within 4 mm. Never along their own rim: a unit test
    caught an early version dragging open-rim vertices sideways. The snap is sequential, because a simultaneous one swapped facing
    corners.
  - Winding is made consistent across every shared edge, and each piece is turned outward by ray parity (the atlas winding is not
    trusted). Normals are smooth across the seams.
- **Kept:** region names (extras.region_names) and per-vertex `_REGION`, `_ARM`, `_LEG`.
  - Arm regions: deltoid, arm, bicipital grooves, elbow, cubital fossa, forearm, radial foveola, wrist, hand, digits. Leg regions:
    thigh, knee, popliteal fossa, leg, ankle, malleoli, foot, digits of foot.
  - Gluteal, hip, inguinal and femoral-triangle regions count as trunk. The old name regex had treated gluteal/femoral as limb and
    missed the elbow and bicipital grooves.
  - The side views fade the limbs by max(_ARM, _LEG) per vertex.
- **Result** (manifest.skin_weld and GLB extras):
  - 240 sheets (27,732 vertices, 45,028 faces) became one mesh of 22,726 vertices and 45,009 faces. The exact merge closed most
    seams; 337 rim vertices were snapped, max 3.9 mm (p99 3.7 mm).
  - Orientation: 6 pieces (body 41,028 faces, each auricle 1,989, and 3 single faces). The atlas sheets already faced outward, so no
    piece had to turn. Inconsistent shared edges: 0.
  - Left open: 766 open edges (holes where hair/nails/eyebrows were excluded, plus T-junction seams that are closed geometrically).
    Also 78 rim vertices with a residual crack of up to 3.5 mm, almost all in the folds of the auricles, plus a few on the lateral
    thorax and arm. They are invisible in the glass skin; more snap passes oscillated instead of converging.
  - Edges with more than 2 faces: 5, in the atlas's own auricle and big-toe meshes; 9 exact duplicate faces dropped.
- **Viewer:** one skin mesh and one glass material; the limb fade is per vertex. The atlas's flat "SKELETAL SYSTEM" label board
  (`Skeletal system.g`, in the skeleton export since D39) became visible in the full-body view and is now hidden in the viewer. The
  exporter still includes it; exclude `.g` boards from the skeleton at the next export.

## 2026-10-02 (look approved with polish; atlas X-ray; Scenes 3-4)

**D49 Atlas X-ray meshes, isocenter and Phase 0 sanity sheet.** DECIDED (Rugved: sanity sheet first), method DEFAULT.
- **Closed meshes** (`preprocess/scripts/build_atlas_xray.py`, `cpt/closemesh.py`). Path length needs closed, outward-wound meshes;
  the atlas tubes are open at both ends (12-vertex rings).
  - Every boundary loop is fan-capped from its own rim centroid. Holes only; no vertex moves (unit-tested).
  - Left tree = LM stem + LAD/LCx spline branches + septal branches (14 meshes). Right tree = RCA spline branches + right
    inferolateral branch (15). Split parent meshes are left out (they duplicate their splines).
  - Overlapping tubes at junctions are summed, not unioned: a few mm of double path where a branch starts inside its parent.
  - Heart chambers are capped at the valve rings, for the faint silhouette. The right atrium keeps 1 non-manifold edge from the atlas.
  - Bones: closed bones within 300 mm of the isocenter (136). Skipped as not closable: ethmoid, both humeri, xiphoid.
  - Every heart uses its own coronaries: everything is the one Z-Anatomy atlas under its one transform.
- **Isocenter** = volume centroid of both closed trees = (25.4, -45.5, 1291.5) LPS mm. It is fixed and never moves with the
  injected tree (the D4 rule, for the atlas).
- **Exact CPU mesh renderer** (`cpt/meshrender.py`): per-pixel signed ray/triangle crossings (exit - entry), rasterised by triangle
  bounding box.
  - Tested against analytic sphere chords at an oblique view (< 0.25 mm), inward winding and the AP raster orientation.
  - It is the CPU twin of the GPU method, and the ground truth for the atlas.
- **Sanity sheet** (`preprocess/scripts/phase0_atlas.py`, out/phase0/atlas/): the Phase 0 views and figure code, skeleton faint.
  0 unpaired pixels in every view.
  - RCA "C" in LAO 45 and "L" in RAO 30: by eye, yes.
  - Spider view (LAO 40 / CAUD 30) opens the LM bifurcation: yes.
  - Spine flip (computed; T4-T8 centroid minus heart centroid, screen x): -103 mm in RAO 30 and +92 mm in LAO 45 (spine left, then
    right). Also -31 mm in AP, -104 in RAO 30 / CAUD 25 and +81 in the spider view.
  - Superior projects up in all 8 views.

**D50 Scenes 3 (cath lab) and 4 (X-ray pass).** DECIDED (Rugved: spec), details DEFAULT. web/src/cathLab.ts; atlas.html.
- **Room:** room up = -y (supine). The table top touches the body's most posterior point; floor 950 mm below.
  - The C-arm stand is at the head end. The C-arm is the hero scene's construction, re-skinned: satin shell, dark accents, a blue
    trim on the arc.
  - The rig is oriented every frame by the same CArm basis (u, v, d) at the fixed isocenter, so it cannot drift from the projection.
- **C-arm views** (buttons): AP, RAO 30, LAO 45, RAO caudal (RAO 30 / CAUD 25), Spider (LAO 40 / CAUD 30).
  - Swings are smooth in angle space; every frame is a real CArm pose, and the image is live while the X-ray is on.
  - On arrival the acquisition builds outward from the centre of the detector.
- **Cameras:** Room (patient's right, toward the feet, from above); Operator (patient's right side at the hip, eyes ~1.65 m above
  the floor); Beam (side-on: tube, heart, detector in one line; free orbit with the projection fixed); Side by side (heart from
  the detector side with screen-up = v, next to the image). The Beam and Side-by-side cameras ride with the C-arm during swings.
- **X-ray** (Scene 4): the validated GPU renderer (angio.ts) on the D49 meshes, with selective LCA/RCA injection. The bones are faint
  (k 0.010/mm) and the heart a faint silhouette, through a new optional "soft" channel (k 0.0035/mm).
  - The soft channel is off by default, so the ASOCA app is unchanged; the phantom e2e still passes.
  - In 3D the non-injected tree is dimmed. A beam pyramid runs from the focal spot to the detector corners.
  - The image shows on the detector's outer face (u right, v up) and in a monitor inset (render target blitted unchanged).
- **Verified:** web/e2e/atlas_xray.e2e.mjs compares GPU against CPU path length at AP, RAO 30, LAO 45, RAO 30/CAUD 25 and the spider
  view (left tree), plus LAO 45 (right tree).
  - Every pose: r = 1.0000, mean error 0.001 mm, 0 repaired pixels.
  - The left-right and up-down mirror images all fail (r <= 0.13).
- **Captions** are one line, in words; button labels carry the view names.
- **Not yet:** the heart beats in 3D but the X-ray meshes are the rest pose (static image).

**D51 Look polish** (Rugved's review of D46-D48).
- **Pulmonary arteries:** lighter blue than the venae cavae and cardiac veins (standard convention); no violet.
- **Trunk shape** (reported, not reshaped), measured along the valve -> bifurcation axis:
  - 35-37 mm over the first ~14 mm (the sinus end; wider than a typical adult main PA);
  - 22-25 mm mid-trunk;
  - 28-29 mm at the bifurcation, matching the 28 mm bifurcation tube, so it is NOT bulbous there.
- **Coronary contrast:** myocardium muted toward brown with little specular. Coronaries brighter, more saturated, with a small
  emissive lift. The aorta stays a softer red.
- **Tissue:** three terms added to the myocardium's physical lighting.
  - A wrap-lighting / subsurface-like warm term in the terminator.
  - A faint warm back-scatter at grazing angles.
  - Procedural muscle-fibre normal detail: helical ridges around the LV long axis, from the REST position (they stay on the muscle
    while it beats). They fade out where they would alias (fwidth), which fixed a moire seen in the side-by-side view.
- **Chest view:** a soft warm rim light on the heart, driven by the body fade (0 in the close-up, 1 in the chest view and the lab).
  - A first version washed the whole heart pink: the rim term had the view vector's sign inverted (vViewPosition already points
    surface -> camera). Fixed, together with the same slip in the back-scatter term.

## 2026-10-02 (review of D49-D51; Scene 5)

**D52 Junctions counted once: each tree is one boolean-unioned solid for the X-ray.** DECIDED (Rugved), method DEFAULT.
- `build_atlas_xray.py` unions each tree's closed branch meshes with manifold3d 3.5.4 (pinned in requirements.txt).
  - Result: left 1329.2 -> 1279.3 mm3, right 1585.7 -> 1556.2 mm3 (50 and 30 mm3 of double path removed).
  - The per-branch meshes for selection, labels and hover are unchanged (z_anatomy_heart.glb). The pre-union trees are kept in
    assets only, for the before/after figure.
- **Isocenter** is now the union's volume centroid: (25.27, -45.48, 1291.25). It was (25.37, -45.54, 1291.50), a 0.3 mm shift.
- **Bodies:** the union has 5 (left) and 8 (right) bodies.
  - The LM meets the LAD/LCx starts flush at a cap plane (gap 0.00003 mm, zero overlap), so it stays a separate body.
  - The others (5-12 mm3) are septal and right-inferolateral side-branch tubes that the atlas draws free-floating, not reaching
    their parent. Reported, not bridged.
- **Tested** (tests/test_atlas_union.py) at the LAD_branch_02, LCx_branch_04 and RCA_branch_02 junctions.
  - A ray through the junction sees through the union exactly the union of the per-branch intervals (no double count); the
    summed tree saw more. The test fails if no overlap exists, so it cannot pass vacuously.
  - The ray passes 0.04 mm beside the junction point, which is exactly a cap-centre vertex shared by every fan triangle.
- **Re-verified on the unioned trees:** GPU = CPU r = 1.0000 at all six poses, mirrors fail, sanity sheet passes.
- **Figure:** out/review/lab/junction_fix_before_after.png. Up to 3.6 mm of double path at the LM bifurcation; the union never adds
  path anywhere (max +0.0005 mm).

**D53 Scene 5: catheter + contrast (ILLUSTRATIVE, not physics; the footer says so).** DECIDED (Rugved: spec), details DEFAULT.
- **Data:** `preprocess/scripts/build_atlas_cath.py`, from the Blender probe and the manifest. The probe now covers every coronary
  spline; peak 4.7 GB.
  - Routes, resampled at 1 mm on the vessel centrelines:
    - Right femoral: puncture 40 mm down the femoral artery (its common femoral part), up the iliacs and the aorta to the top of
      the ascending aorta. 637 mm.
    - Right radial: puncture 30 mm above the radial artery's distal end, then the brachial, axillary, subclavian and
      brachiocephalic arteries into the arch. 753 mm.
  - Shapes: JL4 -> LM and JR4 -> RCA, each a centripetal Catmull-Rom from the top of the ascending aorta to the EFFECTIVE OSTIUM in
    the manifest. The last ~5 mm run coaxial with the coronary's initial direction, and the tip sits 3 mm inside.
    - JL4: its primary curve rests on the contralateral wall, 9 mm below the ostium and at least 5 mm above the valve; the
      approach comes from inside the lumen.
    - Checks: tip tangent 0.0 deg for both. Minimum clearance of the catheter surface to the aortic wall, outside the 4 mm
      engagement zone: JL4 0.25 mm, JR4 2.85 mm.
    - A first JL4 came within -0.73 mm of the wall (0.73 mm outside the lumen): the LM leaves the aorta almost tangentially (75 deg
      from the wall normal). Fixed by approaching from inside the lumen. The coronaries and the aorta were never moved.
  - Contrast fill distances: a tree graph of every spline, grown from the ostial spline outward (Prim-like). The first version
    let two splines pick each other and form an island.
    - Distance 0 = the effective ostium; the buried trunk is negative.
    - Every spline joins within 0.5 mm. Max 150 mm (left), 254 mm (right).
    - Per-vertex values for the X-ray solids and every 3D branch node, each node from its own spline (no bleeding across a
      junction): atlas_fill.bin.
- **Sequence** (web/src/cath.ts):
  - The J-wire leads the 6F catheter (2 mm OD) up the route (6.5 s); the wire withdraws (1.6 s).
  - The catheter morphs from straight in the ascending aorta to its JL4/JR4 shape and engages (2.2 s).
  - Inject: contrast fills by tree distance in 1.0 s, holds 1.3 s, washes out proximal-first in 1.6 s, with a small reflux puff
    at the ostium.
- **One geometry, two views.**
  - The same closed tube meshes are drawn in 3D and given to the X-ray's new device channel: k 0.3/mm; the catheter wall weighs
    1, the metal wire 5.
  - The 3D glow (fill front band) and the X-ray fill read the SAME uniform, so they fill at the same moment.
- **Renderer** (angio.ts): optional per-mesh weight, an optional fill window by per-vertex distance, the device channel, and an
  optional motion-field hook. With none in use the shaders are the validated ones: phantom e2e and GPU = CPU still pass.
- **Cine:** during the injection only, the heart beats. The 3D heart and the X-ray geometry use the same field GLSL and the same
  uniforms. e2e: with the beat on, the X-ray changes (r falls to 0.51); off again, it equals the static CPU frame (r = 1.00000).
- **Cameras:** Room, Operator (femoral or radial, following the access), Beam, Aortic root.
  - The root close-up hides the atria, pulmonary arteries and veins and ghosts the ventricles (as in Scene 1).
  - In Scene 5 the aortic wall and access vessels are glass-red, so the catheter is seen inside them.
- **Regression caught by e2e:** creating the sim reset the shared fill window to "no contrast", which emptied Scene 4's X-ray.
  Fixed: outside Scene 5 the window is "everything".
- **Recording at the spider view:** at RAO caudal the detector sits on the operator's side and blocks the operator camera, which
  is correct geometry but a poor recording. The RAO 30 / CAUD 25 mid-injection image is delivered separately.

**D54 Review decisions on Scenes 3-4.** DECIDED (Rugved).
- **Heartbeat** paused by default in Scenes 3-5, with a "Beating heart" toggle; always on in Scenes 1-2. Breathing is held in the lab
  (DEFAULT: as during an acquisition), so the 3D heart and the static X-ray agree.
- **Operator camera:** Scene 3 offers femoral (at the hip) or radial (beside the right shoulder, over the arm; no arm board is
  modelled). Scene 5's operator position follows the chosen access.
- **Room camera:** approved as is.

## 2026-10-04 (v1.0)

**D55 Floating branches: none. A union input fix instead of bridges.** DECIDED (Rugved: report, bridge <= 3 mm), outcome measured.
- **Report** (`cpt/bridges.py`, in `build_atlas_xray.py`; atlas_xray.json and manifest `floating_branches`):
  - The trees are split into single-spline tubes (19 left, 22 right) and grouped by contact.
  - Every tube touches or overlaps its tree: surface gap <= 0.01 mm. There are 0 floating components, 0 bridges and 0 gaps > 3 mm.
  - The LM meets the LAD/LCx flush at a cap plane (gap 0.00003 mm); it is connected and needs no bridge.
  - The bridge machinery stays in the build (closed tube from the branch's proximal centreline end to the parent centreline, origin
    radius, flagged "illustrative bridge" in the manifest) and acts if a gap ever appears.
- **Correction of D52:** the 5 and 8 "bodies" were not floating branches. Multi-spline objects (the septal branches, the right
  inferolateral branch) went into the union as ONE mesh each, so their overlaps with the parent were not merged.
  - The union now splits every part into its tubes first: left 1279.3 -> 1277.8 mm3, right 1556.2 -> 1553.5 mm3. Bodies: left 2
    (main + the flush LM), right 1. Isocenter (25.23, -45.51, 1291.30).
  - Figure out/review/lab/septal_before_after.png: up to 0.97 mm of double path removed at a septal origin; nothing added (max
    +0.0001 mm). Junction tests, GPU = CPU and the sanity sheet all re-pass.

**D56 Scene 6: cross-section (illustrative; the panel says so).** DECIDED (Rugved: spec), details DEFAULT.
- **Data:** every spline's centreline, authored radius and fill distance (build_atlas_cath.py, trees.*.centrelines).
- **Slice:** perpendicular to the centreline, with parallel-transport frames so it never spins.
  - It shows the lumen at the atlas radius and an illustrative wall: intima 0.12, media 0.30, adventitia 0.38 mm (0.8 mm in all,
    labelled).
  - Epicardial fat is a soft 2.6 mm halo.
  - The lumen shows contrast from the SAME fill window as the 3D glow and the X-ray.
  - The catheter tip appears where the engaged catheter crosses the plane (blue-grey wall with an outline, so it reads against
    contrast).
- **Controls:** pick any coronary point (click), or follow the catheter tip; a slider scrubs along the vessel.
- **Synced markers:** a gold ring on the 3D vessel and a gold dot on the X-ray. The dot is CArm.project of the slice point mapped
  to the monitor (u right, v up); e2e agrees within 0.02 px.
- **Layout:** the 3D view is shifted left of the slice panel by a projection view offset (no camera trick).

**D57 One-row toolbar.** DECIDED (Rugved: spec).
- [Tour] | < Heart / In the chest / Cath lab / X-ray / Catheter / Cross-section > | 2-4 essentials | [More].
- Controls are declared per scene and rendered by web/src/toolbar.ts; everything secondary is in the More drawer.
- Measured at 1280 px: one row in every scene, widest 1245 px (X-ray), no overflow.

**D58 Predict on the atlas.** DECIDED (Rugved).
- The SAME PredictMode (predict.ts logic: candidates, flips, mirror distractors, degenerate-pose rule, error tracking) runs on this
  app's X-ray, with the new look. The record is kept per viewer, under its own key.
- Presets: RAO 30, LAO 45, RAO caudal, spider (left tree), RAO 30, LAO 45 (right). AP is excluded, because both flips reproduce
  it.
- Stats are in a collapsed "Your record". The mirror distractor and "clear my record" are in More.
- e2e: 4 distinct candidates, correct answer recorded, C-arm lands exactly on the target.

**D59 Guided tour ("Tour").** DECIDED (Rugved: 10 steps).
- Steps: heart beating -> into the chest -> cath lab -> swing to RAO caudal -> X-ray forms -> walk around the beam (side-on, orbit
  about the beam axis, side by side) -> spider -> catheter up and engaged (root close-up) -> contrast in 3D and X-ray -> the slice
  at the LM with the catheter tip inside.
- Pause, back, next, end; step dots, no numbers. Each step's action rebuilds the state it needs, so back and next work from
  anywhere.

**D60 Performance and quality pass.** DEFAULT (measured on this laptop, headless Chromium on the real GPU, 1600x1000).
- **Bottlenecks found by profiling** (fill rate and per-frame GPU churn, not JavaScript):
  - the faint skeleton (702k triangles, 278 draw calls, PBR per transparent layer);
  - double-sided glass skin;
  - clearcoat on the C-arm;
  - per-frame vertex-buffer re-creation for the catheter (frames stalled up to 0.78 s).
- **Fixes:**
  - Display skeleton: simplified to 25 % and merged into trunk and limbs; true surface deviation median 0.48 mm, worst bone
    4.4 mm. Display only; the X-ray keeps full bones.
  - A light bone shader; front-face glass in the lab scenes; Blinn-Phong hardware materials without an environment lookup
    (MeshStandard + PMREM on the C-arm cost ~20 fps in the operator view).
  - Preallocated catheter and wire buffers shared by 3D and the X-ray.
  - Slice redrawn only when it changes; fibre detail off while the chambers are ghosted.
  - Every shader variant precompiled at load. The fadeable materials are permanently transparent, so fades never recompile.
- **Resolution:** a fixed ~1.15 Mpx pixel budget. An adaptive scheme was tried and dropped: every resize reallocated the canvas
  and stalled a frame by up to 0.6 s (measured).
- **Pulsed fluoroscopy:** the live X-ray re-renders at most 15 times a second (as real pulsed fluoro and cine do), not every
  display frame, while the catheter moves or the heart beats.
- **First-use costs:** the warm-up also DRAWS the scene once (compiling does not upload buffers), the slice ring, the catheter tip
  ghost and the slice's 2D canvas. Dynamic buffers are re-uploaded only when their content changes: a per-frame partial upload of
  a buffer the GPU was still reading stalled ~0.5 s on ANGLE/D3D11.
- **Result** (out/review/v1/fps.json): 45-60 fps in all 14 measured views (also on the built app); the tightest are the heart
  close-up (45) and the Scene 6 slice during injection (46).
- **Tour stalls** (tour_stalls.mjs, unrecorded): worst frame 783 ms -> 67 ms; mean 57 fps over the 76 s tour.
- **Visual fixes:**
  - the C-arm turns to glass when it hides the heart;
  - the beam is shown only in Scene 4;
  - the angiogram texture is mipmapped and anisotropic (no detector moire);
  - shorter one-line footers;
  - the room / C-arm can no longer appear in Scenes 1-2 (a regression caught in review shots).

**D61 Fresh-eyes review outcome.** DEFAULT. A reviewer agent that had not seen the build reviewed the screenshots (1280 / 1920),
the toolbar and the tour recording against the v1.0 checklist. It found 17 problems in round 1 and 12 in round 2 (the single
re-review). The fixes:
- **3D coronaries:** drawn as each tree's closed UNION (the X-ray's solid), so the origins show no open tube ends. The branch
  meshes stay as invisible pick proxies for hover, labels and slice picking. Label mode shows the per-branch colours.
- **Transitions:** entering the lab from Scenes 1-2, or switching between the room and a heart-only view (side by side, aortic
  root, slice), is a 0.25 s fade cut. A flight from the chest passed through the detector, and the room popped out mid-move.
- **C-arm fades:** they use world bounding boxes. The stand arm's scaled bounding sphere had hidden it permanently. In the
  operator view, parts within 0.9 m of the eye fade out; a part hiding the heart turns to glass.
- **Detector z-fighting:** both detector faces were coplanar with the housing's bevelled faces and z-fought while the arm moved.
  They now sit 3 mm clear (display only; the projection geometry is the CArm math).
- **Scene 6 tip ghost:** the catheter tip sits a few mm inside the left main, hidden by the opaque contrast-filled vessel, so the
  slice ring looked "past the tip". The catheter's last 40 mm is now drawn faintly where the vessel hides it.
- **Predict:** each round shows the question's injection in the lab and the toolbar (the pose is unchanged until answered).
- **Smaller fixes:**
  - side by side framed to the half panel;
  - the X-ray inset bottom-left with an opaque frame;
  - catheter contrast during injection;
  - rim light in the chest view only;
  - subtler fibre relief and fat lobules;
  - wider, darker table;
  - footer backing;
  - shorter captions;
  - the Predict panel clear of the licence footer.
- **Not changed, with reasons:**
  - aortic-root seam, crease and left-main origin shape: atlas geometry, approved in review; never edited per structure (D37);
  - flat-capped great-vessel ends: closed ends were requested;
  - table seen through the glass patient, and hands past the table edge: the atlas pose and a glass body;
  - heart tint differs through the glass body and the ghosted root views: a lighting and transparency effect, not a different
    material;
  - Predict prompts name angles for random views: same Predict logic as the original app, by request.
