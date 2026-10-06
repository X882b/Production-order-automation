CREATE TABLE IF NOT EXISTS tools (
    id BIGSERIAL PRIMARY KEY,

    sheet_name TEXT,                 -- STANDARDNI OBLIK / SPEC. OBLIK
    oznaka_stancne TEXT,             -- OZNAKA ŠTANCNE
    oznaka_proizvodjaca TEXT,        -- OZNAKA PROIZVOĐAČA

    dimenzija_sirina_mm NUMERIC,     -- DIMENZIJE širina (mm)
    dimenzija_visina_mm NUMERIC,     -- DIMENZIJE visina (mm)

    broj_zuba TEXT,                  -- keep as text for now
    obim_cilindra_mm NUMERIC,        -- CRITICAL
    raspored TEXT,                   -- e.g. "3 x 2"

    rows_long INTEGER,               -- parsed from raspored
    rows_wide INTEGER,               -- parsed from raspored

    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS tools_oznaka_stancne_idx
    ON tools (oznaka_stancne);

CREATE INDEX IF NOT EXISTS tools_sheet_name_idx
    ON tools (sheet_name);

CREATE INDEX IF NOT EXISTS tools_obim_idx
    ON tools (obim_cilindra_mm);
