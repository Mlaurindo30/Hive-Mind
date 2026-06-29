"""Real K2 tests for auxiliary vector collections and backfill."""
from __future__ import annotations

from pathlib import Path
import uuid

import pytest

from core.database import serialize_f32
from core.vector_backend import MilvusBackend, SQLiteVecBackend
from core.vector_collections import COLLECTIONS, EMBED_DIM


def _vec(value: float) -> list[float]:
    return [value] * EMBED_DIM


def _seed_neuron_vector(conn, neuron_id: str, neuron_type: str, value: float) -> None:
    conn.execute(
        """
        INSERT INTO neurons(
            id, label, type, source_file, content, hash, workspace_id,
            embedding_model, embedding_dim
        )
        VALUES (?, ?, ?, ?, ?, ?, 'default', 'snowflake-arctic-embed2:latest', ?)
        """,
        (
            neuron_id,
            f"{neuron_type} seed",
            neuron_type,
            f"cortex/temporal/Hive-Mind/{neuron_type}/{neuron_id}.md",
            f"{neuron_type} content {neuron_id}",
            f"hash-{neuron_id}",
            EMBED_DIM,
        ),
    )
    conn.execute(
        "INSERT INTO search_vec(neuron_id, embedding) VALUES (?, ?)",
        (neuron_id, serialize_f32(_vec(value))),
    )
    conn.commit()


def _seed_auxiliary_sources(conn, tmp_path: Path) -> list[Path]:
    _seed_neuron_vector(conn, "doc-seed", "document", 0.21)
    _seed_neuron_vector(conn, "code-seed", "code", 0.31)
    conn.execute(
        """
        INSERT INTO visual_memories(id, image_path, description, ocr_text, workspace_id)
        VALUES ('visual-seed', '/tmp/screen.png', 'Tela de validacao K2', 'texto OCR K2', 'default')
        """
    )
    conn.execute(
        """
        INSERT INTO causal_edges(id, cause_neuron_id, effect_neuron_id, label, confidence, source)
        VALUES ('edge-seed', 'doc-seed', 'code-seed', 'causes', 0.9, 'test')
        """
    )
    summary = tmp_path / "cerebro" / "cerebelo" / "semanal" / "2026-W01.md"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("# Semana 01\n\nResumo real para backfill K2.\n", encoding="utf-8")
    conn.commit()
    return [summary.parent]


@pytest.mark.real
@pytest.mark.requires_service("ollama")
def test_auxiliary_collections_backfill_to_sqlite_and_query(real_db, tmp_path):
    from core.vector_sync import backfill_auxiliary_vectors_to_sqlite

    summary_roots = _seed_auxiliary_sources(real_db, tmp_path)

    reports = backfill_auxiliary_vectors_to_sqlite(real_db, summary_roots=summary_roots, limit=1)
    by_collection = {report.collection: report for report in reports}

    for collection in (
        "document_vectors",
        "code_vectors",
        "visual_vectors",
        "graph_vectors",
        "summary_vectors",
    ):
        assert COLLECTIONS[collection].status == "live"
        assert by_collection[collection].failed == 0, by_collection[collection].errors
        assert by_collection[collection].upserted == 1

    backend = SQLiteVecBackend(real_db)
    assert backend.query("document_vectors", _vec(0.21), top_k=1)[0]["id"] == "doc-seed"
    assert backend.query("code_vectors", _vec(0.31), top_k=1)[0]["id"] == "code-seed"
    assert backend.count("visual_vectors") == 1
    assert backend.count("graph_vectors") == 1
    assert backend.count("summary_vectors") == 1
    assert real_db.execute("SELECT COUNT(*) FROM vector_metadata").fetchone()[0] >= 5


@pytest.mark.real
@pytest.mark.requires_service("ollama", "milvus")
def test_auxiliary_collections_sync_to_milvus_is_real(real_db, tmp_path):
    from core.vector_sync import (
        backfill_auxiliary_vectors_to_sqlite,
        sync_auxiliary_vectors_to_milvus,
    )

    summary_roots = _seed_auxiliary_sources(real_db, tmp_path)
    backfill_auxiliary_vectors_to_sqlite(real_db, summary_roots=summary_roots, limit=1)

    prefix = f"hm_aux_{uuid.uuid4().hex[:12]}_"
    backend = MilvusBackend(collection_prefix=prefix)
    collections = [
        "document_vectors",
        "code_vectors",
        "visual_vectors",
        "graph_vectors",
        "summary_vectors",
    ]
    try:
        reports = sync_auxiliary_vectors_to_milvus(real_db, backend, limit=1)
        by_collection = {report.collection: report for report in reports}
        for collection in collections:
            assert by_collection[collection].scanned == 1
            assert by_collection[collection].upserted == 1
            assert by_collection[collection].failed == 0, by_collection[collection].errors
            assert backend.count(collection) == 1
    finally:
        for collection in collections:
            name = f"{prefix}{collection}"
            if backend._client.has_collection(name):
                backend._client.drop_collection(name)
