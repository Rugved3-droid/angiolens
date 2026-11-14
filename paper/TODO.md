# Open items for the author (Rugved)

Status, 2026-11-14 (finalize pass): the submission package in `paper/submission/` is final. Full trace: `paper/AUDIT.md`.
No placeholders remain (ORCIDs, date, funding and competing-interest statements are filled; the suggested-reviewer section was
removed from the cover letter; no [CITE NEEDED] remains).

## Still worth a look before submitting

1. **Table 1.** AngioAID 3D and the 3D-printing abstract are described from their titles only (jacc.org returned HTTP 403). If
   you have the abstracts, upgrade NR cells only where the abstract documents the feature.
2. **Licence-to-publish.** Fig. 2, Fig. 5a-d and ESM_1 show Z-Anatomy renders (CC BY-SA 4.0). Each carries the credit
   "Rendered from Z-Anatomy models (CC BY-SA 4.0), derived from BodyParts3D (DBCLS)" and the cover letter tells the editor.
   Confirm the journal's licence (or its open-access option) is compatible with share-alike.
3. **AngioView** is positioned neutrally in the paper; make sure that is the framing you want.
4. **ESM_1** (3:40). Trimmed copy of `D:/angiolens-video/AngioLens_tour.mp4` (original untouched). Source segments cut:
   178.0-184.0 s ("understanding ... should be measurable"), 213.5-237.0 s (overlay card with the older 6-pose numbers
   r = 1.000 / mirrors r <= 0.13) and 243.6-254.6 s (closing tagline "from something you have to memorize to something you
   actually understand" and "Thank you"). Retained narration describes design intent ("this is the part I really wish I had
   as a trainee"; "instead of just memorizing ... you can actually see the three-dimensional reason") but makes no outcome claim.

## Resolved

- Display convention: stated as AngioLens's own convention (Methods 2.2, Discussion); E2 tests that the app follows it.
- "Named-view angles vary in practice": deleted.
- Code citation: https://github.com/Rugved3-droid/angiolens, tag `v1.1-ijcars`, commit 198c6d4da1f980cdaa301f5131ccb83ebffb5be1.
  The old tag `v1.1` was deleted locally and on GitHub (it clashed with the branch `v1.1`, which is unchanged).
- Authors: Rugved Parmar, MBBS; Md Fahim, MD; Shreya P. Trivedi, MD; ORCIDs on the title page and in CITATION.cff.
- Earlier decisions (v1.1, study mode, spider view, E4 dropped, ASOCA removed, E2 second phantom, SSIM in ESM_2, tile
  mismatch, E5 cold rerun, references verified): see git history of this file.

## Notes

- `make paper` reruns every experiment; the finalize pass rebuilt figures and documents from the committed results
  (`--skip=e1,e1b,e2,e2v2,e3,e3m,probe,e5,capture`) because no experiment changed.
- `paper/submission/AngioLens_coauthor_review.pdf` (title page + manuscript + ESM_2) is for co-authors; do not upload it.
- Machine RAM: 12 GB; run experiments one at a time (`make paper` does).
