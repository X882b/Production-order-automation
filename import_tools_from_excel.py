import os
import re
import pandas as pd
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

EXCEL_PATH = ROOT / "stancne" / "Kopija Dimenzije štancni (002).xlsx"

DB_DSN = (
    f"postgresql://{os.environ['PG_USER']}:{os.environ['PG_PASS']}"
    f"@localhost:{os.getenv('PG_PORT', '5432')}/{os.environ['PG_DB']}"
)

SHEETS = ["STANDARDNI OBLIK", "SPEC. OBLIK"]

COL_MAP = {
    "DIMENZIJE širina (mm)": "dimenzija_sirina_mm",
    "DIMENZIJE visina (mm)": "dimenzija_visina_mm",
    "BROJ ZUBA": "broj_zuba",
    "OBIM CILINDRA": "obim_cilindra_mm",
    "RASPORED Š x V": "raspored",
    "OZNAKA ŠTANCNE": "oznaka_stancne",
    "OZNAKA PROIZVOĐAČA": "oznaka_proizvodjaca",
}

def parse_num(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    if not s:
        return None
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

def parse_raspored(val):
    if pd.isna(val):
        return (None, None, None)
    raw = str(val).strip()
    if not raw:
        return (None, None, None)

    s = raw.lower().replace("×", "x").replace(" ", "")
    m = re.match(r"^(\d+)x(\d+)$", s)
    if not m:
        return (raw, None, None)

    rows_long = int(m.group(1))
    rows_wide = int(m.group(2))
    return (raw, rows_long, rows_wide)

def main():
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    inserted = 0

    for sheet in SHEETS:
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet)

        # Keep only columns we care about if present
        available = [c for c in COL_MAP.keys() if c in df.columns]
        if not available:
            print(f"[WARN] Sheet '{sheet}' has none of the expected columns.")
            continue

        sub = df[available].copy()

        for _, row in sub.iterrows():
            oznaka_stancne = str(row.get("OZNAKA ŠTANCNE", "")).strip()
            oznaka_proizvodjaca = str(row.get("OZNAKA PROIZVOĐAČA", "")).strip()

            # Skip fully empty rows
            if not any(str(row.get(c, "")).strip() for c in available):
                continue

            dim_s = parse_num(row.get("DIMENZIJE širina (mm)"))
            dim_v = parse_num(row.get("DIMENZIJE visina (mm)"))
            broj_zuba = str(row.get("BROJ ZUBA", "")).strip() or None
            obim = parse_num(row.get("OBIM CILINDRA"))
            raspored_raw, rows_long, rows_wide = parse_raspored(row.get("RASPORED Š x V"))

            cur.execute(
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
                (
                    sheet,
                    oznaka_stancne or None,
                    oznaka_proizvodjaca or None,
                    dim_s,
                    dim_v,
                    broj_zuba,
                    obim,
                    raspored_raw,
                    rows_long,
                    rows_wide,
                ),
            )
            inserted += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"Inserted {inserted} tool rows.")

if __name__ == "__main__":
    main()
