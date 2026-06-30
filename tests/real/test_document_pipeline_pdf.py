"""Real K6 PDF DocumentPipeline tests."""
from __future__ import annotations

import pytest


def _write_minimal_pdf(path):
    from pypdf import PdfWriter

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    # pypdf can create a valid PDF without external binary fixtures. Blank PDFs
    # have no extractable text, so the pipeline should still create a parent
    # record and an auditable fallback chunk.
    page.compress_content_streams()
    with path.open("wb") as handle:
        writer.write(handle)


@pytest.mark.real
@pytest.mark.requires_service("ollama")
def test_pdf_document_pipeline_uses_real_pdf_parser_and_parent_citations(real_db, tmp_path):
    from core.document_pipeline import DocumentPipeline
    from core.vector_backend import SQLiteVecBackend

    source = tmp_path / "contrato-k6.pdf"
    _write_minimal_pdf(source)

    pipeline = DocumentPipeline(real_db)
    result = pipeline.ingest(source, project="Hive-Mind")

    assert result.document_id.startswith("doc-")
    assert result.chunks_count >= 1
    assert result.indexed_vectors == result.chunks_count

    row = real_db.execute("SELECT * FROM document_chunks WHERE document_id = ?", (result.document_id,)).fetchone()
    assert row is not None
    assert row["source_uri"].endswith("contrato-k6.pdf")
    assert row["offset_start"] == 0
    assert row["offset_end"] > 0
    assert row["content"]

    backend = SQLiteVecBackend(real_db)
    assert backend.count("document_vectors") == result.chunks_count

    citations = pipeline.query("contrato k6 pdf", top_k=1)
    assert citations
    assert citations[0]["parent"]["id"] == result.document_id
    assert citations[0]["source_uri"].endswith("contrato-k6.pdf")
