"""Import dies (štancne) from the Excel sheet into the tools table.

Re-running is safe: each imported sheet's rows are replaced in one
transaction. Use --dry-run to see what would be imported without writing.
"""
import os
import re
import sys
import pandas as pd
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

EXCEL_PATH = ROOT / "stancne" / "Kopija Dimenzije štancni (002).xlsx"

SHEETS = ["STANDARDNI OBLIK", "SPEC. OBLIK"]

# Every sheet has the same layout: two header rows (in SPEC. OBLIK a label
# is split across both), a blank row, then data. Columns are read by
# position; the header word must be found there or the import aborts.
COLUMNS = {
    "dimenzija_sirina_mm": (1, "širina"),
    "dimenzija_visina_mm": (2, "visina"),
    "broj_zuba":           (3, "zuba"),
    "obim_cilindra_mm":    (4, "cilindra"),
    "raspored":            (5, "raspored"),
    "oznaka_stancne":      (9, "štancne"),
    "oznaka_proizvodjaca": (10, "proizvođača"),
}
HEADER_ROWS = 3


def cell_text(val):
    """Excel cell -> stripped text, or None when empty. 71.0 -> '71'."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, float) and val.is_integer():
        val = int(val)
    s = str(val).strip()
    return s or None


def parse_num(val):
    s = cell_text(val)
    if s is None:
        return None
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_raspored(val):
    raw = cell_text(val)
    if raw is None:
        return (None, None, None)

    s = raw.lower().replace("×", "x").replace(" ", "")
    m = re.match(r"^(\d+)x(\d+)$", s)
    if not m:
        return (raw, None, None)

    rows_long = int(m.group(1))
    rows_wide = int(m.group(2))
    return (raw, rows_long, rows_wide)


def read_sheet(sheet: str) -> list[tuple]:
    df = pd.read_excel(EXCEL_PATH, sheet_name=sheet, header=None, dtype=object)

    for col, word in COLUMNS.values():
        header = " ".join(cell_text(df.iat[r, col]) or "" for r in range(2)).lower() \
            if col < df.shape[1] else ""
        if word not in header:
            sys.exit(f"[ERROR] Sheet '{sheet}': column {col} should contain '{word}', "
                     f"found '{header}'. Layout changed – nothing imported.")

    rows = []
    for i in range(HEADER_ROWS, len(df)):
        cell = {f: df.iat[i, col] for f, (col, _) in COLUMNS.items()}
        if all(cell_text(v) is None for v in cell.values()):
            continue   # blank or title-only row
        raspored_raw, rows_long, rows_wide = parse_raspored(cell["raspored"])
        rows.append((
            sheet,
            cell_text(cell["oznaka_stancne"]),
            cell_text(cell["oznaka_proizvodjaca"]),
            parse_num(cell["dimenzija_sirina_mm"]),
            parse_num(cell["dimenzija_visina_mm"]),
            cell_text(cell["broj_zuba"]),
            parse_num(cell["obim_cilindra_mm"]),
            raspored_raw,
            rows_long,
            rows_wide,
        ))
    return rows


def main():
    dry_run = "--dry-run" in sys.argv

    # Read and validate every sheet before touching the database
    by_sheet = {sheet: read_sheet(sheet) for sheet in SHEETS}
    for sheet, rows in by_sheet.items():
        print(f"{sheet}: {len(rows)} tool rows")
    if dry_run:
        print("Dry run – nothing written.")
        return

    db_dsn = (
        f"postgresql://{os.environ['PG_USER']}:{os.environ['PG_PASS']}"
        f"@localhost:{os.getenv('PG_PORT', '5432')}/{os.environ['PG_DB']}"
    )
    conn = psycopg2.connect(db_dsn)
    with conn, conn.cursor() as cur:   # one transaction: all sheets or nothing
        for sheet, rows in by_sheet.items():
            cur.execute("DELETE FROM tools WHERE sheet_name = %s", (sheet,))
            cur.executemany(
                """
                INSERT INTO tools (
                    sheet_name,
                    oznaka_stancne,
                    oznaka_proizvodjaca,
                    dimenzija_sirina_mm,
                    dimenzija_visina_mm,
                    broj_zuba,
                    obim_cilindra_mm,
                    raspored,
                    rows_long,
                    rows_wide
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
    conn.close()

    print(f"Imported {sum(len(r) for r in by_sheet.values())} tool rows "
          f"(replacing the previous rows of these sheets).")


if __name__ == "__main__":
    main()
