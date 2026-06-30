"""Real K6 markdown DocumentPipeline tests.

Uses a real SQLite UMC database, real sqlite-vec tables and real Ollama
embeddings. No mocks.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.real
@pytest.mark.requires_service("ollama")
def test_markdown_document_pipeline_chunks_indexes_and_returns_parent_citations(real_db, tmp_path):
    from core.document_pipeline import DocumentPipeline
    from core.vector_backend import SQLiteVecBackend

    source = tmp_path / "arquitetura-k6.md"
    source.write_text(
        """# Arquitetura K6

Introducao geral que deve ficar como contexto pai.

## Chunking Por Secao

O DocumentPipeline precisa quebrar Markdown por secoes pequenas e preservar
offsets para citacao precisa. O parent document deve continuar recuperavel.

## Citacoes

Cada resultado deve retornar source_uri, offset_start, offset_end e parent com
document_id e file_hash. Isso permite resposta com evidencia verificavel.
""",
        encoding="utf-8",
    )

    pipeline = DocumentPipeline(real_db)
    result = pipeline.ingest(source, project="Hive-Mind")

    assert result.document_id.startswith("doc-")
    assert result.chunks_count >= 3
    assert result.indexed_vectors == result.chunks_count

    docs = real_db.execute("SELECT * FROM document_memories WHERE id = ?", (result.document_id,)).fetchall()
    assert len(docs) == 1
    metadata = json.loads(docs[0]["metadata"])
    assert metadata["source"] == "document_pipeline"
    assert metadata["content_type"] == "text/markdown"

    rows = real_db.execute(
        "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY chunk_index",
        (result.document_id,),
    ).fetchall()
    assert len(rows) == result.chunks_count
    assert {row["parent_id"] for row in rows} == {result.document_id}
    assert all(row["source_uri"].endswith("arquitetura-k6.md") for row in rows)
    assert all(row["offset_start"] < row["offset_end"] for row in rows)
    assert any(row["heading"] == "Chunking Por Secao" for row in rows)

    backend = SQLiteVecBackend(real_db)
    assert backend.count("document_vectors") == result.chunks_count

    citations = pipeline.query("citacao precisa parent document", top_k=2)
    assert citations
    top = citations[0]
    assert top["source_uri"].endswith("arquitetura-k6.md")
    assert top["offset_start"] < top["offset_end"]
    assert top["parent"]["id"] == result.document_id
    assert top["parent"]["source_uri"].endswith("arquitetura-k6.md")
    assert top["parent"]["file_hash"] == result.file_hash
    assert "content" in top and top["content"]
