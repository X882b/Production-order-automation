"""The production order as a Word file, laid out like the shop's template.

Letter page with margins 10/5/5/3 mm, Arial 12 pt bold. As in the template,
labels are padded with spaces so the values line up, the top fields are
separated by empty paragraphs, and the name, the quantity, the delivery
date, the Štampa and "napred ide" lines and NAPOMENA carry the template's
sizes and italics. The wording itself comes from order_text. No Qt here.
"""
import datetime
import os
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, Twips

from order_text import boja_text, datum_potpis_lines, datum_text

# ── Run formats: (bold, italic, size in pt; None = the 12 pt of the page) ────

B = (True, False, None)
BI = (True, True, None)
B14 = (True, False, 14)
BI14 = (True, True, 14)
B11 = (True, False, 11)
I = (False, True, None)
I11 = (False, True, 11)
S11 = (False, False, 11)
N = (False, False, None)

# ── Measuring text, to pad it with spaces as the template does ───────────────

# Advance widths of Arial Bold in 1/2048 em, by character (taken from the
# metric-compatible Liberation Sans Bold)
_ARIAL_BOLD = {
    487: "'",
    569: " ,./I\\ijl‘’",
    573: "|",
    682: "!()-:;[]`ft",
    797: "*r{}",
    819: "°",
    971: '"',
    1024: "zž„“”",
    1139: "#$0123456789J_aceksvxyčćš–€",
    1180: "µ",
    1196: "+<=>^~×",
    1251: "?FLTZbdghnopquŽđø",
    1366: "EPSVXYŠ",
    1479: "&ABCDHKNRUČĆĐ",
    1593: "GOQwØ",
    1706: "M",
    1821: "%m",
    1933: "W",
    1997: "@",
    2048: "—",
}
_WIDTH = {ch: w for w, chars in _ARIAL_BOLD.items() for ch in chars}


def text_width(text: str, size: float = 12) -> float:
    """Width in pt of text in Arial Bold (characters not in the table count as 'n')."""
    return sum(_WIDTH.get(ch, 1251) for ch in text) * size / 2048


# The colour rows' cylinder (Z-93) starts this far from the left margin
_CYLINDER_AT = 478.2


def pad_to(text: str, at: float = _CYLINDER_AT) -> str:
    """The spaces after text that bring what follows to `at` pt, at least one."""
    return " " * max(1, round((at - text_width(text)) / text_width(" ")))


# Spaces after each label, as in the template: the values start about 120 pt in
_LABEL_PAD = {
    "MAŠINA:": 21, "ŠIFRA:": 24, "NAZIV:": 24, "DIMENZIJA:": 16, "MATERIJAL:": 15,
    "ŠIRINA:": 23, "NARUČILAC:": 14, "KOLIČINA:": 17, "ALATI:": 24, "OPIS:": 26,
}
_OPIS_INDENT = 36   # OPIS's next lines start under its first

# ── The lines, as (runs, centred) ────────────────────────────────────────────


def _label(label: str, value: str) -> str:
    return label + " " * _LABEL_PAD[label] + value if value else label


def _naziv_runs(naziv: str) -> list:
    """'nalepnica Demo sok 0,5 l': the kind of label in plain bold, the name
    after it bold italic 14 pt."""
    kind, _, name = naziv.partition(" ")
    if not name:
        return [(_label("NAZIV:", naziv), B)]
    return [(_label("NAZIV:", kind + " "), B), (name, BI14)]


def _stampa_runs(line: str) -> list:
    """Bold italic 14 pt; its dates at the end in italic, not bold: the proof's
    date at 12 pt, the list of earlier runs in brackets at 11 pt."""
    m = re.search(r"(?:\(\s*)?\d{1,2}\.\d{1,2}\.\d{4}.*$", line)
    if not m:
        return [(line, BI14)]
    tail = m.group(0)
    return [(line[:m.start()], BI14), (tail, I11 if tail.startswith("(") else I)]


_NAPRED_RE = re.compile(r"^(?P<lead>.*?)(?P<slovo>slovo )„(?P<letter>[^“]*)“ (?P<u>u nazivu) „(?P<name>[^“]*)“(?P<end>.*)$")


def _napred_runs(line: str, italic_lead: bool) -> list:
    """'Pri štampi napred ide slovo „D“ u nazivu „Demo“.': the letter and the
    name in 14 pt, the name italic. The printing line's start is italic too."""
    m = _NAPRED_RE.match(line)
    if not m:
        return [(line, B)]
    lead = [(m["lead"], BI), (m["slovo"], B)] if italic_lead else [(m["lead"] + m["slovo"], B)]
    return lead + [
        (f"„{m['letter']}“ ", B14), (m["u"], B), (" „", B14), (m["name"], BI14), ("“", B14),
        (m["end"], BI),
    ]


def _rasecanje_runs(line: str) -> list:
    """The slitting line in bold, except each '-1476 otkucaja/rolna' (with the
    ' + ' after it, or the rest of the line after the last) in 11 pt not
    bold; the roll count after a ' + ' bold 11 pt."""
    runs, pos = [], 0
    found = list(re.finditer(r"-\d+ otkucaja/rolna", line))
    for k, m in enumerate(found):
        runs.append((line[pos:m.start()], B))
        if k == len(found) - 1:
            runs.append((line[m.start():], S11))
            pos = len(line)
            break
        pos = m.end()
        plus = re.match(r" \+ (\d+)", line[pos:])
        if plus:
            runs += [(line[m.start():pos] + " + ", S11), (plus.group(1), B11)]
            pos += plus.end()
        else:
            runs.append((line[m.start():pos], S11))
    runs.append((line[pos:], B))
    return [run for run in runs if run[0]]


def order_lines(order: dict) -> list[tuple[list, bool]]:
    """The order's paragraphs as (runs, centred), top to bottom; a run is
    (text, format). order holds the form's values: broj (6276, or 6276-1
    for a version), masina, sifra, naziv, dimenzija, materijal, sirina,
    narucilac, kolicina (the two parts of order_text.kolicina_parts), rok
    and datum (ISO), boje (colour rows), stampa, napred, alati, opis,
    rasecanje, odmotavanje and napomena (the last NAPOMENA lines)."""
    def text(key):
        return (order.get(key) or "").strip()

    def lines_of(key):      # a text box's lines, each its own paragraph
        return [line.strip() for line in text(key).splitlines() if line.strip()]

    empty = ([], False)
    lines = [([], True), ([(f"NALOG ZA PROIZVODNJU {order['broj']}", B)], True), empty]
    for label, key in (("MAŠINA:", "masina"), ("ŠIFRA:", "sifra")):
        lines += [([(_label(label, text(key)), B)], False), empty]
    lines += [(_naziv_runs(text("naziv")), False), empty]
    for label, key in (("DIMENZIJA:", "dimenzija"), ("MATERIJAL:", "materijal"),
                       ("ŠIRINA:", "sirina"), ("NARUČILAC:", "narucilac")):
        lines += [([(_label(label, text(key)), B)], False), empty]
    main, small = order.get("kolicina") or ("", "")
    lines += [([(_label("KOLIČINA:", main), B), (small, S11)], False), empty]
    lines += [([("ROK ZA ISPORUKU: ", BI14), (datum_text(order.get("rok")), BI14)], False), empty]

    lines.append(([("ŠIFRA BOJA:", B)], False))
    for row in order.get("boje") or []:
        head, cylinder = boja_text(row)
        lines.append(([(head + pad_to(head) + cylinder if cylinder else head, B)], False))
    lines += [(_stampa_runs(line), False) for line in lines_of("stampa")]
    if text("napred"):
        lines.append((_napred_runs(text("napred"), italic_lead=True), False))
    lines += [([(" ", BI14)], False), ([(_label("ALATI:", text("alati")), B)], False), empty]

    opis = lines_of("opis")
    lines.append(([(_label("OPIS:", opis[0] if opis else ""), B)], False))
    lines += [([(" " * _OPIS_INDENT + line, B)], False) for line in opis[1:]]
    lines += [empty, ([("NAPOMENA:", B)], False)]
    lines += [(_rasecanje_runs(line), False) for line in lines_of("rasecanje")]
    if text("odmotavanje"):
        lines.append((_napred_runs(text("odmotavanje"), italic_lead=False), False))
    lines += [([(line, B)], False) for line in lines_of("napomena")]

    # An empty line, then the date and the line to sign on (the template's
    # line there is an old text in white)
    datum, dan, potpis = datum_potpis_lines(order.get("datum"))
    lines += [empty, ([(datum, N)], False), ([(dan, B)], False), ([(potpis, B)], False)]
    return lines


# ── The Word document ────────────────────────────────────────────────────────

def order_document(order: dict) -> Document:
    """The order as a python-docx Document."""
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Twips(12240), Twips(15840)    # Letter
    section.left_margin, section.right_margin = Twips(567), Twips(284)      # 10 and 5 mm
    section.top_margin, section.bottom_margin = Twips(284), Twips(170)      # 5 and 3 mm
    section.header_distance = section.footer_distance = Twips(0)

    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(12)
    fonts = normal.element.rPr.rFonts
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), "Arial")
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.0

    props = doc.core_properties
    props.author = props.last_modified_by = props.comments = ""
    props.title = f"NALOG ZA PROIZVODNJU {order['broj']}"
    props.created = props.modified = datetime.datetime.now()

    for runs, centred in order_lines(order):
        par = doc.add_paragraph()
        if centred:
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for text, (bold, italic, size) in runs:
            if not text:
                continue
            run = par.add_run(text)
            run.bold = bold or None
            run.italic = italic or None
            if size:
                run.font.size = Pt(size)
    return doc


def write_order(path: Path, order: dict) -> None:
    """Write the order to path. The file appears whole (written beside it
    under another name, then renamed), so the watcher never reads half of it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        order_document(order).save(str(tmp))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


# ── Where the order's file goes ──────────────────────────────────────────────

def file_title(naziv: str) -> str:
    """The name part of the file name, made as the watcher makes it
    (server/watcher_v2_1.py, sanitize_title_for_filename)."""
    base = (naziv or "nedefinisano").strip()
    for ch in r'\/:*?"<>|':
        base = base.replace(ch, " ")
    return re.sub(r"\s+", " ", base).strip()[:80]


def order_file(docs_dir: Path, broj: int | str, naziv: str, rel_path: str | None,
               today: datetime.date) -> Path:
    """Where order broj's Word file is, or goes (broj 6276, or 6276-1 for a
    version): the file the database has for it, else a file of the
    watcher's naming ('6276 - ...docx') anywhere in the orders folder, else
    a new one in today's folder as the watcher files them (YYYY/MM/DD/6276 -
    naziv.docx). A second file for one order would be taken by the watcher
    for a new order."""
    docs_dir = Path(docs_dir)
    if rel_path:
        return docs_dir / rel_path
    found = sorted(p for p in docs_dir.rglob(f"{broj} - *.docx") if not p.name.startswith((".", "~")))
    if found:
        return found[0]
    return docs_dir / f"{today:%Y}" / f"{today:%m}" / f"{today:%d}" / f"{broj} - {file_title(naziv)}.docx"
