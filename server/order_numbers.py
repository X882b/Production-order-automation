"""Order numbers as they are shown: 12345 for an order, and 12345-1,
12345-2, ... for its versions.

A version is an order of its own (its own fields, colour rows and Word
file) made from an earlier order and numbered after it. In the database it
is a row of documents like any order: base_number and doc_version say whose
version it is, and its key doc_number comes from doc_version_seq, which
counts down from -1, so versions never use up or move the order numbers
(schema_versions.sql). The other tables use doc_number as they always did.
"""
import re
from typing import NamedTuple

from sqlalchemy import text

# 12345, or 12345-1 for a version (1 to 999)
_BROJ_RE = re.compile(r"([1-9]\d*)(?:-([1-9]\d{0,2}))?")
MAX_VERSION = 999


class Broj(NamedTuple):
    """An order's number as shown: Broj(12345) is '12345', Broj(12345, 1) '12345-1'."""
    base: int
    version: int | None = None

    def __str__(self) -> str:
        return f"{self.base}-{self.version}" if self.version else str(self.base)


def parse_broj(s) -> Broj | None:
    """'12345' -> Broj(12345), '12345-1' -> Broj(12345, 1); None for anything else."""
    m = _BROJ_RE.fullmatch(str(s if s is not None else "").strip())
    if not m:
        return None
    return Broj(int(m.group(1)), int(m.group(2)) if m.group(2) else None)


def broj_sql(table: str = "") -> str:
    """SQL for the number shown for a row of documents (optionally of `table`)."""
    t = f"{table}." if table else ""
    return (f"CASE WHEN {t}doc_version IS NULL THEN {t}doc_number::text "
            f"ELSE {t}base_number::text || '-' || {t}doc_version::text END")


def broj_of(cx, doc_number: int) -> str | None:
    """The number shown for the order with key doc_number; None if there is none."""
    return cx.execute(text(f"SELECT {broj_sql()} FROM documents WHERE doc_number = :n"),
                      {"n": doc_number}).scalar_one_or_none()


def key_of(cx, broj: Broj) -> int | None:
    """The key (doc_number) of the order numbered broj; None if there is none."""
    if broj.version is None:
        sql = "SELECT doc_number FROM documents WHERE doc_number = :b AND doc_version IS NULL"
    else:
        sql = "SELECT doc_number FROM documents WHERE base_number = :b AND doc_version = :v"
    return cx.execute(text(sql), {"b": broj.base, "v": broj.version}).scalar_one_or_none()


def new_version(cx, doc_number: int, user: str, version: int | None = None) -> tuple[int, str] | None:
    """Make a version of order doc_number, or of the order doc_number is a
    version of (from 12345-1 comes 12345-2, never 12345-1-1). It takes the
    next free version, or `version` if that is given and free.

    Returns the new version's (key, shown number); None if there is no such
    order or `version` is taken. Raises ValueError past MAX_VERSION.
    """
    base = cx.execute(text(
        "SELECT COALESCE(base_number, doc_number) FROM documents WHERE doc_number = :n"
    ), {"n": doc_number}).scalar_one_or_none()
    if base is None:
        return None
    # The order's row is locked, so its versions are numbered one at a time
    cx.execute(text("SELECT 1 FROM documents WHERE doc_number = :b FOR UPDATE"), {"b": base})
    if version is None:
        version = cx.execute(text(
            "SELECT COALESCE(MAX(doc_version), 0) + 1 FROM documents WHERE base_number = :b"
        ), {"b": base}).scalar_one()
        if version > MAX_VERSION:
            raise ValueError(f"order {base} already has {MAX_VERSION} versions")
    elif key_of(cx, Broj(base, version)) is not None:
        return None
    key = cx.execute(text("""
        INSERT INTO documents (doc_number, title, status, created_by, base_number, doc_version)
        VALUES (nextval('doc_version_seq'), '', 'draft', :u, :b, :v)
        RETURNING doc_number
    """), {"u": user, "b": base, "v": version}).scalar_one()
    return key, str(Broj(base, version))
