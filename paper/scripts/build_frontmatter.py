"""title_page.docx and cover_letter.docx for the IJCARS submission.

    .venv\\Scripts\\python paper\\scripts\\build_frontmatter.py

The total word count in the cover letter is read from paper/submission/manuscript.wordcount.json (written by build_manuscript.py).
"""
import json
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ROOT = Path(__file__).resolve().parents[2]
SUB = ROOT / "paper" / "submission"
WC = json.loads((SUB / "manuscript.wordcount.json").read_text(encoding="utf-8"))
TITLE = "AngioLens: an open-source, geometry-verified coronary angiography projection simulator for training"
REPO = "https://github.com/Rugved3-droid/angiolens"
COMMIT = "198c6d4da1f980cdaa301f5131ccb83ebffb5be1"


def new_doc():
    d = Document()
    s = d.sections[0]
    s.page_height, s.page_width = Cm(29.7), Cm(21.0)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(s, side, Cm(2.5))
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Times New Roman", Pt(11)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    st.paragraph_format.space_after = Pt(6)
    return d


def p(d, text, bold=False, size=None, sup_marks=True):
    par = d.add_paragraph()
    import re
    for tok in re.split(r"(\^[^^]+\^)", text):
        if not tok:
            continue
        r = par.add_run(tok[1:-1] if tok.startswith("^") else tok)
        r.font.superscript = tok.startswith("^")
        r.bold = bold
        if size:
            r.font.size = Pt(size)
    return par


# ---------------- title page ----------------
d = new_doc()
p(d, "Title page", bold=True, size=10)
p(d, TITLE, bold=True, size=14)
p(d, "Rugved Parmar, MD^1^ (corresponding author) · Md Fahim, MD^1^ · Shreya P. Trivedi, MD^2^")
p(d, "^1^ Department of Medicine, SUNY Downstate Health Sciences University / Kings County Hospital Center, Brooklyn, NY, USA")
p(d, "^2^ Beth Israel Deaconess Medical Center / Harvard Medical School, Boston, MA, USA")
p(d, "Corresponding author: Rugved Parmar, parmarrugved@gmail.com", bold=True)
p(d, "ORCID", bold=True)
for n in ("Rugved Parmar", "Md Fahim", "Shreya P. Trivedi"):
    p(d, f"{n}: [ORCID placeholder 0000-0000-0000-0000]")
p(d, "Acknowledgments", bold=True)
p(d, "The anatomy used in AngioLens and in all figures is the Z-Anatomy open atlas (Models of human anatomy, "
     "https://github.com/Z-Anatomy/Models-of-human-anatomy), licensed under CC BY-SA 4.0, which includes models derived from "
     "BodyParts3D (The Database Center for Life Science, CC BY-SA 2.1 Japan). We thank the Z-Anatomy and BodyParts3D authors "
     "for making their work openly available.")
p(d, "Author contributions (CRediT)", bold=True)
p(d, "Rugved Parmar: conceptualization, software, methodology, formal analysis, visualization, writing – original draft. "
     "Md Fahim: software review, validation, writing – review and editing. "
     "Shreya P. Trivedi: supervision, writing – review and editing.")
p(d, "Code availability", bold=True)
p(d, f"{REPO} (MIT licence), release tag v1.1, commit {COMMIT}.")
d.save(SUB / "title_page.docx")

# ---------------- cover letter ----------------
d = new_doc()
for line in ("[Date]", "", "The Editors", "International Journal of Computer Assisted Radiology and Surgery"):
    p(d, line)
p(d, "Dear Editors,")
p(d, f"We submit our manuscript “{TITLE}” for consideration as an Original Article in the International Journal of "
     "Computer Assisted Radiology and Surgery.")
p(d, "AngioLens is an open-source, browser-based coronary angiography projection simulator. Its contribution is not a new "
     "feature set but a verifiable one: the C-arm projection conventions are specified explicitly and tested against an "
     "independent first-principles derivation, with mirrored and sign-swapped renders as negative controls that the tests must "
     "reject; the rendered images are compared with an exact reference renderer over the full angle range; and the quiz "
     "distractors, which encode LAO/RAO, cranial/caudal and mirror errors, are verified to be the "
     "transformations they are labelled as. The work fits the journal's scope in simulation, education and training, and in "
     "validation methods for computer-assisted systems. It reports software verification only: no human participants, no "
     "learner data and no claims of educational effectiveness.")
p(d, f"Total word count (title, authors, abstract, main text, figure captions, tables, statements and references, as counted by "
     f"the journal's rule): {WC['total']:,} words. The manuscript has 5 figures, 2 tables and {WC['references_cited']} references, "
     "and two Online Resources (a demonstration video and the full verification tables).")
p(d, "This manuscript has not been published and is not under consideration for publication elsewhere. All authors approved "
     "the submission.")
p(d, "Reuse of material: the application screenshots and renders in the figures and in Online Resource 1 were produced by the "
     "authors with their own software. The anatomy shown is from the Z-Anatomy atlas (CC BY-SA 4.0), attributed in the captions "
     "and acknowledgments.")
p(d, f"Code and all verification scripts are openly available at {REPO} (release tag v1.1, commit {COMMIT}).")
p(d, "Suggested independent reviewers", bold=True)
for k in (1, 2, 3):
    p(d, f"{k}. [Name], [Position], [Institution], [institutional e-mail], [expertise relevant to this work]")
p(d, "Sincerely,")
p(d, "Rugved Parmar, MD, on behalf of all authors")
p(d, "Department of Medicine, SUNY Downstate Health Sciences University / Kings County Hospital Center, Brooklyn, NY, USA")
p(d, "parmarrugved@gmail.com")
d.save(SUB / "cover_letter.docx")
print("title_page.docx, cover_letter.docx written; total words", WC["total"])
