# Phase 1 verification report: AngioLens

Branch `paper/ijcars-verification` (from `v1.1` at `198c6d4`). Run on 2026-11-14 on the machine described under E5.

Every number below is read from a CSV or JSON in `paper/results/`, written by the script named in each section. One command
regenerates everything: `.venv\Scripts\python paper\scripts\run_phase1.py`. No app code was changed (`paper/CHANGELOG_code.md`).
Decisions and open questions are in `paper/TODO.md`.

**At a glance**

| Experiment | Result |
|---|---|
| E1: point projection, browser vs Python | 713 poses × 3,413 centerline points. Max 7.5 × 10⁻¹³ px (float64 overlay path); max 6.4 × 10⁻⁴ px (float32 GPU vertex path) |
| E1b: rendered GPU image vs exact CPU reference | 1,406 images (5° grid × 2 trees): r ≥ 0.9999 in all, MAE ≤ 0.0010 mm, centroid shift ≤ 0.015 px, mask IoU ≥ 0.998. Mirror sensitivity holds in every image |
| E2: chiral phantom vs first-principles derivation | correct render PASS at 9/10 named views; **1 FAIL** (phantom-design flaw, see below). Negative controls detected: mirror 10/10, LAO↔RAO 8/8 applicable, CRAN↔CAUD 7/7 applicable, up-down mirror 10/10; phantom 2 (update at the end): 10/10 |
| E3: Predict distractors | logic valid for 32,780/32,780 candidate sets; 612 rendered items: every distractor is its labelled transformation (2,448/2,448), 0/3,672 pairs near-duplicate (max IoU 0.209); correct tile byte-identical to re-render in 610/612 |
| E4: foreshortening vs recommended views | dropped from the paper (author decision); future work |
| E5: performance | rerun (cold loads): iGPU 59.9 fps, Scene 1 1.2 s; NVIDIA 59.9 fps, 1.0 s; software 1.5 fps (see the update at the end; the first run is superseded) |

---

## E1. Projection geometry agreement (browser vs Python reference)

Script: `paper/scripts/e1_projection_agreement.py` (browser side `paper/scripts/browser/e1_browser.mjs`).
Results: `paper/results/e1/e1_summary.csv`, `e1_per_pose.csv`, `e1_named_views.csv`, `e1_heatmap.png`, `e1_meta.json`.

**Method**
- Poses:
  - the full angle grid, LAO/RAO −90…+90 × CRAN/CAUD −45…+45 in 5° steps (37 × 19 = 703 poses);
  - plus 10 named views (table in `inventory.md` §2), 713 poses in all.
- Points: all 3,413 evaluated Z-Anatomy coronary centerline samples, both trees (LPS mm), at the app's isocenter.
- Detector: 250 mm, 512 px (0.488 mm/px).
- Reference: `cpt.geometry.CArm.project` → `DetectorGrid.screen_to_pixel` (float64).
- Browser: the unmodified `web/src/geometry.ts`, loaded in Chromium 153 through the app's Vite server, along two paths:
  - *overlay*: `CArm.project` + `screenToPixel` (float64). Used for overlays, picking and the Scene 6 dot.
  - *vertex*: `CArm.clipMatrix(250)` evaluated in float32 (`Math.fround` on each operation) → NDC → pixel. This is the arithmetic the
    GPU vertex stage applies to every mesh vertex.
- Discrepancy: the 2D Euclidean distance at the detector.

**Results** (`e1_summary.csv`)

| Scope | Path | Poses | Mean px | Median px | 95th pct px | Max px | Max % of detector width |
|---|---|---|---|---|---|---|---|
| 5° grid | overlay (float64) | 703 | 6.7e-14 | 2.8e-14 | 2.8e-13 | 7.5e-13 | 1.5e-13 |
| 5° grid | vertex (float32) | 703 | 1.29e-4 | 1.13e-4 | 3.24e-4 | 6.36e-4 | 1.24e-4 |
| named views | overlay | 10 | 6.3e-14 | 0 | 2.4e-13 | 7.5e-13 | 1.5e-13 |
| named views | vertex | 10 | 1.38e-4 | 1.31e-4 | 3.04e-4 | 5.54e-4 | 1.08e-4 |

The per-named-view breakdown is in `e1_named_views.csv`. Its largest value is the classic spider view (LAO 45 / CAUD 30): max 5.5e-4 px
on the vertex path. The heatmap (`e1_heatmap.png`) has two panels: a = overlay path and b = vertex path. Both show max discrepancy
per pose on a log scale, with the named views circled.

**Interpretation and limits**
- The two implementations agree to floating-point rounding. On the float32 vertex path the worst error is 0.0006 px (0.3 µm at the
  detector).
- This experiment shows that the **TypeScript and Python twins compute the same geometry**. It does *not* show that the geometry is
  clinically right, because both encode the same convention. E2 tests the convention against an independent derivation.
- It also does not include rasterisation. E1b does.

## E1b. Rendered image agreement (GPU app vs exact CPU reference)

Script: `paper/scripts/e1b_render_agreement.py` (browser side `paper/scripts/browser/e1b_gpu.mjs`).
Results: `paper/results/e1b/e1b_summary.csv`, `e1b_per_pose.csv`, `e1b_meta.json`.

**Method**
- Poses: the same 5° grid plus the named views, for the left and the right atlas tree: 1,406 GPU images.
- GPU image: the atlas app's own `readThickness()`, i.e. vessel path length in mm, with the heartbeat off. Taken in Scene 4,
  headless Chromium, ANGLE D3D11, on the Intel UHD GPU (`e1b_meta.json`).
- Reference: `cpt.meshrender.mesh_thickness_image` on the same closed meshes, which gives exact ray/triangle path lengths.
- Metrics:
  - Pearson r;
  - mean |error| over pixels where either image is nonzero (the existing e2e metric);
  - path-length-weighted centroid shift;
  - binary-mask IoU;
  - r of the left-right and up-down *mirrored* GPU image against the reference (sensitivity).
- Acceptance: the repo's own e2e rule (r > 0.95, MAE < 0.25 mm, mirrored r < 0.6).

**Results** (`e1b_summary.csv`, both trees)

| Scope | Images | r min | MAE max (mm) | Centroid shift max (px) | IoU min | Mirrored r max (L-R / U-D) | Pass |
|---|---|---|---|---|---|---|---|
| 5° grid | 1,406 | 1.0000 | 0.0010 | 0.015 | 0.9984 | 0.531 / 0.458 | 1,406 / 1,406 |
| named views | 20 | 1.0000 | 0.0008 | 0.002 | 0.9989 | 0.352 / 0.159 | 20 / 20 |

- The CPU reference reported 0 unpaired pixels in every image (`cpu_unpaired_px`).
- The highest mirrored correlation, L-R r = 0.531, occurs for the left tree at RAO 35 / CRAN 20 (`e1b_per_pose.csv`). It is below
  the 0.6 rule, but it shows that a mirror test on this anatomy has a margin of about 0.07 at the worst pose, not the
  margin of about 0.5 seen at the standard views.

**Interpretation.** The image the learner sees agrees with the exact reference to within 0.001 mm of path length at every
pose of the grid. Rasterisation, the float32 clip matrix, entry/exit accumulation and the GL row flip add no measurable geometric
error (≤ 0.015 px centroid shift).

## E2. Orientation and handedness (synthetic phantom, first-principles derivation, negative controls)

Script: `paper/scripts/e2_orientation.py` (browser side `paper/scripts/browser/e2_browser.mjs`).
Results: `paper/results/e2/e2_tests.csv`, `e2_views.csv`, `e2_derivation.csv`, `e2_meta.json`.

**Phantom** (synthetic; no patient or atlas data)
- Three tube letters, each drawn in a coronal plane so it reads normally at AP:
  - "L" at iso + (+60, −15, +25) mm: left, anterior, superior;
  - "R" at iso + (−60, +20, +5) mm: right, posterior;
  - "F" at iso + (+5, −30, −55) mm: feet side, anterior.
- Stroke radius 1.5 mm; glyphs 18 × 30 mm.
- Every centre has three distinct nonzero coordinates, so each angle-sign swap moves every marker.
- Built with the repo's phantom tooling (capsule voxels → marching cubes → GLB) and rendered by the classic app's GPU renderer through
  its existing `?case=` route.

**Derivation.** It is written out in the script's docstring and does not import `cpt.geometry`:
1. Patient frame LPS.
2. At AP the detector is anterior, d₀ = (0, −1, 0). The image is displayed as seen from the detector, head up, so patient left is
   screen right: r₀ = (1, 0, 0), up₀ = (0, 0, 1). [CITE NEEDED: angiographic display convention]
3. LAO α rotates the detector about the long axis z toward the patient's left: d₁ = (sin α, −cos α, 0), r₁ = (cos α, sin α, 0).
   [CITE NEEDED: DICOM positioner primary angle]
4. Cranial β tilts the detector toward the head, about r₁: d = cos β·d₁ + sin β·z, up = cos β·z − sin β·d₁.
5. Point source at iso − SOD·d; flat detector at iso + (SID − SOD)·d.

Consequences:
- **Equivalence.** Step 4 gives exactly the code's `v = normalize(z − (z·d)d)`, since z − sin β·d = cos β·(cos β·z − sin β·d₁). It
  also gives the code's `u = v × d` = z × d₁ = r₁. So the code's closed form *is* this rotation composition. The phantom test checks
  the whole render chain against it.
- **Handedness.** A coronal letter's handedness on screen is sign(cos α · cos β), with perspective removed
  (`e2_derivation.csv`, `letter_handedness_det`). It reads normally at every |α| < 90° and is edge-on at |α| = 90°.
  - A mirror reverses it.
  - An angle-sign swap does *not* reverse it. Swaps can only be caught by **position**, and the test is designed to use position.

**Decision rule** (fixed in the script before the run). A render passes for a view iff all three hold:
- (a) mask IoU with the expected image ≥ 0.70;
- (b) exactly 3 components, each centroid within 2.0 px (0.98 mm) of its expected centroid;
- (c) for |α| < 90°, each letter matches its true glyph better than its mirror image.

**Negative controls**, all of which must fail: a left-right mirrored render; a LAO↔RAO swapped render (−α, β); a CRAN↔CAUD swapped
render (α, −β); and an up-down mirrored render (extra). A swap of an angle that is 0 yields the identical image. It is reported as not
applicable: no image-based test can see it, and the swap changes nothing.

**Results** (`e2_tests.csv`, `e2_meta.json` summary)

| View (α, β) | Correct render | Mirror L-R | LAO↔RAO swap | CRAN↔CAUD swap | Mirror U-D |
|---|---|---|---|---|---|
| RAO caudal (−30, −25) | PASS (IoU 0.969, max err 0.45 px) | detected | detected | detected | detected |
| RAO cranial (−30, +30) | PASS (0.969, 0.16 px) | detected | detected | detected | detected |
| AP cranial (0, +35) | PASS (0.972, 0.54 px) | detected | n/a (α = 0) | detected | detected |
| AP caudal (0, −30) | PASS (0.957, 0.94 px) | detected | n/a (α = 0) | detected | detected |
| LAO cranial (+40, +30) | PASS (0.978, 0.09 px) | detected | detected | detected | detected |
| LAO caudal / spider, atlas (+40, −30) | PASS (0.981, 0.09 px) | detected | detected | detected | detected |
| **LAO caudal / spider, classic (+45, −30)** | **FAIL** (IoU 0.985; 2 components, see below) | (fails) | (fails) | (fails) | (fails) |
| Left lateral (+90, 0) | PASS (0.921, 0.58 px; handedness n/a, edge-on) | detected | detected | n/a (β = 0) | detected |
| RAO 30 (−30, 0) | PASS (0.968, 0.93 px) | detected | detected | n/a (β = 0) | detected |
| LAO 45 (+45, 0) | PASS (0.973, 1.43 px) | detected | detected | n/a (β = 0) | detected |

Negative-control IoU against the expected image ranged from 0.000 to 0.162 (`e2_tests.csv`), against ≥ 0.92 for correct renders.

**Failure, stated plainly.** At LAO 45 / CAUD 30 the "R" and "F" markers of *this phantom* overlap in projection. The render
therefore has 2 connected components, not 3, and the correct render fails rule (b).
- This is a flaw in the phantom design, not in the app. The render agrees with the derivation there (IoU 0.985, the highest of any view,
  and the "L" centroid is within 0.23 px).
- Because the positive control fails at that view, its negative controls are uninformative: they "fail" trivially. The detection counts
  above therefore exclude that view.
- I did not move the markers after seeing this. The options are in TODO U7.

**Second limitation.** Under a mirror or swap the components match the wrong markers. The handedness sub-rule (c) then compares a
letter with a different glyph and is not informative; it passed in most negative controls. Every detection came from rules (a) and (b).
Handedness is shown correct only for the correct renders: all 24 letters at the 8 valid views with |α| < 90° match their true
glyph and none match the mirror (`e2_views.csv`). See TODO U8.

**Interpretation.** At the 9 views where the phantom is valid, the rendered position of every marker matches the first-principles
prediction within 1.43 px (0.70 mm at the detector). Each deliberately mirrored or sign-swapped render is rejected with a large margin.

## E3. Distractor validity (Predict mode, atlas app)

Script: `paper/scripts/e3_distractors.py` (browser side `paper/scripts/browser/e3_browser.mjs`), with `paper/scripts/e3_margins.py`.
Results: `paper/results/e3/e3_summary.json`, `e3_items.csv`, `e3_pairs.csv`, `e3_labels.csv`, `e3_margins.csv`, `e3_similarity.png`.

**What an "item" is.** Predict items are generated, not stored. Each round, `drawPose` picks a target (a preset or a random pose) and
`makeCandidates` builds four options. Coverage was therefore split in two:
1. **Logic:** `makeCandidates` on every integer target over the full range (181 × 91 = 16,471 targets), with the mirror toggle off and
   on.
2. **Rendered items:** the real atlas PredictMode object, unmodified. That is every preset target × mirror off/on (12 items) plus
   600 seeded rounds of the real flow (300 with the mirror toggle off, 300 on). In each round the answer is given, the C-arm moves to
   the target, and the next round starts from there. Seed 20261114. Total: 612 items, 2,448 candidate images.

**(1) Logic** (`e3_summary.json` → `logic`)
- 32,780 of 32,780 candidate sets are valid: four distinct kinds, exactly one correct, each kind's angles and mirror flags equal to
  its label's transformation, and no two candidates describing the same image.
- `makeCandidates` threw for 162 sets, all inside the degenerate zone |α| < 5° and |β| < 5° (81 targets × 2 settings), as designed.
- `drawPose` produced 0 degenerate targets in 100,000 seeded draws.

**(2a) The correct option is the reference render**
- The correct tile shown to the learner was byte-identical to an independent re-render of the target pose in **610 of 612** items.
  All four tiles were byte-identical in **606 of 612** items.
- The 6 exceptions differ in 15-72 bytes of 1,048,576 (RGBA), i.e. a few pixels (`e3_items.csv`, `max_tile_bytes_differ_any`).
  Their vessel images still match the CPU reference at r = 1.0000.
  - I have not identified the cause. Likely candidates: GPU nondeterminism, or the app's live 15 fps image refresh interleaving with the
    tile render. Not verified.
  - This is reported as a finding. It is not a geometry error, because the labels and positions are unaffected (below).
- The correct candidate's vessel image matched the exact CPU reference at the target pose in every item: r ≥ 0.99999, mask IoU ≥ 0.9988.

**(2b) The four options are distinct** (binary vessel masks, path length > 0; 3,672 pairs)

| Pairs | n | IoU median | IoU 95th pct | IoU max | SSIM median | SSIM max |
|---|---|---|---|---|---|---|
| all pairs | 3,672 | 0.035 | 0.106 | 0.209 | 0.892 | 0.931 |
| pairs with the correct option | 1,836 | 0.042 | 0.131 | 0.205 | 0.895 | 0.931 |

The per-pair-type breakdown (12 types) is in `e3_summary.json` → `by_pair_type` and `e3_similarity.png` (a: IoU, b: SSIM).
- The most similar pair type was LAO/RAO flip vs both flipped, with IoU max 0.209.
- **Near-duplicate threshold** (fixed before the run): a pair is flagged if its IoU is at least the highest IoU between the correct view
  and the same view moved 5° on one axis. 5° is the app's own "same image" bound, `DEGENERATE_DEG`.
  - That per-item threshold ranged from 0.209 to 0.522 (median 0.310).
  - **0 of 3,672 pairs were flagged**, and 0 were flagged under a fixed IoU ≥ 0.9 rule.
  - Every distractor differs from the correct image by more than a 5° C-arm error does.
- **SSIM is not informative here.** Vessel masks are sparse (about 1-2 % of pixels), so SSIM is dominated by the shared empty
  background and sits at 0.86-0.93 for every pair, related or not. I recommend reporting IoU as the distinctness measure and SSIM
  only with this caveat. Alternatively, compute SSIM on a crop around the vessels (would need your OK, since it changes the metric
  after seeing the data).

**(2c) Each distractor is the transformation it is labelled as.** Each candidate's GPU vessel image was correlated with CPU references
of all six hypotheses: correct, LAO/RAO flip, CRAN/CAUD flip, both flipped, L-R mirror, U-D mirror.
- The label was the best match for **2,448 of 2,448** candidates, with r(label) ≥ 0.99999.
- Margin over the next-best hypothesis, on targets where all six hypotheses are distinct images (`e3_margins.csv`):

| Label | n | Label best match | Min margin (r) |
|---|---|---|---|
| correct | 429 | 429 | 0.526 |
| LAO/RAO flip | 429 | 429 | 0.489 |
| CRAN/CAUD flip | 429 | 429 | 0.526 |
| both flipped | 218 | 218 | 0.489 |
| L-R mirror | 211 | 211 | 0.621 |

- At the 183 targets with β = 0 (RAO 30 and LAO 45 presets), the app correctly offers mirrors instead of a CRAN/CAUD flip. My hypothesis
  set still contained that flip, which is the identical image there. The raw margin in `e3_summary.json` is therefore 0.0 for
  "correct" and "LAO/RAO flip": a tie with an identical image, an artefact of the test, not of the app. The label was the best match in
  all 183 of those items as well.

## E4. Segment foreshortening vs recommended views: **NOT RUN**

`paper/benchmarks/recommended_views.csv` was not supplied, and per the brief I did not invent it (TODO M1). Two further prerequisites
are open:
- the foreshortening definition (TODO U4: the app's F vs the brief's projected/true ratio);
- the atlas has no named diagonals, OMs or PDA and no saved branch labels in the repo (TODO U5). Only the LM, LAD, LCx and RCA trunks
  are defined today.

## E5. Performance (first run, SUPERSEDED by the cold-load rerun below; files kept in `paper/results/e5_v1_warm/`)

Script: `paper/scripts/browser/e5_performance.mjs`. Results (this first run): `paper/results/e5_v1_warm/`.

**Hardware:**
- Intel Core i5-10300H (4 cores / 8 threads), 11.9 GB RAM, Windows 11 Home 10.0.26200.
- GPUs: NVIDIA GeForce GTX 1650 Ti and Intel UHD Graphics.
- Software: Chromium 153.0.8010.12 (Playwright), Node v24.12.0.
- Served: `vite preview` of the production build (`web/dist`) on localhost.

**Method.** 5 repetitions per configuration, each in a fresh browser context.
- *Load:* navigation start to the app's ready flag.
- *Rotation:* in Scene 4 the C-arm was swept continuously for 10 s (α = 90 sin(2πt/6 s), β = 30 sin(2πt/4 s)). The X-ray was
  re-rendered on **every** animation frame. This is a worst case; the app itself refreshes the X-ray at 15 frames/s.
- *Memory:* the JS heap (CDP), plus the working set of all Playwright Chromium processes.

**Results** (`e5_summary.csv`, median of 5 [min-max])

| Configuration | GPU used | Load, Scene 1 (ms) | Load, Scene 4 (ms) | Rotation fps | Frame p95 (ms) | JS heap after rotation (MB) | Chromium working set (MB) |
|---|---|---|---|---|---|---|---|
| headless, D3D11 | Intel UHD (ANGLE) | 1,691 [1,591-4,833] | 1,453 [1,151-1,681] | 59.9 [59.9-59.9] | 33.4 | 12.4 [12.0-12.9] | 838 [818-858] |
| headless, SwiftShader (no GPU) | software | 5,116 [4,037-5,552] | 28,739 [26,888-30,435] | 1.3 [1.3-1.3] | 1,483 | 9.3 [8.9-9.9] | 689 [675-724] |

The Scene 4 page reported 16 MB transferred (`transfer_mb_scene4`).

**Interpretation**
- On this laptop's integrated GPU the app holds the display rate (59.9 fps median, i.e. the 60 Hz frame cadence) while the C-arm
  rotates and the X-ray is re-rendered every frame.
- The 95th-percentile frame time is 33.4 ms: an occasional skipped frame, not sustained slowdown.
- Without a GPU (SwiftShader) the app is not usable: 1.3 fps, and about 29 s to reach Scene 4. A WebGL-capable GPU is a requirement.

**Limitations of this measurement, stated plainly**
1. **Scene 4 was loaded right after Scene 1 in the same context.** Its load time therefore benefits from compiled shaders and any
   cached responses, and is not a cold load. Scene 1 is the cold-load figure. The first repetition's Scene 1 load, 4,833 ms, includes
   first-start costs.
2. **Chromium ran on the Intel iGPU**, not the GTX 1650 Ti. ANGLE's default adapter choice was not overridden.
3. **The "this machine, visible window" run was not done** (`--headed=1`; TODO U9). Both runs are headless.
4. **fps is capped by the frame cadence**, so it shows the app keeps up, not how much headroom remains.
5. **GPU memory is not measured.** The JS heap excludes GPU buffers and textures, and the working set covers every Chromium process.
6. **Single machine, localhost.** No network latency; no other browsers, operating systems or GPUs.

---

## Failures and limitations, collected

1. **E2 positive control failed at one view**, the classic spider (LAO 45 / CAUD 30): two phantom markers overlap there. This is a
   phantom-design flaw; the app's image matches the derivation (IoU 0.985). Options are in TODO U7.
2. **E2 handedness sub-rule** is uninformative once markers are mis-matched. Detection of the negative controls rests on IoU and
   position (TODO U8).
3. **E1 is a twin-implementation test.** It cannot detect a convention that is wrong in both twins. E2 covers that against a derivation
   that rests on the DICOM angle definitions and the display convention; both still need citations.
4. **E3: 6 of 612 items had tiles that differ from a re-render by 15-72 bytes.** The cause is not identified; labels and geometry are
   unaffected.
5. **E3: SSIM saturates on sparse masks** (0.86-0.93 for every pair) and does not discriminate. Use IoU.
6. **E3: the raw label margin of 0** at β = 0 targets is a tie with an identical hypothesis in my test set, not an app defect
   (`e3_margins.csv`).
7. **E4 not run:** the benchmark table is missing, the definition is open and the segment labels are missing (TODO M1, U4, U5).
8. **E5:** Scene 4 load is warm, the run is headless only, it used the integrated GPU, and it covers a single machine.
9. **All experiments use one atlas anatomy and synthetic phantoms.** Anatomical variation (dominance, other hearts) is not tested,
   and no ASOCA data was used.
10. **The spider view differs between the two apps** (40 vs 45° LAO). Both were measured (TODO U3).


---

# Update after the author's review (2026-11-14): decisions applied

The author approved the following, and the runs below were made one at a time.
- E4 is dropped: no E4 outputs had been produced, so nothing was deleted.
- ASOCA is out of the paper.
- E2 is rerun with a second phantom.
- The tile mismatch is investigated for up to 1 h.
- E5 is rerun with cold loads and the discrete GPU.
- SSIM moves to the Online Resource.

## E2, second phantom (`paper/results/e2_v2/`, `e2_orientation.py --phantom=v2`)
- **The change.** Only the F letter moved, to iso + (+40, −25, −65) mm. The position was chosen *before rendering*, analytically:
  no two letters may come within 5 px at any named view (the closest gap is 67 px).
- **Correct renders** passed at **10/10** views, with IoU ≥ 0.891 and maximum
  centroid error 1.43 px. This includes the classic spider view, where phantom 1 failed.
- **Handedness** was correct for all 27 non-lateral letters.
- **Negative controls detected:**

  | Control | Detected |
  |---|---|
  | Left-right mirror | 10/10 |
  | LAO↔RAO swap | 8/8 |
  | CRAN↔CAUD swap | 7/7 |
  | Up-down mirror | 10/10 |

  Their maximum IoU against the expected image was 0.168.
- **Phantom 1 is kept** (9/10, with the overlap explained) and reported alongside phantom 2 in the manuscript.

## E3 tile mismatch: investigation (`browser/e3_tile_probe.mjs` → `results/e3/e3_tile_probe.json`)
The probe replayed both seeded flows (600 rounds). Each tile was compared with an immediate re-render and with 5 further re-renders.
- **Mismatching tiles:** 2 of 2,400. These were *different* rounds from the 6 seen in E3, so
  the mismatch does not recur for the same items.
- **Repeat renders of the same pose:** 7 of 12,000 differed. The renderer itself is
  occasionally nondeterministic at the byte level.
- **Where and how large:** each difference is a ~4 × 4-pixel patch outside the vessels (0 vessel pixels among
  the differing pixels), up to 14 grey levels, equal in R, G and B.
- **Conclusion:** consistent with run-to-run GPU nondeterminism in the composite/bone layers on the Intel iGPU. Labels, geometry and
  vessel pixels are unaffected. The cause is attributed, not proven at the driver level.

## E5, rerun (`paper/results/e5/`)
Every scene is now cold-loaded in its own fresh browser context. Three configurations were run, and the GPU actually used is read
back from WebGL on every run:

| Configuration | GPU used | Load, Scene 1 (s) | Load, Scene 4 (s) | fps | p95 frame (ms) | Heap (MB) |
|---|---|---|---|---|---|---|
| headless | Intel UHD (iGPU) | 1.2 | 1.2 | 59.9 | 33.4 | 14.8 |
| visible window, `--force_high_performance_gpu` | NVIDIA GTX 1650 Ti | 1.0 | 1.0 | 59.9 | 16.8 | 14.5 |
| headless, SwiftShader | software | 4.6 | 4.6 | 1.5 | 1333.3 | 9.8 |

- **Software rendering:** cold-loaded, it ran at 1.5 fps (the first, warm run gave 1.3 fps). Its
  Scene 4 load fell from ~29 s in the first run to 4.6 s. The first run's sequential same-context loading
  was therefore flawed, not merely warm.
- **Transfer:** a cold Scene 4 load transfers 27 MB.

## E4
Dropped from the paper (atlas lacks named branches; no recommended-view table). Listed as future work in the manuscript.
