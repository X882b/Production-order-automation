import os

import meilisearch
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_index = meilisearch.Client(
    os.getenv("MEILI_URL", "http://meili:7700"),
    os.getenv("MEILI_KEY", ""),
).index("docs")

_FIELDS = [
    "broj_naloga", "naziv", "masina", "sifra", "dimenzija", "materijal",
    "sirina", "narucilac", "alati", "rok_isporuke", "rel_path",
]


@router.get("/documents/search")
def search_documents(
    q: str = Query("", max_length=200),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        res = _index.search(q.strip(), {
            "limit": limit,
            "attributesToRetrieve": _FIELDS,
        })
    except meilisearch.errors.MeilisearchError as e:
        raise HTTPException(status_code=503, detail=f"search unavailable: {e}")
    return res["hits"]
