# Coronary Projection Trainer

Personal learning tool: how a 3D coronary tree becomes a 2D angiogram at a given C-arm angle.
Geometry rules: [CONVENTIONS.md](CONVENTIONS.md). Choices and open questions: [DECISIONS.md](DECISIONS.md).

**Status: Phase 0** (data loading, LPS, projection math, tests, reference PNGs). No UI yet.

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

## Layout

```
preprocess/cpt/geometry.py   C-arm frame, projection, magnification, foreshortening
preprocess/cpt/volume.py     NRRD -> LPS (RAS converted, anything else rejected)
preprocess/cpt/case.py       case loading, left/right split, isocenter
preprocess/cpt/render.py     reference CPU path-length renderer, detector raster
preprocess/cpt/synthetic.py  voxel phantoms
tests/                       one test per convention
web/                         (Phase 1) Vite + TypeScript + three.js
```
