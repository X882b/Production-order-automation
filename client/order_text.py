"""Fixed wording of the production order's text lines.

The order is read at the press and by the watcher, so these lines are built
word for word as in the order template. Like formatting.py, no Qt here.
"""
from formatting import fmt_cylinder_from_zuba

# OPIS is the same on nearly every order; the form starts with it and lets
# the user change it
OPIS_DEFAULT = (
    "Svaki nastavak rolne izvršiti precizno zbog mašinskog etiketiranja.\n"
    "Nastavak koji je fabrički urađen zameniti, odnosno, izbaciti iz rolne."
)


def napred_ide_text(slovo: str, naziv: str) -> str:
    """'W', 'EHW' -> 'Pri štampi napred ide slovo „W“ u nazivu „EHW“.'

    Empty until both the letter and the name are given.
    """
    slovo, naziv = (slovo or "").strip(), (naziv or "").strip()
    if not slovo or not naziv:
        return ""
    return f"Pri štampi napred ide slovo „{slovo}“ u nazivu „{naziv}“."


def alati_text(oznaka: str, zuba) -> str:
    """'0000', 93 -> 'štancna oznake 0000, Z-93' (the order's ALATI line).

    Without a number of teeth the line ends after the die number.
    """
    oznaka = (oznaka or "").strip()
    if not oznaka:
        return ""
    cylinder = fmt_cylinder_from_zuba(zuba)
    return f"štancna oznake {oznaka}, {cylinder}" if cylinder else f"štancna oznake {oznaka}"
