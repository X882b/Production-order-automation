"""Searching the die catalogue column by column (the form's ALATI search).

No Qt here, so the matching rules can be tested on their own.
"""
from formatting import fmt_cylinder_from_zuba
from order_text import stancna_oznake

# (column header, key in a /lookup/tools row, kind): one search field each
COLUMNS = [
    ("Oznaka štancne",     "oznaka_stancne",      "text"),
    ("Oznaka proizvođača", "oznaka_proizvodjaca", "text"),
    ("Širina",             "dimenzija_sirina_mm", "number"),
    ("Visina",             "dimenzija_visina_mm", "number"),
    ("Zuba",               "broj_zuba",           "number"),
    ("Obim cilindra",      "obim_cilindra_mm",    "number"),
    ("Raspored",           "raspored",            "text"),
]
_KIND = {key: kind for _header, key, kind in COLUMNS}


def cell_text(row: dict, key: str) -> str:
    """A die's value as the table shows it; numbers without trailing zeros."""
    value = row.get(key)
    if value is None:
        return ""
    if _KIND.get(key) == "number":
        try:
            return f"{float(value):g}"
        except (TypeError, ValueError):
            pass
    return str(value).strip()


def _squash(text: str) -> str:
    return (text or "").casefold().replace(" ", "").replace("×", "x")


def matches(row: dict, typed: dict) -> bool:
    """True when the die fits every field that has something typed in it.

    A number must start with what was typed ("65" finds 65 and 65.5, not
    165); text must contain it, ignoring case and spaces ("3x2" finds
    "3 x 2").
    """
    for key, text in typed.items():
        text = _squash(text)
        if not text:
            continue
        shown = _squash(cell_text(row, key))
        if _KIND.get(key) == "number":
            if not shown.startswith(text.replace(",", ".")):
                return False
        elif text not in shown:
            return False
    return True


def dimenzija_text(row: dict) -> str:
    """'65 x 140 mm' from a die's width and height; one of them if alone."""
    parts = [cell_text(row, key) for key in ("dimenzija_sirina_mm", "dimenzija_visina_mm")]
    parts = [p for p in parts if p]
    return " x ".join(parts) + " mm" if parts else ""


def summary(row: dict) -> str:
    """One line naming a die: 'ABC25-02-12345 (T-001) · 65 x 140 mm · Z-93 · 3x2'."""
    parts = [
        stancna_oznake(cell_text(row, "oznaka_stancne"), cell_text(row, "oznaka_proizvodjaca")),
        dimenzija_text(row),
        fmt_cylinder_from_zuba(row.get("broj_zuba")),
        cell_text(row, "raspored"),
    ]
    return " · ".join(p for p in parts if p)
