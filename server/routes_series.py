from datetime import date
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import text

from server.db import engine
from server.order_numbers import broj_sql

router = APIRouter()


class SeriesEntry(BaseModel):
    sifra: str
    datum: date
    note: Optional[str] = None
    doc_number: Optional[int] = None


@router.get("/series")
def get_series(sifra: str = Query(..., max_length=200)):
    with engine.connect() as cx:
        rows = cx.execute(
            # broj: the run's order as shown (12345, or 12345-1 for a version)
            text(f"""
                SELECT s.id, s.sifra, s.datum, s.note, s.doc_number,
                       {broj_sql("d")} AS broj
                FROM product_series s
                LEFT JOIN documents d ON d.doc_number = s.doc_number
                WHERE LOWER(s.sifra) = LOWER(:s)
                ORDER BY s.datum
            """),
            {"s": sifra},
        ).mappings().all()
    return [
        {**dict(r), "datum": r["datum"].isoformat()}
        for r in rows
    ]


@router.post("/series")
def add_series_entry(entry: SeriesEntry):
    with engine.begin() as cx:
        exists = cx.execute(
            text("SELECT id FROM product_series WHERE LOWER(sifra)=LOWER(:s) AND datum=:d"),
            {"s": entry.sifra, "d": entry.datum},
        ).fetchone()
        if exists:
            return {"ok": True, "duplicate": True, "id": exists[0]}
        row = cx.execute(
            text("""
                INSERT INTO product_series (sifra, datum, note, doc_number)
                VALUES (:s, :d, :n, :dn)
                RETURNING id
            """),
            {"s": entry.sifra, "d": entry.datum, "n": entry.note, "dn": entry.doc_number},
        ).fetchone()
    return {"ok": True, "duplicate": False, "id": row[0]}


@router.delete("/series/{entry_id}")
def delete_series_entry(entry_id: int):
    with engine.begin() as cx:
        cx.execute(
            text("DELETE FROM product_series WHERE id = :id"),
            {"id": entry_id},
        )
    return {"ok": True}
