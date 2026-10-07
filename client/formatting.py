"""Number and cylinder formatting helpers for the production-order form.

Production orders use Serbian number formatting: "." groups thousands and
"," is the decimal separator ("20.000 kom", "12,23 kom/m"). These helpers
have no Qt dependency, so they can be unit-tested on their own.
"""


def parse_int_sr(s: str) -> int | None:
    """'20.000' / '20 000' -> 20000. Raises ValueError on e.g. '1,5'."""
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace(".", "").replace(" ", "")
    return int(s)

def parse_float_sr(s: str) -> float | None:
    """'1.234,5' -> 1234.5, '225,417' -> 225.417, and '225.417' (as shown in
    the ALATI table) -> 225.417. Raises ValueError on garbage."""
    s = (s or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s:                 # Serbian: dots are thousands, comma is decimal
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:       # 1.234.567
        s = s.replace(".", "")
    # a single "." without "," is a decimal point
    return float(s)

def fmt_int_sr(n: int | None) -> str:
    if n is None:
        return ""
    return f"{n:,}".replace(",", ".")

def fmt_float_sr(n: float | None, decimals: int = 2) -> str:
    if n is None:
        return ""
    txt = f"{n:,.{decimals}f}"
    # 12,345.67 -> 12.345,67
    txt = txt.replace(",", "X").replace(".", ",").replace("X", ".")
    return txt

def fmt_zuba(value) -> str:
    if value is None:
        return ""
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except Exception:
        return str(value).strip()

def fmt_cylinder_from_zuba(value) -> str:
    z = fmt_zuba(value)
    return f"Z-{z}" if z else ""

def _fmt_cylinder(text: str) -> str:
    """Normalise a cylinder entry: bare number → 'Z-{n}', 'Z88' → 'Z-88'."""
    t = text.strip()
    if not t:
        return t
    import re as _re
    if _re.match(r'^[Zz]-\d', t):
        return "Z-" + t[2:]
    if _re.match(r'^[Zz]\d', t):
        return "Z-" + t[1:]
    if _re.match(r'^\d', t):
        return "Z-" + t
    return t
