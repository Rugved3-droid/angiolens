# Open items for the author (Rugved)

Status, 2026-11-14: Phases 0-5 are complete and the submission package is in `paper/submission/`. The full trace is in
`paper/AUDIT.md`.

## Must do by hand before submitting

1. **ORCID iDs** for all three authors. The title page has placeholders.
2. **Three suggested reviewers** in `cover_letter.docx`: name, institution, institutional e-mail and expertise. Also fill in the
   **date**.
3. **ESM_1.mp4.** It is built from `D:\angiolens-video\AngioLens_tour.mp4` plus a title card. Watch it once. Two items:
   - The tour shows an older on-screen card: "six standard views · correlation r = 1.000" and "mirrors r ≤ 0.13". These come from
     the repo's 6-pose e2e test, not from this paper; across the full grid the mirrored r reaches 0.531.
   - It ends with "From something you have to memorize to something you actually understand", which implies a learning benefit.

   Re-record or trim if you want the video to match the paper's claims exactly. The photosensitivity check passed (max 1 flash/s).
4. **[CITE NEEDED] display convention.** Methods 2.2 and the Discussion state the angiographic display convention without a
   reference: the image is seen from the detector, so patient left is on the image right at AP. Supply a citation or accept it as a
   stated design choice.
5. **[CITE NEEDED] "named-view angles vary in practice"** (Methods 2.4). Green 2016 likely supports it, but its view tables are
   images that could not be read. Please confirm.
6. **Table 1.** AngioAID 3D and the 3D-printing abstract are described from their titles only: jacc.org returned HTTP 403. If you
   have the abstracts, upgrade NR cells only where the abstract documents the feature.
7. **Licence-to-publish.** Fig. 2, Fig. 5a-d and ESM_1 show Z-Anatomy renders (CC BY-SA 4.0). Confirm the journal's licence
   (or its open-access option) is compatible with share-alike for these figures.
8. **AngioView.** The App Store description (seller Annas Rahman) describes features very close to AngioLens: a 3D simulator,
   C-arm drag, standard views and segment names. The paper positions it neutrally. Make sure that is the framing you want.

## Resolved by the author's decisions (2026-11-14)

- **Version:** v1.1 is described. Tag `v1.1` → `198c6d4`.
- **Study mode:** one sentence, no learner data.
- **Spider view:** LAO 40/CAUD 30 is primary; classic LAO 45/CAUD 30 is mentioned.
- **E4:** dropped and listed as future work. No E4 outputs existed, so no `wip/e4` branch was needed.
- **ASOCA:** removed. The ethics text is "did not involve human participants, human data, or animals".
- **E2:** the second phantom was run and both phantoms are reported.
- **SSIM:** in Online Resource 2, with one main-text sentence.
- **Tile mismatch:** investigated and attributed to GPU nondeterminism.
- **E5:** rerun with cold loads, including the NVIDIA run.
- **Code citation:** GitHub URL + tag + commit only, no archive DOI.
- **References:** every entry was verified (Crossref and publisher pages). Added: DICOM PS3.3, Dumay 1994, Chen & Carroll 2000,
  Jensen 2016, Voelker 2016 and Wang 2004.

## Notes

- **Tag/branch name clash.** The tag `v1.1` and the branch `v1.1` have the same name. GitHub resolves both, but locally
  `git checkout v1.1` is ambiguous; use `git checkout tags/v1.1`.
- **Machine RAM.** This machine (12 GB RAM) ran out of memory once when experiments overlapped. `make paper` runs them in sequence.
