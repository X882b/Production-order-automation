"""Fixed wording of the production order's text lines.

The order is read at the press and by the watcher, so these lines are built
word for word as in the order template. Like formatting.py, no Qt here.
"""
import math

from formatting import fmt_cylinder_from_zuba, fmt_int_sr

# OPIS is the same on nearly every order; the form starts with it and lets
# the user change it
OPIS_DEFAULT = (
    "Svaki nastavak rolne izvršiti precizno zbog mašinskog etiketiranja.\n"
    "Nastavak koji je fabrički urađen zameniti, odnosno, izbaciti iz rolne."
)


# NAPOMENA starts with this after the slitting and unwinding lines; the
# user can change it
NAPOMENA_DEFAULT = "Upakovati u kutije."


def _napred_ide(prefix: str, slovo: str, naziv: str) -> str:
    slovo, naziv = (slovo or "").strip(), (naziv or "").strip()
    if not slovo or not naziv:
        return ""
    return f"{prefix} napred ide slovo „{slovo}“ u nazivu „{naziv}“."


def napred_ide_text(slovo: str, naziv: str) -> str:
    """'D', 'Demo' -> 'Pri štampi napred ide slovo „D“ u nazivu „Demo“.'

    Empty until both the letter and the name are given.
    """
    return _napred_ide("Pri štampi", slovo, naziv)


def odmotavanje_text(slovo: str, naziv: str) -> str:
    """NAPOMENA's unwinding line, with the same letter and name:
    'Pri odmotavanju gotove rolnice napred ide slovo „D“ u nazivu „Demo“.'"""
    return _napred_ide("Pri odmotavanju gotove rolnice", slovo, naziv)


def alati_text(oznaka: str, zuba) -> str:
    """'0000', 93 -> 'štancna oznake 0000, Z-93' (the order's ALATI line).

    Without a number of teeth the line ends after the die number.
    """
    oznaka = (oznaka or "").strip()
    if not oznaka:
        return ""
    cylinder = fmt_cylinder_from_zuba(zuba)
    return f"štancna oznake {oznaka}, {cylinder}" if cylinder else f"štancna oznake {oznaka}"


# ── NAPOMENA: slitting into rolls ────────────────────────────────────────────

def rolne_word(n: int) -> str:
    """Serbian plural after a number: 1 rolna, 3 rolne, 99 rolni (11–14 rolni)."""
    if n % 10 == 1 and n % 100 != 11:
        return "rolna"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "rolne"
    return "rolni"


def otkucaji(kom_po_rolni, stancna_mm, rows_long) -> int | None:
    """Length of a roll in tenths of a metre, the counter's unit.

    Along one lane every label takes the die circumference divided by the
    rows along it: Z-93 (295,275 mm) with 2 rows -> 147,64 mm, so 1.000 kom
    -> 147,6 m -> 1476. None when the die isn't known.
    """
    if not kom_po_rolni or not stancna_mm or not rows_long:
        return None
    return math.floor(kom_po_rolni * stancna_mm / rows_long / 100 + 0.5)


def split_rolls(total_kom, kom_po_rolni, lanes) -> list[tuple[int, int]]:
    """Proposed (rolls, kom/rolna) groups: full rolls in whole sets of lanes,
    then the rest spread over the lanes, rounded up to 5 kom.

    100.000 kom, 1.000 kom/rolna, 3 lanes -> [(99, 1000), (3, 335)]
    """
    if not total_kom or not kom_po_rolni or total_kom <= 0 or kom_po_rolni <= 0:
        return []
    lanes = lanes if lanes and lanes > 0 else 1
    full = total_kom // (kom_po_rolni * lanes) * lanes
    rest = total_kom - full * kom_po_rolni
    groups = []
    if rest:
        per_roll = math.ceil(math.ceil(rest / lanes) / 5) * 5
        if per_roll >= kom_po_rolni:      # the rest is another full set
            full += lanes
        else:
            groups.append((lanes, per_roll))
    if full:
        groups.insert(0, (full, kom_po_rolni))
    return groups


def rasecanje_text(caure: str, groups, stancna_mm, rows_long, max_d: str) -> str:
    """NAPOMENA's slitting line, e.g. 'Raseći na čaure Ø45/Ø52/65 mm,
    99 rolni x 1.000 kom/rolna-1476 otkucaja/rolna + 3 rolne x 335
    kom/rolna-495 otkucaja/rolna (max. Ø150mm),'

    groups is a list of (rolls, kom/rolna); otkucaja/rolna is left out when
    the die isn't known. Empty without groups.
    """
    parts = []
    for rolls, kom in groups:
        part = f"{rolls} {rolne_word(rolls)} x {fmt_int_sr(kom)} kom/rolna"
        otk = otkucaji(kom, stancna_mm, rows_long)
        if otk is not None:
            part += f"-{otk} otkucaja/rolna"
        parts.append(part)
    if not parts:
        return ""
    caure = (caure or "").strip()
    head = f"Raseći na čaure {caure}" if caure else "Raseći"
    max_d = (max_d or "").strip()
    tail = f" (max. Ø{max_d}mm)" if max_d else ""
    return f"{head}, {' + '.join(parts)}{tail},"


def napomena_text(*lines: str) -> str:
    """The NAPOMENA text: its non-empty lines, one per line."""
    return "\n".join(line.strip() for line in lines if line and line.strip())
