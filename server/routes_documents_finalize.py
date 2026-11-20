import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from server.db import engine
from server.order_numbers import broj_sql, key_of, parse_broj

router = APIRouter()

# doc_params key holding everything entered in the form, as JSON
_FORM_STATE = "form_state"


class FinalizeDoc(BaseModel):
    doc_number: int
    machine_id: Optional[int] = None

    sifra: Optional[str] = None
    naziv: Optional[str] = None
    dimenzija: Optional[str] = None
    sirina: Optional[str] = None

    customer_id: Optional[int] = None
    material_id: Optional[int] = None

    kolicina_text: Optional[str] = None
    kolicina_kom_naruceno: Optional[int] = None
    kolicina_kom_po_m: Optional[float] = None
    kolicina_m_dobrih: Optional[int] = None
    kolicina_add_m: Optional[int] = None

    stancna_mm: Optional[float] = None
    rows_long: Optional[int] = None
    rows_wide: Optional[int] = None

    kolicina_note: Optional[str] = None
    rok_isporuke: Optional[date] = None

    # Text lines of the order, kept in doc_params under the same keys the
    # watcher uses for what it reads from the Word file
    stampa: Optional[str] = None
    napred_slovo: Optional[str] = None
    napred_naziv: Optional[str] = None
    alati: Optional[str] = None
    opis: Optional[str] = None
    napomena: Optional[str] = None
    # The order's date at its bottom
    datum_doc: Optional[date] = None

    # Every field of the form as it was saved, so the order can be reopened
    # in the form exactly as it was (see GET /documents/form/{broj})
    form_state: Optional[dict] = None


_DOC_PARAMS = {
    "stampa", "napred_slovo", "napred_naziv", "alati", "opis", "napomena", "datum_doc",
}


# What saving answers with: the key, the order's Word file and its number as
# shown (12345, or 12345-1 for a version)
_RETURNING = f"RETURNING doc_number, rel_path, {broj_sql()} AS broj"


def _set_param(cx, doc_number: int, key: str, value: str) -> None:
    cx.execute(text("""
        INSERT INTO doc_params (doc_number, key, value_text)
        VALUES (:n, :k, :v)
        ON CONFLICT (doc_number, key) DO UPDATE SET value_text = EXCLUDED.value_text
    """), {"n": doc_number, "k": key, "v": value})


@router.post("/documents/finalize")
def finalize_document(payload: FinalizeDoc):
    params = payload.model_dump()
    form_state = params.pop("form_state")
    with engine.begin() as cx:
        row = cx.execute(
            text(f"""
                UPDATE documents SET
                  machine_id            = :machine_id,
                  sifra                 = :sifra,
                  naziv                 = :naziv,
                  dimenzija             = :dimenzija,
                  sirina                = :sirina,
                  customer_id           = :customer_id,
                  material_id           = :material_id,
                  kolicina_text         = :kolicina_text,
                  kolicina_kom_naruceno = :kolicina_kom_naruceno,
                  kolicina_kom_po_m     = :kolicina_kom_po_m,
                  kolicina_m_dobrih     = :kolicina_m_dobrih,
                  kolicina_add_m        = :kolicina_add_m,
                  stancna_mm            = :stancna_mm,
                  rows_long             = :rows_long,
                  rows_wide             = :rows_wide,
                  kolicina_note         = :kolicina_note,
                  rok_isporuke          = :rok_isporuke,
                  status                = 'final'
                WHERE doc_number = :doc_number
                {_RETURNING}
            """),
            params,
        ).mappings().fetchone()

        if not row:
            row = cx.execute(
                text(f"""
                    INSERT INTO documents (
                      doc_number, machine_id, sifra, naziv, dimenzija, sirina,
                      customer_id, material_id, kolicina_text, kolicina_kom_naruceno,
                      kolicina_kom_po_m, kolicina_m_dobrih, kolicina_add_m,
                      stancna_mm, rows_long, rows_wide, kolicina_note, rok_isporuke,
                      status
                    ) VALUES (
                      :doc_number, :machine_id, :sifra, :naziv, :dimenzija, :sirina,
                      :customer_id, :material_id, :kolicina_text, :kolicina_kom_naruceno,
                      :kolicina_kom_po_m, :kolicina_m_dobrih, :kolicina_add_m,
                      :stancna_mm, :rows_long, :rows_wide, :kolicina_note, :rok_isporuke,
                      'final'
                    )
                    {_RETURNING}
                """),
                params,
            ).mappings().fetchone()

        # A line that's given is stored, an emptied one removed; lines the
        # request leaves out stay as they are. Dates as ISO, like the watcher.
        for key in sorted(_DOC_PARAMS & payload.model_fields_set):
            value = params[key]
            value = value.isoformat() if isinstance(value, date) else (value or "").strip()
            if value:
                _set_param(cx, payload.doc_number, key, value)
            else:
                cx.execute(text(
                    "DELETE FROM doc_params WHERE doc_number = :n AND key = :k"
                ), {"n": payload.doc_number, "k": key})

        if form_state is not None:
            _set_param(cx, payload.doc_number, _FORM_STATE,
                       json.dumps(form_state, ensure_ascii=False))

    # rel_path: the order's Word file in the orders folder, once the watcher has it;
    # broj: its number as shown (12345, or 12345-1 for a version)
    return {"ok": True, "doc_number": row["doc_number"], "rel_path": row["rel_path"],
            "broj": row["broj"]}


@router.get("/documents/form/{broj}")
def get_document_form(broj: str):
    """The form's fields as saved with order broj (6276, or 6276-1 for a
    version), with the order's key. 404 for an order that was never saved
    from the form (one that only exists as a Word file)."""
    number = parse_broj(broj)
    row, key = None, None
    with engine.connect() as cx:
        key = key_of(cx, number) if number else None
        if key is not None:
            row = cx.execute(text(
                "SELECT value_text FROM doc_params WHERE doc_number = :n AND key = :k"
            ), {"n": key, "k": _FORM_STATE}).fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="no saved form for this order")
    return {"doc_number": key, "broj": str(number), "form_state": json.loads(row[0])}
