# Coronary Projection Trainer

Personal learning tool: how the 3D heart and its coronary arteries become the 2D angiogram at any C-arm angle.
Geometry rules: [CONVENTIONS.md](CONVENTIONS.md). Choices and open questions: [DECISIONS.md](DECISIONS.md).

## v1.1 (branch `v1.1`, in progress)

- `npm run launch:v1`: the frozen v1.0, built and served on port 5177 (its own worktree and data snapshot; DECISIONS D64).
- `npm run verify`: every suite plus the static build (the pre-commit hook runs it).
- **Study session:** `study.html`. Pre-test on the ASOCA patient, atlas training, post-test, results and a CSV per participant
  (D65).
- **X-ray shadow mode:** `atlas.html?ff=shadow`, then More -> X-ray shadow (D66). Feature flags: `?ff=shadow`, `?ff=all`,
  `?ff=none`.

## Launch (v1.0)

```powershell
cd web
npm install          # once
npm run launch       # = npm run build && npm run start: builds the static app, serves dist/ and opens /atlas.html on port 5178
```

`npm run start` serves an existing build without rebuilding. The app is static (no backend). The anatomy files in
`web/public/anatomy/` are git-ignored and must be built first (section "Atlas scenes" below).

**Status (2026-10-04): v1.0** (tag `v1.0`; release candidate `v1.0-rc1`). A cinematic, animated explainer, not a dashboard: no numbers in the main experience (view names
only). Two apps share one validated geometry engine:

- **The atlas app** (`atlas.html`, the v1.0 product): the Z-Anatomy heart, skeleton and skin (CC BY-SA 4.0).
  - One toolbar row: **Tour**, a scene stepper with Back and Next, 2-4 controls per scene, and **More** for the rest.
  1. **Heart:** the beating heart; an aortic-root close-up.
  2. **In the chest:** a glass body with faint bones; five views.
  3. **Cath lab:** table, patient and C-arm. Smooth swings between AP, RAO 30, LAO 45, RAO caudal and spider; Room and Operator
     (femoral or radial) cameras.
  4. **X-ray:** the validated engine on the atlas coronaries, with selective left or right injection and a faint skeleton and heart
     silhouette.
     - The image builds on the detector and in the monitor.
     - Beam view (free orbit) and side-by-side.
     - **Predict**: which of four images does a named view make? Same distractors and error tracking as the CT app.
  5. **Catheter** (illustrative): right femoral or radial access.
     - A J-wire and a 6F catheter go up to the aortic root; JL4 or JR4 engages the effective ostium.
     - Contrast fills the tree in 3D and on the X-ray together, with a cine heartbeat.
  6. **Cross-section** (illustrative): a large labelled slice (lumen, three-layer wall, epicardial fat, catheter tip).
     - It is synced with a ring on the 3D vessel and a dot on the X-ray; pick any coronary or follow the tip, and slide along
       the vessel.
  - **Tour:** ten auto-advancing steps from the beating heart to the slice at the left main, with pause, back and next.
  - Phone controller, Mission/Guess and relative-move questions are v1.1.
- **The CT app** (`index.html`, ASOCA case Normal_12, a real patient CT):
  - validated projection with a 3D panel, metrics and heatmaps behind "Advanced", branch labels with SCCT segments, Predict;
  - the distal-RCA extension is off (judged venous-leaning) and dominance is "indeterminate".

The TotalSegmentator heart (section "Simple view" below) is **no longer the hero heart**: Z-Anatomy is (D43). The
TotalSegmentator pipeline is kept only for the CT case's own anatomy.

## Atlas scenes (Z-Anatomy)

Source, license and frame: DECISIONS D37-D63 and CONVENTIONS sections 10-12. All exports are git-ignored.

```powershell
# 1. export (needs Startup.blend in assets/anatomy/source/; checks free memory first; peak ~6.2 GB)
powershell -ExecutionPolicy Bypass -File preprocess\blender\run_blender.ps1 -Script preprocess\blender\export_anatomy.py `
  -Log assets\anatomy\blender_stdout.txt -ScriptArgs "assets\anatomy\frame.json|assets\anatomy|assets\anatomy\provenance.json"
# 2. weld the skin regions into one surface
.\.venv\Scripts\python preprocess\scripts\weld_skin.py
# 3. copy the viewer files and check
foreach ($f in "heart","heart_illustrative","access_routes","skeleton","skin") { Copy-Item "assets\anatomy\z_anatomy_$f.glb" web\public\anatomy\ }
.\.venv\Scripts\python -m pytest -q tests\test_anatomy_frame.py tests\test_anatomy_export.py tests\test_weld.py
# 4. atlas X-ray: closed meshes + isocenter, the Phase 0 sanity sheet (out/phase0/atlas/), GPU reference fixtures
.\.venv\Scripts\python preprocess\scripts\build_atlas_xray.py
.\.venv\Scripts\python preprocess\scripts\build_display_skeleton.py    # the simplified glass-body bones (D60)
.\.venv\Scripts\python preprocess\scripts\phase0_atlas.py
.\.venv\Scripts\python preprocess\scripts\atlas_xray_fixtures.py
.\.venv\Scripts\python preprocess\scripts\junction_before_after.py   # D52 figure -> out/review/lab/
# 5. Scene 5 data: routes, JL4/JR4 shapes, contrast-fill distances (needs the probe: run_blender.ps1 -Script probe_great_vessels.py)
.\.venv\Scripts\python preprocess\scripts\build_atlas_cath.py
# 6. display aorta (D62): one smoothed solid, coronary origins filleted, ostia re-measured on it (writes the manifest), then the
#    catheters / fill distances again from the re-measured ostia; free vessel ends for the end fade
.\.venv\Scripts\python preprocess\scripts\build_aorta_display.py
.\.venv\Scripts\python preprocess\scripts\build_atlas_cath.py
.\.venv\Scripts\python preprocess\scripts\build_vessel_ends.py
cd web; node e2e/atlas_xray.e2e.mjs        # GPU == CPU on the atlas (mirrors fail) + cine field moves / static frame unchanged
node e2e/atlas_shots.mjs shots              # review screenshots -> out/review/atlas/
node e2e/lab_shots.mjs all                  # cath lab / X-ray screenshots + swing recording -> out/review/lab/
node e2e/cath_shots.mjs all                 # Scene 5 screenshots + full-sequence recording -> out/review/cath/
node e2e/atlas_v1.e2e.mjs                   # Predict on the atlas, Scene 6 sync (dot = engine projection, shared fill), stepper
node e2e/v1_shots.mjs all                   # every scene at 1280 / 1920 px, toolbar, fps per view, tour recording -> out/review/v1/
                                            #   OUT=v1_1 (another folder), ONLY=s1_root,s5_root (some views), SUFFIX="&aorta=atlas"
node e2e/root_zoom.mjs                      # aortic-root close-ups (PREFIX=before_ SUFFIX="&aorta=atlas": the original segments)
node e2e/hover_probe.mjs "scene=6" 1280x800 120,280   # names what is under a screen point (identify objects in review shots)
node e2e/hide_probe.mjs "scene=6" "Superior vena cava"  # hides named meshes one at a time and screenshots
node e2e/tour_stalls.mjs                    # plays the tour and lists every frame slower than 50 ms
node e2e/inject_stall.mjs                   # frame times + shader-program count around the first injection
node e2e/scene6_stall.mjs                   # frame times + CPU profile entering Scene 6 and injecting (stall diagnosis)
node e2e/fade_probe.mjs "scene=5&engaged"   # per C-arm part: distance from the camera and fade alpha
```

Files: `z_anatomy_heart.glb` (atlas radii, THE geometry), `z_anatomy_heart_illustrative.glb` (illustrative taper, comparison only),
`z_anatomy_access_routes.glb` (femoral + right radial, hidden by default), `z_anatomy_skeleton.glb`, `z_anatomy_skin.glb` (welded),
`manifest.json` (per-object provenance, calibre, effective ostia, access-route continuity, weld statistics).

The URL accepts `atlas.html?scene=1|2&view=front|lao|root|left|right|feet|head|body&routes&still`, and for the lab
`atlas.html?scene=3|4&carm=ap|rao30|lao45|raocaud|spider&cam=room|operator|beam|split&inject=left|right&op=femoral|radial`, and
for the catheter `atlas.html?scene=5&access=femoral|radial&target=left|right&cam=room|operator|beam|root&engaged&fill=0..1`,
the slice `atlas.html?scene=6&target=left|right&fill=0..1`, Predict `atlas.html?scene=4&predict` and the tour `atlas.html?tour`.

## Data

ASOCA (Gharleghi et al. 2022, https://doi.org/10.1016/j.dib.2022.108543). Non-commercial use; do not redistribute.
`data/`, `out/` and `web/public/cases/` are git-ignored.

Expected layout, one folder per case:

```
data/raw/<case_id>/CTCA_<case_id>.nrrd
data/raw/<case_id>/Annotation_<case_id>.nrrd
```

To add a case from the original ASOCA zip, extract the two members unmodified, for example `Normal_5`:

```powershell
.\.venv\Scripts\python -c "import zipfile,shutil,os; z=zipfile.ZipFile(r'D:\ASOCADataAccess.zip'); c='Normal_5'; os.makedirs(f'data/raw/{c}',exist_ok=True); [shutil.copyfileobj(z.open(f'ASOCADataAccess/Normal/{s}/{c}.nrrd'), open(f'data/raw/{c}/{d}_{c}.nrrd','wb')) for s,d in [('CTCA','CTCA'),('Annotations','Annotation')]]"
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python -m pytest -q                                  # all geometry/loader/raster tests
.\.venv\Scripts\python preprocess\scripts\phase0_synthetic.py        # chiral phantom -> out/phase0/synthetic/
.\.venv\Scripts\python preprocess\scripts\phase0_case.py --case Normal_12   # -> out/phase0/Normal_12/
```

Phase 0 outputs:
- one PNG per view (`left_RAO30_CAUD25.png`, …)
- one contact sheet per tree
- `case_meta.json` (header, affine, SHA-256 of the inputs, isocenter, tree split)

Each image carries a glyph showing the patient L/P/S axes projected through the same C-arm.

## Phase 1: build case assets and run the viewer

```powershell
.\.venv\Scripts\python preprocess\scripts\build_case.py --case Normal_12      # -> web/public/cases/Normal_12/ (~75 s)
.\.venv\Scripts\python preprocess\scripts\review_masks.py --case Normal_12    # bone vs blood-pool review figure
cd web
npm install
npm run dev                                                                    # http://localhost:5178/?case=Normal_12
```

The URL accepts `?case=<id>&alpha=-30&beta=-25&inject=left|right`. Arrow keys nudge the C-arm 1° (Shift: 5°).

Label mode: tick "Label mode (branches)", click a vessel in either panel, then pick a BRANCH name (LM, LAD, D1, ...). Segments (LAD prox/mid/dist, LCx prox/dist, RCA prox/mid/dist) are derived from the branch labels and shown with "show derived segments". Check the splits in both panels, then press "Approve segmentation" (any later label change voids the approval). Missions use approved segments only. Labels autosave in the browser. To make them part of the
case, use "Export labels.json" and put the file in `web/public/cases/<id>/`.

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q                        # Python: geometry, loader, raster, masks, centerlines, meshes
.\.venv\Scripts\python preprocess\scripts\make_ts_fixtures.py
cd web; npx vitest run                                     # TypeScript geometry vs Python fixtures, rays, picking
npx playwright install chromium                            # once
..\.venv\Scripts\python ..\preprocess\scripts\build_phantom.py
node e2e/phantom.e2e.mjs                                   # GPU angiogram vs Python reference; mirror images must fail
node e2e/interaction.e2e.mjs                               # click selection in both panels, Label mode, export
node e2e/metrics.e2e.mjs                                   # in-browser metrics + worker map optimum equal Python
node e2e/segments.e2e.mjs                                  # derived segments + approval, ray colours = capsule metric, scale floors
node e2e/predict.e2e.mjs                                   # Predict: candidates, correct tile orientation, mirror distractor, scoring
node e2e/screens.mjs Normal_12 '[{"name":"x","a":-30,"b":-25,"tree":"left","sel":5}]'   # review screenshots
```

## Layout

```
preprocess/cpt/geometry.py     C-arm frame, projection, magnification, foreshortening
preprocess/cpt/volume.py       NRRD -> LPS (RAS converted, anything else rejected)
preprocess/cpt/case.py         case loading, left/right split, isocenter
preprocess/cpt/render.py       reference CPU path-length renderer, detector raster
preprocess/cpt/synthetic.py    voxel phantoms
preprocess/cpt/masks.py        bone (positive definition) and blood-pool masks
preprocess/cpt/centerline.py   centerline graph (official ASOCA paths; skeleton fallback)
preprocess/cpt/mesh.py, glb.py closed LPS meshes, verbatim GLB writer
tests/                         one test per convention
web/src/geometry.ts            TypeScript twin of geometry.py
web/src/angio.ts               GPU path-length angiogram
web/src/scene3d.ts             3D panel: anatomy, C-arm, detector ghost, rays
web/src/rays.ts                projection rays, overlap culprits, picking
web/src/labels.ts              Label mode storage
preprocess/cpt/metrics.py      Phase 2 metrics (reference)
web/src/metrics.ts             Phase 2 metrics (app); metricsWorker.ts, metricsPanel.ts, heatmap.ts
preprocess/cpt/extension.py    non-expert extension tracer (separate layer; D20)
reviews/                       human review records (mask approvals); no patient data
web/e2e/                       headless-browser checks
```

## Predict mode

Press **Predict** in the header. You are told a target view (e.g. "RAO 30 / CAUD 25") and shown four angiograms:
- the correct one;
- LAO/RAO sign flipped;
- CRAN/CAUD sign flipped;
- both flipped, or, with the toggle, a left-right mirror image.

Pick one (A-D). The answer is revealed and the C-arm swings from where you were to the target. Your errors are tallied by type, so you can see
which axis you tend to get wrong. The C-arm controls are locked while a question is open.

## Simple view (default) and Advanced

The app opens in a simple, explanatory view. It shows this patient's heart (segmented from the CT with TotalSegmentator's open
`total` task) inside a translucent body on a cath table, with a C-arm whose beam and detector image follow the chosen angle. Only a
standard-view menu, two angle sliders and a one-line caption are shown. **Advanced** (top right) brings back every panel and mode
(Explore, Predict, labels, metrics, heatmaps).

Building the hero assets (once per case):

```powershell
python -m venv .venv-ts; .\.venv-ts\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv-ts\Scripts\python -m pip install TotalSegmentator nibabel pynrrd
# offline config (no usage statistics), weights stored in .totalseg/
$env:TOTALSEG_HOME_DIR = "$PWD\.totalseg"   # with config.json {"send_usage_stats": false}
.\.venv-ts\Scripts\TotalSegmentator -i data\derived\Normal_12\ts\ct.nii.gz -o data\derived\Normal_12\ts\seg --task total -d cpu --roi_subset heart aorta superior_vena_cava inferior_vena_cava pulmonary_vein atrial_appendage_left brachiocephalic_trunk
.\.venv\Scripts\python preprocess\scripts\build_anatomy.py --case Normal_12   # meshes + epicardial assertion
.\.venv\Scripts\python preprocess\scripts\build_body.py --case Normal_12      # CC0 body, approximate fit
cd web; node e2e/hero_shots.mjs                                              # review screenshots + swing recording
```
