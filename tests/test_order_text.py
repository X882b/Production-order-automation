"""The order's fixed text lines, word for word as in the order template."""
import pytest

from order_text import (
    NAPOMENA_DEFAULT, OPIS_DEFAULT, alati_text, caure_text, napomena_text,
    napred_ide_text, obrnuto_slovo, odmotavanje_text, otkucaji, rasecanje_text,
    rolne_word, split_rolls,
)


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
