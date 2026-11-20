"""The order's fixed text lines, word for word as in the order template."""
import pytest

from order_text import (
    KOM_PO_ROLNI_DEFAULT, MAX_D_DEFAULT, NAPOMENA_DEFAULT, OPIS_DEFAULT,
    alati_text, caure_text, datum_potpis_lines, datum_text, napomena_text,
    napred_ide_text, obrnuto_slovo, odmotavanje_text, otkucaji, ranije_serije,
    rasecanje_text, rolne_word, split_rolls, stampa_text, stancna_oznake,
)

RUNS = [
    {"datum": "2026-08-12", "doc_number": 6270},
    {"datum": "2026-11-15", "doc_number": 6276},
    {"datum": "2026-04-04", "doc_number": None},    # a date added by hand
    {"datum": "2026-12-29", "doc_number": 6280},
]


@pytest.mark.parametrize("doc_number, expected", [
    (None, ["2026-04-04", "2026-08-12", "2026-11-15", "2026-12-29"]),   # no number yet
    (6290, ["2026-04-04", "2026-08-12", "2026-11-15", "2026-12-29"]),   # a new order: all are earlier
    (6276, ["2026-04-04", "2026-08-12"]),      # a saved order: not its own run, nor later ones
    (6270, ["2026-04-04"]),
    (6280, ["2026-04-04", "2026-08-12", "2026-11-15"]),
])
def test_ranije_serije(doc_number, expected):
    assert ranije_serije(RUNS, doc_number) == expected


def test_ranije_serije_of_a_product_without_runs():
    assert ranije_serije([], 6276) == []


def test_stampa_line_for_a_first_run_names_the_proof():
    assert stampa_text([], "2025-04-04") == (
        "Štampa prema pripremi, prema uzorcima odštampanim kao probni uzorak 04.04.2025."
    )


@pytest.mark.parametrize("serije, joined", [
    (["2026-08-12"], "12.08.2026"),
    (["2026-08-12", "2026-11-15"], "12.08.2026 i 15.11.2026"),
    (["2026-08-12", "2026-11-15", "2026-12-29"], "12.08.2026,15.11.2026 i 29.12.2026"),
    (["2026-12-29", "2026-08-12", "2026-11-15"], "12.08.2026,15.11.2026 i 29.12.2026"),   # in date order
])
def test_stampa_line_lists_the_earlier_runs(serije, joined):
    assert stampa_text(serije, "2025-04-04") == (
        f"Štampa prema pripremi i prema uzorcima odštampanim u prethodnim serijama ({joined})."
    )


def test_slitting_defaults():
    assert (KOM_PO_ROLNI_DEFAULT, MAX_D_DEFAULT) == ("1.000", "150")


def test_napred_ide_sentence():
    assert napred_ide_text("D", "Demo") == "Pri štampi napred ide slovo „D“ u nazivu „Demo“."


def test_napred_ide_uses_serbian_quotation_marks():
    text = napred_ide_text("D", "Demo")

    assert text.count("„") == 2   # „ opening, low
    assert text.count("“") == 2   # “ closing, high


def test_napred_ide_trims_input():
    assert napred_ide_text("  D ", " Demo sok ") == "Pri štampi napred ide slovo „D“ u nazivu „Demo sok“."


@pytest.mark.parametrize("slovo, naziv", [("", "Demo"), ("D", ""), ("  ", "  "), (None, None)])
def test_napred_ide_is_empty_until_both_are_given(slovo, naziv):
    assert napred_ide_text(slovo, naziv) == ""
    assert odmotavanje_text(slovo, naziv) == ""


@pytest.mark.parametrize("slovo, naziv, expected", [
    ("D", "Demo", "o"),             # first letter at the press -> last when unwinding
    ("o", "Demo", "D"),             # and the other way round
    ("d", "Demo", "o"),             # any case; the answer is written as in the name
    ("O", "Demo", "D"),
    ("D", "Demo ...", "o"),         # dots after the name are not its last letter
    ("k", "Demo sok", "D"),
    ("A", "Ana", "a"),              # same letter at both ends: as written wins
    ("a", "Ana", "A"),
    ("e", "Demo", ""),              # at neither end: nothing to propose
    ("De", "Demo", ""),
    ("", "Demo", ""),
    ("D", "", ""),
    (None, None, ""),
])
def test_obrnuto_slovo(slovo, naziv, expected):
    assert obrnuto_slovo(slovo, naziv) == expected


def test_odmotavanje_sentence_names_the_other_end_of_the_name():
    assert odmotavanje_text("D", "Demo") == (
        "Pri odmotavanju gotove rolnice napred ide slovo „o“ u nazivu „Demo“."
    )


def test_odmotavanje_is_empty_when_the_letter_is_at_neither_end():
    assert odmotavanje_text("e", "Demo") == ""


@pytest.mark.parametrize("oznaka, zuba, expected", [
    ("0000", 93, "štancna oznake 0000, Z-93"),
    ("ABC25-02-12345", "93", "štancna oznake ABC25-02-12345, Z-93"),
    ("ABC25-02-12345", 93.0, "štancna oznake ABC25-02-12345, Z-93"),
    (" 0000 ", 88, "štancna oznake 0000, Z-88"),
    ("0000", None, "štancna oznake 0000"),
    ("0000", "", "štancna oznake 0000"),
    ("", 93, ""),
    (None, 93, ""),
])
def test_alati_line(oznaka, zuba, expected):
    assert alati_text(oznaka, zuba) == expected


@pytest.mark.parametrize("oznaka, zuba, interna, expected", [
    # the die maker's code, then the shop's own code in brackets
    ("ABC23-09-12345", 96, "XYZ-042S", "štancna oznake ABC23-09-12345 (XYZ-042S), Z-96"),
    ("ABC23-09-12345", None, " XYZ-042S ", "štancna oznake ABC23-09-12345 (XYZ-042S)"),
    ("ABC23-09-12345", 96, "abc23-09-12345", "štancna oznake ABC23-09-12345, Z-96"),   # the same: once
    ("ABC23-09-12345", 96, "-", "štancna oznake ABC23-09-12345, Z-96"),                # a dash: none
    ("ABC23-09-12345", 96, None, "štancna oznake ABC23-09-12345, Z-96"),
    ("", 96, "XYZ-042S", ""),                                    # no maker's code, no line
])
def test_alati_line_with_the_shops_own_code(oznaka, zuba, interna, expected):
    assert alati_text(oznaka, zuba, interna) == expected


@pytest.mark.parametrize("oznaka, interna, expected", [
    ("ABC23-09-12345", "XYZ-042S", "ABC23-09-12345 (XYZ-042S)"),
    ("ABC23-09-12345", "ABC23-09-12345", "ABC23-09-12345"),
    ("ABC23-09-12345", "ABC23 -09-12345", "ABC23-09-12345"),
    ("ABC23-09-12345", "—", "ABC23-09-12345"),
    ("ABC23-09-12345", "", "ABC23-09-12345"),
    ("", "XYZ-042S", "XYZ-042S"),          # only the own code (the die summary shows it)
    (None, None, ""),
])
def test_stancna_oznake(oznaka, interna, expected):
    assert stancna_oznake(oznaka, interna) == expected


def test_opis_default_is_the_two_standard_sentences():
    assert OPIS_DEFAULT.splitlines() == [
        "Svaki nastavak rolne izvršiti precizno zbog mašinskog etiketiranja.",
        "Nastavak koji je fabrički urađen zameniti, odnosno, izbaciti iz rolne.",
    ]


def test_napomena_default():
    assert NAPOMENA_DEFAULT == "Upakovati u kutije."


# ── NAPOMENA: slitting into rolls ────────────────────────────────────────────

@pytest.mark.parametrize("n, word", [
    (1, "rolna"), (21, "rolna"), (101, "rolna"),
    (2, "rolne"), (3, "rolne"), (4, "rolne"), (22, "rolne"), (34, "rolne"),
    (5, "rolni"), (10, "rolni"), (11, "rolni"), (12, "rolni"), (14, "rolni"),
    (99, "rolni"), (111, "rolni"), (112, "rolni"),
])
def test_rolne_word(n, word):
    assert rolne_word(n) == word


@pytest.mark.parametrize("kom, stancna, rows_long, expected", [
    (1000, 295.275, 2, 1476),     # Z-93 die, 2 rows along: 147,64 mm per label
    (335, 295.275, 2, 495),
    (1000, 225.425, 1, 2254),     # Z-71, 1 row along
    (1000, None, 2, None),        # no die chosen
    (1000, 295.275, None, None),
    (None, 295.275, 2, None),
])
def test_otkucaji(kom, stancna, rows_long, expected):
    assert otkucaji(kom, stancna, rows_long) == expected


@pytest.mark.parametrize("total, per_roll, lanes, expected", [
    (100_000, 1000, 3, [(99, 1000), (3, 335)]),   # 1.000 left over 3 lanes -> 334 -> 335
    (99_000, 1000, 3, [(99, 1000)]),              # whole sets only
    (100_000, 1000, 1, [(100, 1000)]),
    (100_000, 1000, None, [(100, 1000)]),         # lanes unknown: one lane
    (500, 1000, 3, [(3, 170)]),                   # less than a set: rest only
    (2_997, 1000, 3, [(3, 1000)]),                # rest rounds up to a full set
    (20_000, 3000, 2, [(6, 3000), (2, 1000)]),
    (None, 1000, 3, []),
    (100_000, None, 3, []),
    (100_000, 0, 3, []),
])
def test_split_rolls(total, per_roll, lanes, expected):
    assert split_rolls(total, per_roll, lanes) == expected


@pytest.mark.parametrize("unutra, spolja, sirina, expected", [
    ("45", "52", "65", "Ø45/Ø52/65 mm"),
    (" 40 ", "45", "90", "Ø40/Ø45/90 mm"),
    ("Ø45", "ø52", "65 mm", "Ø45/Ø52/65 mm"),   # typed with Ø or mm anyway
    ("76", "", "", "Ø76 mm"),
    ("76", "", "65", "Ø76/65 mm"),
    ("", "", "", ""),
    (None, None, None, ""),
])
def test_caure_text(unutra, spolja, sirina, expected):
    assert caure_text(unutra, spolja, sirina) == expected


def test_rasecanje_line_as_in_the_order_template():
    line = rasecanje_text(caure_text("45", "52", "65"), [(99, 1000), (3, 335)], 295.275, 2, "150")

    assert line == (
        "Raseći na čaure Ø45/Ø52/65 mm, 99 rolni x 1.000 kom/rolna-1476 otkucaja/rolna"
        " + 3 rolne x 335 kom/rolna-495 otkucaja/rolna (max. Ø150mm),"
    )


def test_rasecanje_line_for_two_lanes_and_four_labels_around():
    # 2.450 kom on a Z-81 die (257,175 mm), 2 lanes, 4 around: 64,29 mm per label
    groups = split_rolls(2450, 1225, 2)
    line = rasecanje_text(caure_text("40", "45", "90"), groups, 257.175, 4, "Ø300 mm")

    assert groups == [(2, 1225)]
    assert line == "Raseći na čaure Ø40/Ø45/90 mm, 2 rolne x 1.225 kom/rolna-788 otkucaja/rolna (max. Ø300mm),"


def test_rasecanje_line_without_die_cores_or_max():
    assert rasecanje_text("", [(100, 1000)], None, None, "") == "Raseći, 100 rolni x 1.000 kom/rolna,"


def test_rasecanje_line_is_empty_without_groups():
    assert rasecanje_text("Ø76 mm", [], 295.275, 2, "150") == ""


def test_napomena_joins_the_lines_given():
    assert napomena_text("A,", "", "  ", "Upakovati u kutije.\n") == "A,\nUpakovati u kutije."


# ── the bottom: date and signature ───────────────────────────────────────────

@pytest.mark.parametrize("iso, expected", [
    ("2025-07-18", "18.07.2025."),
    ("2026-01-05", "05.01.2026."),
    ("", ""),
    (None, ""),
])
def test_datum_text(iso, expected):
    assert datum_text(iso) == expected


def test_date_and_signature_lines_as_in_the_order_template():
    datum, date, line = datum_potpis_lines("2025-07-18")

    assert datum == " " * 9 + "Datum" + " " * 94 + "Potpis,"
    assert date == "      18.07.2025."
    assert line == " " * 101 + "-" * 32
