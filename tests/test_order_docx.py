"""The production order as a Word file: the template's lines word for word,
its spacing and formatting, and the watcher reading it back. Fictional data."""
import datetime

import docx
import pytest
from docx.shared import Pt

import order_docx
from order_docx import B, B11, B14, BI, BI14, I, I11, N, S11, order_lines
from order_text import (
    NAPOMENA_DEFAULT, OPIS_DEFAULT, alati_text, caure_text, datum_potpis_lines,
    kolicina_parts, napred_ide_text, odmotavanje_text, rasecanje_text,
)
from server import watcher_v2_1 as watcher

CMYK = [("I", "C", "Process Cyan"), ("II", "M", "Process Magenta"),
        ("III", "Y", "Process Yellow"), ("IV", "K", "Process Black")]
ROWS = [
    {"position_label": pos, "klise_code": "0000", "variant": var, "color_text": color,
     "raster": "390 l/cm", "cylinder": "Z-93"}
    for pos, var, color in CMYK
] + [{"position_label": "VIII", "klise_code": "uređaj za lakiranje", "variant": None,
      "color_text": "UV lak", "raster": "160 l/cm", "cylinder": "Z-88"}]
RASECANJE = rasecanje_text(caure_text("45", "52", "65"), [(99, 1000), (3, 335)], 295.275, 2, "150")
STAMPA = "Štampa prema pripremi, prema uzorcima odštampanim kao probni uzorak 04.04.2025."
ORDER = {
    "broj": 6276, "masina": "Nilpeter FA2500", "sifra": "DEMO-250101",
    "naziv": "nalepnica Demo sok 0,5 l, P+Z", "dimenzija": "65 x 140 mm", "materijal": "PE WHITE",
    "sirina": "235 mm", "narucilac": "Primer d.o.o., Beograd",
    "kolicina": kolicina_parts(4930, 100_000, 20.32, 3), "rok": "2025-07-24", "boje": ROWS,
    "stampa": STAMPA, "napred": napred_ide_text("D", "Demo"),
    "alati": alati_text("ABC23-09-12345", 93, "XYZ-042S"), "opis": OPIS_DEFAULT,
    "rasecanje": RASECANJE, "odmotavanje": odmotavanje_text("D", "Demo"),
    "napomena": NAPOMENA_DEFAULT, "datum": "2025-07-18",
}


def texts(order):
    return ["".join(text for text, _fmt in runs) for runs, _centred in order_lines(order)]


def runs_of(order, start):
    """The runs of the first line starting with start."""
    return next(runs for runs, _ in order_lines(order) if "".join(t for t, _ in runs).startswith(start))


# ── the lines, word for word and spaced as in the template ───────────────────

def test_lines_as_in_the_order_template():
    sp = " ".__mul__
    assert texts(ORDER) == [
        "",
        "NALOG ZA PROIZVODNJU 6276",
        "",
        "MAŠINA:" + sp(21) + "Nilpeter FA2500",
        "",
        "ŠIFRA:" + sp(24) + "DEMO-250101",
        "",
        "NAZIV:" + sp(24) + "nalepnica Demo sok 0,5 l, P+Z",
        "",
        "DIMENZIJA:" + sp(16) + "65 x 140 mm",
        "",
        "MATERIJAL:" + sp(15) + "PE WHITE",
        "",
        "ŠIRINA:" + sp(23) + "235 mm",
        "",
        "NARUČILAC:" + sp(14) + "Primer d.o.o., Beograd",
        "",
        "KOLIČINA:" + sp(17) + "4930 m dobrih (100.000 kom) (20,32 kom/m) - 3 reda",
        "",
        "ROK ZA ISPORUKU: 24.07.2025.",
        "",
        "ŠIFRA BOJA:",
        # the cylinder set at the right with as many spaces as the template has
        "I kliše oznake 0000, C, boja Process Cyan, raster 390l/cm," + sp(45) + "Z-93",
        "II kliše oznake 0000, M, boja Process Magenta, raster 390l/cm," + sp(38) + "Z-93",
        "III kliše oznake 0000, Y, boja Process Yellow, raster 390l/cm," + sp(41) + "Z-93",
        "IV kliše oznake 0000, K, boja Process Black, raster 390l/cm," + sp(42) + "Z-93",
        "VIII uređaj za lakiranje, UV lak, raster 160l/cm," + sp(66) + "Z-88",
        STAMPA,
        "Pri štampi napred ide slovo „D“ u nazivu „Demo“.",
        " ",
        "ALATI:" + sp(24) + "štancna oznake ABC23-09-12345 (XYZ-042S), Z-93",
        "",
        "OPIS:" + sp(26) + "Svaki nastavak rolne izvršiti precizno zbog mašinskog etiketiranja.",
        sp(36) + "Nastavak koji je fabrički urađen zameniti, odnosno, izbaciti iz rolne.",
        "",
        "NAPOMENA:",
        RASECANJE,
        "Pri odmotavanju gotove rolnice napred ide slovo „o“ u nazivu „Demo“.",
        "Upakovati u kutije.",
        "",
        *datum_potpis_lines("2025-07-18"),
    ]
    assert [centred for _runs, centred in order_lines(ORDER)][:3] == [True, True, False]


def test_empty_fields_leave_the_label_alone_and_optional_lines_out():
    order = {"broj": 7, "kolicina": ("", ""), "rok": "2025-07-24", "datum": "2025-07-18"}
    lines = texts(order)

    assert "MAŠINA:" in lines and "ALATI:" in lines and "OPIS:" in lines and "KOLIČINA:" in lines
    assert lines[lines.index("ŠIFRA BOJA:") + 1] == " "      # no colour rows, Štampa or napred line
    assert lines[lines.index("NAPOMENA:") + 1] == ""          # no NAPOMENA lines


def test_a_long_colour_row_keeps_one_space_before_the_cylinder():
    row = dict(ROWS[0], color_text="Pantone 2945 C i Pantone 7406 C, štampa na lepku, preko celog polja")
    line = texts(dict(ORDER, boje=[row]))[22]
    assert line.endswith("polja, raster 390l/cm, Z-93")



def test_each_line_typed_in_a_text_box_is_its_own_paragraph():
    order = dict(ORDER, stampa=STAMPA + "\nPrema odobrenom uzorku kupca.",
                 rasecanje=RASECANJE + "\n\nSvaku rolnu obeležiti brojem.")
    lines = texts(order)

    assert lines[lines.index(STAMPA) + 1] == "Prema odobrenom uzorku kupca."
    assert lines[lines.index(RASECANJE) + 1] == "Svaku rolnu obeležiti brojem."
    assert runs_of(order, "Svaku rolnu") == [("Svaku rolnu obeležiti brojem.", B)]

# ── formatting ───────────────────────────────────────────────────────────────

def test_name_quantity_and_delivery_date_formatting():
    assert runs_of(ORDER, "NAZIV:") == [("NAZIV:" + " " * 24 + "nalepnica ", B), ("Demo sok 0,5 l, P+Z", BI14)]
    assert runs_of(ORDER, "KOLIČINA:") == [
        ("KOLIČINA:" + " " * 17 + "4930 m dobrih (100.000 kom)", B), (" (20,32 kom/m) - 3 reda", S11),
    ]
    assert runs_of(ORDER, "ROK") == [("ROK ZA ISPORUKU: ", BI14), ("24.07.2025.", BI14)]


@pytest.mark.parametrize("line, runs", [
    (STAMPA, [(STAMPA[:-11], BI14), ("04.04.2025.", I)]),
    ("Štampa prema pripremi i prema uzorcima odštampanim u prethodnim serijama (12.08.2026 i 15.11.2026).",
     [("Štampa prema pripremi i prema uzorcima odštampanim u prethodnim serijama ", BI14),
      ("(12.08.2026 i 15.11.2026).", I11)]),
    ("Štampa prema odobrenom uzorku kupca.", [("Štampa prema odobrenom uzorku kupca.", BI14)]),
])
def test_stampa_line_formatting(line, runs):
    assert runs_of(dict(ORDER, stampa=line), "Štampa") == runs


def test_napred_ide_and_unwinding_lines_formatting():
    assert runs_of(ORDER, "Pri štampi") == [
        ("Pri štampi napred ide ", BI), ("slovo ", B), ("„D“ ", B14), ("u nazivu", B),
        (" „", B14), ("Demo", BI14), ("“", B14), (".", BI),
    ]
    assert runs_of(ORDER, "Pri odmotavanju") == [
        ("Pri odmotavanju gotove rolnice napred ide slovo ", B), ("„o“ ", B14), ("u nazivu", B),
        (" „", B14), ("Demo", BI14), ("“", B14), (".", BI),
    ]
    typed = "Pri odmotavanju napred ide kraj sa logom."   # changed by hand: plain bold
    assert runs_of(dict(ORDER, odmotavanje=typed), "Pri odmotavanju") == [(typed, B)]


def test_slitting_line_formatting():
    assert runs_of(ORDER, "Raseći") == [
        ("Raseći na čaure Ø45/Ø52/65 mm, 99 rolni x 1.000 kom/rolna", B),
        ("-1476 otkucaja/rolna + ", S11), ("3", B11),
        (" rolne x 335 kom/rolna", B),
        ("-495 otkucaja/rolna (max. Ø150mm),", S11),
    ]
    plain = "Raseći, 100 rolni x 1.000 kom/rolna,"   # no die: no counter lengths
    assert runs_of(dict(ORDER, rasecanje=plain), "Raseći") == [(plain, B)]


def test_date_and_signature_formatting():
    datum, dan, potpis = (runs for runs, _ in order_lines(ORDER)[-3:])
    assert [fmt for _, fmt in datum + dan + potpis] == [N, B, B]


# ── the Word file ────────────────────────────────────────────────────────────

def test_word_file_page_font_and_runs(tmp_path):
    path = tmp_path / "6276 - nalepnica Demo.docx"
    order_docx.write_order(path, ORDER)

    doc = docx.Document(str(path))
    section = doc.sections[0]
    assert (round(section.page_width.mm, 1), round(section.page_height.mm, 1)) == (215.9, 279.4)
    assert [round(m.mm) for m in (section.left_margin, section.right_margin,
                                  section.top_margin, section.bottom_margin)] == [10, 5, 5, 3]
    normal = doc.styles["Normal"]
    assert (normal.font.name, normal.font.size) == ("Arial", Pt(12))
    assert normal.paragraph_format.space_after == Pt(0)

    assert [p.text for p in doc.paragraphs] == texts(ORDER)
    naziv = next(p for p in doc.paragraphs if p.text.startswith("NAZIV:"))
    assert [(r.bold, r.italic, r.font.size) for r in naziv.runs] == [(True, None, None), (True, True, Pt(14))]
    assert not list(tmp_path.glob(".*"))   # the file appears whole, no temporary file is left


def test_the_watcher_reads_the_word_file_back(tmp_path):
    path = tmp_path / "6276 - nalepnica Demo.docx"
    order_docx.write_order(path, ORDER)

    meta = watcher.parse_production_order(path)

    assert watcher.parse_warnings(meta) == []
    assert {key: meta[key] for key in (
        "doc_number", "masina", "sifra", "naziv", "dimenzija", "materijal", "sirina", "narucilac",
        "kolicina_text", "kolicina_m_dobrih", "kolicina_kom_naruceno", "rok_isporuke",
        "alati_raw", "stancna_code", "datum_doc",
    )} == {
        "doc_number": 6276, "masina": "Nilpeter FA2500", "sifra": "DEMO-250101",
        "naziv": "nalepnica Demo sok 0,5 l, P+Z", "dimenzija": "65 x 140 mm", "materijal": "PE WHITE",
        "sirina": "235 mm", "narucilac": "Primer d.o.o., Beograd",
        "kolicina_text": "4930 m dobrih (100.000 kom) (20,32 kom/m) - 3 reda",
        "kolicina_m_dobrih": 4930, "kolicina_kom_naruceno": 100_000, "rok_isporuke": "2025-07-24",
        "alati_raw": "štancna oznake ABC23-09-12345 (XYZ-042S), Z-93",
        "stancna_code": "ABC23-09-12345", "datum_doc": "2025-07-18",
    }
    assert meta["kolicina_kom_po_m"] == pytest.approx(20.32)
    assert [(r["position_label"], r["klise_code"], r["variant"], r["color_text"], r["raster"], r["cylinder"])
            for r in meta["color_rows"]] == [
        (pos, "0000", var, color, "390l/cm", "Z-93") for pos, var, color in CMYK
    ] + [("VIII", "uređaj za lakiranje", None, "UV lak", "160l/cm", "Z-88")]
    assert meta["opis"] == " | ".join(OPIS_DEFAULT.splitlines())
    assert meta["napomena"] == " | ".join([RASECANJE, odmotavanje_text("D", "Demo"), NAPOMENA_DEFAULT])


# ── where the file goes ──────────────────────────────────────────────────────

@pytest.mark.parametrize("naziv", [
    "nalepnica Demo sok 0,5 l, P+Z", 'etiketa "Demo" 1/2 l: *akcija*', "  ", "", "x" * 120,
])
def test_file_title_is_made_as_the_watcher_makes_it(naziv):
    assert order_docx.file_title(naziv) == watcher.sanitize_title_for_filename(naziv, "nedefinisano")


def test_order_file(tmp_path):
    today = datetime.date(2026, 11, 20)

    # the file the database has for the order
    assert order_docx.order_file(tmp_path, 6276, "x", "2026/10/02/6276 - x.docx", today) == \
        tmp_path / "2026/10/02/6276 - x.docx"
    # a new one in today's folder, named as the watcher names them
    assert order_docx.order_file(tmp_path, 6276, "nalepnica Demo: sok", None, today) == \
        tmp_path / "2026/11/20/6276 - nalepnica Demo sok.docx"
    # one of the watcher's naming already in the folder, not yet in the database
    old = tmp_path / "2026/11/19/6276 - nalepnica Demo.docx"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"")
    (old.parent / ".6276 - nalepnica Demo.docx.tmp").write_bytes(b"")
    (old.parent / "62760 - druga.docx").write_bytes(b"")
    assert order_docx.order_file(tmp_path, 6276, "nalepnica Demo", None, today) == old
