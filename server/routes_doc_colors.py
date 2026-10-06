from typing import Optional, List

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from server.db import engine

router = APIRouter()


class ColorRow(BaseModel):
    position_num: int
    position_label: str
    klise_code: Optional[str] = None
    variant: Optional[str] = None
    color_text: Optional[str] = None
    raster: Optional[str] = None
    cylinder: Optional[str] = None
    supplier: Optional[str] = None
    note: Optional[str] = None


class SaveColorsPayload(BaseModel):
    doc_number: int
    rows: List[ColorRow]


@router.post("/documents/colors/save")
def save_document_colors(payload: SaveColorsPayload):
    with engine.begin() as cx:
        cx.execute(
            text("DELETE FROM document_color_rows WHERE doc_number = :n"),
            {"n": payload.doc_number},
        )
        for row in payload.rows:
            cx.execute(
                text("""
                    INSERT INTO document_color_rows (
                        doc_number, position_num, position_label,
                        klise_code, variant, color_text, raster, cylinder, supplier, note
                    ) VALUES (
                        :dn, :pn, :pl, :kc, :va, :ct, :ra, :cy, :su, :no
                    )
                """),
                {
                    "dn": payload.doc_number,
                    "pn": row.position_num,
                    "pl": row.position_label,
                    "kc": row.klise_code,
                    "va": row.variant,
                    "ct": row.color_text,
                    "ra": row.raster,
                    "cy": row.cylinder,
                    "su": row.supplier,
                    "no": row.note,
                },
            )
    return {"ok": True, "saved": len(payload.rows)}


@router.get("/documents/colors/{doc_number}")
def get_document_colors(doc_number: int):
    with engine.connect() as cx:
        rows = cx.execute(
            text("""
                SELECT
                    id, doc_number, position_num, position_label,
                    klise_code, variant, color_text, raster, cylinder, supplier, note
                FROM document_color_rows
                WHERE doc_number = :n
                ORDER BY position_num
            """),
            {"n": doc_number},
        ).mappings().all()
    return [dict(r) for r in rows]
