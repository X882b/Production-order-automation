"""A date or month typed in the order search becomes a filter on the
order's date; the rest is searched as text."""
import pytest

from server.routes_search import parse_query


@pytest.mark.parametrize("q, text, days", [
    ("18.07.2025", "", (20250718, 20250718)),
    ("18.07.2025.", "", (20250718, 20250718)),            # as the order writes it
    ("8.7.2025", "", (20250708, 20250708)),
    ("07.2025", "", (20250701, 20250731)),
    ("Demo 07.2025", "Demo", (20250701, 20250731)),
    ("01.07.2025 15.08.2025", "", (20250701, 20250815)),  # from the first to the last
    ("08.2025 Primer 07.2025", "Primer", (20250701, 20250831)),
    ("Demo", "Demo", None),
    ("", "", None),
    ("31.02.2025", "31.02.2025", None),                   # no such day: stays text
    ("13.2025", "13.2025", None),                         # no such month
    ("1.250 kom", "1.250 kom", None),                     # a number, not a date
    ("DEMO-250101", "DEMO-250101", None),
])
def test_parse_query(q, text, days):
    expected = f"datum_sort >= {days[0]} AND datum_sort <= {days[1]}" if days else None
    assert parse_query(q) == (text, expected)
