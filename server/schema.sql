CREATE SEQUENCE IF NOT EXISTS doc_number_seq START 100000 INCREMENT BY 1;

CREATE TABLE IF NOT EXISTS documents (
  doc_number     BIGINT PRIMARY KEY DEFAULT nextval('doc_number_seq'),
  title          TEXT,
  ext            TEXT NOT NULL DEFAULT 'docx',
  rel_path       TEXT NOT NULL DEFAULT '',
  sha256         TEXT NOT NULL DEFAULT '',
  size_bytes     BIGINT NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by     TEXT,
  file_created_at  TIMESTAMPTZ,
  file_modified_at TIMESTAMPTZ,
  customer       TEXT,
  status         TEXT NOT NULL DEFAULT 'draft'
);

CREATE TABLE IF NOT EXISTS doc_params (
  doc_number   BIGINT REFERENCES documents(doc_number) ON DELETE CASCADE,
  key          TEXT NOT NULL,
  value_text   TEXT,
  value_num    DOUBLE PRECISION,
  unit         TEXT,
  PRIMARY KEY (doc_number, key)
);

CREATE TABLE IF NOT EXISTS doc_text (
  doc_number BIGINT PRIMARY KEY REFERENCES documents(doc_number) ON DELETE CASCADE,
  content    TEXT,
  tsv        tsvector
);

CREATE INDEX IF NOT EXISTS doc_text_tsv_gin ON doc_text USING GIN(tsv);

CREATE OR REPLACE FUNCTION doc_text_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.tsv := setweight(to_tsvector('simple', coalesce(NEW.content,'')), 'A');
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS doc_text_tsv ON doc_text;
CREATE TRIGGER doc_text_tsv BEFORE INSERT OR UPDATE ON doc_text
FOR EACH ROW EXECUTE FUNCTION doc_text_tsv_trigger();
