"""The order's fixed text lines, word for word as in the order template."""
import pytest

from order_text import OPIS_DEFAULT, alati_text, napred_ide_text


def test_napred_ide_sentence():
    assert napred_ide_text("W", "EHW") == "Pri štampi napred ide slovo „W“ u nazivu „EHW“."


def test_napred_ide_uses_serbian_quotation_marks():
    text = napred_ide_text("W", "EHW")

    assert text.count("„") == 2   # „ opening, low
    assert text.count("“") == 2   # “ closing, high


def test_napred_ide_trims_input():
    assert napred_ide_text("  W ", " Demo sok ") == "Pri štampi napred ide slovo „W“ u nazivu „Demo sok“."


@pytest.mark.parametrize("slovo, naziv", [("", "EHW"), ("W", ""), ("  ", "  "), (None, None)])
def test_napred_ide_is_empty_until_both_are_given(slovo, naziv):
    assert napred_ide_text(slovo, naziv) == ""


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
