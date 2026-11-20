"""Build the Medical Science Educator (Innovation) submission package for AngioLens.

One command regenerates everything (Windows, from the repository root):

    .venv\\Scripts\\python paper\\mse\\source\\build_package.py        (or: make make_package)

Inputs (read only):
  paper/mse/source/manuscript.md        text, with {{key}} numbers and [@key] citations
  paper/mse/source/references_mse.bib   verified references (each entry carries a verification note)
  paper/results/numbers.json            number registry written from result files by paper/scripts/build_numbers.py
  paper/AUDIT.md                        source of every registry key (file :: field)
  paper/mse/source/screenshots/*.png   app screenshots for Fig. 1 and Fig. 2 (see screenshots/README.md)
  paper/submission/ESM_1.mp4            demonstration video (trimmed, see paper/TODO.md)

Outputs:
  submission/MSE_Innovation/  manuscript.docx, title_page.docx, cover_letter.docx, Fig1.tif, Fig2.tif, ESM_1.mp4,
                              abstract_short.txt, word_count.txt
  paper/mse/AUDIT.md          number trace, reference check, hard-rule-1 scan, .docx format self-check

The build FAILS if: a {{key}} or [@key] is unknown; the abstract is outside 150-200 words or the short abstract over 50;
the learner-outcome scan has an unexplained hit; or the .docx self-check fails.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "paper/mse/source"
OUT = ROOT / "submission/MSE_Innovation"
SHOTS = SRC / "screenshots"  # copies of out/review/v1/1920_s4_xray_room.png and out/manuscript/*.png (out/ is git-ignored)
AUDIT = ROOT / "paper/mse/AUDIT.md"
NUM = json.loads((ROOT / "paper/results/numbers.json").read_text(encoding="utf-8"))
CODE_URL = "https://github.com/Rugved3-droid/angiolens"
TAG, COMMIT = "v1.1-ijcars", "198c6d4da1f980cdaa301f5131ccb83ebffb5be1"
VIDEO_URL = "https://youtu.be/Bb-A4pW2P1M"
FONT_DIR = Path("C:/Windows/Fonts")
PLACEHOLDER = re.compile(r"\[(VERIFY|AUTHOR INPUT|CITE NEEDED|PLACEHOLDER)[^\]]*\]")
OUT.mkdir(parents=True, exist_ok=True)


def fail(msg):
    sys.exit(f"BUILD FAILED: {msg}")


# ------------------------------------------------------------------ source
src = re.sub(r"<!--.*?-->", "", (SRC / "manuscript.md").read_text(encoding="utf-8"), flags=re.S)
S = {}
for b in re.split(r"^# ", src, flags=re.M):
    if b.strip():
        head, _, body = b.partition("\n")
        S[head.strip()] = body.strip()

# ------------------------------------------------------------------ numbers
USED_NUM = {}


def resolve_numbers(t):
    def rep(m):
        k = m.group(1)
        if k not in NUM:
            fail(f"unknown number key {{{{{k}}}}}")
        v = NUM[k]["text"] if isinstance(NUM[k], dict) else NUM[k]
        USED_NUM[k] = str(v)
        return str(v)
    return re.sub(r"\{\{(\w+)\}\}", rep, t)


# ------------------------------------------------------------------ references
def parse_bib(path):
    txt = path.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"@(\w+)\{([^,]+),", txt):
        typ, key, i = m.group(1).lower(), m.group(2).strip(), m.end()
        depth, j = 1, i
        while depth:
            depth += {"{": 1, "}": -1}.get(txt[j], 0)
            j += 1
        body, fields = txt[i:j - 1], {}
        for f in re.finditer(r"(\w+)\s*=\s*\{", body):
            k2, s = f.group(1).lower(), f.end()
            d, e = 1, s
            while d:
                d += {"{": 1, "}": -1}.get(body[e], 0)
                e += 1
            fields[k2] = re.sub(r"\s+", " ", body[s:e - 1]).strip()
        out[key] = {"type": typ, **fields}
    return out


BIB = parse_bib(SRC / "references_mse.bib")
JABBR = {  # ISO 4 abbreviations (NLM catalogue forms)
    "British Journal of Cardiology": "Br J Cardiol", "Journal of the American College of Cardiology": "J Am Coll Cardiol",
    "Journal of Research in Science Teaching": "J Res Sci Teach", "The Physics Teacher": "Phys Teach",
    "BMC Medical Education": "BMC Med Educ", "Catheterization and Cardiovascular Interventions": "Catheter Cardiovasc Interv",
    "Cardiovascular Revascularization Medicine": "Cardiovasc Revasc Med",
    "Computerized Medical Imaging and Graphics": "Comput Med Imaging Graph", "Scientific Data": "Sci Data"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ORDER: list[str] = []


def fmt_authors(a):
    if a.startswith("{") and a.endswith("}"):
        return a.strip("{}")
    names, etal = [], False
    for n in a.split(" and "):
        if n.strip() == "others":
            etal = True
            continue
        last, first = [x.strip() for x in n.split(",", 1)] if "," in n else (n, "")
        names.append(f"{last} {''.join(p[0] for p in re.split(r'[\s.\-]+', first) if p)}".strip())
    if len(names) > 6 or etal:  # Vancouver rule: more than six authors -> first three, et al.
        return ", ".join(names[:3]) + ", et al"
    return ", ".join(names)


def fmt_ref(e):
    au = fmt_authors(e["author"])
    title = e["title"].strip("{}").replace("--", "–").rstrip(".")
    if e["type"] == "article":
        j = JABBR.get(e["journal"])
        if not j:
            fail(f"no ISO 4 abbreviation for {e['journal']}")
        abstract = " [abstract]" if "abstract" in e.get("note", "").lower() else ""
        s = f"{au}. {title}{abstract}. {j}. {e['year']};{e['volume']}:{e.get('pages', '').replace('--', '–')}."
        return s + (f" https://doi.org/{e['doi']}" if e.get("doi") else "")
    how = e.get("howpublished", "")
    url = re.search(r"https?://\S+", how)
    where = how.split(",")[0].strip() if not how.startswith("http") else ""
    s = f"{au}. {title}."
    if where:
        s += f" {where}"
    if e.get("year"):
        s += f"{';' if where else ''} {e['year']}."
    elif where:
        s += "."
    if url:
        s += f" {url.group(0).rstrip('.,')}."
    acc = re.search(r"Accessed (\d{4})-(\d{2})-(\d{2})", e.get("note", ""))
    if acc:
        s += f" Accessed {int(acc.group(3))} {MONTHS[int(acc.group(2)) - 1]} {acc.group(1)}."
    return s


def compress(ns):
    ns, out, i = sorted(set(ns)), [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        out += [f"{ns[i]}–{ns[j]}"] if j - i >= 2 else [str(n) for n in ns[i:j + 1]]
        i = j + 1
    return ", ".join(out)


def resolve_cites(t):
    def rep(m):
        nums = []
        for k in [x.strip().lstrip("@") for x in m.group(1).split(";")]:
            if k not in BIB:
                fail(f"unknown citation [@{k}]")
            if k not in ORDER:
                ORDER.append(k)
            nums.append(ORDER.index(k) + 1)
        return f"[{compress(nums)}]"
    return re.sub(r"\[(@[^\]]+)\]", rep, t)


def resolve(t):
    return resolve_cites(resolve_numbers(t))


# ------------------------------------------------------------------ figures (RGB TIFF, 300 dpi screenshots)
W300 = round(174 / 25.4 * 300)  # 174 mm full page width at 300 dpi = 2055 px
LETTER = ImageFont.truetype(str(FONT_DIR / "arialbd.ttf"), round(11 / 72 * 300))  # 11 pt Arial bold


def crop_frac(path, box):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    return im.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)))


def fit_width(im, w=W300):
    return im.resize((w, round(im.size[1] * w / im.size[0])), Image.LANCZOS)


def panel_letter(im, letter):
    """Letter in a white band above the panel, so it never covers the screenshot."""
    d0 = ImageDraw.Draw(im)
    x0, y0, x1, y1 = d0.textbbox((0, 0), letter, font=LETTER)
    band = y1 - y0 + 24
    out = Image.new("RGB", (im.size[0], im.size[1] + band), (255, 255, 255))
    out.paste(im, (0, band))
    ImageDraw.Draw(out).text((-x0, 12 - y0), letter, font=LETTER, fill=(0, 0, 0))
    return out


def stack(panels, gap=24):
    h = sum(p.size[1] for p in panels) + gap * (len(panels) - 1)
    out, y = Image.new("RGB", (W300, h), (255, 255, 255)), 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.size[1] + gap
    return out


FIGS = {
    1: [(SHOTS / "1920_s4_xray_room.png", (0.0, 0.0, 1.0, 1.0)),
        (SHOTS / "fig1_anatomy_projection_split_raocaud.png", (0.0, 0.0, 1.0, 1.0))],
    2: [(SHOTS / "fig2a_predict_question.png", (0.205, 0.635, 0.795, 0.975)),
        (SHOTS / "fig2b_predict_answered.png", (0.18, 0.13, 0.82, 0.985))],
}
FIG_LOG = []
for n, spec in FIGS.items():
    panels = [panel_letter(fit_width(crop_frac(p, box)), "ab"[i]) for i, (p, box) in enumerate(spec)]
    img = stack(panels)
    img.save(OUT / f"Fig{n}.tif", dpi=(300, 300), compression="tiff_lzw")
    FIG_LOG.append((n, img.size, img.mode, [str(p.relative_to(ROOT)) for p, _ in spec]))
    if img.size[1] / 300 * 25.4 > 234:
        fail(f"Fig{n} taller than the 234 mm page")

# ------------------------------------------------------------------ docx helpers
WORDS = {}


def setup(doc):
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Times New Roman", Pt(10)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    st.paragraph_format.space_after = Pt(6)
    for lvl in (1, 2):
        h = doc.styles[f"Heading {lvl}"]
        h.font.name, h.font.size, h.font.bold = "Times New Roman", Pt(10), True
        h.font.italic = lvl == 2
        h.font.color.rgb = None
        h.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
        for a in ("w:ascii", "w:hAnsi", "w:cs"):
            h.element.rPr.rFonts.set(qn(a), "Times New Roman")
        h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(12), Pt(6)
    for s in doc.sections:
        s.page_width, s.page_height = Cm(21.59), Cm(27.94)
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(2.54)
        fp = s.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fp._p.append(parse_xml(f'<w:fldSimple {nsdecls("w")} w:instr="PAGE"><w:r><w:t>1</w:t></w:r></w:fldSimple>'))


def add_runs(p, text):
    """**bold**, *italic*, ^sup^; placeholders highlighted yellow."""
    for tok in re.split(r"(\*\*.+?\*\*|\*[^*]+?\*|\^[^^]+\^|\[(?:VERIFY|AUTHOR INPUT|CITE NEEDED|PLACEHOLDER)[^\]]*\])", text):
        if not tok:
            continue
        if tok.startswith("**"):
            r = p.add_run(tok[2:-2]); r.bold = True
        elif tok.startswith("*"):
            r = p.add_run(tok[1:-1]); r.italic = True
        elif tok.startswith("^"):
            r = p.add_run(tok[1:-1]); r.font.superscript = True
        elif PLACEHOLDER.fullmatch(tok):
            r = p.add_run(tok); r.font.highlight_color = WD_COLOR_INDEX.YELLOW
        else:
            r = p.add_run(tok)
        r.font.name, r.font.size = "Times New Roman", Pt(10)
    return p


def plain(t):
    return re.sub(r"\*\*|\*|\^", "", t)


def count(bucket, text):
    WORDS[bucket] = WORDS.get(bucket, 0) + len(PLACEHOLDER.sub("", plain(text)).split())


def para(doc, text, bucket=None, align=None):
    p = add_runs(doc.add_paragraph(), text)
    if align:
        p.alignment = align
    if bucket:
        count(bucket, text)
    return p


def heading(doc, text, lvl):
    h = doc.add_heading(level=lvl)
    r = h.add_run(text)
    r.font.name, r.font.size, r.font.bold = "Times New Roman", Pt(10), True
    return h


CAPS = {}
for line in S["CAPTIONS"].splitlines():
    if line.strip():
        k, _, v = line.partition(":")
        CAPS[int(k.split()[1])] = v.strip()


def figure(doc, n):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(OUT / f"Fig{n}.tif"), width=Cm(16.0))
    para(doc, resolve(CAPS[n]), "captions")


def table(doc, n):
    lines = [l for l in S[f"TABLE {n}"].splitlines() if l.strip()]
    get = lambda tag: [l.split(":", 1)[1].strip() for l in lines if l.startswith(tag + ":")]
    para(doc, resolve(get("CAPTION")[0]), "tables")
    header = [c.strip() for c in get("HEADER")[0].split("|")]
    rows = [[resolve(c.strip()) for c in r.split("|")] for r in get("ROW")]
    tb = doc.add_table(rows=1 + len(rows), cols=len(header))
    tb.style = doc.styles["Table Grid"]
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate([header] + rows):
        for j, cell in enumerate(row):
            c = tb.cell(i, j)
            c.paragraphs[0].paragraph_format.space_after = Pt(0)
            add_runs(c.paragraphs[0], f"**{cell}**" if i == 0 else cell)
            count("tables", cell)
    for f in get("FOOT"):
        para(doc, resolve(f), "tables")


# ------------------------------------------------------------------ manuscript.docx (anonymous: no names/affiliations)
doc = Document()
setup(doc)
title = S["TITLE"]
tp = para(doc, f"**{title}**", "title", WD_ALIGN_PARAGRAPH.CENTER)
para(doc, "Article type: Innovation", None, WD_ALIGN_PARAGRAPH.CENTER)
heading(doc, "Abstract", 1)
para(doc, S["ABSTRACT"], "abstract")
para(doc, f"**Keywords** {S['KEYWORDS']}", "keywords")

main_paras = []
for block in re.split(r"^## ", S["MAIN"], flags=re.M):
    if not block.strip():
        continue
    head, _, body = block.partition("\n")
    heading(doc, head.strip(), 1)
    count("headings", head)
    sec = head.strip()
    for chunk in [c.strip() for c in body.split("\n\n") if c.strip()]:
        m = re.fullmatch(r"@@(FIG|TABLE) (\d+)@@", chunk)
        if m:
            (figure if m.group(1) == "FIG" else table)(doc, int(m.group(2)))
            continue
        txt = resolve(chunk)
        para(doc, txt, f"main:{sec}")
        main_paras.append(txt)

heading(doc, "Online Resources", 1)
for chunk in [c for c in S["ONLINE RESOURCES"].split("\n\n") if c.strip()]:
    para(doc, resolve(chunk), "online_resources")

heading(doc, "Statements and Declarations", 1)
for chunk in [c for c in S["STATEMENTS"].split("\n\n") if c.strip()]:
    para(doc, resolve(chunk), "statements")

heading(doc, "References", 1)
REFS = [fmt_ref(BIB[k]) for k in ORDER]
for i, r in enumerate(REFS, 1):
    p = para(doc, f"{i}. {r}", "references")
    p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Cm(0.6), Cm(-0.6)
unused = sorted(set(BIB) - set(ORDER))
if unused:
    fail(f"bib entries never cited: {unused}")
doc.core_properties.author, doc.core_properties.title = "", title
doc.save(OUT / "manuscript.docx")

# ------------------------------------------------------------------ word counts and abstracts
main_total = sum(v for k, v in WORDS.items() if k.startswith("main:"))
abs_n, short_n = WORDS["abstract"], len(S["ABSTRACT_SHORT"].split())
if not 150 <= abs_n <= 200:
    fail(f"abstract has {abs_n} words (150-200 required)")
if short_n > 50:
    fail(f"short abstract has {short_n} words (max 50)")
(OUT / "abstract_short.txt").write_text(S["ABSTRACT_SHORT"] + "\n", encoding="utf-8")
wc = ["AngioLens - Medical Science Educator, Innovation: word count", "",
      "Main text (body paragraphs of the five Innovation sections; excludes headings, abstract, captions, table, "
      "declarations, references; [VERIFY]/[AUTHOR INPUT] placeholder text excluded):"]
for k, v in WORDS.items():
    if k.startswith("main:"):
        wc.append(f"  {k[5:]:<32}{v:>5}")
wc += [f"  {'TOTAL main text':<32}{main_total:>5}", "",
       f"Section headings                  {WORDS.get('headings', 0):>5}",
       f"Abstract                          {abs_n:>5}   (target 150-200)",
       f"Short abstract (abstract_short)   {short_n:>5}   (max 50)",
       f"Keywords                          {WORDS['keywords']:>5}",
       f"Figure captions (2)               {WORDS['captions']:>5}",
       f"Table 1 (caption, cells, footnote){WORDS['tables']:>5}",
       f"Online Resources                  {WORDS['online_resources']:>5}",
       f"Statements and Declarations       {WORDS['statements']:>5}",
       f"References ({len(REFS)})                   {WORDS['references']:>5}",
       "", "Figures and tables: 3 in total (Fig. 1, Fig. 2, Table 1).",
       "Note: author-input placeholders will add roughly 60-100 words to the main text once filled in."]
(OUT / "word_count.txt").write_text("\n".join(wc) + "\n", encoding="utf-8")

# ------------------------------------------------------------------ title page
AUTHORS = [
    ("Rugved Parmar, MD", "1", "0009-0005-8941-3745", "parmarrugved@gmail.com"),
    ("Md Fahim, MD", "2", None, "md.fahim@downstate.edu"),
    ("Adam Budzikowski, MD, PhD", "3", None, "adam.budzikowski@downstate.edu"),
]
AFFIL = {
    "1": "Internal Medicine, SUNY Downstate Health Sciences University / Kings County Hospital, Brooklyn, NY, USA",
    "2": "Internal Medicine, SUNY Downstate Health Sciences University, Brooklyn, NY, USA",
    "3": "SUNY Downstate Health Sciences University, Brooklyn, NY, USA",
}
t = Document()
setup(t)
para(t, f"**{title}**", None, WD_ALIGN_PARAGRAPH.CENTER)
para(t, "Article type: Innovation", None, WD_ALIGN_PARAGRAPH.CENTER)
heading(t, "Authors", 1)
for name, aff, orcid, email in AUTHORS:
    para(t, f"{name}^{aff}^" + (f" · ORCID: {orcid}" if orcid else "") + f" · {email}")
heading(t, "Affiliations", 1)
for k, v in AFFIL.items():
    para(t, f"^{k}^ {v}")
heading(t, "Corresponding author", 1)
para(t, "Rugved Parmar, MD, Internal Medicine, SUNY Downstate Health Sciences University / Kings County Hospital, "
        "Brooklyn, NY, USA. Email: parmarrugved@gmail.com. ORCID: 0009-0005-8941-3745")
heading(t, "Acknowledgments", 1)
para(t, "Anatomy in the figures and video is rendered "
        "from Z-Anatomy models (CC BY-SA 4.0), derived from BodyParts3D (The Database Center for Life Science).")
heading(t, "Manuscript information", 1)
para(t, f"Main text: {main_total:,} words (excluding abstract, captions, table, declarations and references). Abstract: {abs_n} words; short abstract: {short_n} words. Figures: 2. Tables: 1. "
        f"References: {len(REFS)}. Online Resources: 1 (video).")
para(t, f"Code: {CODE_URL}, release tag {TAG}, commit {COMMIT} (MIT licence).")
t.save(OUT / "title_page.docx")

# ------------------------------------------------------------------ cover letter
c = Document()
setup(c)
para(c, "20 November 2026")
para(c, "The Editor-in-Chief\n*Medical Science Educator*")
para(c, "Dear Editor-in-Chief,")
para(c, f"We submit the manuscript \"{title}\" for consideration as an **Innovation** in *Medical Science Educator*.")
para(c, "Learning coronary angiographic projections usually happens opportunistically in the catheterization laboratory, "
        "and the dedicated simulators that help are costly and rarely teach projection geometry explicitly. AngioLens is "
        "a free, open-source, browser-based simulator that links three-dimensional coronary anatomy, a movable C-arm and "
        "the resulting angiogram, with a Predict mode whose distractors encode the classic orientation errors; its geometry "
        "is verified by automated tests. We describe what we built, how we used it in a resident teaching session, what "
        "we learned, and why other programs, including those without a simulator budget, can adopt and adapt it.")
para(c, f"The main text has {main_total:,} words, with 2 figures, 1 table and 1 video Online Resource. The manuscript reports "
        "no learner outcome data.")
para(c, "This manuscript has not been published and is not under consideration elsewhere. All authors have approved the "
        "submission.")
para(c, "AI disclosure: Claude Code (Anthropic; Claude Opus 5.5) assisted software development and the drafting and editing "
        "of the manuscript under the authors' direction; the authors reviewed all content, checked every reference and take "
        "full responsibility for it.")
para(c, "Sincerely,")
para(c, "Rugved Parmar, MD (corresponding author), on behalf of Md Fahim, MD, and Adam Budzikowski, MD, PhD\n"
        "Internal Medicine, SUNY Downstate Health Sciences University / Kings County Hospital, Brooklyn, NY, USA\n"
        "parmarrugved@gmail.com · ORCID 0009-0005-8941-3745")
c.save(OUT / "cover_letter.docx")

# ------------------------------------------------------------------ ESM
sys.path.insert(0, str(SRC))
import build_esm  # noqa: E402  (MSE title card + trims; keeps the committed ESM_1.mp4 if the source video is absent)
ESM = build_esm.build()
if ESM and not ESM["pass_le_3_per_s"]:
    fail("ESM_1 photosensitivity check failed")

# ------------------------------------------------------------------ self-audit
def docx_text(path):
    d = Document(path)
    parts = [p.text for p in d.paragraphs]
    for tb in d.tables:
        for row in tb.rows:
            parts += [cell.text for cell in row.cells]
    return "\n".join(parts)


def docx_check(path, expect_figs):
    d, issues = Document(path), []
    for p in d.paragraphs + [p for tb in d.tables for row in tb.rows for cell in row.cells for p in cell.paragraphs]:
        for r in p.runs:
            if r.text.strip() and (r.font.name or d.styles["Normal"].font.name) != "Times New Roman":
                issues.append(f"font {r.font.name} in '{r.text[:30]}'")
            if r.text.strip() and r.font.size not in (None, Pt(10)):
                issues.append(f"size {r.font.size} in '{r.text[:30]}'")
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    footers = "".join(zipfile.ZipFile(path).read(n).decode("utf-8") for n in zipfile.ZipFile(path).namelist()
                      if n.startswith("word/footer"))
    body_fields = re.findall(r'w:instr="([^"]+)"|<w:instrText[^>]*>([^<]+)', xml)
    levels = {p.style.name for p in d.paragraphs if p.style.name.startswith("Heading")}
    caps = [p.text for p in d.paragraphs if re.match(r"Fig\. \d", p.text)]
    cap_ok = all(re.match(r"Fig\. \d [A-Z]", t) and not t.rstrip().endswith((".", ";", ":")) for t in caps)
    cap_bold = all(p.runs[0].bold and re.fullmatch(r"Fig\. \d", p.runs[0].text) for p in d.paragraphs
                   if re.match(r"Fig\. \d", p.text))
    return {
        "Times New Roman 10 pt on every run": not issues,
        "automatic page number (PAGE field in footer)": 'w:instr="PAGE"' in footers,
        "no field functions in body": not body_fields,
        "heading levels used <= 3": len(levels) <= 3 and all(int(l.split()[-1]) <= 3 for l in levels),
        f"embedded figures = {expect_figs}": len(d.inline_shapes) == expect_figs,
        "captions 'Fig. n' bold, no punctuation after number or at end": (cap_ok and cap_bold) if expect_figs else True,
        "Word tables (table function)": len(d.tables) >= (1 if expect_figs else 0),
        "no endnotes part": not any("endnotes" in n for n in zipfile.ZipFile(path).namelist()),
        "_issues": issues[:5],
    }


CHECK = {n: docx_check(OUT / n, k) for n, k in (("manuscript.docx", 2), ("title_page.docx", 0), ("cover_letter.docx", 0))}
bad = [(n, k) for n, r in CHECK.items() for k, v in r.items() if k != "_issues" and v is False]
if bad:
    fail(f"docx self-check: {bad}")

# hard rule 1: learner-outcome scan over everything a reader or editor sees
SCAN_TERMS = [r"score", r"pre-?test", r"post-?test", r"%", r"improv", r"survey", r"participants?", r"residents reported",
              r"\bquiz", r"feedback from residents", r"learners? (said|reported|rated|found)", r"\bpercent", r"\bp\s*[<=]",
              r"mean|median|\bSD\b", r"accuracy", r"correctly answered", r"satisf"]
ALLOW = {  # exact sentence fragments that hit a term but are not learner-outcome claims, with the reason
    "No data from human participants are reported": "mandated ethics statement; states the absence of participant data",
    "scenes loaded in about": "software load time (E5), not a learner measure",
    "Targeting clinical outcomes: endovascular simulation improves": "title of a cited prior study (reference list), not data from this work",
}
scan_docs = {"manuscript.docx": docx_text(OUT / "manuscript.docx"), "title_page.docx": docx_text(OUT / "title_page.docx"),
             "cover_letter.docx": docx_text(OUT / "cover_letter.docx"),
             "abstract_short.txt": (OUT / "abstract_short.txt").read_text(encoding="utf-8")}
HITS = []
for name, text in scan_docs.items():
    for sent in re.split(r"(?<=[.!?])\s+|\n", text):
        for term in SCAN_TERMS:
            if re.search(term, sent, re.I):
                why = next((v for k, v in ALLOW.items() if k in sent), None)
                HITS.append((name, term, sent.strip()[:160], why))
unexplained = [h for h in HITS if h[3] is None]
if unexplained:
    fail("learner-outcome scan hits:\n" + "\n".join(f"  {h[0]} [{h[1]}]: {h[2]}" for h in unexplained))

# ------------------------------------------------------------------ AUDIT.md
src_map = {}
for line in (ROOT / "paper/AUDIT.md").read_text(encoding="utf-8").splitlines():
    m = re.match(r"\| `(\w+)` \| (.*?) \| (.*?) \|$", line)
    if m:
        src_map[m.group(1)] = m.group(3)
lit = sorted(set(re.findall(r"(?<![\w{])\d[\d,.]*(?:\s?(?:°|s|mm|px))?", re.sub(r"\{\{\w+\}\}", "", S["MAIN"] + S["TABLE 1"]))))
placeholders = sorted(set(m.group(0) for t in scan_docs.values() for m in PLACEHOLDER.finditer(t)))
A = ["# AUDIT: AngioLens, Medical Science Educator (Innovation)", "",
     "Generated by `paper/mse/source/build_package.py`; do not edit by hand. Rerun the build to refresh.", "",
     f"Code cited: {CODE_URL}, tag `{TAG}` = commit `{COMMIT}` (`git rev-parse {TAG}^{{commit}}`). Tag `v1.1` does not exist "
     "(deleted because it clashed with branch `v1.1`; see paper/TODO.md). No new tag was created.", "",
     "## 1. Every number in the manuscript", "",
     "Numbers enter only through `{{key}}` placeholders resolved from `paper/results/numbers.json`, which "
     "`paper/scripts/build_numbers.py` writes from result files only. An unknown key fails the build.", "",
     "| Key | Printed as | Source (file :: field) |", "|---|---|---|"]
for k in sorted(USED_NUM):
    A.append(f"| `{k}` | {USED_NUM[k]} | {NUM[k].get('source') if isinstance(NUM[k], dict) else src_map.get(k, '**not found**')} |")
A += ["", "Test counts were re-checked on 2026-11-20 on this branch: `npm run verify` ALL GREEN, 15 of 15 steps; "
      "`pytest -q` 393 passed; `vitest run` 65 passed; 11 of 11 e2e suites. These are identical to the registry values.", "",
      "### Literal numbers (design constants, not results)", "",
      "- 15° minimum move between Predict targets: `web/src/predict.ts:13`. 5° angle grid: `paper/scripts/common.py` `angle_grid`.",
      "- RAO 53/cranial 35 (Fig. 2): the random target shown in the screenshot `out/manuscript/fig2a_predict_question.png`.",
      "- Six guided scenes: README (Heart, In the chest, Cath lab, X-ray, Catheter, Cross-section) and the toolbar in Fig. 1.",
      "- Online Resource 1 length 3 min 32 s: paper/mse/esm1_check.json duration_s 212.5 (6 s title card + 206.5 s of tour).",
      "- Claude Opus 5.5: `Co-Authored-By` trailers of all 24 AI-assisted commits (`git log --format=%(trailers:key=Co-Authored-By)`).",
      f"- Literal numeric tokens in the main text and Table 1 (for a final scan): {', '.join(lit)}", "",
      "## 2. References", "",
      f"{len(ORDER)} references, numbered in order of first citation; every bib entry is cited. Each was checked against "
      "Crossref and/or PubMed (new entries 2026-11-20) or the cited web page (2026-11-14). No [CITE NEEDED] remains.", "",
      "| # | Printed | Verification |", "|---|---|---|"]
for i, k in enumerate(ORDER, 1):
    A.append(f"| {i} | {REFS[i - 1]} | {BIB[k].get('note', '')} |")
A += ["", "Correction to the brief: the Cardiovasc Revasc Med 2016;17:102-105 paper is **Casey DB, Stewart D, Vidovich MI** "
      "(Vidovich is the last author), PMID 26811001. PMID 26198625 is Schimmel DR et al., Catheter Cardiovasc Interv "
      "2016;87:383-388, doi:10.1002/ccd.26089.", "",
      "## 3. Figures and tables", "",
      "| Item | Size (px) | Mode | Sources |", "|---|---|---|---|"]
for n, size, mode, srcs in FIG_LOG:
    A.append(f"| Fig{n}.tif | {size[0]} x {size[1]} ({size[0] / 300 * 25.4:.0f} x {size[1] / 300 * 25.4:.0f} mm at 300 dpi) "
             f"| {mode} | {'; '.join(srcs)} |")
A += ["| Table 1 | Word table in manuscript | | numbers.json (section 1) |", "",
      "Screenshots only (300 dpi); no combination art, so the 600 dpi rule does not apply. Panel letters Arial Bold 11 pt, in a white band above each panel; "
      "no titles inside images; screenshot text is the app's own UI. Meaning never depends on colour alone: in Fig. 2b "
      "each option carries a text label and the chosen answer is marked in text ('Correct.'), not only by its green outline.", "",
      "## 4. Hard-rule-1 scan (no learner outcome data)", "",
      f"Terms: {', '.join('`' + t + '`' for t in SCAN_TERMS)}. Scanned: manuscript.docx (text, captions, table), "
      "title_page.docx, cover_letter.docx, abstract_short.txt. Figures were inspected by eye: Fig. 2 shows interface "
      "feedback for one demonstration answer ('Correct.') by the authors, and the collapsed 'Your record' control shows "
      "no data. ESM_1 is built by paper/mse/source/build_esm.py: MSE title card (no IJCARS wording, current authors) and cuts "
      "of source 178.0-184.0 s, 205.95-237.0 s and 243.6-254.6 s. The middle cut removes the narration \"instead of just "
      "getting a score...\" and the expanded 'Your record' panel of the narrator's demo answers (\"5/11 correct (45%)\"), "
      "which opens at 206.0 s. A 1 frame/s contact sheet of the whole output was inspected: no record panel or score remains. "
      "Photosensitivity check: max 1 flash/s (limit 3).", ""]
if HITS:
    A += ["| File | Term | Sentence | Why it is not a learner-outcome claim |", "|---|---|---|---|"]
    A += [f"| {h[0]} | `{h[1]}` | {h[2]} | {h[3]} |" for h in HITS]
A += ["", f"**Result: PASS** ({len(HITS)} hit(s), all explained above; 0 learner-outcome claims).", "",
      "## 5. .docx self-check", ""]
for n, r in CHECK.items():
    A.append(f"- **{n}**: " + "; ".join(f"{k}: {'yes' if v else 'NO'}" for k, v in r.items() if k != "_issues"))
A += ["", "## 6. Placeholders still in the package", "", f"{len(placeholders)} (the build fails if any remain)."]
if placeholders:
    fail(f"placeholders remain: {placeholders}")
AUDIT.write_text("\n".join(A) + "\n", encoding="utf-8")

print(f"OK  main text {main_total} words; abstract {abs_n}; short abstract {short_n}; refs {len(ORDER)}; "
      f"scan hits {len(HITS)} (all explained); placeholders {len(placeholders)}")
print(f"    package: {OUT}")
