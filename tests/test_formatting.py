"""Serbian number and cylinder formatting used by the production-order form."""
import pytest

from formatting import (
    _fmt_cylinder,
    fmt_cylinder_from_zuba,
    fmt_float_sr,
    fmt_int_sr,
    parse_float_sr,
    parse_int_sr,
)


@pytest.mark.parametrize("text, expected", [
    ("20.000", 20000),
    ("20 000", 20000),
    ("  1500 ", 1500),
    ("1.234.567", 1234567),
    ("", None),
    ("   ", None),
    (None, None),
])
def test_parse_int_sr(text, expected):
    assert parse_int_sr(text) == expected


@pytest.mark.parametrize("text", ["1,5", "abc", "12kom"])
def test_parse_int_sr_rejects_non_integers(text):
    with pytest.raises(ValueError):
        parse_int_sr(text)


@pytest.mark.parametrize("text, expected", [
    ("1.234,5", 1234.5),       # dot groups thousands, comma is the decimal
    ("225,417", 225.417),
    ("225.417", 225.417),      # a lone dot is a decimal point (ALATI table)
    ("1.234.567", 1234567.0),  # several dots can only be thousands
    ("1 234,5", 1234.5),
    ("12", 12.0),
])
def test_parse_float_sr(text, expected):
    assert parse_float_sr(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "   ", None])
def test_parse_float_sr_empty_is_none(text):
    assert parse_float_sr(text) is None


@pytest.mark.parametrize("text", ["abc", "1,2,3", "12 mm"])
def test_parse_float_sr_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_float_sr(text)


@pytest.mark.parametrize("value, expected", [
    (0, "0"),
    (999, "999"),
    (20000, "20.000"),
    (1234567, "1.234.567"),
    (None, ""),
])
def test_fmt_int_sr(value, expected):
    assert fmt_int_sr(value) == expected


@pytest.mark.parametrize("value, decimals, expected", [
    (12.231, 2, "12,23"),
    (1234.5, 2, "1.234,50"),
    (225.417, 3, "225,417"),
    (0.5, 2, "0,50"),
    (None, 2, ""),
])
def test_fmt_float_sr(value, decimals, expected):
    assert fmt_float_sr(value, decimals) == expected


@pytest.mark.parametrize("value", [0, 7, 999, 1000, 20000, 1234567])
def test_int_round_trip(value):
    assert parse_int_sr(fmt_int_sr(value)) == value


@pytest.mark.parametrize("value", [0.5, 12.23, 225.417, 1234.5, 1234567.891])
def test_float_round_trip(value):
    assert parse_float_sr(fmt_float_sr(value, 3)) == pytest.approx(value)


@pytest.mark.parametrize("teeth, expected", [
    (93, "Z-93"),
    ("93", "Z-93"),
    (93.0, "Z-93"),
    ("93.0", "Z-93"),
    (92.5, "Z-92.5"),
    (None, ""),
    ("", ""),
])
def test_fmt_cylinder_from_zuba(teeth, expected):
    assert fmt_cylinder_from_zuba(teeth) == expected


@pytest.mark.parametrize("text, expected", [
    ("93", "Z-93"),
    (" 63 ", "Z-63"),
    ("Z88", "Z-88"),
    ("z88", "Z-88"),
    ("Z-88", "Z-88"),
    ("z-88", "Z-88"),
    ("UV", "UV"),
    ("", ""),
    ("   ", ""),
])
def test_fmt_cylinder_normalises_entries(text, expected):
    assert _fmt_cylinder(text) == expected
