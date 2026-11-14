# Phase 0 inventory: AngioLens (repository `coronary-projection-trainer`)

Snapshot: branch `paper/ijcars-verification`, created from `v1.1` at `198c6d4` (2026-10-22). Taken 2026-11-14.
Nothing in `web/src/` or `preprocess/` was changed for this inventory or for Phase 1.

> **Base branch.** `main` (`e2bec32`) is v1.0 plus the license commits. `v1.1` (`198c6d4`) adds the study session, shadow mode, peel
> mode and the Detector view, i.e. 41 more files. This paper branch starts from **v1.1** because that is the newest released code.
> If the paper should describe v1.0 instead, rebase before Phase 2 (U1 in TODO.md).

## 1. Architecture

| Layer | What it is | Files |
|---|---|---|
| Anatomy (atlas) | Z-Anatomy `Startup.blend` (CC BY-SA 4.0), exported by Blender 4.2.16 into LPS mm with one transform (`diag(1000)`) | `preprocess/blender/export_anatomy.py`, `preprocess/anatomy_frame.py`, `CONVENTIONS.md` §10 |
| Anatomy (CT, optional) | ASOCA `Normal_12` (licence-gated; git-ignored) through the "classic" app | `preprocess/scripts/build_case.py`, `web/public/cases/` (ignored) |
| X-ray meshes | closed coronary trees, one boolean union per tree; bone; heart soft tissue | `preprocess/scripts/build_atlas_xray.py` → `web/public/anatomy/atlas_xray_*.glb` (ignored) |
| Geometry (reference) | C-arm pose → source, detector, screen axes, projection, foreshortening | `preprocess/cpt/geometry.py` |
| Geometry (app) | same, in TypeScript, plus the WebGL clip matrix | `web/src/geometry.ts` |
| Image (reference) | exact CPU path length, ray/triangle entry-exit sums | `preprocess/cpt/meshrender.py` (meshes), `preprocess/cpt/render.py` (voxels, `DetectorGrid`) |
| Image (app) | GPU path length: entry/exit depth sums + counts, silhouette repair, Beer-Lambert display | `web/src/angio.ts` |
| Apps | **atlas** (`web/atlas.html`, `src/atlasHero.ts`: six scenes, Predict, tour, v1.1 features); **classic** CT/phantom app (`web/index.html`, `src/main.ts`); **study** session (`web/study.html`, `src/study/`) | |
| Predict mode | pure logic (`src/predict.ts`) + UI and tile rendering (`src/predictUI.ts`); used by both apps | |
| Metrics | foreshortening + 2D capsule overlap, Python and TS twins | `preprocess/cpt/metrics.py`, `web/src/metrics.ts` |

## 2. Conventions as implemented

**Patient frame.** LPS: +x patient left, +y posterior, +z superior, mm (`CONVENTIONS.md:8`). Atlas source axes are already L, P, S;
R = identity, s = 1000 (`CONVENTIONS.md:154-157`). glTF +Y-up is ignored; loaders reject non-identity node transforms
(`CONVENTIONS.md:71-73`).

**Angles** (DICOM positioner convention, `CONVENTIONS.md:19-20`):
- `web/src/geometry.ts:9-10`: `ALPHA_RANGE = [-90, 90]; // LAO +, RAO -`, `BETA_RANGE = [-45, 45]; // CRAN +, CAUD -`
- `preprocess/cpt/geometry.py:15-16`: the same ranges. Out-of-range angles throw (`geometry.ts:65-66`, `geometry.py:64-70`).

**Detector direction** (from the isocenter):
- `geometry.ts:27-31` / `geometry.py:20-23`: `d(α,β) = (sin α cos β, −cos α cos β, sin β)`. AP: d = (0, −1, 0), so the detector is
  anterior and the source posterior. LAO (α > 0) moves the detector toward patient left; cranial (β > 0) moves it superior.

**Screen axes and handedness:**
- `geometry.ts:34-40` / `geometry.py:26-38`: `v = normalize(z − (z·d)d)` (screen up = projected superior); `u = v × d` (screen right).
  So `u × v = d`: the image is seen from the detector looking back at the source. At AP, u = (1,0,0), so patient left is screen right.
- The WebGL clip matrix (`geometry.ts:111-122`) is mirror-handed by construction. Renderers therefore never use winding or
  `gl_FrontFacing`; they use world-space face normals (`CONVENTIONS.md:76-78`).

**Source and detector:** SID 1000 mm, SOD 750 mm (`geometry.ts:7-8`). `S = iso − SOD·d`, `D = iso + (SID−SOD)·d`
(`geometry.ts:70-71`, `geometry.py:87-92`).

**Projection:** the ray S→p hits the detector plane at q. Screen = ((q−D)·u, (q−D)·v), in detector mm (`geometry.ts:88-98`,
`geometry.py:103-117`).

**Raster:** row 0 is the top (+v) and column 0 is the left (−u) (`geometry.ts:141-149`, `render.py:34-39`).
- The GPU render target starts at the bottom. `angio.ts:309-314` (`readImage`) and `angio.ts:319-326` (`readThickness`) flip GL rows on
  readback.
- No display stage flips or rotates an image (`CONVENTIONS.md:4`).
- The **only** deliberate flip in the codebase is Predict's mirror distractor (`predictUI.ts:101-116`).

**Isocenter:** a single constant per case: the volume centroid of both closed coronary trees (`CONVENTIONS.md:228-229`).
Atlas value: (25.233, −45.512, 1291.3) mm (`web/public/anatomy/atlas_xray.json`).

**Detector in the atlas:** 250 mm wide, 512 × 512 px (`cathLab.ts:65`, `cathLab.ts:99`), so 0.488 mm per pixel.

**Foreshortening:** `F = 1 − Σ|Δp − (Δp·r)r| / Σ|Δp|`, with r the unit ray from S to each pair midpoint (`geometry.ts:126-138`,
`geometry.py:126-142`).
- F = 0 means fully in view; F = 1 means end-on.
- It is not "projected ÷ true length", which is what the Phase 1 brief asks for in E4. See TODO U4.

**Named views as implemented.** These are the values the code ships; the paper's view names map onto them.

| View | α, β | Where |
|---|---|---|
| RAO caudal | −30, −25 | `atlasHero.ts:927`, `main.ts:25` |
| RAO cranial | −30, +30 | `main.ts:26` (classic only) |
| AP cranial | 0, +35 | `main.ts:27` (classic only) |
| AP caudal | 0, −30 | `main.ts:29` (classic only) |
| LAO cranial | +40, +30 | `main.ts:28`; RCA variant +30, +20 at `main.ts:33` |
| LAO caudal "spider" | **+40, −30** (atlas) / **+45, −30** (classic) | `atlasHero.ts:928` vs `main.ts:29`: **the two apps disagree** (TODO U3) |
| RAO 30 / LAO 45 | −30, 0 / +45, 0 | `atlasHero.ts:925-926`, `main.ts:31-32` |
| Left lateral | +90, 0 | not a preset; the α range end |

**Predict mode** (`predict.ts`):
- Candidates for a target (α, β) (`predict.ts:62-89`):
  - correct;
  - `alpha-flip` (−α, β): "LAO/RAO sign flipped";
  - `beta-flip` (α, −β): "CRAN/CAUD sign flipped";
  - `both-flip` (−α, −β), or with the toggle on `mirror-lr` (a left-right mirrored image of the correct view).
- If |α| or |β| < 5° (`DEGENERATE_DEG`, `predict.ts:12`), that flip would reproduce the same image. It is replaced by a mirror
  (`mirror-lr` or `mirror-ud`).
- Targets come from `drawPose` (`predict.ts:94-113`):
  - 50 % preset, 50 % random;
  - random poses have |α| in 10-70° and |β| in 10-40°;
  - every target is at least 15° from the previous pose.
- Atlas presets (`atlasHero.ts:1383-1386`): RAO 30, LAO 45, RAO caudal and spider (LCA); RAO 30 and LAO 45 (RCA).
- Items are **generated, not stored**: there is no fixed item bank.

## 3. Python reference implementation

- `cpt/geometry.py`: the projection (above).
- `cpt/render.py`: `DetectorGrid` and the voxel path-length renderer.
- `cpt/meshrender.py`: exact CPU path length through closed meshes; ground truth for the atlas X-ray. Takes about 0.2 s per 512² image.
- `cpt/metrics.py`: foreshortening, capsule overlap and angle maps.
- Fixtures for the browser tests:
  - `preprocess/scripts/build_phantom.py` (synthetic chiral phantom);
  - `atlas_xray_fixtures.py` (CPU references at 6 atlas poses).

## 4. Existing tests: commands and results (run 2026-11-14 on this branch)

One command runs every gate: `cd web && npm run verify` (`web/scripts/verify_all.mjs`). **Result: ALL GREEN in 5.1 min, 15 of 15
steps passed.**

| Step | Command | Result |
|---|---|---|
| pytest | `.venv\Scripts\python -m pytest -q` | **393 passed** (60 warnings) |
| typecheck | `npx tsc --noEmit` | pass |
| vitest | `npx vitest run` | **65 passed, 7 files** |
| e2e × 11 | `node e2e/<suite>.e2e.mjs` for phantom, atlas_xray, atlas_label, predict, atlas_v1, interaction, metrics, segments, study, shadow, peel | 11 of 11 pass |
| build | `npm run build` | pass |

pytest has 82 `test_` functions in 16 files; parametrisation brings the count to 393. The tests most relevant to the paper:

| Test | Checks |
|---|---|
| `tests/test_geometry.py` (17) | AP detector anterior; AP screen right = patient left; RAO 30 spine left of heart; LAO 45 spine right of heart; superior up over the whole α×β grid; α moves the detector left; β moves it cranial; foreshortening 0 / 1 / 45° cases; frame orthonormal with u×v = d; S and D positions; screen round trip; isocenter translation only; out-of-range rejected; view labels |
| `tests/test_render.py` (8) | voxel renderer: patient left renders right at AP; superior renders top (also cranial/caudal); posterior renders left in RAO 30 and right in LAO 45; render = point projection; analytic sphere thickness; pixel mapping round trip |
| `tests/test_meshrender.py` (3) | analytic sphere chord at an oblique view; inward winding gives a negative path; AP left-right and superior-top |
| `tests/test_anatomy_frame.py` (6) | atlas frame: identity × 1000; Y-up source recovered; mirrored labels and mirrored geometry rejected; landmarks and scale |
| `tests/test_metrics.py` (7) | foreshortening and overlap metric rules; angle-map grid; metrics never read pixels (mutation-tested guard) |
| other pytest files | volume header and LPS handling (7), meshes and GLB (3), closed meshes (2), atlas union (1), anatomy export (5), aorta display (6), catheter (3), weld (6), masks (2), centerline (4), extension (2) |
| `web/tests/geometry.test.ts` | TS geometry rules, and TS = Python on `fixtures/geometry.json` (8 poses × 25 points, 1e-9 mm); clip matrix = point projection; raster mapping |
| `web/tests/predict.test.ts` | candidate kinds, mirror toggle, degenerate replacement, drawPose range and spacing, angular distance, summary counts |
| `web/tests/{metrics,heatmap,rays,segments,study}.test.ts` | metric twins; heatmap scaling; overlap rays; derived segments never invented; study-session design |
| `e2e/phantom` | classic-app GPU image vs the Python voxel reference on the chiral phantom at 6 poses (r > 0.95, MAE < 0.25 mm); L-R and U-D mirrors must fail |
| `e2e/atlas_xray` | atlas GPU vs CPU mesh renderer at 6 poses; mirrors must fail; cine field moves the image, and the static frame has r = 1 |
| `e2e/predict`, `e2e/atlas_v1` | four distinct candidates with one correct; correct tile not mirrored (r vs path length); answer recorded; C-arm moves to the target |
| `e2e/study`, `shadow`, `peel`, `interaction`, `metrics`, `segments`, `atlas_label` | v1.1 and UI features (not the paper's core) |

**What the existing suite does not cover:**
1. projection agreement over a dense angle grid (fixtures have 8 poses);
2. GPU = CPU on the atlas beyond 6 poses;
3. a phantom whose expected image is derived independently of `cpt.geometry`;
4. negative controls for angle-sign swaps (only mirrors are tested);
5. similarity between Predict distractors, or verification that each distractor's image is the labelled transformation;
6. foreshortening at the named views on the atlas;
7. performance.

Phase 1 adds these as measurement harnesses in `paper/scripts/`.

## 5. Facts that constrain the paper

- **The study session exists in v1.1** (`web/study.html`: pre-test, training, post-test, CSV export). The paper must not report any
  data from it, and should mention it only as a feature, if at all (TODO U2).
- **Atlas coronaries have no named diagonals, OMs or PDA.** In Z-Anatomy they are unnamed splines (`assets/anatomy/CORONARY_REPORT.md`).
  Segment-level E4 needs the branch labels and the derived SCCT segments, and the repo holds no label file
  (`atlas_branch_labels.json` is absent; labels live in browser localStorage). See TODO U5.
- **GPU used by headless Chromium:** ANGLE chose the Intel UHD iGPU, not the GTX 1650 Ti (E1b, E5 metadata).
