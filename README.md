# Coronary Projection Trainer

Personal learning tool: how a 3D coronary tree becomes a 2D angiogram at a given C-arm angle.
Geometry rules: [CONVENTIONS.md](CONVENTIONS.md). Choices and open questions: [DECISIONS.md](DECISIONS.md).

**Status: Phase 2** (foreshortening, inter/self capsule overlap, angle-space heatmaps), on top of Phase 1 (dual viewer, thickness angiogram, C-arm, detector ghost, projection rays, linked selection, Label mode). Next: Phase 3 (Mission, Guess); the DRR comes after Phase 3.

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
