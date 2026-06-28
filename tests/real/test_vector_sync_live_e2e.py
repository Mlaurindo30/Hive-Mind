"""Live K2 E2E: real project/claude-mem DBs -> real Milvus, bounded batch."""
from __future__ import annotations

from pathlib import Path
import uuid

import pytest

from core.vector_backend import MilvusBackend


@pytest.mark.real
@pytest.mark.requires_service("milvus", "claude_mem")
def test_live_memory_and_observation_vectors_sync_to_milvus_with_bounded_real_batch():
    """Use real local databases read-only and write only to a temporary Milvus prefix."""
    import core.database as db
    from core.vector_sync import (
        sync_memory_vectors_to_milvus,
        sync_observation_vectors_to_milvus,
    )

    claude_mem_db = Path.home() / ".claude-mem" / "claude-mem.db"
    assert Path(db.DB_PATH).exists(), f"hive_mind.db ausente em {db.DB_PATH}"
    assert claude_mem_db.exists(), f"claude-mem.db ausente em {claude_mem_db}"

    prefix = f"hm_live_e2e_{uuid.uuid4().hex[:12]}_"
    backend = MilvusBackend(collection_prefix=prefix)
    memory_collection = f"{prefix}memory_vectors"
    observation_collection = f"{prefix}observation_vectors"

    conn = db.get_connection()
    try:
        memory_report = sync_memory_vectors_to_milvus(conn, backend, limit=3)
        observation_report = sync_observation_vectors_to_milvus(claude_mem_db, backend, limit=3)

        assert memory_report.failed == 0, memory_report.errors
        assert observation_report.failed == 0, observation_report.errors
        assert memory_report.scanned == 3
        assert observation_report.scanned == 3
        assert memory_report.upserted == 3
        assert observation_report.upserted == 3

        assert backend.count("memory_vectors") == 3
        assert backend.count("observation_vectors") == 3

        memory_again = sync_memory_vectors_to_milvus(conn, backend, limit=3)
        observation_again = sync_observation_vectors_to_milvus(claude_mem_db, backend, limit=3)
        assert memory_again.upserted == 0
        assert memory_again.skipped == 3
        assert observation_again.upserted == 0
        assert observation_again.skipped == 3
    finally:
        conn.close()
        for collection in (memory_collection, observation_collection):
            if backend._client.has_collection(collection):
                backend._client.drop_collection(collection)
