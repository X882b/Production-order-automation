"""Reading the die catalogue's RASPORED column."""
import pytest

pytest.importorskip("pandas")   # the import runs on the host, not in the server image

import import_tools_from_excel as imp


@pytest.mark.parametrize("cell, rows_long, rows_wide", [
    ("3x2", 2, 3),      # 3 lanes across the web, 2 labels around the cylinder
    ("2 x 4", 4, 2),
    ("3×2", 2, 3),
    ("1X1", 1, 1),
])
def test_raspored_is_lanes_across_by_labels_around(cell, rows_long, rows_wide):
    assert imp.parse_raspored(cell) == (cell, rows_long, rows_wide)


@pytest.mark.parametrize("cell", ["po uzorku", "3x", "3x2x1"])
def test_unreadable_raspored_keeps_the_text_only(cell):
    assert imp.parse_raspored(cell) == (cell, None, None)


def test_empty_raspored():
    assert imp.parse_raspored(None) == (None, None, None)
