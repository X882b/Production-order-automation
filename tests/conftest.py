"""Shared test setup.

The watcher creates its database engine and search client when it is
imported. Point it at an in-memory SQLite URL so importing it never needs
Postgres or Meilisearch; the parsing code under test makes no database calls.
"""
import os

os.environ.setdefault("PG_DSN", "sqlite://")

import pytest
from docx import Document


@pytest.fixture
def make_docx(tmp_path):
    """Return a function that writes a .docx with one paragraph per line."""
    def _make(lines, name="order.docx"):
        doc = Document()
        for line in lines:
            doc.add_paragraph(line)
        path = tmp_path / name
        doc.save(str(path))
        return path
    return _make
