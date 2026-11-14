"""paper/submission/AngioLens_coauthor_review.pdf: title page + manuscript + Online Resource 2, for co-author review (not uploaded).

    .venv\\Scripts\\python paper\\scripts\\build_review_pdf.py

The two .docx files are converted with Microsoft Word (docx2pdf.ps1, COM automation) and merged with PyMuPDF.
"""
import subprocess
from pathlib import Path

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[2]
SUB = ROOT / "paper" / "submission"
TMP = ROOT / "paper" / "results" / "raw"
TMP.mkdir(parents=True, exist_ok=True)
OUT = SUB / "AngioLens_coauthor_review.pdf"

parts = []
for name in ("title_page", "manuscript"):
    pdf = TMP / f"review_{name}.pdf"
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "paper" / "scripts" / "docx2pdf.ps1"),
                    str(SUB / f"{name}.docx"), str(pdf)], check=True)
    parts.append(pdf)
parts.append(SUB / "ESM_2.pdf")

doc = fitz.open()
toc = []
for pdf, label in zip(parts, ("Title page", "Manuscript", "Online Resource 2 (ESM_2)")):
    src = fitz.open(pdf)
    toc.append([1, label, doc.page_count + 1])
    doc.insert_pdf(src)
doc.set_toc(toc)
doc.set_metadata({"title": "AngioLens - co-author review copy", "author": "Rugved Parmar, Md Fahim, Shreya P. Trivedi"})
doc.save(OUT, garbage=3, deflate=True)
print(f"{OUT.name}: {doc.page_count} pages ({', '.join(f'{t[1]} p{t[2]}' for t in toc)})")
