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

    return {"ok": True, "doc_number": row["doc_number"]}
