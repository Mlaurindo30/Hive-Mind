"""Real K8 tests for knowledge coverage health.

Uses a real sqlite-vec database and the real K8 pruning/tombstone path. No
mocked vector backend is used for the core acceptance checks.
"""
from __future__ import annotations

import pytest

from pathlib import Path
import json


def _zero_vector_blob():
    from core.database import serialize_f32

    return serialize_f32([0.0] * 1024)


@pytest.mark.real
def test_knowledge_health_prunes_orphan_vectors_and_writes_tombstones(real_db, tmp_path):
    from scripts.health.knowledge_health import (
        compute_knowledge_health,
        evaluate_fail_closed,
        write_report,
    )

    real_db.execute(
        """
        INSERT INTO neurons(id, label, type, source_file, content, hash, workspace_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "neuron-k8",
            "K8 decision",
            "decision",
            "cerebro/cortex/frontal/decisoes/k8.md",
            "K8 mede cobertura e poda vetores orfaos.",
            "hash-k8",
            "default",
        ),
    )
    real_db.execute(
        "INSERT INTO search_vec(neuron_id, embedding) VALUES (?, ?)",
        ("neuron-k8", _zero_vector_blob()),
    )
    real_db.execute(
        """
        INSERT INTO document_memories(id, file_path, file_hash, workspace_id)
        VALUES (?, ?, ?, ?)
        """,
        ("doc-k8", str(tmp_path / "k8.md"), "doc-hash-k8", "default"),
    )
    real_db.execute(
        """
        INSERT INTO document_chunks(
            id, document_id, parent_id, source_uri, chunk_index,
            content, offset_start, offset_end, hash, workspace_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("chunk-k8", "doc-k8", "doc-k8", str(tmp_path / "k8.md"), 0, "K8 chunk", 0, 8, "chunk-hash-k8", "default"),
    )
    real_db.execute(
        "INSERT INTO vec_documents(chunk_id, embedding) VALUES (?, ?)",
        ("chunk-k8", _zero_vector_blob()),
    )
    real_db.execute(
        "INSERT INTO vec_documents(chunk_id, embedding) VALUES (?, ?)",
        ("orphan-chunk-k8", _zero_vector_blob()),
    )
    real_db.execute(
        """
        INSERT INTO vector_metadata(
            collection, id, parent_id, parent_type, brain_lobe,
            knowledge_type, project, source_uri, hash, valid_at, workspace_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "document_vectors",
            "chunk-k8",
            "doc-k8",
            "document",
            "parietal",
            "document_chunk",
            "Hive-Mind",
            str(tmp_path / "k8.md"),
            "chunk-hash-k8",
            "2026-06-30T00:00:00Z",
            "default",
        ),
    )
    real_db.execute(
        """
        INSERT INTO query_route_log(query_hash, intent, first_route, retrieval_path_json, confidence, workspace_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("hash-query-k8", "document", "document", json.dumps([{"route": "document"}]), 0.9, "default"),
    )
    real_db.commit()

    metrics = compute_knowledge_health(real_db, prune_orphans=True)
    failures = evaluate_fail_closed(metrics)

    assert failures == []
    assert metrics["orphan_vectors_before_prune"] == 1
    assert metrics["orphan_vectors_pruned"] == 1
    assert metrics["orphan_vectors"] == 0
    assert metrics["collections"]["document_vectors"]["vectorized_pct"] == 100.0
    assert metrics["document_vectors_vectorized_pct"] == 100.0
    assert metrics["query_route_distribution"]["document"] == 1
    assert real_db.execute(
        "SELECT COUNT(*) FROM knowledge_tombstones WHERE reason='orphan_vector'"
    ).fetchone()[0] == 1
    assert real_db.execute(
        "SELECT COUNT(*) FROM vec_documents WHERE chunk_id='orphan-chunk-k8'"
    ).fetchone()[0] == 0

    report = write_report(metrics, failures, root=tmp_path)
    assert report.exists()
    assert "Knowledge Health" in report.read_text(encoding="utf-8")


@pytest.mark.real
def test_knowledge_health_accepts_document_vectors_backfilled_from_neurons(real_db):
    from scripts.health.knowledge_health import compute_knowledge_health, evaluate_fail_closed

    real_db.execute(
        """
        INSERT INTO neurons(id, label, type, source_file, content, hash, workspace_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "doc-neuron-k8",
            "Documento legado",
            "document",
            "cerebro/cortex/parietal/inbox/doc.md",
            "Documento legado do vault indexado antes do pipeline K6.",
            "hash-doc-neuron-k8",
            "default",
        ),
    )
    real_db.execute(
        "INSERT INTO vec_documents(chunk_id, embedding) VALUES (?, ?)",
        ("doc-neuron-k8", _zero_vector_blob()),
    )
    real_db.execute(
        """
        INSERT INTO vector_metadata(
            collection, id, parent_id, parent_type, brain_lobe,
            knowledge_type, project, source_uri, hash, valid_at, workspace_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "document_vectors",
            "doc-neuron-k8",
            "doc-neuron-k8",
            "neuron",
            "parietal",
            "document",
            "default",
            "cerebro/cortex/parietal/inbox/doc.md",
            "hash-doc-neuron-k8",
            "2026-07-01T00:00:00Z",
            "default",
        ),
    )
    real_db.commit()

    metrics = compute_knowledge_health(real_db)

    assert evaluate_fail_closed(metrics) == []
    assert metrics["orphan_vectors"] == 0
    assert metrics["collections"]["document_vectors"]["source_total"] == 1
    assert metrics["collections"]["document_vectors"]["vectorized_pct"] == 100.0


@pytest.mark.real
def test_knowledge_health_prunes_document_vector_for_non_document_neuron(real_db):
    from scripts.health.knowledge_health import compute_knowledge_health, evaluate_fail_closed

    real_db.execute(
        """
        INSERT INTO neurons(id, label, type, source_file, content, hash, workspace_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "summary-neuron-k8",
            "Resumo anual",
            "summary",
            "cerebro/cerebelo/anual/2026.md",
            "Resumo anual nao deve morar em document_vectors.",
            "hash-summary-neuron-k8",
            "default",
        ),
    )
    real_db.execute(
        "INSERT INTO vec_documents(chunk_id, embedding) VALUES (?, ?)",
        ("summary-neuron-k8", _zero_vector_blob()),
    )
    real_db.execute(
        """
        INSERT INTO vector_metadata(
            collection, id, parent_id, parent_type, brain_lobe,
            knowledge_type, project, source_uri, hash, valid_at, workspace_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "document_vectors",
            "summary-neuron-k8",
            "summary-neuron-k8",
            "neuron",
            "cerebelo",
            "summary",
            "default",
            "cerebro/cerebelo/anual/2026.md",
            "hash-summary-neuron-k8",
            "2026-07-01T00:00:00Z",
            "default",
        ),
    )
    real_db.commit()

    metrics = compute_knowledge_health(real_db, prune_orphans=True)

    assert evaluate_fail_closed(metrics) == []
    assert metrics["orphan_vectors_before_prune"] == 1
    assert metrics["orphan_vectors_pruned"] == 1
    assert metrics["orphan_vectors"] == 0
    assert real_db.execute(
        "SELECT COUNT(*) FROM vec_documents WHERE chunk_id='summary-neuron-k8'"
    ).fetchone()[0] == 0


@pytest.mark.real
def test_knowledge_health_counts_only_vectorizable_claude_mem_observations(tmp_path, monkeypatch):
    import sqlite3
    import time

    from core.database import serialize_f32
    from scripts.health.knowledge_health import (
        _claude_mem_observation_total,
        _claude_mem_observation_vector_total,
    )

    db = tmp_path / "claude-mem.db"
    now = int(time.time())
    conn = sqlite3.connect(db)
    conn.enable_load_extension(True)
    try:
        import sqlite_vec

        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)
    conn.execute(
        """
        CREATE TABLE observations(
            id INTEGER PRIMARY KEY,
            narrative TEXT,
            text TEXT,
            facts TEXT,
            created_at_epoch INTEGER
        )
        """
    )
    conn.execute("CREATE VIRTUAL TABLE vec_observations USING vec0(embedding float[1024])")
    conn.executemany(
        "INSERT INTO observations(id, narrative, text, facts, created_at_epoch) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "narrativa", None, None, now - 120),
            (2, None, "texto", None, now - 120),
            (3, None, None, "[\"facts only\"]", now - 120),
            (4, "", "   ", None, now - 120),
            (5, "recente em processamento", None, None, now),
        ],
    )
    for rowid in (1, 2, 5):
        conn.execute(
            "INSERT INTO vec_observations(rowid, embedding) VALUES (?, ?)",
            (rowid, serialize_f32([0.0] * 1024)),
        )
    conn.commit()
    conn.close()
    monkeypatch.setenv("CLAUDE_MEM_DB", str(db))
    monkeypatch.setenv("HIVE_OBSERVATION_VECTOR_GRACE_SECONDS", "60")

    assert _claude_mem_observation_total() == 2
    assert _claude_mem_observation_vector_total() == 2


@pytest.mark.real
def test_knowledge_health_cli_fail_closed_acceptance():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/health/knowledge_health.py", "--fail-closed", "--json", "--no-report"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["failures"] == []
    assert "neurons_vectorized_pct" in payload["metrics"]
    assert "summary_vectors_total" in payload["metrics"]
    assert "collections" in payload["metrics"]
