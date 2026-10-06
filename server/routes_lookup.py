from fastapi import APIRouter, Query
from sqlalchemy import text

from server.db import engine

router = APIRouter()


def _like(q: str) -> str:
    return f"%{q.strip()}%"


@router.get("/lookup/machines")
def lookup_machines(q: str = Query("", max_length=100)):
    with engine.connect() as cx:
        rows = cx.execute(
            text("SELECT id, name FROM machines WHERE active=TRUE AND name ILIKE :q ORDER BY name LIMIT 20"),
            {"q": _like(q)},
        ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/lookup/customers")
def lookup_customers(q: str = Query("", max_length=100)):
    with engine.connect() as cx:
        rows = cx.execute(
            text("SELECT id, name FROM customers WHERE active=TRUE AND name ILIKE :q ORDER BY name LIMIT 20"),
            {"q": _like(q)},
        ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/lookup/materials")
def lookup_materials(q: str = Query("", max_length=100)):
    with engine.connect() as cx:
        rows = cx.execute(
            text("SELECT id, name FROM materials WHERE active=TRUE AND name ILIKE :q ORDER BY name LIMIT 20"),
            {"q": _like(q)},
        ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/lookup/products")
def lookup_products(q: str = Query("", max_length=100)):
    with engine.connect() as cx:
        rows = cx.execute(
            text("""
                SELECT
                  p.id, p.sifra, p.naziv, p.dimenzija, p.sirina,
                  c.id AS customer_id, c.name AS customer_name,
                  m.id AS material_id, m.name AS material_name
                FROM products p
                LEFT JOIN customers c ON c.id = p.customer_id
                LEFT JOIN materials m ON m.id = p.material_id
                WHERE p.active = TRUE
                  AND (p.sifra ILIKE :q OR p.naziv ILIKE :q)
                ORDER BY p.sifra
                LIMIT 20
            """),
            {"q": _like(q)},
        ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/lookup/tools")
def lookup_tools(
    q: str = Query("", max_length=100),
    limit: int = Query(5000, ge=1, le=5000),   # all dies (~2000 since SPEC. OBLIK)
):
    with engine.connect() as cx:
        rows = cx.execute(
            text("""
                SELECT
                  id, sheet_name, oznaka_stancne, oznaka_proizvodjaca,
                  dimenzija_sirina_mm, dimenzija_visina_mm, broj_zuba,
                  obim_cilindra_mm, raspored, rows_long, rows_wide
                FROM tools
                WHERE active = TRUE
                  AND COALESCE(oznaka_stancne, '') <> ''
                  AND COALESCE(oznaka_stancne, '') <> '-'
                  AND (
                    COALESCE(oznaka_stancne, '')                     ILIKE :q
                    OR COALESCE(oznaka_proizvodjaca, '')             ILIKE :q
                    OR COALESCE(CAST(dimenzija_sirina_mm AS TEXT), '') ILIKE :q
                    OR COALESCE(CAST(dimenzija_visina_mm AS TEXT), '') ILIKE :q
                    OR COALESCE(CAST(obim_cilindra_mm AS TEXT), '')  ILIKE :q
                    OR COALESCE(raspored, '')                        ILIKE :q
                    OR COALESCE(broj_zuba, '')                       ILIKE :q
                  )
                ORDER BY oznaka_stancne NULLS LAST, id
                LIMIT :limit
            """),
            {"q": _like(q), "limit": limit},
        ).mappings().all()
    return [dict(r) for r in rows]
