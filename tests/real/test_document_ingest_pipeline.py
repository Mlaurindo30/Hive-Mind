"""Real K6 coverage for scripts/knowledge/document_ingest.py -> DocumentPipeline."""
from __future__ import annotations

import pytest


def _write_minimal_pdf(path):
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=300, height=200)
    with path.open("wb") as handle:
        writer.write(handle)


@pytest.mark.real
@pytest.mark.requires_service("ollama")
def test_document_ingest_single_file_feeds_document_pipeline(real_db, tmp_path):
    from core.vector_backend import SQLiteVecBackend
    from scripts.knowledge import document_ingest

    source = tmp_path / "ingest-k6.pdf"
    _write_minimal_pdf(source)

    assert document_ingest.ingest_single_file(source) is True

    doc = real_db.execute(
        "SELECT * FROM document_memories WHERE file_path = ?",
        (str(source.resolve()),),
    ).fetchone()
    assert doc is not None

    chunks = real_db.execute(
        "SELECT * FROM document_chunks WHERE document_id = ?",
        (doc["id"],),
    ).fetchall()
    assert chunks
    assert all(row["parent_id"] == doc["id"] for row in chunks)
    assert all(row["source_uri"] == str(source.resolve()) for row in chunks)

    obs = real_db.execute(
        "SELECT * FROM observations WHERE type = 'document_ingest' AND title LIKE ?",
        ("%ingest-k6.pdf%",),
    ).fetchone()
    assert obs is not None

    assert SQLiteVecBackend(real_db).count("document_vectors") == len(chunks)
