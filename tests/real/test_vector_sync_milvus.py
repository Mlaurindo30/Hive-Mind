"""Real K2 sync/backfill tests: hive_mind.db memory_vectors -> Milvus."""
from __future__ import annotations

import uuid

import pytest

from core.database import serialize_f32
from core.vector_backend import MilvusBackend
from core.vector_collections import EMBED_DIM


def _vec(value: float) -> list[float]:
    return [value] * EMBED_DIM


def _seed_neuron_vector(
    conn,
    neuron_id: str,
    vector: list[float],
    *,
    hash_value: str,
    workspace_id: str = "default",
    source_file: str = "cortex/temporal/Hive-Mind/k2/neuronio-sync.md",
) -> None:
    conn.execute(
        """
        INSERT INTO neurons(
            id, label, type, source_file, content, hash, workspace_id,
            embedding_model, embedding_dim
        )
        VALUES (?, ?, 'fact', ?, ?, ?, ?, 'snowflake-arctic-embed2:latest', ?)
        """,
        (
            neuron_id,
            f"Neuron {neuron_id}",
            source_file,
            f"Content {neuron_id}",
            hash_value,
            workspace_id,
            EMBED_DIM,
        ),
    )
    conn.execute(
        "INSERT INTO search_vec(neuron_id, embedding) VALUES (?, ?)",
        (neuron_id, serialize_f32(vector)),
    )
    conn.commit()


@pytest.mark.real
@pytest.mark.requires_service("milvus")
def test_sync_memory_vectors_to_milvus_is_real_and_idempotent(real_db):
    from core.vector_sync import sync_memory_vectors_to_milvus

    prefix = f"hm_sync_{uuid.uuid4().hex[:12]}_"
    backend = MilvusBackend(collection_prefix=prefix)
    collection_name = f"{prefix}memory_vectors"

    try:
        _seed_neuron_vector(real_db, "sync-default", _vec(0.31), hash_value="hash-a")
        _seed_neuron_vector(real_db, "sync-team", _vec(0.31), hash_value="hash-b", workspace_id="team-a")

        first = sync_memory_vectors_to_milvus(real_db, backend)
        assert first.scanned == 2
        assert first.upserted == 2
        assert first.skipped == 0
        assert first.failed == 0

        hits = backend.query("memory_vectors", _vec(0.31), top_k=10, filters={"workspace_id": "team-a"})
        assert [hit["id"] for hit in hits] == ["sync-team"]
        assert hits[0]["metadata"]["hash"] == "hash-b"
        assert hits[0]["metadata"]["project"] == "Hive-Mind"

        second = sync_memory_vectors_to_milvus(real_db, backend)
        assert second.scanned == 2
        assert second.upserted == 0
        assert second.skipped == 2
        assert second.failed == 0

        real_db.execute("UPDATE neurons SET hash = 'hash-b2', content = 'changed' WHERE id = 'sync-team'")
        real_db.commit()
        third = sync_memory_vectors_to_milvus(real_db, backend)
        assert third.scanned == 2
        assert third.upserted == 1
        assert third.skipped == 1
        assert third.failed == 0

        hits = backend.query("memory_vectors", _vec(0.31), top_k=10, filters={"workspace_id": "team-a"})
        assert hits[0]["metadata"]["hash"] == "hash-b2"
    finally:
        if backend._client.has_collection(collection_name):
            backend._client.drop_collection(collection_name)


@pytest.mark.real
@pytest.mark.requires_service("milvus")
def test_sync_memory_vectors_reports_milvus_row_failure_without_hiding_it(real_db):
    from core.vector_sync import sync_memory_vectors_to_milvus

    prefix = f"hm_sync_{uuid.uuid4().hex[:12]}_"
    backend = MilvusBackend(collection_prefix=prefix)
    collection_name = f"{prefix}memory_vectors"

    try:
        too_long_source = "cortex/temporal/Hive-Mind/" + ("x" * 1300) + ".md"
        _seed_neuron_vector(
            real_db,
            "bad-metadata",
            _vec(0.41),
            hash_value="bad-hash",
            source_file=too_long_source,
        )

        report = sync_memory_vectors_to_milvus(real_db, backend)
        assert report.scanned == 1
        assert report.upserted == 0
        assert report.failed == 1
        assert "bad-metadata" in report.errors[0]
    finally:
        if backend._client.has_collection(collection_name):
            backend._client.drop_collection(collection_name)
