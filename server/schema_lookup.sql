-- Lookup tables for Production Order form

CREATE TABLE IF NOT EXISTS machines (
  id      BIGSERIAL PRIMARY KEY,
  name    TEXT NOT NULL UNIQUE,
  active  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS customers (
  id      BIGSERIAL PRIMARY KEY,
  name    TEXT NOT NULL UNIQUE,
  active  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS materials (
  id      BIGSERIAL PRIMARY KEY,
  name    TEXT NOT NULL UNIQUE,
  active  BOOLEAN NOT NULL DEFAULT TRUE
);

-- Product catalog to enable ŠIFRA -> autofill
CREATE TABLE IF NOT EXISTS products (
  id          BIGSERIAL PRIMARY KEY,
  sifra       TEXT NOT NULL UNIQUE,
  naziv       TEXT NOT NULL DEFAULT '',
  dimenzija   TEXT NOT NULL DEFAULT '',
  sirina      TEXT NOT NULL DEFAULT '',
  customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,
  material_id BIGINT REFERENCES materials(id) ON DELETE SET NULL,
  active      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS products_sifra_idx ON products (sifra);
CREATE INDEX IF NOT EXISTS products_naziv_idx ON products (naziv);

-- Extend documents table with production-order fields (safe additive)
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS machine_id BIGINT REFERENCES machines(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS sifra TEXT,
  ADD COLUMN IF NOT EXISTS naziv TEXT,
  ADD COLUMN IF NOT EXISTS dimenzija TEXT,
  ADD COLUMN IF NOT EXISTS sirina TEXT,
  ADD COLUMN IF NOT EXISTS customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS material_id BIGINT REFERENCES materials(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS kolicina_text TEXT,
  ADD COLUMN IF NOT EXISTS rok_isporuke DATE;

-- Presses offered in the MAŠINA list
INSERT INTO machines(name) VALUES
  ('Mark Andy'),
  ('Nilpeter F200'),
  ('Nilpeter FA2500')
ON CONFLICT (name) DO NOTHING;
