"""The watcher's production-order parser and its helpers.

Orders here are synthetic: fictional products and customers laid out the way
the parser expects a real order (one field per paragraph).
"""
import pytest

from formatting import fmt_float_sr, fmt_int_sr
from server import watcher_v2_1 as watcher

ORDER = [
    "NALOG ZA PROIZVODNJU 6276",
    "MAŠINA: Nilpeter FA2500",
    "ŠIFRA: DEMO-250101",
    "NAZIV: nalepnica Demo sok 0,5 l, P+Z",
    "DIMENZIJA: 65 x 140 mm",
    "MATERIJAL: PE WHITE",
    "ŠIRINA: 235 mm",
    "NARUČILAC: Primer d.o.o., Beograd",
    "KOLIČINA: 1650 m dobrih (20.000 kom) (12,23 kom/m)",
    "ROK ZA ISPORUKU: 24.07.2025.",
    "ALATI: štanca ABC25-02-12345, obim 225,417 mm, raspored 3 x 2",
    "ŠIFRA BOJA:",
    "I kliše oznake DEMO-01, P, boja Pantone 286 C, raster 390l/cm, Z-93",
    "II kl.ozn. DEMO-02, Z, Cyan, ras. 400l/cm, Z-93 (novi)",
    "(boje prema odobrenom uzorku)",
    "VIII uređaj za lakiranje, UV lak, raster 160l/cm, Z-63",
    "OPIS: smer odmotavanja 4",
    "jezgro 76 mm",
    "NAPOMENA: hitna isporuka",
    "-------------------------",
    "24.06.2025.",
]


# ── whole documents ──────────────────────────────────────────────────────────

def test_parses_a_complete_order(make_docx):
    meta = watcher.parse_production_order(make_docx(ORDER))

    assert meta["doc_number"] == 6276
    assert meta["masina"] == "Nilpeter FA2500"
    assert meta["sifra"] == "DEMO-250101"
    assert meta["naziv"] == "nalepnica Demo sok 0,5 l, P+Z"
    assert meta["dimenzija"] == "65 x 140 mm"
    assert meta["materijal"] == "PE WHITE"
    assert meta["sirina"] == "235 mm"
    assert meta["narucilac"] == "Primer d.o.o., Beograd"
    assert meta["kolicina_text"] == "1650 m dobrih (20.000 kom) (12,23 kom/m)"
    assert meta["kolicina_m_dobrih"] == 1650
    assert meta["kolicina_kom_naruceno"] == 20000
    assert meta["kolicina_kom_po_m"] == pytest.approx(12.23)
    assert meta["rok_isporuke"] == "2025-07-24"
    assert meta["alati_raw"] == "štanca ABC25-02-12345, obim 225,417 mm, raspored 3 x 2"
    assert meta["stancna_code"] == "ABC25-02-12345"
    assert meta["opis"] == "smer odmotavanja 4 | jezgro 76 mm"
    assert meta["napomena"] == "hitna isporuka"
    assert meta["datum_doc"] == "2025-06-24"
    assert meta["full_text"] == "\n".join(ORDER)
    assert watcher.parse_warnings(meta) == []


def test_parses_colour_and_lacquer_rows(make_docx):
    rows = watcher.parse_production_order(make_docx(ORDER))["color_rows"]

    assert rows == [
        {
            "position_num": 1, "position_label": "I",
            "klise_code": "DEMO-01", "variant": "P", "color_text": "Pantone 286 C",
            "raster": "390l/cm", "cylinder": "Z-93", "supplier": None, "note": None,
        },
        {   # abbreviated "kl.ozn.", no "boja", "ras." prefix, cylinder note kept
            "position_num": 2, "position_label": "II",
            "klise_code": "DEMO-02", "variant": "Z", "color_text": "Cyan",
            "raster": "400l/cm", "cylinder": "Z-93 (novi)", "supplier": None, "note": None,
        },
        {   # the annotation line in between is skipped
            "position_num": 3, "position_label": "VIII",
            "klise_code": "uređaj za lakiranje", "variant": None, "color_text": "UV lak",
            "raster": "160l/cm", "cylinder": "Z-63", "supplier": None, "note": None,
        },
    ]


def test_labels_without_diacritics(make_docx):
    meta = watcher.parse_production_order(make_docx([
        "MASINA: Mark Andy",
        "SIFRA: DEMO-1",
        "SIRINA: 120 mm",
        "NARUCILAC: Primer d.o.o.",
        "KOLICINA: 500 m dobrih (5.000 pari) (10,5 pari/m)",
    ]))

    assert meta["masina"] == "Mark Andy"
    assert meta["sifra"] == "DEMO-1"
    assert meta["sirina"] == "120 mm"
    assert meta["narucilac"] == "Primer d.o.o."
    assert meta["kolicina_kom_naruceno"] == 5000
    assert meta["kolicina_kom_po_m"] == pytest.approx(10.5)


def test_colour_section_ends_at_next_field(make_docx):
    meta = watcher.parse_production_order(make_docx([
        "ŠIFRA BOJA:",
        "I kliše oznake DEMO-01, P, boja Crna, raster 390l/cm, Z-93",
        "ALATI: ABC25-02-12345",
    ]))

    assert len(meta["color_rows"]) == 1
    assert meta["stancna_code"] == "ABC25-02-12345"


def test_description_ends_at_a_later_field(make_docx):
    # Some older orders put MATERIJAL / ALATI after OPIS
    meta = watcher.parse_production_order(make_docx([
        "OPIS: smer odmotavanja 4",
        "jezgro 76 mm",
        "MATERIJAL: PP transparent",
        "ALATI: xyz14-05-54321",
    ]))

    assert meta["opis"] == "smer odmotavanja 4 | jezgro 76 mm"
    assert meta["materijal"] == "PP transparent"
    assert meta["stancna_code"] == "XYZ14-05-54321"


def test_template_placeholder_number_is_not_an_order_number(make_docx):
    meta = watcher.parse_production_order(make_docx(["NALOG ZA PROIZVODNJU 0001"]))

    assert meta["doc_number"] is None
    assert "missing document number" in watcher.parse_warnings(meta)


def test_unreadable_file_gives_empty_result(tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a Word document")

    assert watcher.parse_production_order(path) == {}


# ── parse warnings ───────────────────────────────────────────────────────────

def test_warnings_for_an_empty_order():
    assert watcher.parse_warnings({}) == [
        "missing document number",
        "missing ŠIFRA",
        "missing NAZIV",
        "missing DIMENZIJA",
        "missing ROK ZA ISPORUKU",
        "missing KOLIČINA",
        "missing ALATI",
        "no color/lacquer rows parsed",
    ]


@pytest.mark.parametrize("prefixes, text, expected", [
    ("", "štanca ABC25-02-12345, obim 225,417 mm", "ABC25-02-12345"),
    ("", "DEMO-T-001", "DEMO-T-001"),
    ("", "štanca po uzorku, Z-93, 3 x 2", None),
    ("", "štanca ABC25-02-12345A", None),    # not cut short to "ABC25-02"
    ("", "ABC-12345-B", None),
    ("ABC,XYZ", "štanca ABC25-02-12345A", "ABC25-02-12345A"),
    ("ABC,XYZ", "PE-60, štanca ABC25-02-12345", "ABC25-02-12345"),   # listed prefixes only
    ("ABC,XYZ", "XYZ7", "XYZ7"),                                     # no hyphen needed
    (" ABC , XYZ ,", "xyz14-05-54321", "xyz14-05-54321"),
    ("ABC,XYZ", "DEMO-T-001", None),
])
def test_die_code_pattern(prefixes, text, expected):
    m = watcher._stancna_re(prefixes).search(text)

    assert (m.group(0) if m else None) == expected


def test_warns_when_die_code_is_not_recognised():
    warnings = watcher.parse_warnings({"alati_raw": "štanca po uzorku"})

    assert "ALATI found but die/tool code was not extracted" in warnings


@pytest.mark.parametrize("line, warning", [
    ("KOLIČINA: po dogovoru",                            "KOLIČINA found but not extracted: kom"),
    ("KOLIČINA: (1,5 kom)",                              "KOLIČINA found but not extracted: kom"),
    ("KOLIČINA: 1650 m dobrih (20.000 kom) (12,2,3 kom/m)", "KOLIČINA found but not extracted: kom/m"),
    ("KOLIČINA: 1645,5 m dobrih (20.000 kom)",           "KOLIČINA found but not extracted: m dobrih"),
    ("KOLIČINA: 2 role po 10.000 kom",                   "KOLIČINA found but not extracted: kom"),
    ("KOLIČINA: 20.000 - 25.000 kom",                    "KOLIČINA found but not extracted: kom"),
    ("KOLIČINA: 1650 m dobrih (2 x 10.000 kom) (12,23 kom/m)",
     "KOLIČINA found but not extracted: m dobrih, kom, kom/m"),
    ("KOLIČINA: 1650 m, dodati 50 m (20.000 kom)",       "KOLIČINA found but not extracted: m dobrih, kom"),
    ("KOLIČINA: (20.000 kom) - rolne po 500 m",          "KOLIČINA found but not extracted: kom"),
])
def test_warns_about_quantity_figures_that_are_not_extracted(make_docx, line, warning):
    meta = watcher.parse_production_order(make_docx(["ŠIFRA: DEMO-1", line]))

    assert meta["kolicina_text"]
    assert warning in watcher.parse_warnings(meta)


@pytest.mark.parametrize("line", [
    "KOLIČINA: 20 m dobrih (25.000 kom) (1.234,50 kom/m)",
    "KOLIČINA: (20.000 kom)",               # the GUI's line when no die is chosen
    "KOLIČINA: 1650 m dobrih (20.000 kom)",  # no per-metre figure written
    "KOLIČINA: 1650 m (20.000 kom)",
])
def test_no_quantity_warning_when_written_figures_are_extracted(make_docx, line):
    meta = watcher.parse_production_order(make_docx([line]))

    assert not [w for w in watcher.parse_warnings(meta) if w.startswith("KOLIČINA")]


# ── field helpers ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("24.07.2025.", "2025-07-24"),
    ("24.07.2025", "2025-07-24"),
    ("1.2.2026", "2026-02-01"),
    ("do 05.11.2025. najkasnije", "2025-11-05"),
    ("31.09.2025", None),   # no 31st of September
    ("odmah", None),
])
def test_to_iso_date(text, expected):
    assert watcher._to_iso_date(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("1645 m  dobrih    (20.000 kom )   (12,23 kom/m)", (1645, 20000, 12.23)),
    ("1.645 m dobrih (20.000 kom) (12,23 kom/m)", (1645, 20000, 12.23)),
    ("500 m dobrih (5.000 pari) (10,5 pari/m)", (500, 5000, 10.5)),
    ("300 m dobrih (1.200 kompleta) (4 kompleta/m)", (300, 1200, 4.0)),
    ("20 m dobrih (25.000 kom) (1.234,50 kom/m)", (20, 25000, 1234.5)),
    ("2 m dobrih (2.500.000 kom) (1.234.567,8 kom/m)", (2, 2500000, 1234567.8)),
    ("1650 m dobrih (20.000 kom) (12.23 kom/m)", (1650, 20000, 12.23)),
    ("1650 m dobrih (20.000,00 kom) (12,23 kom/m)", (1650, 20000, 12.23)),
    ("1650 m dobrih (20 000 kom) (12,23 kom/m)", (1650, 20000, 12.23)),
    ("1650 m dobrih (20,000 kom) (12,23 kom/m)", (1650, 20000, 12.23)),
    ("1650 m dobrih (20000.00 kom) (12,23 kom/m)", (1650, 20000, 12.23)),
])
def test_parse_quantity(text, expected):
    q = watcher._parse_quantity(text)

    assert (q["kolicina_m_dobrih"], q["kolicina_kom_naruceno"]) == expected[:2]
    assert q["kolicina_kom_po_m"] == pytest.approx(expected[2])


@pytest.mark.parametrize("text, expected", [
    ("(20.000 kom)", {"kolicina_kom_naruceno": 20000}),
    ("20.000 kom", {"kolicina_kom_naruceno": 20000}),
    ("(20.000,00 kom)", {"kolicina_kom_naruceno": 20000}),
    ("(5.000 pari)", {"kolicina_kom_naruceno": 5000}),
    ("1650 m dobrih (20.000 kom)", {"kolicina_m_dobrih": 1650, "kolicina_kom_naruceno": 20000}),
    ("(20 000,00 kom)", {"kolicina_kom_naruceno": 20000}),
    ("(1 500,00 kom)", {"kolicina_kom_naruceno": 1500}),
    ("1 000 000,00 kom", {"kolicina_kom_naruceno": 1000000}),
    ("1650 m (20.000 kom)", {"kolicina_m_dobrih": 1650, "kolicina_kom_naruceno": 20000}),
    ("1650 metara dobrih (20.000 kom)", {"kolicina_m_dobrih": 1650, "kolicina_kom_naruceno": 20000}),
    ("1650 m. dobrih (20.000 kom)", {"kolicina_m_dobrih": 1650, "kolicina_kom_naruceno": 20000}),
    ("(20.000 kom) - hitno", {}),           # a note could change the count
    ("(10.000 kom) - po roli", {}),
    ("(10.000 kom) - x 2", {}),
    ("(1,5 kom)", {}),                       # not a piece count
    ("po dogovoru", {}),
    # Any other layout is left for review: per-roll or per-variant counts,
    # ranges, sums, tolerances, dates in front, odd grouping
    ("2 role po 10.000 kom", {}),
    ("(2 x 10.000 kom)", {}),
    ("2x10.000 kom", {}),
    ("10.000 kom x 2", {}),
    ("(10.000 kom) x 2", {}),
    ("10.000 kom po varijanti", {}),
    ("1.000 kom na roli, ukupno 20.000 kom", {}),
    ("(20.000 kom) - 2 role po 10.000 kom", {}),
    ("20.000 - 25.000 kom", {}),
    ("P 10.000 + Z 10.000 kom", {}),
    ("20.000 ± 500 kom", {}),
    ("do 15.08. 500 kom", {}),
    ("do 24/07 500 kom", {}),
    ("20'000 kom", {}),
    ("(12,23 kom/m)", {}),
    ("(20.000 kom) (1 234,50 kom/m)", {}),
    ("1650 m dobrih (2 x 10.000 kom) (12,23 kom/m)", {}),
    # More than the column holds: a date glued to the metres (full-line pattern)
    ("isporuka 24.07.2025. 650 m dobrih (8.000 kom) (12,23 kom/m)",
     {"kolicina_kom_naruceno": 8000, "kolicina_kom_po_m": 12.23}),
])
def test_quantity_line_with_some_figures(text, expected):
    assert watcher._parse_quantity(text) == expected


@pytest.mark.parametrize("m_dobrih, kom, kom_po_m", [
    (1650, 20_000, 12.231),
    (12_340, 1_250_000, 101.3),
    (10, 5, 0.5),
    (20, 25_000, 1234.5),        # "1.234,50 kom/m"
    (1, 1_500_000, 1_234_567.8),
    (3, 3_000, 999.999),         # rounds up to "1.000,00 kom/m"
])
def test_reads_the_quantity_line_the_gui_writes(m_dobrih, kom, kom_po_m):
    # Same format string as the GUI (recompute_kolicina_display, KolicinaDialog)
    line = f"{m_dobrih} m dobrih ({fmt_int_sr(kom)} kom) ({fmt_float_sr(kom_po_m, 2)} kom/m)"
    line += " - hitno"   # a free-text note may follow

    q = watcher._parse_quantity(line)

    assert q["kolicina_m_dobrih"] == m_dobrih
    assert q["kolicina_kom_naruceno"] == kom
    assert q["kolicina_kom_po_m"] == pytest.approx(round(kom_po_m, 2))


# ── order numbers and file names ─────────────────────────────────────────────

@pytest.mark.parametrize("stem, expected", [
    ("6276 - nalepnica Demo", 6276),
    ("6276 - nalepnica Demo_2", 6276),   # the watcher's de-duplicated name
    ("6276", 6276),
    ("nalog 6276", None),
    ("20251006 sken", None),             # a date-like number is not adopted
    ("0001 - sablon", None),             # template placeholder
])
def test_detect_number_from_filename(stem, expected):
    assert watcher.detect_number_from_filename(stem) == expected


@pytest.mark.parametrize("text, expected", [
    ("Firma\nNALOG ZA PROIZVODNJU 6276\nMAŠINA: X", 6276),
    ("nalog za proizvodnju 15", 15),
    ("NALOG ZA PROIZVODNJU 0001", None),
    ("", None),
])
def test_detect_number_from_text(text, expected):
    assert watcher.detect_number_from_text(text) == expected


@pytest.mark.parametrize("title, fallback, expected", [
    ('Etiketa 1/2: "Demo"*', "x", "Etiketa 1 2 Demo"),
    ("", "6276 - stari naziv", "6276 - stari naziv"),
    ("", "", "nedefinisano"),
    ("a" * 100, "", "a" * 80),
])
def test_sanitize_title_for_filename(title, fallback, expected):
    assert watcher.sanitize_title_for_filename(title, fallback) == expected
