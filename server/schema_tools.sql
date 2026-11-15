CREATE TABLE IF NOT EXISTS tools (
    id BIGSERIAL PRIMARY KEY,

    sheet_name TEXT,                 -- STANDARDNI OBLIK / SPEC. OBLIK
    oznaka_stancne TEXT,             -- OZNAKA ŠTANCNE
    oznaka_proizvodjaca TEXT,        -- OZNAKA PROIZVOĐAČA

    dimenzija_sirina_mm NUMERIC,     -- DIMENZIJE širina (mm)
    dimenzija_visina_mm NUMERIC,     -- DIMENZIJE visina (mm)

    broj_zuba TEXT,                  -- keep as text for now
    obim_cilindra_mm NUMERIC,        -- CRITICAL
    raspored TEXT,                   -- "3 x 2": lanes across the web x labels around the cylinder

    rows_long INTEGER,               -- labels around the cylinder (raspored's second number)
    rows_wide INTEGER,               -- lanes across the web (raspored's first number)

    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS tools_oznaka_stancne_idx
    ON tools (oznaka_stancne);

CREATE INDEX IF NOT EXISTS tools_sheet_name_idx
    ON tools (sheet_name);

CREATE INDEX IF NOT EXISTS tools_obim_idx
    ON tools (obim_cilindra_mm);

-- Imports before this fix stored the two numbers of raspored the other way
-- round. Derive both again from the text; safe to re-run.
UPDATE tools t
SET rows_wide = p.parts[1]::int,
    rows_long = p.parts[2]::int
FROM (
    SELECT id,
           regexp_match(replace(replace(lower(raspored), '×', 'x'), ' ', ''),
                        '^(\d{1,4})x(\d{1,4})$') AS parts
    FROM tools
) p
WHERE p.id = t.id
  AND p.parts IS NOT NULL
  AND (t.rows_wide IS DISTINCT FROM p.parts[1]::int
       OR t.rows_long IS DISTINCT FROM p.parts[2]::int);
