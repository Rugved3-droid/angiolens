# Submission checklist: Medical Science Educator, Innovation

Checked 2026-11-20 against the generated package (`submission/MSE_Innovation/`). The automatic checks come from
`paper/mse/AUDIT.md` sections 4-5, and the docx files were also rendered with Word and inspected page by page.
✅ = done. All items are done.

## Article type and structure

- ✅ Article type stated as Innovation in the manuscript, title page and cover letter.
- ✅ Structure follows the Innovation model: The Problem, What Was Created, How It Was Implemented, What We Learned, Why It
  Is Useful to Others.
- ✅ Title is concise and keeps "open-source" and "coronary angiography".
- ✅ Abstract is 187 words (150-200), with no references and no abbreviations.
- ✅ Short abstract is 47 words (≤ 50), in `abstract_short.txt`.
- ✅ Five keywords.
- ✅ Main text is 1,500 words (target about 1,500).
- ✅ Both abstract lengths are supplied (187 and 47 words); paste whichever Editorial Manager asks for.
- ✅ Three figures or tables in total (Fig. 1, Fig. 2, Table 1).
- ✅ At most three heading levels; only level 1 is used, plus run-in bold headings.
- ✅ Every abbreviation is defined at first use (3D, LAO, RAO, DICOM, AP, AI).
- ✅ The abstract uses none of them.

## Formatting

- ✅ Word .docx.
- ✅ Times New Roman 10 pt on every run (automatic check).
- ✅ Automatic page numbers (PAGE field in the footer).
- ✅ No field functions in the body.
- ✅ Indents use paragraph formatting, not spaces (hanging indent in the reference list).
- ✅ Table 1 is built with the Word table function.
- ✅ No footnotes needed; no endnotes part.
- ✅ References are numbered in square brackets in order of first citation, with ranges such as [10, 11].
- ✅ Reference list in MSE style, with ISO 4 abbreviations and a full DOI link wherever one exists.
- ✅ Only published work is cited: 13 references (journal articles and abstracts, a standard, an app and the atlas repository).
- ✅ Manuscript is anonymous; names and affiliations are on the title page only.

## Figures

- ✅ Figures are embedded in the manuscript body and also supplied as `Fig1.tif` and `Fig2.tif`.
- ✅ Both are RGB at 300 dpi (screenshots; there is no combination art, so the 600 dpi rule does not apply).
- ✅ Width 174 mm; height 207 and 198 mm, within the page.
- ✅ Panel letters are Arial Bold 11 pt, and there are no titles inside the images.
- ✅ Meaning does not rely on colour alone: Fig. 2b has text labels and "Correct." in text.
- ✅ Captions follow the format "**Fig. 1** caption", with no punctuation after the number or at the end (automatic check).
- ✅ Third-party anatomy is credited in every caption (Z-Anatomy CC BY-SA 4.0 / BodyParts3D).
- ✅ `ESM_1.mp4` is rebuilt for MSE (title card; score narration and record panel cut; flash check passed) and listed as Online Resource 1.

## Statements and Declarations (placed before the references)

- ✅ Funding, competing interests, ethics, consent to participate, consent to publish, data, code, author contributions and
  AI disclosure are all present.
- ✅ Funding and competing-interest statements final.
- ✅ CRediT roles final.
- ✅ Ethics statement: no human-participant data reported; the ASOCA public de-identified dataset sentence is included,
  because the optional CT case and the study mode use it.
- ✅ Code availability gives the GitHub URL, tag `v1.1-ijcars`, the full commit hash and the MIT licence (OSI-approved).
- ✅ AI use is documented in the Methods-equivalent section ("What Was Created"), naming the tool, model, purpose and author
  oversight.
- ✅ AI disclosure statement names the tool and model, its purpose, the sections it touched, author responsibility and reference
  checking.
- ✅ AI tool list final (Claude Code, Claude Opus 5.5).

## Hard rules

- ✅ Rule 1, no learner outcome data. The scan passed: 2 hits, both explained (the mandated ethics sentence and a cited
  title). Figures were inspected, and the ESM narration was checked.
- ✅ Rule 2, no fabricated numbers. Every result number comes through `numbers.json` and is traced in AUDIT section 1.
  Literal design constants are listed with their sources.
- ✅ Rule 3, no invented references. All 13 were verified (Crossref, PubMed or the cited page), and no [CITE NEEDED] remains.
- ✅ Rule 4, no invented people. Only author-supplied names and emails are used; reviewers and the missing ORCIDs are omitted.
- ✅ Rule 5, software unchanged. There is no diff in `web/`, `preprocess/` or `tests/` against `v1.1-ijcars`.
- ✅ Rule 6, branch `paper/mse-innovation`, not merged to main.

## Package

- ✅ `manuscript.docx`, `title_page.docx`, `cover_letter.docx`, `Fig1.tif`, `Fig2.tif`, `ESM_1.mp4`, `abstract_short.txt`
  and `word_count.txt`.
- ✅ One command rebuilds everything: `paper\mse\source\make_package.cmd` or `make make_package`.
- ✅ Cover letter: Innovation type, pitch, word count, not under consideration elsewhere, and the AI line.
- ✅ No reviewer placeholders; enter reviewers in Editorial Manager.
- ✅ Author details complete: emails and affiliations for all three; ORCID given for the corresponding author.
- ✅ Teaching session described (October 2026, SUNY Downstate / Kings County).
- ✅ No placeholders anywhere; the build fails if one returns.
