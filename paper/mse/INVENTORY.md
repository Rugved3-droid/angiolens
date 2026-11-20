# Phase 0 inventory: AngioLens -> Medical Science Educator (Innovation)

Taken 2026-11-20 on branch `paper/mse-innovation`, created from `paper/ijcars-verification` at `ab82d63`.
No simulator code (`web/src/`, `preprocess/`) is changed on this branch.

## Code identity

- Remote: `origin https://github.com/Rugved3-droid/angiolens.git`.
- **Tag `v1.1` does not exist.** `paper/TODO.md` records that it was deleted locally and on GitHub because it clashed with the branch `v1.1`.
  The IJCARS work cites tag **`v1.1-ijcars`**, which points to commit **`198c6d4da1f980cdaa301f5131ccb83ebffb5be1`**. That is also the
  head of branch `v1.1`. This package cites `v1.1-ijcars` and that commit. No new tag was created.
- Licence: MIT (`LICENSE`), which is OSI-approved. Third-party anatomy assets are not in the repository (README line 259).

## Earlier manuscripts (reused, not resubmitted)

| Draft | Where | Use here |
|---|---|---|
| Medical Teacher "New Wave" (2026-10-22) | `D:\AngiolensMT.docx` (= `D:\AngioLens_Medical_Teacher_New_Wave_Final.docx`), cover `D:\AngioLensCovermt.docx`; outside the repo | Narrative and lessons framing; Fig. 1/2 screenshots (`out/manuscript/*.png`). It contains **no learner scores**. |
| IJCARS Original Article (submitted 2026-11-14) | `paper/manuscript/manuscript.md`, `paper/submission/` | Verification results (numbers registry), verified references, ESM_1.mp4 |
| Supervisor copy | `D:\Supervisor_papers\AngioLens_manuscript_for_supervisor.docx` | Same as the IJCARS text |

Both earlier drafts list Dr. Shreya P. Trivedi as an author. This package does not.

## Verification results and tests

- `paper/results/numbers.json` is the number registry. It is written by `paper/scripts/build_numbers.py` from result files only.
  `paper/AUDIT.md` traces every key to its file and field. The experiments are E1, E1b, E2 (two phantoms), E3 and E5, all present
  with raw outputs.
- **Test suite, rerun 2026-11-20 on this branch:** `cd web && npm run verify` gives **ALL GREEN (6.3 min), 15 of 15 steps**.
  pytest **393 passed**; typecheck pass; vitest **65 passed (7 files)**; 11 of 11 e2e suites (phantom, atlas_xray,
  atlas_label, predict, atlas_v1, interaction, metrics, segments, study, shadow, peel); build pass. The counts are identical
  to the 2026-11-14 values in `numbers.json`.

## Figures, screenshots, video

- `out/manuscript/`: four app screenshots (3840x2160, 2026-10-22): a split 3D/projection view at RAO caudal and at spider,
  and a Predict question before and after answering. They are used for MSE Fig. 1b and Fig. 2.
- `out/review/v1/1920_s4_xray_room.png` (1920x1080, 2026-10-04): a room view with the C-arm, translucent patient and detector
  image at RAO caudal. It is used for MSE Fig. 1a.
- `paper/figures/Fig1-5.tif`: the IJCARS figures. These are technical, so MSE replaces them with a verification table.
- `paper/submission/ESM_1.mp4` (3:40): a trimmed copy of the narrated tour. Trimming removed the older numbers card and the outcome-flavoured
  closing lines (see `paper/TODO.md`). It is reused as MSE `ESM_1.mp4`. The public demo is https://youtu.be/Bb-A4pW2P1M.

## References

- `paper/references_provided.bib` has 13 entries, verified on 2026-11-14 against Crossref and publisher pages.
- New entries were verified on 2026-11-20 against Crossref and PubMed:
  - Lee 2022: PMID 36028807, verified as given.
  - Schimmel 2016: PMID 26198625, doi:10.1002/ccd.26089.
  - Casey 2016 (Cardiovasc Revasc Med 17:102-105; PMID 26811001): **the first author is Casey DB, not Vidovich MI.**
    Vidovich is the senior (last) author.
  - The two ASOCA papers: Gharleghi 2022 and 2023.

## Constraints found

- **Learner data:** the repo holds no resident quiz data, CSV exports or score tables. Study-session records live only in
  browser localStorage, so none are in git. `web/study.html` (a study mode) exists as a feature and is not reported on.
- **ASOCA** (a de-identified public coronary CT angiography dataset, licence-gated, not redistributed) is used by the
  optional CT case and by the study mode. It is therefore cited.
- **AI tools in the repo history:** all 24 co-authored commits carry `Co-Authored-By: Claude Opus 5.5`, using Claude Code
  (Anthropic). No other assistant appears in the history or the README.
- **Teaching session:** the repo has no record of the session's date, format or size. Those facts are author inputs (see OPEN_ITEMS).

Decision: the verification results and the test suite are present and passing, so the work continues to Phase 1 without stopping.
