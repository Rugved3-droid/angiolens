# Coronary Projection Trainer

Personal learning tool: how a 3D coronary tree becomes a 2D angiogram at a given C-arm angle.
Geometry rules: [CONVENTIONS.md](CONVENTIONS.md). Choices and open questions: [DECISIONS.md](DECISIONS.md).

**Status (2026-10-02).** The product is a simple, cinematic, animated explainer, not a dashboard. There are no numbers by default;
metrics live behind "Advanced". There are two apps on one validated geometry engine:

- **A. Main C-arm app** (`index.html`, ASOCA case Normal_12, a real patient CT):
  - validated LPS projection and X-ray rendering, with a synchronized 3D panel (C-arm, detector ghost, rays);
  - metrics and heatmaps, branch labels with derived SCCT segments, and Predict mode;
  - the distal-RCA extension is off (judged venous-leaning) and dominance is "indeterminate".
- **B. Atlas scenes** (`atlas.html`, the Z-Anatomy heart, skeleton and skin, CC BY-SA 4.0). Not yet connected to the C-arm.
  - Scene 1: the beating heart close-up, with an aortic-root close-up.
  - Scene 2: the heart inside a glass body, with five views.
  - The vessels have the atlas's own authored sizes (D46), and the great vessels down to the iliac bifurcation are shown.
  - Catheter access routes are exported but hidden (D47). The skin is one welded surface (D48).

- **Scene 3, cath lab:** table, glass patient, C-arm. Smooth swings between the standard views; Room and Operator cameras.
- **Scene 4, X-ray pass:** the validated engine on the atlas coronaries (D49-D50). Selective LCA/RCA injection with a faint skeleton
  and heart silhouette; beam cone; the image builds on the detector; Beam (free orbit) and Side-by-side views.

Next (not started): Scene 5 (catheter up the aorta to the effective ostium, contrast filling), Scene 6 (cross-section), the
phone-as-detector controller, relative-move Predict questions, Mission/Guess. The TotalSegmentator heart (section "Simple view" below) is **no longer the hero heart**: Z-Anatomy is (D43). The
TotalSegmentator pipeline is kept only for the ASOCA case's own anatomy.

## Atlas scenes (Z-Anatomy)

Source, license and frame: DECISIONS D37-D48 and CONVENTIONS sections 10-11. All exports are git-ignored.

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
.\.venv\Scripts\python preprocess\scripts\phase0_atlas.py
.\.venv\Scripts\python preprocess\scripts\atlas_xray_fixtures.py
cd web; node e2e/atlas_xray.e2e.mjs        # GPU angiogram == CPU reference on the atlas; mirrored images must fail
node e2e/atlas_shots.mjs shots              # review screenshots -> out/review/atlas/
node e2e/lab_shots.mjs all                  # cath lab / X-ray screenshots + swing recording -> out/review/lab/
```

Files: `z_anatomy_heart.glb` (atlas radii, THE geometry), `z_anatomy_heart_illustrative.glb` (illustrative taper, comparison only),
`z_anatomy_access_routes.glb` (femoral + right radial, hidden by default), `z_anatomy_skeleton.glb`, `z_anatomy_skin.glb` (welded),
`manifest.json` (per-object provenance, calibre, effective ostia, access-route continuity, weld statistics).

The URL accepts `atlas.html?scene=1|2&view=front|lao|root|left|right|feet|head|body&routes&still`, and for the lab
`atlas.html?scene=3|4&carm=ap|rao30|lao45|raocaud|spider&cam=room|operator|beam|split&inject=left|right`.

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
