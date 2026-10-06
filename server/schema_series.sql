CREATE TABLE IF NOT EXISTS product_series (
    id          SERIAL PRIMARY KEY,
    sifra       VARCHAR NOT NULL,
    datum       DATE NOT NULL,
    note        TEXT,
    doc_number  INT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_product_series_sifra_datum
    ON product_series (LOWER(sifra), datum);
