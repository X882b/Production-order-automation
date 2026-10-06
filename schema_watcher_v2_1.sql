BEGIN;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS modified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS parse_status TEXT DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS parse_warnings TEXT;

CREATE TABLE IF NOT EXISTS document_parse_audit (
  id BIGSERIAL PRIMARY KEY,
  doc_number INTEGER NOT NULL REFERENCES documents(doc_number) ON DELETE CASCADE,
  parser_version TEXT NOT NULL,
  parse_status TEXT NOT NULL,
  warnings TEXT,
  parsed_color_rows INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_parse_audit_doc_number_created
  ON document_parse_audit (doc_number, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_documents_parse_status
  ON documents (parse_status);

COMMIT;
