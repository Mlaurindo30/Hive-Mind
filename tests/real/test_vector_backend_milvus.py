"""Real K2 tests for MilvusBackend.

Requires a real Milvus service. Start it with:
`docker compose -f integrations/milvus/docker-compose.yml up -d`.
"""
from __future__ import annotations

import os
import uuid

import pytest

from core.vector_backend import MilvusBackend
from core.vector_collections import EMBED_DIM


def _vec(value: float) -> list[float]:
    return [value] * EMBED_DIM


def _metadata(workspace_id: str = "default") -> dict[str, str]:
    return {
        "parent_id": "neuron-1",
        "parent_type": "neuron",
        "brain_lobe": "temporal",
        "knowledge_type": "fact",
        "project": "Hive-Mind",
        "source_uri": "tests/real/test_vector_backend_milvus.py",
        "hash": uuid.uuid4().hex,
        "valid_at": "2026-06-28T00:00:00Z",
        "workspace_id": workspace_id,
    }


@pytest.mark.real
@pytest.mark.requires_service("milvus")
def test_milvus_backend_e2e_upsert_query_filter_delete():
    prefix = f"hm_test_{uuid.uuid4().hex[:12]}_"
    backend = MilvusBackend(uri=os.environ.get("MILVUS_URI", "http://localhost:19530"), collection_prefix=prefix)
    collection_name = f"{prefix}memory_vectors"

    try:
        backend.upsert("memory_vectors", "mv-default", _vec(0.11), _metadata("default"))
        backend.upsert("memory_vectors", "mv-team", _vec(0.11), _metadata("team-a"))

        hits = backend.query("memory_vectors", _vec(0.11), top_k=10, filters={"workspace_id": "team-a"})

        assert [h["id"] for h in hits] == ["mv-team"]
        assert hits[0]["metadata"]["workspace_id"] == "team-a"
        assert backend.count("memory_vectors", filters={"workspace_id": "team-a"}) == 1

        backend.delete("memory_vectors", "mv-team")
        assert backend.count("memory_vectors", filters={"workspace_id": "team-a"}) == 0
    finally:
        backend._client.drop_collection(collection_name)


@pytest.mark.real
@pytest.mark.requires_service("milvus")
def test_milvus_backend_rejects_missing_canonical_metadata():
    prefix = f"hm_test_{uuid.uuid4().hex[:12]}_"
    backend = MilvusBackend(uri=os.environ.get("MILVUS_URI", "http://localhost:19530"), collection_prefix=prefix)
    try:
        with pytest.raises(ValueError, match="metadata obrigatorio ausente"):
            backend.upsert("memory_vectors", "mv-bad", _vec(0.12), {"workspace_id": "default"})
    finally:
        collection_name = f"{prefix}memory_vectors"
        if backend._client.has_collection(collection_name):
            backend._client.drop_collection(collection_name)
