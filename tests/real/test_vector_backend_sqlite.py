"""Real K2 tests for the local sqlite-vec VectorBackend."""
from __future__ import annotations

import pytest

from core.database import serialize_f32
from core.vector_backend import SQLiteVecBackend
from core.vector_collections import EMBED_DIM


def _vec(value: float) -> list[float]:
    return [value] * EMBED_DIM


def _seed_memory_vector(conn, neuron_id: str, vector: list[float], *, workspace_id: str = "default") -> None:
    conn.execute(
        """
        INSERT INTO neurons(id, label, type, content, workspace_id, embedding_model, embedding_dim)
        VALUES (?, ?, 'fact', ?, ?, 'snowflake-arctic-embed2:latest', ?)
        """,
        (neuron_id, f"Label {neuron_id}", f"Content {neuron_id}", workspace_id, EMBED_DIM),
    )
    conn.execute(
        "INSERT INTO search_vec(neuron_id, embedding) VALUES (?, ?)",
        (neuron_id, serialize_f32(vector)),
    )
    conn.commit()


@pytest.mark.real
def test_sqlite_vector_backend_queries_memory_vectors(real_db):
    backend = SQLiteVecBackend(conn=real_db)
    _seed_memory_vector(real_db, "n-default", _vec(0.10))
    _seed_memory_vector(real_db, "n-other", _vec(0.90))

    hits = backend.query("memory_vectors", _vec(0.10), top_k=1)

    assert hits[0]["id"] == "n-default"
    assert hits[0]["distance"] >= 0


@pytest.mark.real
def test_sqlite_vector_backend_filters_by_workspace_id(real_db):
    backend = SQLiteVecBackend(conn=real_db)
    _seed_memory_vector(real_db, "n-default", _vec(0.20), workspace_id="default")
    _seed_memory_vector(real_db, "n-team", _vec(0.20), workspace_id="team-a")

    hits = backend.query("memory_vectors", _vec(0.20), top_k=5, filters={"workspace_id": "team-a"})

    assert [h["id"] for h in hits] == ["n-team"]


@pytest.mark.real
def test_sqlite_vector_backend_rejects_wrong_dimension(real_db):
    backend = SQLiteVecBackend(conn=real_db)

    with pytest.raises(ValueError, match="esperado 1024d"):
        backend.query("memory_vectors", [0.1, 0.2], top_k=1)


@pytest.mark.real
def test_sqlite_vector_backend_serves_auxiliary_collections(real_db):
    backend = SQLiteVecBackend(conn=real_db)

    for collection in (
        "document_vectors",
        "code_vectors",
        "visual_vectors",
        "graph_vectors",
        "summary_vectors",
    ):
        assert backend.count(collection) == 0
