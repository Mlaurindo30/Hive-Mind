"""Real K2 tests for claude-mem observation_vectors routing and Milvus sync."""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.vector_backend import MilvusBackend, SQLiteVecBackend
from core.vector_collections import EMBED_DIM


def _vec(value: float) -> list[float]:
    return [value] * EMBED_DIM


def _open_claude_mem_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    import sqlite_vec

    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute(
        """
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT NOT NULL,
            project TEXT NOT NULL,
            text TEXT,
            type TEXT NOT NULL,
            title TEXT,
            subtitle TEXT,
            facts TEXT,
            narrative TEXT,
            concepts TEXT,
            files_read TEXT,
            files_modified TEXT,
            prompt_number INTEGER,
            discovery_tokens INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            created_at_epoch INTEGER NOT NULL,
            content_hash TEXT,
            generated_by_model TEXT,
            relevance_count INTEGER DEFAULT 0,
            merged_into_project TEXT,
            agent_type TEXT,
            agent_id TEXT,
            metadata TEXT
        )
        """
    )
    conn.execute(
        f"""
        CREATE VIRTUAL TABLE vec_observations
        USING vec0(embedding float[{EMBED_DIM}] distance_metric=cosine)
        """
    )
    conn.commit()
    return conn


def _seed_observation(
    conn: sqlite3.Connection,
    obs_id: int,
    vector: list[float],
    *,
    project: str = "Hive-Mind",
    obs_type: str = "discovery",
    hash_value: str = "obs-hash",
    created_at: str = "2026-06-28T10:00:00Z",
    title: str = "Observation vector routing",
) -> None:
    conn.execute(
        """
        INSERT INTO observations(
            id, memory_session_id, project, text, type, title, facts, narrative,
            created_at, created_at_epoch, content_hash, metadata
        )
        VALUES (?, 'session-real', ?, ?, ?, ?, ?, ?, ?, 1782637200, ?, ?)
        """,
        (
            obs_id,
            project,
            f"text {obs_id}",
            obs_type,
            title,
            json.dumps([f"fact {obs_id}"]),
            f"narrative {obs_id}",
            created_at,
            hash_value,
            json.dumps({"workspace_id": "default"}),
        ),
    )
    conn.execute(
        "INSERT INTO vec_observations(rowid, embedding) VALUES (?, ?)",
        (obs_id, json.dumps(vector)),
    )
    conn.commit()


@pytest.mark.real
def test_sqlite_backend_queries_claude_mem_observation_vectors(tmp_path, real_db):
    claude_mem_db = tmp_path / "claude-mem.db"
    cm = _open_claude_mem_db(claude_mem_db)
    try:
        _seed_observation(cm, 101, _vec(0.21), project="Hive-Mind", obs_type="discovery")
        _seed_observation(cm, 102, _vec(0.95), project="Other", obs_type="event")

        backend = SQLiteVecBackend(conn=real_db, claude_mem_db=claude_mem_db)

        assert backend.count("observation_vectors") == 2
        assert backend.count("observation_vectors", filters={"project": "Hive-Mind"}) == 1

        hits = backend.query(
            "observation_vectors",
            _vec(0.21),
            top_k=5,
            filters={"project": "Hive-Mind", "knowledge_type": "discovery"},
        )

        assert [hit["id"] for hit in hits] == [101]
        assert hits[0]["metadata"]["project"] == "Hive-Mind"
        assert hits[0]["metadata"]["knowledge_type"] == "discovery"

        with pytest.raises(NotImplementedError, match="worker"):
            backend.upsert("observation_vectors", "103", _vec(0.21), {})
    finally:
        cm.close()


@pytest.mark.real
@pytest.mark.requires_service("milvus")
def test_sync_observation_vectors_to_milvus_is_real_and_idempotent(tmp_path):
    from core.vector_sync import sync_observation_vectors_to_milvus

    claude_mem_db = tmp_path / "claude-mem.db"
    cm = _open_claude_mem_db(claude_mem_db)
    prefix = f"hm_obs_sync_{uuid.uuid4().hex[:12]}_"
    backend = MilvusBackend(collection_prefix=prefix)
    collection_name = f"{prefix}observation_vectors"

    try:
        _seed_observation(cm, 201, _vec(0.33), project="Hive-Mind", hash_value="obs-a")
        _seed_observation(cm, 202, _vec(0.77), project="Other", hash_value="obs-b")

        first = sync_observation_vectors_to_milvus(claude_mem_db, backend)
        assert first.collection == "observation_vectors"
        assert first.scanned == 2
        assert first.upserted == 2
        assert first.skipped == 0
        assert first.failed == 0

        hits = backend.query(
            "observation_vectors",
            _vec(0.33),
            top_k=10,
            filters={"project": "Hive-Mind", "knowledge_type": "discovery"},
        )
        assert [hit["id"] for hit in hits] == ["obs-201"]
        assert hits[0]["metadata"]["parent_type"] == "claude_mem_observation"
        assert hits[0]["metadata"]["source_uri"] == "claude-mem:observations/201"

        second = sync_observation_vectors_to_milvus(claude_mem_db, backend)
        assert second.scanned == 2
        assert second.upserted == 0
        assert second.skipped == 2
        assert second.failed == 0

        cm.execute("UPDATE observations SET content_hash = 'obs-a2' WHERE id = 201")
        cm.commit()
        third = sync_observation_vectors_to_milvus(claude_mem_db, backend)
        assert third.scanned == 2
        assert third.upserted == 1
        assert third.skipped == 1
        assert third.failed == 0
    finally:
        cm.close()
        if backend._client.has_collection(collection_name):
            backend._client.drop_collection(collection_name)
