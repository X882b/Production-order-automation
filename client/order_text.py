"""Fixed wording of the production order's text lines.

The order is read at the press and by the watcher, so these lines are built
word for word as in the order template. Like formatting.py, no Qt here.
"""
import datetime
import math
import re

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

# What NAPOMENA's slitting line starts from on a new order
KOM_PO_ROLNI_DEFAULT = "1.000"
MAX_D_DEFAULT = "150"


def _datum(iso: str) -> str:
    """'2025-04-04' -> '04.04.2025'; anything else is returned as it is."""
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(iso or "")


def ranije_serije(serije: list[dict], doc_number) -> list[str]:
    """The dates of the product's production runs before this order's own.

    serije are the product's rows from /series ({"datum": ISO date,
    "doc_number": the order that run was for, or None}). An order with no
    run of its own yet comes after all of them; a saved one has its own run
    among them, and that run and later ones are not "earlier runs".
    """
    own = next(
        (r for r in serije if doc_number is not None and r.get("doc_number") == doc_number),
        None,
    )
    return sorted(
        r["datum"] for r in serije
        if r is not own and (own is None or r["datum"] < own["datum"])
    )


def stampa_text(serije: list[str], probni_uzorak: str) -> str:
    """The 'Štampa prema pripremi' line, from ISO dates.

    serije are the product's earlier production runs:
    'Štampa prema pripremi i prema uzorcima odštampanim u prethodnim
    serijama (12.08.2026,15.11.2026 i 29.12.2026).' Without any, the line
    names the proof instead: 'Štampa prema pripremi, prema uzorcima
    odštampanim kao probni uzorak 04.04.2025.'
    """
    if not serije:
        return (
            "Štampa prema pripremi, prema uzorcima odštampanim "
            f"kao probni uzorak {_datum(probni_uzorak)}."
        )
    datumi = [_datum(d) for d in sorted(serije)]
    joined = datumi[0] if len(datumi) == 1 else ",".join(datumi[:-1]) + " i " + datumi[-1]
    return (
        "Štampa prema pripremi i prema uzorcima odštampanim "
        f"u prethodnim serijama ({joined})."
    )


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


def obrnuto_slovo(slovo: str, naziv: str) -> str:
    """The letter at the other end of the name: 'D', 'Demo' -> 'o';
    'o', 'Demo ...' -> 'D'; 'e', 'Demo' -> '' (at neither end).

    The finished roll unwinds the other way round from how it was printed,
    so the name's last letter leads where its first did, and the first where
    the last did.
    """
    slovo = (slovo or "").strip()
    ends = [ch for ch in (naziv or "") if ch.isalnum()]
    if not slovo or not ends:
        return ""
    first, last = ends[0], ends[-1]
    for fold in (str, str.casefold):          # as written first, then any case
        if fold(slovo) == fold(first):
            return last
        if fold(slovo) == fold(last):
            return first
    return ""


def odmotavanje_text(slovo: str, naziv: str) -> str:
    """NAPOMENA's unwinding line, proposed from the letter that leads at the
    press: 'D', 'Demo' ->
    'Pri odmotavanju gotove rolnice napred ide slovo „o“ u nazivu „Demo“.'

    Empty when that letter is at neither end of the name.
    """
    return _napred_ide("Pri odmotavanju gotove rolnice", obrnuto_slovo(slovo, naziv), naziv)


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

def _mm(text: str) -> str:
    """'Ø45', '45 mm' -> '45': the form writes Ø and mm itself."""
    return re.sub(r"(?i)\s*mm\s*$", "", (text or "").replace("Ø", "").replace("ø", "")).strip()


def caure_text(unutrasnji: str, spoljni: str, sirina: str) -> str:
    """'45', '52', '65' -> 'Ø45/Ø52/65 mm': the core's inner and outer
    diameter and its width. Parts left empty are left out."""
    parts = [f"Ø{d}" for d in (_mm(unutrasnji), _mm(spoljni)) if d]
    if _mm(sirina):
        parts.append(_mm(sirina))
    return "/".join(parts) + " mm" if parts else ""


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
    max_d = _mm(max_d)
    tail = f" (max. Ø{max_d}mm)" if max_d else ""
    return f"{head}, {' + '.join(parts)}{tail},"


def napomena_text(*lines: str) -> str:
    """The NAPOMENA text: its non-empty lines, one per line."""
    return "\n".join(line.strip() for line in lines if line and line.strip())


# ── The bottom: the order's date, and a line to sign by hand ─────────────────

DATUM_LABEL = "Datum"
POTPIS_LABEL = "Potpis,"
POTPIS_LINIJA = "-" * 32    # the order is signed by hand; no name is printed


def datum_text(iso: str) -> str:
    """'2025-07-18' -> '18.07.2025.', the order's date as its bottom writes
    it; anything else is returned as it is."""
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y.")
    except (TypeError, ValueError):
        return str(iso or "")


def datum_potpis_lines(iso: str) -> list[str]:
    """The order's last three lines, padded with spaces as in the template so
    that "Potpis," and the line to sign on sit at the right:

        9 spaces + 'Datum' + 94 spaces + 'Potpis,'    (not bold)
        6 spaces + '18.07.2025.'                       (bold)
        101 spaces + 32 dashes                         (bold)

    The watcher reads the date line as the order's date (datum_doc).
    """
    return [
        " " * 9 + DATUM_LABEL + " " * 94 + POTPIS_LABEL,
        " " * 6 + datum_text(iso),
        " " * 101 + POTPIS_LINIJA,
    ]
