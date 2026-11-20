import datetime
import os
import re

import meilisearch
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_index = meilisearch.Client(
    os.getenv("MEILI_URL", "http://meili:7700"),
    os.getenv("MEILI_KEY", ""),
).index("docs")

_FIELDS = [
    "broj_naloga", "datum", "datum_sort", "naziv", "masina", "sifra", "dimenzija",
    "materijal", "sirina", "narucilac", "alati", "rok_isporuke", "rel_path",
]

# The order's date as YYYYMMDD (see the watcher's _search_date_fields), to
# filter and sort by
_DATE_KEY = "datum_sort"

# A day (18.07.2025) or a month (07.2025) typed in the search, written as the
# orders write dates
_DAY_RE = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})\.?(?![\d.])")
_MONTH_RE = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{4})\.?(?![\d.])")


def parse_query(q: str) -> tuple[str, str | None]:
    """Split what was typed into the words to search for and a filter on the
    order's date.

    A day (18.07.2025) finds the orders of that day, a month (07.2025) those
    of that month; with more than one, everything from the first to the last.
    'Demo 07.2025' -> ('Demo', 'datum_sort >= 20250701 AND datum_sort <= 20250731').
    What is not a real date stays text.
    """
    spans = []   # (first, last) day as YYYYMMDD

    def day(m):
        try:
            d = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return m.group(0)
        key = int(d.strftime("%Y%m%d"))
        spans.append((key, key))
        return " "

    def month(m):
        mon, year = int(m.group(1)), int(m.group(2))
        if not 1 <= mon <= 12:
            return m.group(0)
        spans.append((year * 10000 + mon * 100 + 1, year * 10000 + mon * 100 + 31))
        return " "

    text = " ".join(_MONTH_RE.sub(month, _DAY_RE.sub(day, q)).split())
    if not spans:
        return text, None
    first, last = min(s for s, _ in spans), max(e for _, e in spans)
    return text, f"{_DATE_KEY} >= {first} AND {_DATE_KEY} <= {last}"


_settings_applied = False


def _ensure_settings() -> None:
    """Let the index filter and sort by the order's date (once per start;
    this also creates the index on a fresh install)."""
    global _settings_applied
    if _settings_applied:
        return
    task = _index.update_settings({
        "filterableAttributes": [_DATE_KEY],
        "sortableAttributes": [_DATE_KEY],
    })
    done = _index.wait_for_task(task.task_uid)
    if done.status != "succeeded":
        raise HTTPException(status_code=503, detail=f"search settings not applied: {done.error}")
    _settings_applied = True


@router.get("/documents/search")
def search_documents(
    q: str = Query("", max_length=200),
    limit: int = Query(50, ge=1, le=200),
):
    """Orders matching q, newest first among equally good matches; a date or
    month in q keeps only the orders of that day or month."""
    text, date_filter = parse_query(q.strip())
    params = {
        "limit": limit,
        "attributesToRetrieve": _FIELDS,
        "sort": [f"{_DATE_KEY}:desc"],
    }
    if date_filter:
        params["filter"] = date_filter
    try:
        _ensure_settings()
        res = _index.search(text, params)
    except meilisearch.errors.MeilisearchError as e:
        raise HTTPException(status_code=503, detail=f"search unavailable: {e}")
    return res["hits"]
