-- Versions of an order: 12345-1, 12345-2, ... (server/order_numbers.py).
--
-- A version is a row of documents like any order, with its own fields,
-- colour rows and Word file. base_number is the order it is a version of,
-- doc_version the number after the dash. Its doc_number, the key the other
-- tables use, comes from doc_version_seq, which counts down from -1, so
-- versions never use up or move the order numbers (doc_number_seq and the
-- highest doc_number).
--
-- Safe to run again.

CREATE SEQUENCE IF NOT EXISTS doc_version_seq INCREMENT BY -1 MAXVALUE -1 START WITH -1;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS base_number BIGINT REFERENCES documents(doc_number),
  ADD COLUMN IF NOT EXISTS doc_version INTEGER CHECK (doc_version BETWEEN 1 AND 999);

CREATE UNIQUE INDEX IF NOT EXISTS documents_base_version_uq
  ON documents (base_number, doc_version) WHERE doc_version IS NOT NULL;
