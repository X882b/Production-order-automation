"""Searching the die catalogue column by column."""
import pytest

import alati_filter

DIES = [
    {"id": 1, "oznaka_stancne": "ABC25-02-12345", "oznaka_proizvodjaca": "T-001",
     "dimenzija_sirina_mm": 65.0, "dimenzija_visina_mm": 140.0, "broj_zuba": "93",
     "obim_cilindra_mm": 295.275, "raspored": "3 x 2"},
    {"id": 2, "oznaka_stancne": "XYZ14-05-54321", "oznaka_proizvodjaca": "T-002s",
     "dimenzija_sirina_mm": 90.0, "dimenzija_visina_mm": 60.0, "broj_zuba": "81",
     "obim_cilindra_mm": 257.175, "raspored": "2x4"},
    {"id": 3, "oznaka_stancne": "ABC19-11-00777", "oznaka_proizvodjaca": None,
     "dimenzija_sirina_mm": 165.0, "dimenzija_visina_mm": 65.5, "broj_zuba": "93",
     "obim_cilindra_mm": 295.275, "raspored": None},
]


def found(**typed):
    return [die["id"] for die in DIES if alati_filter.matches(die, typed)]


def test_one_search_field_per_column():
    assert [key for _header, key, _kind in alati_filter.COLUMNS] == [
        "oznaka_stancne", "oznaka_proizvodjaca", "dimenzija_sirina_mm",
        "dimenzija_visina_mm", "broj_zuba", "obim_cilindra_mm", "raspored",
    ]


def test_nothing_typed_finds_every_die():
    assert found() == [1, 2, 3]
    assert found(oznaka_stancne="", raspored="  ") == [1, 2, 3]


@pytest.mark.parametrize("typed, expected", [
    ({"oznaka_stancne": "abc"}, [1, 3]),                # text: contains, any case
    ({"oznaka_stancne": "12345"}, [1]),
    ({"oznaka_proizvodjaca": "t-00"}, [1, 2]),
    ({"oznaka_proizvodjaca": "002S"}, [2]),
    ({"dimenzija_sirina_mm": "65"}, [1]),               # number: starts with, so not 165
    ({"dimenzija_sirina_mm": "1"}, [3]),
    ({"dimenzija_visina_mm": "65"}, [3]),               # 65.5
    ({"dimenzija_visina_mm": "65,5"}, [3]),             # decimal comma
    ({"broj_zuba": "93"}, [1, 3]),
    ({"obim_cilindra_mm": "257"}, [2]),
    ({"raspored": "3x2"}, [1]),                         # spaces ignored
    ({"raspored": "2 X 4"}, [2]),
    ({"raspored": "3×2"}, [1]),
])
def test_each_field_searches_its_own_column(typed, expected):
    assert found(**typed) == expected


def test_a_die_must_fit_every_field_that_is_filled_in():
    assert found(broj_zuba="93", dimenzija_sirina_mm="65") == [1]
    assert found(broj_zuba="93", dimenzija_sirina_mm="90") == []
    # the value is searched only in its own column: 65 is die 3's height
    assert found(dimenzija_sirina_mm="65", dimenzija_visina_mm="65") == []


def test_cell_text_shows_numbers_without_trailing_zeros():
    assert alati_filter.cell_text(DIES[0], "dimenzija_sirina_mm") == "65"
    assert alati_filter.cell_text(DIES[0], "obim_cilindra_mm") == "295.275"
    assert alati_filter.cell_text(DIES[2], "oznaka_proizvodjaca") == ""


def test_dimenzija_text():
    assert alati_filter.dimenzija_text(DIES[0]) == "65 x 140 mm"
    assert alati_filter.dimenzija_text({"dimenzija_sirina_mm": 65}) == "65 mm"
    assert alati_filter.dimenzija_text({}) == ""


def test_summary_names_the_chosen_die():
    assert alati_filter.summary(DIES[0]) == "ABC25-02-12345 (T-001) · 65 x 140 mm · Z-93 · 3 x 2"
    assert alati_filter.summary(DIES[2]) == "ABC19-11-00777 · 165 x 65.5 mm · Z-93"
