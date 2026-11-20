# Open items before clicking submit (Rugved)

Package: `submission/MSE_Innovation/`. Rebuild after any edit to `paper/mse/source/manuscript.md`:
`paper\mse\source\make_package.cmd` (or `make make_package`). Every placeholder is highlighted yellow in the .docx files, and
`paper/mse/AUDIT.md` section 6 lists them.

## Must do

1. **Confirm the Innovation limits in Editorial Manager.** The package has 1,426 main-text words, a 187-word abstract, a
   47-word short abstract (`abstract_short.txt`), and 3 figures or tables in total. Paste whichever abstract the system asks for.
2. **Fill in the teaching-session facts** (manuscript, "How It Was Implemented"): the institution and setting, the month and
   year, the duration, which author ran it, the equipment, and whether the Predict sequence described is what actually happened.
   Describe it only; add no numbers about residents' answers.
3. **Write the two author-observation sentences** (manuscript, "What We Learned", second and third lessons): how Predict items
   worked as discussion prompts, and what confused people at the interface level. These must be your own observations. Use no
   scores, counts, percentages or resident quotes. The scan in `build_package.py` fails the build on such terms.
4. **Authors and affiliations (title page):**
   - Dr. Budzikowski: division, department, institution, city, country, email and ORCID.
   - Md Fahim: ORCID.
   - Confirm that "MD" is correct for you. The IJCARS title page said "MBBS".
5. **Dr. Trivedi.** Confirm with her whether she wants to be acknowledged, then either keep the sentence in the title-page
   Acknowledgments or delete it. She is named nowhere else.
6. **Suggested reviewers.** The cover letter has three placeholders. Each needs to be an independent expert with an
   institutional email and no connection to the work or the authors.
7. **Funding and competing interests.** Both statements are marked [VERIFY].
8. **Author contributions (CRediT).** The roles are marked [VERIFY], and every author must approve them.
9. **Every author's approval** of the final manuscript and the submission. This is also a [VERIFY] in the cover letter.
10. **AI disclosure.** Confirm that Claude Code with Claude Opus 5.5 is the only AI tool used for the software and for the
    text. The git history shows only Claude Opus 5.5, but earlier drafts (for example the Medical Teacher version, and any
    use of ChatGPT, Codex or another tool) may have involved others. Edit both [VERIFY] markers on AI use.
11. **Date** the cover letter.
12. **Resolve every remaining `[VERIFY]` and `[AUTHOR INPUT]`**, rebuild, and confirm that `paper/mse/AUDIT.md` section 6 is empty.

## Worth a look

- **Reference correction.** Your brief cited "Vidovich MI et al." for Cardiovasc Revasc Med 2016;17:102-105. Crossref and
  PubMed give the first author as **Casey DB** (Casey DB, Stewart D, Vidovich MI; PMID 26811001), and the reference list uses
  that. PMID 26198625 is Schimmel DR et al., doi:10.1002/ccd.26089.
- **Lee 2022.** The abstract does not name its simulator, so the manuscript says "dedicated high-fidelity simulators" and
  does not call Lee's simulator commercial. Lee discloses consulting for Mentice, and Casey 2016 used AngioMentor.
- **Code citation.** Tag `v1.1` does not exist (it was deleted because it clashed with branch `v1.1`). The paper cites
  `v1.1-ijcars` = `198c6d4da1f980cdaa301f5131ccb83ebffb5be1`, the same commit as branch `v1.1`, and no new tag was created.
  The verification outputs are not in that tag; they are on branch `paper/ijcars-verification` (`ab82d63…`), whose
  app code is identical. Data availability says so.
- **No hosted demo.** Learners need no installation only if someone serves the static build. To adopt AngioLens, a program
  must build the atlas meshes once from Z-Anatomy with Blender. A public hosted build (GitHub Pages, for example) would make
  "runs in any browser" true for readers. Consider adding one and citing its URL.
- **Fig. 1a** is a v1.0-era screenshot (2026-10-04; its toolbar says "Left coronary" where v1.1 says "LCA"). Recapture it
  from `v1.1-ijcars` if you want both panels from the same release.
- **Licence of the figures.** Fig. 1, Fig. 2 and ESM_1 show Z-Anatomy renders (CC BY-SA 4.0), credited in the captions and
  the acknowledgments. Confirm that MSE's licence-to-publish, or its open-access option, is compatible with share-alike.
- **ESM_1.mp4** is the trimmed IJCARS video (3:40). Its retained narration includes "instead of just getting a score, the
  learner can actually see which axis they're consistently getting backwards". That describes the feature and reports no data,
  but cut it if you want zero mention of scores. **Check the YouTube upload** (https://youtu.be/Bb-A4pW2P1M), which I could not
  inspect. If it is the untrimmed `D:/angiolens-video/AngioLens_tour.mp4`, it contains the older numbers card and the
  outcome-flavoured closing lines ("should be measurable" and "something you actually understand"). In that case, drop the link
  from Online Resource 1 or replace the upload with the trimmed cut.
- **Study mode.** The manuscript mentions it only as a feature meant for a future evaluation. Any resident data collected
  earlier must stay out of this paper.
- **The earlier resident quiz.** The repository holds no resident data, CSV exports or scores, so there was nothing to
  exclude.
