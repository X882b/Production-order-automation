"""Order numbers as shown: 12345 for an order, 12345-1 for its versions."""
import pytest

from server.order_numbers import Broj, broj_sql, parse_broj


@pytest.mark.parametrize("text, broj", [
    ("6276", Broj(6276)),
    (6276, Broj(6276)),
    (" 6276-1 ", Broj(6276, 1)),
    ("6276-999", Broj(6276, 999)),
    ("6276-1000", None),      # at most 999 versions
    ("6276-0", None),
    ("6276-01", None),
    ("06276", None),
    ("-5", None),             # never a key
    ("6276-1-1", None),       # a version's version is the next version, never this
    ("6276 - 1", None),
    ("", None),
    (None, None),
])
def test_parse_broj(text, broj):
    assert parse_broj(text) == broj


def test_a_number_is_shown_as_the_order_writes_it():
    assert str(Broj(6276)) == "6276"
    assert str(Broj(6276, 2)) == "6276-2"
    assert parse_broj(str(Broj(6276, 2))) == Broj(6276, 2)


def test_the_shown_number_in_sql_names_its_table():
    assert broj_sql("d") == ("CASE WHEN d.doc_version IS NULL THEN d.doc_number::text "
                             "ELSE d.base_number::text || '-' || d.doc_version::text END")
    assert "d." not in broj_sql()
