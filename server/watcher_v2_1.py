"""
watcher_v2_1.py  –  YU LABEL DMS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Watches the /docs directory for new or modified .docx files.

Improvements over v1 / v2.1 safety patch
────────────────────
  • parse_production_order()  — full structured extraction:
      - MAŠINA, ŠIFRA, NAZIV, DIMENZIJA, MATERIJAL, ŠIRINA, NARUČILAC
      - KOLIČINA   → m_dobrih, kolicina_kom_naruceno, kolicina_kom_po_m
      - ROK ZA ISPORUKU  → ISO date
      - ALATI       → raw text + stancna_code extraction
      - OPIS, NAPOMENA → collected as plain text
      - Datum (signing date at bottom)
      - ŠIFRA BOJA  → list of structured color rows
  • color rows are saved to document_color_rows via the API
  • quantity fields written to documents table columns
  • rok_isporuke saved as a DATE column
  • signing datum_doc written to doc_params
  • backwards-compatible: all previously extracted fields still work
"""

import os
import re
import time
import hashlib
import pathlib
import datetime
import traceback
import unicodedata

from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from sqlalchemy import create_engine, text
from docx import Document as Docx
import meilisearch
import requests

# ── configuration ─────────────────────────────────────────────────────────────

BASE      = pathlib.Path(os.getenv("BASE_LOCAL", "/docs"))
PG_DSN    = os.getenv("PG_DSN")
MEILI_URL = os.getenv("MEILI_URL", "http://meili:7700")
MEILI_KEY = os.getenv("MEILI_KEY", "")
API_BASE  = os.getenv("API_BASE", "http://api:8000")
API_KEY   = os.getenv("API_KEY", "")

SUPPORTED = {".docx"}

engine = create_engine(PG_DSN, future=True)
ms     = meilisearch.Client(MEILI_URL, MEILI_KEY)
idx    = ms.index("docs")


# ══════════════════════════════════════════════════════════════════════════════
# Document parsing
# ══════════════════════════════════════════════════════════════════════════════

# Roman numerals I–XII used as color-position labels
_ROMAN_PAT = r"(?:I{1,3}|IV|VI{0,3}|IX|X{1,2}I{0,3})"

# Matches full color / lacquer rows:
#   "III kliše oznake CODE, variant, boja Color, raster 390l/cm, Z-93"
#   "VIII uređaj za lakiranje, UV lak, raster 160l/cm, Z-63"
_COLOR_RE = re.compile(
    r"^(?P<pos>" + _ROMAN_PAT + r")\s+"
    r"(?:"
        # ── kliše / klišei / kl.oz. rows ────────────────────────────────
        r"(?:kliše\s+(?:oznake|znake)|kl\.\s*ozn\.?|kl\.ozn\.?|kl\.\s*oz\.?|kl\s*\.\s*ozn\.?)\s+"
        r"(?P<klise>[^,]+?)\s*,\s*"
        r"(?P<variant>[^,]+?)\s*,\s*"
        r"(?:boja\s+)?(?P<color>[^,]+?)\s*,\s*"
        r"(?:ras(?:ter)?\.?\s+)?(?P<raster>[^,]+?)\s*,\s*"
        r"(?P<cylinder>Z-\d+(?:\s*\(?[^)]*\)?)?)"
        r"|"
        # ── uređaj za lakiranje rows ─────────────────────────────────────
        r"uređaj\s+za\s+lak(?:iranje)?[^,]*,\s*"
        r"(?P<lak_color>[^,]+?)\s*,\s*"
        r"(?:ras(?:ter)?\.?\s+)?(?P<lak_raster>[^,]*?)\s*,\s*"
        r"(?P<lak_cylinder>Z-\d+(?:[^,\n]*)?)"
    r")",
    re.IGNORECASE,
)

# Quantity line:  "1645 m  dobrih    (20.000 kom )   (12,23 kom/m)"
_QUANTITY_RE = re.compile(
    r"(?P<m_dobrih>\d[\d.\s]*)\s*m\b.*?"
    r"\(\s*(?P<kom>[\d.,\s]+)\s*(?:kom|pari|kompleta?)\.?\s*\).*?"
    r"\(\s*(?P<kom_po_m>[\d.,]+)\s*(?:kom|pari|kompleta?)/m\)",
    re.IGNORECASE,
)

# Date:  "24.07.2025." or "24.07.2025"
_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\.?\b")

# Extract die/tool code from ALATI lines, e.g. "ABC25-02-12345", "XYZ14-05-54321".
# STANCNA_PREFIXES (comma-separated, e.g. "ABC,XYZ") limits it to codes starting
# with the shop's own die prefixes, which also catches codes without a hyphen
# ("XYZ7"). Without it, any letters-then-number code with hyphens counts.
def _stancna_re(prefixes: str) -> re.Pattern:
    names = [re.escape(p.strip()) for p in prefixes.split(",") if p.strip()]
    if names:
        return re.compile(r"\b(?:" + "|".join(names) + r")[A-Z0-9-]*\d[A-Z0-9-]*\b", re.IGNORECASE)
    # A whole code only: "ABC25-02-12345A" is no match rather than "ABC25-02"
    return re.compile(r"\b[A-Z]{2,6}\d*(?:-[A-Z0-9]+)*-\d+(?![A-Z0-9-])", re.IGNORECASE)

_STANCNA_RE = _stancna_re(os.getenv("STANCNA_PREFIXES", ""))

# Standalone date paragraph (the signing date at the bottom of the doc)
_STANDALONE_DATE_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}\.?\s*$")

# "NALOG ZA PROIZVODNJU 6276"  (no colon – handled separately).
# Leading zeros are a template placeholder ("0001"), not a real number.
_NALOG_RE = re.compile(r"^NALOG\s+ZA\s+PROIZVODNJU\s+([1-9]\d*)", re.IGNORECASE)

# Strip whitespace runs
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _to_iso_date(text: str) -> str | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:   # rejects impossible dates such as 31.09.2025
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def _parse_quantity(text: str) -> dict:
    m = _QUANTITY_RE.search(text)
    if not m:
        return {}

    def _int(s):
        return int(re.sub(r"[.,\s]", "", s))

    def _float(s):
        # Same rules as parse_float_sr in client/formatting.py, which formats
        # this figure in the GUI ("1.234,50"); the server image has no client/
        s = s.strip().replace(" ", "")
        if "," in s:             # dots group thousands, comma is the decimal
            s = s.replace(".", "").replace(",", ".")
        elif s.count(".") > 1:   # 1.234.567
            s = s.replace(".", "")
        return float(s)

    result = {}
    for key, group, conv in (
        ("kolicina_m_dobrih",     "m_dobrih", _int),
        ("kolicina_kom_naruceno", "kom",      _int),
        ("kolicina_kom_po_m",     "kom_po_m", _float),
    ):
        try:
            result[key] = conv(m.group(group))
        except ValueError:
            pass   # leave unparsed; parse_warnings flags the order for review
    return result


# Key-value label → internal field name
_LABEL_MAP = {
    "mašina":          "masina",
    "masina":          "masina",
    "šifra":           "sifra",
    "sifra":           "sifra",
    "naziv":           "naziv",
    "dimenzija":       "dimenzija",
    "materijal":       "materijal",
    "širina":          "sirina",
    "sirina":          "sirina",
    "naručilac":       "narucilac",
    "narucilac":       "narucilac",
    "količina":        "kolicina",
    "kolicina":        "kolicina",
    "rok za isporuku": "rok_isporuke",
    "alati":           "alati",
}


def parse_production_order(p: pathlib.Path) -> dict:
    """
    Parse a production-order .docx into a structured dict.

    Returns
    -------
    {
      doc_number        : int | None
      masina            : str | None
      sifra             : str | None
      naziv             : str | None
      dimenzija         : str | None
      materijal         : str | None
      sirina            : str | None
      narucilac         : str | None
      kolicina_text     : str | None     # raw line, e.g. "1645 m dobrih (20.000 kom)"
      kolicina_m_dobrih : int | None
      kolicina_kom_naruceno : int | None
      kolicina_kom_po_m : float | None
      rok_isporuke      : str | None     # ISO date YYYY-MM-DD
      alati_raw         : str | None
      opis              : str | None
      napomena          : str | None
      datum_doc         : str | None     # signing date, ISO
      full_text         : str            # entire document text for FTS
      color_rows        : list[dict]     # parsed color/lacquer rows
    }
    """
    try:
        doc = Docx(str(p))
    except Exception:
        return {}

    result: dict = {
        "doc_number":             None,
        "masina":                 None,
        "sifra":                  None,
        "naziv":                  None,
        "dimenzija":              None,
        "materijal":              None,
        "sirina":                 None,
        "narucilac":              None,
        "kolicina_text":          None,
        "kolicina_m_dobrih":      None,
        "kolicina_kom_naruceno":  None,
        "kolicina_kom_po_m":      None,
        "rok_isporuke":           None,
        "alati_raw":              None,
        "stancna_code":           None,
        "opis":                   None,
        "napomena":               None,
        "datum_doc":              None,
        "full_text":              "",
        "color_rows":             [],
    }

    section    = None        # "colors" | "opis" | "napomena" | None
    opis_parts: list[str]     = []
    napom_parts: list[str]    = []
    full_lines: list[str]     = []

    # Paragraphs that mark the end of ŠIFRA BOJA (start of a new top field)
    # We detect these by a run of ALL-CAPS Serbian letters followed by ":"
    _TOPLABEL_RE = re.compile(
        r"^[A-ZŠŽĆĐČА-Я][A-ZŠŽĆĐČА-Я\s]{2,25}:",
    )

    for para in doc.paragraphs:
        text = _norm(para.text)
        if not text:
            continue

        full_lines.append(text)
        tl = text.lower()

        # ── "NALOG ZA PROIZVODNJU NNN"  (no colon) ───────────────────────
        m = _NALOG_RE.match(text)
        if m:
            result["doc_number"] = int(m.group(1))
            continue

        # ── section transitions ───────────────────────────────────────────
        if re.match(r"šifra\s+boja", tl):
            section = "colors"
            continue

        if re.match(r"opis\s*:", text, re.IGNORECASE):
            section = "opis"
            tail = re.sub(r"^opis\s*:\s*", "", text, flags=re.IGNORECASE).strip()
            if tail:
                opis_parts.append(tail)
            continue

        if re.match(r"napomena\s*:", text, re.IGNORECASE):
            section = "napomena"
            tail = re.sub(r"^napomena\s*:\s*", "", text, flags=re.IGNORECASE).strip()
            if tail:
                napom_parts.append(tail)
            continue

        # A top-level label ends the color section (but not opis/napomena –
        # those end naturally at "Datum")
        if section == "colors" and _TOPLABEL_RE.match(text):
            section = None

        # ── accumulate multi-line sections ────────────────────────────────
        # v2.1: OPIS/NAPOMENA must stop when a new top-level label appears.
        # Some historical orders place MATERIJAL/ŠIRINA/ALATI after OPIS.
        if section == "opis":
            if _TOPLABEL_RE.match(text) or re.match(r"datum", tl) or re.match(r"-{5,}", text):
                section = None
                # fall through so the label/date line can be parsed below
            else:
                opis_parts.append(text)
                continue

        if section == "napomena":
            if _TOPLABEL_RE.match(text) or re.match(r"datum", tl) or re.match(r"-{5,}", text):
                section = None
                # fall through so the label/date line can be parsed below
            else:
                napom_parts.append(text)
                continue

        # ── color rows ────────────────────────────────────────────────────
        if section == "colors":
            # Skip annotation lines (not starting with a Roman numeral)
            if not re.match(r"^" + _ROMAN_PAT, text, re.IGNORECASE):
                continue
            m = _COLOR_RE.match(text)
            if m:
                pos = m.group("pos")
                if m.group("klise"):
                    result["color_rows"].append({
                        "position_label": pos,
                        "klise_code":  _norm(m.group("klise")),
                        "variant":     _norm(m.group("variant")),
                        "color_text":  _norm(m.group("color")),
                        "raster":      _norm(m.group("raster")),
                        "cylinder":    _norm(m.group("cylinder")),
                        "supplier":    None,
                        "note":        None,
                    })
                else:
                    result["color_rows"].append({
                        "position_label": pos,
                        "klise_code":  "uređaj za lakiranje",
                        "variant":     None,
                        "color_text":  _norm(m.group("lak_color") or "UV lak"),
                        "raster":      _norm(m.group("lak_raster") or ""),
                        "cylinder":    _norm(m.group("lak_cylinder") or ""),
                        "supplier":    None,
                        "note":        None,
                    })
            continue

        # ── standalone signing-date paragraph ─────────────────────────────
        if _STANDALONE_DATE_RE.match(text):
            result["datum_doc"] = _to_iso_date(text)
            continue

        # ── key : value lines ─────────────────────────────────────────────
        if ":" not in text:
            continue

        colon   = text.index(":")
        raw_key = text[:colon].strip().lower()
        raw_val = _norm(text[colon + 1:])

        if not raw_val:
            continue

        # find the matching field
        field = None
        for label, fname in _LABEL_MAP.items():
            if label in raw_key:
                field = fname
                break

        if field is None:
            continue

        if field == "rok_isporuke":
            result["rok_isporuke"] = _to_iso_date(raw_val)

        elif field == "kolicina":
            result["kolicina_text"] = raw_val
            result.update(_parse_quantity(raw_val))

        elif field == "alati":
            result["alati_raw"] = raw_val
            m_st = _STANCNA_RE.search(raw_val)
            if m_st:
                result["stancna_code"] = m_st.group(0).upper()

        else:
            # masina / sifra / naziv / dimenzija / materijal / sirina / narucilac
            result[field] = raw_val

    # ── finalize multi-line sections ──────────────────────────────────────
    result["opis"]      = " | ".join(opis_parts)  or None
    result["napomena"]  = " | ".join(napom_parts) or None
    result["full_text"] = "\n".join(full_lines)

    # ── add position_num (1-based) ────────────────────────────────────────
    for i, row in enumerate(result["color_rows"]):
        row["position_num"] = i + 1

    return result


# ══════════════════════════════════════════════════════════════════════════════
# File helpers (unchanged from v1)
# ══════════════════════════════════════════════════════════════════════════════

def sha256_of(p: pathlib.Path) -> tuple[str, int]:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest(), p.stat().st_size


def sanitize_title_for_filename(title: str, fallback: str) -> str:
    base = (title or fallback or "nedefinisano").strip()
    for ch in r'\/:*?"<>|':
        base = base.replace(ch, " ")
    base = re.sub(r"\s+", " ", base).strip()
    return base[:80]


# ══════════════════════════════════════════════════════════════════════════════
# Sequence / doc-number helpers (unchanged from v1)
# ══════════════════════════════════════════════════════════════════════════════

# Never let one file push doc_number_seq further than this past the highest
# known number (guards against e.g. a date-like "20251006" being adopted).
MAX_NUMBER_AHEAD = 1000


def detect_number_from_text(full_text: str) -> int | None:
    m = re.search(r"NALOG\s+ZA\s+PROIZVODNJU\s+([1-9]\d*)", full_text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def detect_number_from_filename(name: str) -> int | None:
    """Only the watcher's own naming: "6276 - naziv" or a bare "6276"."""
    m = re.match(r"\s*([1-9]\d*)(?:\s+-|\s*$)", name)
    return int(m.group(1)) if m else None


def ensure_seq_at_least(n: int) -> None:
    with engine.begin() as cx:
        cx.execute(text("""
            SELECT setval(
                'doc_number_seq',
                GREATEST(
                    (SELECT COALESCE(MAX(doc_number), 0) FROM documents),
                    :n
                )
            )
        """), {"n": n})


def reserve_new_number(user: str = "watcher") -> int:
    with engine.begin() as cx:
        num = cx.execute(text("SELECT nextval('doc_number_seq')")).scalar_one()
        cx.execute(text("""
            INSERT INTO documents (doc_number, title, status, created_by)
            VALUES (:n, '', 'draft', :u)
        """), {"n": num, "u": user})
    return num


def adopt_manual_number(n: int, user: str = "watcher") -> int | None:
    with engine.begin() as cx:
        row = cx.execute(text(
            "SELECT doc_number FROM documents WHERE doc_number = :n"
        ), {"n": n}).scalar_one_or_none()
        highest = cx.execute(text("""
            SELECT GREATEST(
                (SELECT COALESCE(MAX(doc_number), 0) FROM documents),
                (SELECT last_value FROM doc_number_seq)
            )
        """)).scalar_one()
    if row is not None:
        return None   # already taken
    if n > highest + MAX_NUMBER_AHEAD:
        print(f"[watcher] not adopting implausible number {n} (highest is {highest})")
        return None
    ensure_seq_at_least(n)
    with engine.begin() as cx:
        cx.execute(text("""
            INSERT INTO documents (doc_number, title, status, created_by)
            VALUES (:n, '', 'draft', :u)
        """), {"n": n, "u": user})
    return n


# ══════════════════════════════════════════════════════════════════════════════
# Database / search writes
# ══════════════════════════════════════════════════════════════════════════════

def _save_color_rows(doc_number: int, rows: list[dict]) -> None:
    """
    Delete-and-reinsert color rows for this document.
    Uses the REST API so the same validation path as the GUI applies.
    If the API is unreachable, falls back to direct DB write.
    """
    # Always delete/reinsert, even when rows is empty, to avoid stale rows after edits.
    payload = {
        "doc_number": doc_number,
        "rows": rows,
    }

    try:
        r = requests.post(
            f"{API_BASE}/documents/colors/save",
            json=payload,
            headers={"x-api-key": API_KEY},
            timeout=10,
        )
        r.raise_for_status()
        return
    except Exception as exc:
        print(f"[watcher] color API failed ({exc}), writing direct to DB")

    # Direct DB fallback
    with engine.begin() as cx:
        cx.execute(text(
            "DELETE FROM document_color_rows WHERE doc_number = :n"
        ), {"n": doc_number})
        for row in rows:
            cx.execute(text("""
                INSERT INTO document_color_rows
                  (doc_number, position_num, position_label,
                   klise_code, variant, color_text, raster, cylinder, supplier, note)
                VALUES
                  (:dn, :pn, :pl, :kc, :va, :ct, :ra, :cy, :su, :no)
            """), {
                "dn": doc_number,
                "pn": row.get("position_num", 0),
                "pl": row.get("position_label", ""),
                "kc": row.get("klise_code"),
                "va": row.get("variant"),
                "ct": row.get("color_text"),
                "ra": row.get("raster"),
                "cy": row.get("cylinder"),
                "su": row.get("supplier"),
                "no": row.get("note"),
            })



def parse_warnings(meta: dict) -> list[str]:
    """Return human-readable warnings for missing/weak extraction results."""
    warnings: list[str] = []
    required = [
        ("doc_number", "missing document number"),
        ("sifra", "missing ŠIFRA"),
        ("naziv", "missing NAZIV"),
        ("dimenzija", "missing DIMENZIJA"),
        ("rok_isporuke", "missing ROK ZA ISPORUKU"),
        ("kolicina_text", "missing KOLIČINA"),
        ("alati_raw", "missing ALATI"),
    ]
    for key, message in required:
        if not meta.get(key):
            warnings.append(message)
    if meta.get("alati_raw") and not meta.get("stancna_code"):
        warnings.append("ALATI found but die/tool code was not extracted")
    if meta.get("kolicina_text") and any(
        meta.get(key) is None
        for key in ("kolicina_m_dobrih", "kolicina_kom_naruceno", "kolicina_kom_po_m")
    ):
        warnings.append("KOLIČINA found but quantities were not extracted")
    if not meta.get("color_rows"):
        warnings.append("no color/lacquer rows parsed")
    return warnings


def _save_parse_audit(cx, doc_number: int, meta: dict, warnings: list[str]) -> None:
    """Persist parser status. Requires schema_watcher_v2_1.sql."""
    status = "ok" if not warnings else "needs_review"
    cx.execute(text("""
        UPDATE documents
           SET parse_status = :status,
               parse_warnings = :warnings
         WHERE doc_number = :n
    """), {"n": doc_number, "status": status, "warnings": " | ".join(warnings) or None})
    cx.execute(text("""
        INSERT INTO document_parse_audit
          (doc_number, parser_version, parse_status, warnings, parsed_color_rows)
        VALUES
          (:n, 'watcher_v2_1', :status, :warnings, :rows)
    """), {
        "n": doc_number,
        "status": status,
        "warnings": " | ".join(warnings) or None,
        "rows": len(meta.get("color_rows", [])),
    })

def finalize_new_doc(
    num: int,
    dest: pathlib.Path,
    digest: str,
    size: int,
    meta: dict,
) -> None:
    """Write all parsed fields for a freshly numbered document."""
    rel_path  = str(dest.relative_to(BASE)).replace(os.sep, "/")
    naziv     = meta.get("naziv") or ""
    full_text = meta.get("full_text", "")
    now       = datetime.datetime.now(datetime.timezone.utc)
    warnings  = parse_warnings(meta)

    with engine.begin() as cx:
        cx.execute(text("""
            UPDATE documents SET
              rel_path               = :r,
              sha256                 = :h,
              size_bytes             = :s,
              title                  = COALESCE(NULLIF(:t, ''), title),
              status                 = 'active',
              created_at             = COALESCE(created_at, :now),
              -- lookup FKs (NULL if no match – kept safe)
              sifra                  = :sifra,
              naziv                  = :naziv,
              dimenzija              = :dimenzija,
              sirina                 = :sirina,
              kolicina_text          = :kolicina_text,
              kolicina_kom_naruceno  = :kom_naruceno,
              kolicina_kom_po_m      = :kom_po_m,
              kolicina_m_dobrih      = :m_dobrih,
              rok_isporuke           = :rok_isporuke
            WHERE doc_number = :n
        """), {
            "r":            rel_path,
            "h":            digest,
            "s":            size,
            "t":            naziv,
            "n":            num,
            "now":          now,
            "sifra":        meta.get("sifra"),
            "naziv":        naziv,
            "dimenzija":    meta.get("dimenzija"),
            "sirina":       meta.get("sirina"),
            "kolicina_text": meta.get("kolicina_text"),
            "kom_naruceno": meta.get("kolicina_kom_naruceno"),
            "kom_po_m":     meta.get("kolicina_kom_po_m"),
            "m_dobrih":     meta.get("kolicina_m_dobrih"),
            "rok_isporuke": meta.get("rok_isporuke"),
        })

        # FTS
        cx.execute(text("""
            INSERT INTO doc_text (doc_number, content)
            VALUES (:n, :c)
            ON CONFLICT (doc_number) DO UPDATE SET content = EXCLUDED.content
        """), {"n": num, "c": full_text})

        # doc_params – every extracted field
        params = {
            "masina":    meta.get("masina"),
            "sifra":     meta.get("sifra"),
            "naziv":     naziv,
            "dimenzija": meta.get("dimenzija"),
            "materijal": meta.get("materijal"),
            "sirina":    meta.get("sirina"),
            "narucilac": meta.get("narucilac"),
            "alati":     meta.get("alati_raw"),
            "stancna_code": meta.get("stancna_code"),
            "opis":      meta.get("opis"),
            "napomena":  meta.get("napomena"),
            "datum_doc": meta.get("datum_doc"),
        }
        for key, val in params.items():
            if val is not None:
                cx.execute(text("""
                    INSERT INTO doc_params (doc_number, key, value_text)
                    VALUES (:n, :k, :v)
                    ON CONFLICT (doc_number, key) DO UPDATE
                      SET value_text = EXCLUDED.value_text
                """), {"n": num, "k": key, "v": str(val)})

        _save_parse_audit(cx, num, meta, warnings)

    # color rows
    _save_color_rows(num, meta.get("color_rows", []))

    # Meilisearch
    _index_meili(num, rel_path, meta, full_text)

    print(f"[watcher] new #{num} → {rel_path}  "
          f"({len(meta.get('color_rows', []))} color rows, "
          f"rok={meta.get('rok_isporuke')})")


def update_existing_doc(
    num: int,
    p: pathlib.Path,
    digest: str,
    size: int,
    meta: dict,
) -> None:
    """Re-index an already-numbered document that was modified, renamed or
    moved (rel_path follows the file), or whose first processing failed
    half-way (a 'draft' with no file becomes 'active')."""
    rel_path  = str(p.relative_to(BASE)).replace(os.sep, "/")
    naziv     = meta.get("naziv") or ""
    full_text = meta.get("full_text", "")
    now       = datetime.datetime.now(datetime.timezone.utc)
    warnings  = parse_warnings(meta)

    with engine.begin() as cx:
        cx.execute(text("""
            UPDATE documents SET
              rel_path               = :r,
              status                 = CASE WHEN status = 'draft' THEN 'active' ELSE status END,
              created_at             = COALESCE(created_at, :now),
              sha256                 = :h,
              size_bytes             = :s,
              title                  = COALESCE(NULLIF(:t, ''), title),
              modified_at            = :now,
              sifra                  = :sifra,
              naziv                  = :naziv,
              dimenzija              = :dimenzija,
              sirina                 = :sirina,
              kolicina_text          = :kolicina_text,
              kolicina_kom_naruceno  = :kom_naruceno,
              kolicina_kom_po_m      = :kom_po_m,
              kolicina_m_dobrih      = :m_dobrih,
              rok_isporuke           = :rok_isporuke
            WHERE doc_number = :n
        """), {
            "h":            digest,
            "s":            size,
            "t":            naziv,
            "now":          now,
            "n":            num,
            "r":            rel_path,
            "sifra":        meta.get("sifra"),
            "naziv":        naziv,
            "dimenzija":    meta.get("dimenzija"),
            "sirina":       meta.get("sirina"),
            "kolicina_text": meta.get("kolicina_text"),
            "kom_naruceno": meta.get("kolicina_kom_naruceno"),
            "kom_po_m":     meta.get("kolicina_kom_po_m"),
            "m_dobrih":     meta.get("kolicina_m_dobrih"),
            "rok_isporuke": meta.get("rok_isporuke"),
        })

        cx.execute(text("""
            INSERT INTO doc_text (doc_number, content)
            VALUES (:n, :c)
            ON CONFLICT (doc_number) DO UPDATE SET content = EXCLUDED.content
        """), {"n": num, "c": full_text})

        params = {
            "masina":    meta.get("masina"),
            "sifra":     meta.get("sifra"),
            "naziv":     naziv,
            "dimenzija": meta.get("dimenzija"),
            "materijal": meta.get("materijal"),
            "sirina":    meta.get("sirina"),
            "narucilac": meta.get("narucilac"),
            "alati":     meta.get("alati_raw"),
            "stancna_code": meta.get("stancna_code"),
            "opis":      meta.get("opis"),
            "napomena":  meta.get("napomena"),
            "datum_doc": meta.get("datum_doc"),
        }
        for key, val in params.items():
            if val is not None:
                cx.execute(text("""
                    INSERT INTO doc_params (doc_number, key, value_text)
                    VALUES (:n, :k, :v)
                    ON CONFLICT (doc_number, key) DO UPDATE
                      SET value_text = EXCLUDED.value_text
                """), {"n": num, "k": key, "v": str(val)})

        _save_parse_audit(cx, num, meta, warnings)

    _save_color_rows(num, meta.get("color_rows", []))
    _index_meili(num, rel_path, meta, full_text)

    print(f"[watcher] updated #{num} → {rel_path}")


def _index_meili(
    num: int,
    rel_path: str,
    meta: dict,
    full_text: str,
) -> None:
    doc_ms = {
        "broj_naloga": num,
        "naziv":       meta.get("naziv", ""),
        "masina":      meta.get("masina", ""),
        "sifra":       meta.get("sifra", ""),
        "dimenzija":   meta.get("dimenzija", ""),
        "materijal":   meta.get("materijal", ""),
        "sirina":      meta.get("sirina", ""),
        "narucilac":   meta.get("narucilac", ""),
        "alati":       meta.get("alati_raw", ""),
        "rok_isporuke": meta.get("rok_isporuke", ""),
        "rel_path":    rel_path,
        "content_excerpt": full_text[:2000],
    }
    try:
        idx.add_documents([doc_ms], primary_key="broj_naloga")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Event handlers  (same two-path logic as v1, now using parse_production_order)
# ══════════════════════════════════════════════════════════════════════════════

def handle_new_or_manual_doc(p: pathlib.Path, meta: dict | None = None) -> None:
    if meta is None:
        meta = parse_production_order(p)
    full_text = meta.get("full_text", "")
    digest, size = sha256_of(p)

    # Skip if we already have this exact file content
    with engine.begin() as cx:
        row = cx.execute(text("""
            SELECT doc_number FROM documents
             WHERE sha256 = :h AND size_bytes = :s
             LIMIT 1
        """), {"h": digest, "s": size}).first()
    if row is not None:
        return

    # Decide document number
    cand_text  = meta.get("doc_number") or detect_number_from_text(full_text)
    cand_fname = detect_number_from_filename(p.stem)
    candidate  = cand_text or cand_fname

    final_num: int
    if candidate is not None:
        adopted = adopt_manual_number(candidate)
        final_num = adopted if adopted is not None else reserve_new_number()
    else:
        final_num = reserve_new_number()

    # Stamp the header line in the document
    try:
        doc = Docx(str(p))
        header_line = f"NALOG ZA PROIZVODNJU {final_num}"
        replaced = False
        for para in doc.paragraphs:
            if "NALOG ZA PROIZVODNJU" in para.text:
                para.text = header_line
                replaced = True
                break
        if not replaced and doc.paragraphs:
            doc.paragraphs[0].insert_paragraph_before(header_line)
        doc.save(str(p))
        # Re-parse after header normalisation
        meta = parse_production_order(p)
    except Exception:
        pass

    # Move to date-based subdirectory
    today   = datetime.datetime.now()
    dest_dir = BASE / today.strftime("%Y") / today.strftime("%m") / today.strftime("%d")
    dest_dir.mkdir(parents=True, exist_ok=True)

    naziv      = meta.get("naziv", "")
    safe_title = sanitize_title_for_filename(naziv, p.stem)
    dest       = dest_dir / f"{final_num} - {safe_title}.docx"
    i = 2
    while dest.exists():
        dest = dest_dir / f"{final_num} - {safe_title}_{i}.docx"
        i += 1

    dest.write_bytes(p.read_bytes())
    try:
        p.unlink()
    except Exception:
        pass

    # Final parse + hash from the destination file
    digest, size = sha256_of(dest)
    meta = parse_production_order(dest)

    finalize_new_doc(final_num, dest, digest, size, meta)


def _is_existing_order(num: int, rel_path: str) -> bool:
    """True if the file at rel_path is (still) order `num`: it is the order's
    recorded file, or the order has no file yet / its file is gone (renamed,
    moved, or the first processing failed half-way)."""
    with engine.connect() as cx:
        row = cx.execute(text(
            "SELECT rel_path FROM documents WHERE doc_number = :n"
        ), {"n": num}).first()
    if row is None:
        return False
    old = row.rel_path or ""
    return old == rel_path or not old or not (BASE / old).is_file()


def handle_doc(p: pathlib.Path) -> None:
    rel_path   = str(p.relative_to(BASE)).replace(os.sep, "/")
    meta       = parse_production_order(p)
    cand_text  = meta.get("doc_number")
    cand_fname = detect_number_from_filename(p.stem)

    # A known order – even renamed or moved – keeps its number. The header
    # number, when present, must agree (a copy edited into a new order won't).
    for num in dict.fromkeys(n for n in (cand_fname, cand_text) if n):
        if cand_text in (None, num) and _is_existing_order(num, rel_path):
            digest, size = sha256_of(p)
            update_existing_doc(num, p, digest, size, meta)
            return

    handle_new_or_manual_doc(p, meta)


# ══════════════════════════════════════════════════════════════════════════════
# Watchdog handler
# ══════════════════════════════════════════════════════════════════════════════

class Handler(FileSystemEventHandler):
    def _settle(self, p: pathlib.Path) -> None:
        """Wait until the file stops growing (copy/save finished)."""
        size0 = -1
        for _ in range(10):
            try:
                size1 = p.stat().st_size
            except FileNotFoundError:
                return
            if size1 == size0:
                return
            size0 = size1
            time.sleep(0.2)

    def process(self, p: pathlib.Path) -> None:
        if p.suffix.lower() not in SUPPORTED:
            return
        if p.name.startswith("~$"):   # Office temp files
            return

        try:
            self._settle(p)
            if p.exists():   # may already be moved away, e.g. by handle_new_or_manual_doc
                handle_doc(p)
        except FileNotFoundError:
            pass   # vanished while being processed (moved or deleted)
        except Exception:
            # Never let one bad file kill the observer thread
            print(f"[watcher] ERROR processing {p}:\n{traceback.format_exc()}")

    def on_created(self, event):
        if not event.is_directory:
            self.process(pathlib.Path(event.src_path))

    def on_modified(self, event):
        if not event.is_directory:
            self.process(pathlib.Path(event.src_path))

    def on_moved(self, event):
        # Renames, Word/LibreOffice save-via-rename, finished downloads (.part → .docx)
        if not event.is_directory:
            self.process(pathlib.Path(event.dest_path))


# ══════════════════════════════════════════════════════════════════════════════
# Startup catch-up
# ══════════════════════════════════════════════════════════════════════════════

def backfill() -> None:
    """Process .docx files that are new or changed since the watcher last ran."""
    with engine.connect() as cx:
        known = dict(cx.execute(text(
            "SELECT rel_path, sha256 FROM documents WHERE COALESCE(rel_path, '') <> ''"
        )).all())
    handler = Handler()
    for p in sorted(BASE.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in SUPPORTED or p.name.startswith("~$"):
            continue
        rel_path = str(p.relative_to(BASE)).replace(os.sep, "/")
        try:
            if known.get(rel_path) == sha256_of(p)[0]:
                continue
        except FileNotFoundError:
            continue
        print(f"[watcher] backfill: {rel_path}")
        handler.process(p)


def sync_search_index() -> None:
    """Rebuild the Meilisearch index from Postgres, the source of truth, so
    orders saved from the GUI or while the watcher was down are searchable."""
    with engine.connect() as cx:
        docs = cx.execute(text("""
            SELECT d.doc_number, d.rel_path, d.naziv, d.sifra, d.dimenzija,
                   d.sirina, d.rok_isporuke, t.content
              FROM documents d
              LEFT JOIN doc_text t USING (doc_number)
        """)).mappings().all()
        params: dict[int, dict] = {}
        for r in cx.execute(text("SELECT doc_number, key, value_text FROM doc_params")):
            params.setdefault(r.doc_number, {})[r.key] = r.value_text

    def s(v) -> str:
        return "" if v is None else str(v)

    batch = []
    for d in docs:
        p = params.get(d["doc_number"], {})
        doc_ms = {
            "broj_naloga":  d["doc_number"],
            "naziv":        s(d["naziv"] or p.get("naziv")),
            "masina":       s(p.get("masina")),
            "sifra":        s(d["sifra"] or p.get("sifra")),
            "dimenzija":    s(d["dimenzija"] or p.get("dimenzija")),
            "materijal":    s(p.get("materijal")),
            "sirina":       s(d["sirina"] or p.get("sirina")),
            "narucilac":    s(p.get("narucilac")),
            "alati":        s(p.get("alati")),
            "rok_isporuke": s(d["rok_isporuke"]),
            "rel_path":     s(d["rel_path"]),
            "content_excerpt": s(d["content"])[:2000],
        }
        # Skip empty reserved numbers
        if any(v for k, v in doc_ms.items() if k not in ("broj_naloga", "rel_path")):
            batch.append(doc_ms)
    if batch:
        ms.wait_for_task(idx.add_documents(batch, primary_key="broj_naloga").task_uid)

    # Drop index entries for orders that no longer exist / became empty
    keep, stale, offset = {d["broj_naloga"] for d in batch}, [], 0
    while True:
        page = idx.get_documents({"fields": ["broj_naloga"], "limit": 1000, "offset": offset})
        stale += [d.broj_naloga for d in page.results if d.broj_naloga not in keep]
        offset += len(page.results)
        if not page.results or offset >= page.total:
            break
    if stale:
        idx.delete_documents(stale)
    print(f"[watcher] search index synced: {len(batch)} orders, {len(stale)} stale removed")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    BASE.mkdir(parents=True, exist_ok=True)
    for step in (backfill, sync_search_index):
        try:
            step()
        except Exception:
            print(f"[watcher] startup {step.__name__} failed:\n{traceback.format_exc()}")

    polling  = os.getenv("WATCH_USE_POLLING", "") == "1"
    observer = PollingObserver() if polling else Observer()
    observer.schedule(Handler(), str(BASE), recursive=True)
    observer.start()
    print(f"[watcher] Watching {BASE} … ({'polling' if polling else 'inotify'})")
    try:
        # If the observer thread ever dies, exit so Docker restarts the watcher
        # instead of leaving a container that looks healthy but does nothing.
        while observer.is_alive():
            time.sleep(1)
        print("[watcher] observer thread stopped – exiting")
        raise SystemExit(1)
    finally:
        observer.stop()
        observer.join()
