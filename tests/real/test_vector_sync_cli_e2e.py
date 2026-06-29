"""Real K2 CLI E2E: maintenance command syncs live vectors to Milvus."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from core.vector_backend import MilvusBackend


@pytest.mark.real
@pytest.mark.requires_service("milvus", "claude_mem")
def test_vector_sync_cli_exports_all_live_k2_collections_to_milvus():
    """Run the operator-facing command against real DBs and temp Milvus collections."""
    import core.database as db

    claude_mem_db = Path.home() / ".claude-mem" / "claude-mem.db"
    assert Path(db.DB_PATH).exists(), f"hive_mind.db ausente em {db.DB_PATH}"
    assert claude_mem_db.exists(), f"claude-mem.db ausente em {claude_mem_db}"

    prefix = f"hm_cli_e2e_{uuid.uuid4().hex[:12]}_"
    backend = MilvusBackend(collection_prefix=prefix)
    live_collections = [
        "memory_vectors",
        "observation_vectors",
        "document_vectors",
        "code_vectors",
        "visual_vectors",
        "graph_vectors",
        "summary_vectors",
    ]
    collections = [f"{prefix}{collection}" for collection in live_collections]

    try:
        collection_args = []
        for collection in live_collections:
            collection_args.extend(["--collection", collection])

        result = subprocess.run(
            [
                sys.executable,
                "scripts/maintenance/vector-sync.py",
                *collection_args,
                "--limit",
                "1",
                "--milvus-prefix",
                prefix,
                "--claude-mem-db",
                str(claude_mem_db),
                "--json",
            ],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr or result.stdout
        payload = json.loads(result.stdout)
        by_collection = {item["collection"]: item for item in payload["reports"]}
        backfill = {item["collection"]: item for item in payload["backfill_reports"]}

        for collection in live_collections:
            assert by_collection[collection]["scanned"] == 1
            assert by_collection[collection]["upserted"] == 1
            assert by_collection[collection]["failed"] == 0
            assert backend.count(collection) == 1
        for collection in live_collections[2:]:
            assert backfill[collection]["scanned"] == 1
            assert backfill[collection]["upserted"] == 1
            assert backfill[collection]["failed"] == 0

        again = subprocess.run(
            [
                sys.executable,
                "scripts/maintenance/vector-sync.py",
                *collection_args,
                "--limit",
                "1",
                "--milvus-prefix",
                prefix,
                "--claude-mem-db",
                str(claude_mem_db),
                "--json",
            ],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            capture_output=True,
            check=False,
        )
        assert again.returncode == 0, again.stderr or again.stdout
        second_payload = json.loads(again.stdout)
        second = {item["collection"]: item for item in second_payload["reports"]}
        for collection in live_collections:
            assert second[collection]["upserted"] == 0
            assert second[collection]["skipped"] == 1
    finally:
        for collection in collections:
            if backend._client.has_collection(collection):
                backend._client.drop_collection(collection)
