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
