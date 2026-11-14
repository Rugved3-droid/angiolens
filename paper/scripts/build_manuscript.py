"""Build the IJCARS manuscript (.docx) from paper/manuscript/<source>.md, paper/results/numbers.json and paper/references_provided.bib.

    .venv\\Scripts\\python paper\\scripts\\build_manuscript.py [--src=paper/manuscript/manuscript.md] [--out=paper/submission/manuscript.docx]

Rules enforced (the build FAILS otherwise):
  * every {{key}} must exist in numbers.json (numbers come only from result files);
  * every [@key] must exist in references_provided.bib (no invented references);
  * every figure marker must have a caption and an image file; every table marker a table block.
Output: the .docx (single column, Times New Roman 10 pt, automatic page numbers, figures + captions in the text, Word tables,
equations as native Word (OMML) math), plus <out>.wordcount.json (IJCARS counts everything) and <out>.used.json (numbers,
citations used, for paper/AUDIT.md).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper"
ARGS = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
SRC = ROOT / ARGS.get("src", "paper/manuscript/manuscript.md")
OUT = ROOT / ARGS.get("out", "paper/submission/manuscript.docx")
NUM = json.loads((PAPER / "results" / "numbers.json").read_text(encoding="utf-8"))
FIGDIR = PAPER / "figures"

AUTHORS = "Rugved Parmar^1^ · Md Fahim^1^ · Shreya P. Trivedi^2^"
AFFIL = ["^1^ Department of Medicine, SUNY Downstate Health Sciences University / Kings County Hospital Center, Brooklyn, NY, USA",
         "^2^ Beth Israel Deaconess Medical Center / Harvard Medical School, Boston, MA, USA",
         "Corresponding author: Rugved Parmar, parmarrugved@gmail.com"]

# ---------------------------------------------------------------- bibliography
ACCENTS = {r'{\"o}': "ö", r'{\"u}': "ü", r'{\"a}': "ä", r"{\'e}": "é"}
JABBR = {"British Journal of Cardiology": "Br J Cardiol", "Journal of the American College of Cardiology": "J Am Coll Cardiol",
         "Journal of Research in Science Teaching": "J Res Sci Teach", "The Physics Teacher": "Phys Teach",
         "IEEE Transactions on Medical Imaging": "IEEE Trans Med Imaging", "EuroIntervention": "EuroIntervention",
         "Journal of Interventional Cardiology": "J Interv Cardiol", "IEEE Transactions on Image Processing": "IEEE Trans Image Process"}


def parse_bib(path):
    txt = path.read_text(encoding="utf-8")
    for k, v in ACCENTS.items():
        txt = txt.replace(k, v)
    out = {}
    for m in re.finditer(r"@(\w+)\{([^,]+),", txt):
        typ, key, i = m.group(1).lower(), m.group(2).strip(), m.end()
        depth, j = 1, i
        while depth:
            depth += {"{": 1, "}": -1}.get(txt[j], 0)
            j += 1
        body = txt[i:j - 1]
        fields = {}
        for f in re.finditer(r"(\w+)\s*=\s*\{", body):
            k2, s = f.group(1).lower(), f.end()
            d, e = 1, s
            while d:
                d += {"{": 1, "}": -1}.get(body[e], 0)
                e += 1
            fields[k2] = re.sub(r"\s+", " ", body[s:e - 1]).strip()
        out[key] = {"type": typ, **fields}
    return out


def fmt_authors(a):
    if a.startswith("{") and a.endswith("}"):
        return a.strip("{}")
    names = []
    for n in a.split(" and "):
        last, first = [x.strip() for x in n.split(",", 1)] if "," in n else (n, "")
        initials = "".join(p[0] for p in re.split(r"[\s.\-]+", first) if p)
        names.append(f"{last} {initials}".strip())
    return ", ".join(names)


def fmt_ref(e):
    year = e.get("year", "n.d.")
    au = fmt_authors(e["author"])
    title = e["title"].strip("{}")
    if e["type"] == "article":
        j = JABBR.get(e["journal"], e["journal"])
        pages = e.get("pages", "").replace("--", "–")
        abstract = " [abstract]" if "abstract" in e.get("note", "").lower() else ""
        s = f"{au} ({year}) {title}{abstract}. {j} {e['volume']}:{pages}"
        return s + (f". https://doi.org/{e['doi']}" if e.get("doi") else "")
    url = re.search(r"https?://\S+", e.get("howpublished", ""))
    where = e.get("howpublished", "").split(",")[0].strip() if not e.get("howpublished", "").startswith("http") else ""
    s = f"{au} ({year}) {title}"
    if where:
        s += f". {where}"
    if url:
        s += f". {url.group(0).rstrip('.,')}"
    acc = re.search(r"Accessed (\d{4})-(\d{2})-(\d{2})", e.get("note", ""))
    if acc:
        months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                  "November", "December"]
        s += f". Accessed {int(acc.group(3))} {months[int(acc.group(2)) - 1]} {acc.group(1)}"
    return s


BIB = parse_bib(PAPER / "references_provided.bib")

# ---------------------------------------------------------------- source parsing
src = re.sub(r"<!--.*?-->", "", SRC.read_text(encoding="utf-8"), flags=re.S)
blocks = re.split(r"^# ", src, flags=re.M)
S = {}
for b in blocks:
    if not b.strip():
        continue
    head, _, body = b.partition("\n")
    S[head.strip()] = body.strip()

used_nums, cite_order = {}, []


def resolve_numbers(t):
    def rep(m):
        k = m.group(1)
        if k not in NUM:
            raise SystemExit(f"unknown number key {{{{{k}}}}} in {SRC.name}")
        used_nums[k] = NUM[k]
        return NUM[k]["text"]
    return re.sub(r"\{\{(\w+)\}\}", rep, t)


def compress(ns):
    ns = sorted(set(ns))
    out, i = [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        out.append(f"{ns[i]}–{ns[j]}" if j - i >= 2 else ", ".join(str(x) for x in ns[i:j + 1]))
        i = j + 1
    return ", ".join(out)


def resolve_cites(t):
    def rep(m):
        keys = [k.strip().lstrip("@") for k in m.group(1).split(";")]
        nums = []
        for k in keys:
            if k not in BIB:
                raise SystemExit(f"citation [@{k}] is not in references_provided.bib")
            if k not in cite_order:
                cite_order.append(k)
            nums.append(cite_order.index(k) + 1)
        return f"[{compress(nums)}]"
    return re.sub(r"\[(@[^\]]+)\]", rep, t)


def resolve(t):
    return resolve_cites(resolve_numbers(t))


# ---------------------------------------------------------------- docx helpers
doc = Document()
sec = doc.sections[0]
sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(sec, side, Cm(2.5))
st = doc.styles["Normal"]
st.font.name = "Times New Roman"
st.font.size = Pt(10)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
st.paragraph_format.space_after = Pt(4)
st.paragraph_format.line_spacing = 1.15
for lvl, size in ((1, 12), (2, 11), (3, 10)):
    h = doc.styles[f"Heading {lvl}"]
    h.font.name, h.font.size, h.font.bold, h.font.italic = "Times New Roman", Pt(size), True, False
    h.font.color.rgb = None
    h.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(10), Pt(4)
# automatic page numbers (PAGE field in the footer)
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
fp._p.append(parse_xml(f'<w:fldSimple {nsdecls("w")} w:instr="PAGE"><w:r><w:t>1</w:t></w:r></w:fldSimple>'))

COUNT = {}


def count(bucket, text):
    COUNT[bucket] = COUNT.get(bucket, 0) + len(re.findall(r"\S+", re.sub(r"[\^*]", "", text)))


def add_runs(p, text, size=None, italic=False):
    """**bold** and ^superscript^ markup -> runs."""
    for tok in re.split(r"(\*\*.+?\*\*|\^[^^]+\^)", text):
        if not tok:
            continue
        if tok.startswith("**"):
            r = p.add_run(tok[2:-2]); r.bold = True
        elif tok.startswith("^"):
            r = p.add_run(tok[1:-1]); r.font.superscript = True
        else:
            r = p.add_run(tok)
        if size:
            r.font.size = Pt(size)
        if italic:
            r.italic = True
    return p


def para(text, bucket, size=None, align=None, italic=False):
    t = resolve(text)
    count(bucket, t)
    p = add_runs(doc.add_paragraph(), t, size, italic)
    if align:
        p.alignment = align
    return p


M = 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'


def mr(t, plain=False):
    sty = '<m:rPr><m:sty m:val="p"/></m:rPr>' if plain else ""
    return f"<m:r>{sty}<m:t xml:space=\"preserve\">{t}</m:t></m:r>"


def frac(num, den):
    return f"<m:f><m:num>{num}</m:num><m:den>{den}</m:den></m:f>"


EQS = {
    1: (mr("d") + mr("(α, β) = (", True) + mr("sin α cos β, −cos α cos β, sin β", True) + mr(")", True), "d(α, β) = (sin α cos β, −cos α cos β, sin β)"),
    2: (mr("x") + mr(" = SID ", True) + frac(mr("(") + mr("p") + mr(" − ") + mr("S") + mr(")·") + mr("u"),
                                               mr("(") + mr("p") + mr(" − ") + mr("S") + mr(")·") + mr("d"))
        + mr(",  ", True) + mr("y") + mr(" = SID ", True) + frac(mr("(") + mr("p") + mr(" − ") + mr("S") + mr(")·") + mr("v"),
                                                               mr("(") + mr("p") + mr(" − ") + mr("S") + mr(")·") + mr("d")),
        "x = SID ((p − S)·u)/((p − S)·d), y = SID ((p − S)·v)/((p − S)·d)"),
}


def equation(n, bucket):
    xml, text = EQS[n]
    count(bucket, text)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p._p.append(parse_xml(f"<m:oMathPara {M}><m:oMath>{xml}</m:oMath></m:oMathPara>"))
    p.add_run(f"\t({n})")


CAPS = {}
for line in S.get("CAPTIONS", "").splitlines():
    m = re.match(r"FIG (\d+):\s*(.*?)(\s*Scripts?: .*)?$", line.strip())
    if m:
        CAPS[int(m.group(1))] = (m.group(2).strip(), (m.group(3) or "").strip())


def figure(n):
    png = FIGDIR / f"Fig{n}.png"
    if not png.exists() or n not in CAPS:
        raise SystemExit(f"Fig. {n}: missing image or caption")
    doc.add_paragraph().add_run().add_picture(str(png), width=Cm(16.0))
    cap, script = CAPS[n]
    text = resolve(cap)
    if script:                                                  # IJCARS: no period at the end of the caption
        text = text.rstrip(". ") + f" ({script.replace('Scripts:', 'scripts:').replace('Script:', 'script:')})"
    text = text.rstrip(". ")
    count("captions", text)
    p = add_runs(doc.add_paragraph(), text, size=9)
    p.paragraph_format.space_after = Pt(10)


def table(n):
    blk = S.get(f"TABLE {n}")
    if not blk:
        raise SystemExit(f"Table {n} missing")
    cap = head = foot = None
    rows = []
    for line in blk.splitlines():
        if line.startswith("CAPTION:"):
            cap = line[8:].strip()
        elif line.startswith("HEADER:"):
            head = [c.strip() for c in line[7:].split("|")]
        elif line.startswith("ROW:"):
            rows.append([c.strip() for c in line[4:].split("|")])
        elif line.startswith("FOOT:"):
            foot = line[5:].strip()
    t = resolve(cap)
    count("tables", t)
    p = add_runs(doc.add_paragraph(), t, size=9)
    p.paragraph_format.keep_with_next = True
    tb = doc.add_table(rows=1 + len(rows), cols=len(head))
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    tb.style = doc.styles["Table Grid"]
    for i, row in enumerate([head] + rows):
        for j, cell in enumerate(row):
            c = tb.cell(i, j)
            c.paragraphs[0].text = ""
            txt = resolve(cell)
            count("tables", txt)
            add_runs(c.paragraphs[0], f"**{txt}**" if i == 0 else txt, size=8)
            c.paragraphs[0].paragraph_format.space_after = Pt(0)
    if foot:
        f = resolve(foot)
        count("tables", f)
        add_runs(doc.add_paragraph(), f, size=8).paragraph_format.space_after = Pt(10)


# ---------------------------------------------------------------- document
title = resolve(S["TITLE"])
count("title_authors", title)
tp = doc.add_paragraph()
r = tp.add_run(title); r.bold = True; r.font.size = Pt(14)
count("title_authors", AUTHORS)
add_runs(doc.add_paragraph(), AUTHORS)
for a in AFFIL:
    count("title_authors", a)
    add_runs(doc.add_paragraph(), a, size=9)

h = doc.add_heading("Abstract", level=1); count("abstract", "Abstract")
for line in S["ABSTRACT"].split("\n\n"):
    para(line.strip(), "abstract")
kw = "**Keywords** " + S["KEYWORDS"].strip()
para(kw, "keywords")

bucket = None
BUCKETS = {"1": "introduction", "2": "methods", "3": "results", "4": "discussion", "5": "conclusion"}
for name in [k for k in S if re.match(r"\d ", k)]:
    bucket = BUCKETS[name[0]]
    doc.add_heading(name, level=1); count(bucket, name)
    for chunk in re.split(r"\n\s*\n", S[name]):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("## "):
            first, _, rest = chunk.partition("\n")
            doc.add_heading(first[3:].strip(), level=2); count(bucket, first[3:])
            chunk = rest.strip()
            if not chunk:
                continue
        m = re.fullmatch(r"@@(FIG|TABLE|EQ) (\d+)@@", chunk)
        if m:
            {"FIG": figure, "TABLE": table, "EQ": lambda n: equation(n, bucket)}[m.group(1)](int(m.group(2)))
            continue
        p = para(chunk, bucket)
        p.paragraph_format.first_line_indent = None

if "ONLINE RESOURCES" in S:
    doc.add_heading("Supplementary Information", level=1); count("online_resources", "Supplementary Information")
    for chunk in re.split(r"\n\s*\n", S["ONLINE RESOURCES"]):
        if chunk.strip():
            para(chunk.strip(), "online_resources")

doc.add_heading("Statements and Declarations", level=1); count("statements", "Statements and Declarations")
for chunk in re.split(r"\n\s*\n", S["STATEMENTS"]):
    if chunk.strip():
        para(chunk.strip(), "statements")

doc.add_heading("References", level=1); count("references", "References")
for i, k in enumerate(cite_order, 1):
    t = f"{i}. {fmt_ref(BIB[k])}"
    count("references", t)
    p = doc.add_paragraph(t)
    p.paragraph_format.left_indent = Cm(0.6)
    p.paragraph_format.first_line_indent = Cm(-0.6)
    for r in p.runs:
        r.font.size = Pt(9)

unused = [k for k in BIB if k not in cite_order]
OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
total = sum(COUNT.values())
wc = {"source": str(SRC.relative_to(ROOT)), "total": total, "sections": COUNT,
      "main_text": sum(COUNT.get(k, 0) for k in BUCKETS.values()), "references_cited": len(cite_order),
      "bib_entries_not_cited": unused}
OUT.with_suffix(".wordcount.json").write_text(json.dumps(wc, indent=1), encoding="utf-8")
OUT.with_suffix(".used.json").write_text(json.dumps({"numbers": used_nums, "citations": {k: i + 1 for i, k in enumerate(cite_order)},
                                                       "references": [fmt_ref(BIB[k]) for k in cite_order]}, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps(wc, indent=1))
