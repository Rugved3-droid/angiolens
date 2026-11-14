# Code changes made for the paper

None. Phase 1 changed no file in `web/src/`, `web/index.html`, `web/atlas.html` or `preprocess/`. All measurements are harnesses
in `paper/scripts/` that load the unmodified app modules and pages.

Generated, git-ignored inputs that the harnesses create:
- `web/public/cases/e2_orient/`: the synthetic E2 phantom, loaded through the classic app's existing `?case=` parameter.
