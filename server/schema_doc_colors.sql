CREATE TABLE IF NOT EXISTS document_color_rows (
    id BIGSERIAL PRIMARY KEY,
    doc_number BIGINT REFERENCES documents(doc_number) ON DELETE CASCADE,

    position_num INTEGER NOT NULL,
    position_label TEXT NOT NULL,

    klise_code TEXT,
    variant TEXT,
    color_text TEXT,
    raster TEXT,
    cylinder TEXT,
    supplier TEXT,
    note TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS doc_color_rows_doc_idx
ON document_color_rows(doc_number);
