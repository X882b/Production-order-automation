ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS kolicina_kom_naruceno BIGINT,
  ADD COLUMN IF NOT EXISTS kolicina_kom_po_m NUMERIC,
  ADD COLUMN IF NOT EXISTS kolicina_m_dobrih INTEGER,
  ADD COLUMN IF NOT EXISTS kolicina_add_m INTEGER,

  -- temporary diecut params until ALATI is implemented
  ADD COLUMN IF NOT EXISTS stancna_mm NUMERIC,
  ADD COLUMN IF NOT EXISTS rows_long INTEGER,
  ADD COLUMN IF NOT EXISTS rows_wide INTEGER,

  ADD COLUMN IF NOT EXISTS kolicina_note TEXT;

-- kolicina_text already exists; we keep it as the formatted one-liner
