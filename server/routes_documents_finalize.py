from datetime import date
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from server.db import engine

router = APIRouter()


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
    napred_slovo: Optional[str] = None
    napred_naziv: Optional[str] = None
    alati: Optional[str] = None
    opis: Optional[str] = None


_TEXT_PARAMS = {"napred_slovo", "napred_naziv", "alati", "opis"}


@router.post("/documents/finalize")
def finalize_document(payload: FinalizeDoc):
    params = payload.model_dump()
    with engine.begin() as cx:
        row = cx.execute(
            text("""
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
                RETURNING doc_number
            """),
            params,
        ).mappings().fetchone()

        if not row:
            row = cx.execute(
                text("""
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
                    RETURNING doc_number
                """),
                params,
            ).mappings().fetchone()

        # A line that's given is stored, an emptied one removed; lines the
        # request leaves out stay as they are
        for key in sorted(_TEXT_PARAMS & payload.model_fields_set):
            value = (params[key] or "").strip()
            if value:
                cx.execute(text("""
                    INSERT INTO doc_params (doc_number, key, value_text)
                    VALUES (:n, :k, :v)
                    ON CONFLICT (doc_number, key) DO UPDATE SET value_text = EXCLUDED.value_text
                """), {"n": payload.doc_number, "k": key, "v": value})
            else:
                cx.execute(text(
                    "DELETE FROM doc_params WHERE doc_number = :n AND key = :k"
                ), {"n": payload.doc_number, "k": key})

    return {"ok": True, "doc_number": row["doc_number"]}
