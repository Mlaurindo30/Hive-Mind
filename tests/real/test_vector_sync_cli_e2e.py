"""Real K2 CLI E2E: maintenance command syncs live vectors to Milvus."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from core.database import serialize_f32
from core.vector_backend import MilvusBackend
from core.vector_collections import EMBED_DIM


def _seed_cli_auxiliary_sources(conn, token: str) -> tuple[str, str, str]:
    """Create one real local source for each auxiliary collection."""
    code_id = f"audit-cli-code-{token}"
    visual_id = f"audit-cli-visual-{token}"
    edge_id = f"audit-cli-edge-{token}"
    conn.execute(
        """INSERT INTO neurons(id, label, type, source_file, content, hash, workspace_id,
                                embedding_model, embedding_dim)
           VALUES (?, ?, 'code', ?, ?, ?, 'default', 'snowflake-arctic-embed2:latest', ?)""",
        (code_id, "CLI K2 code source", f"cortex/occipital/{code_id}.py",
         "real CLI K2 code vector source", f"hash-{code_id}", EMBED_DIM),
    )
    conn.execute("INSERT INTO search_vec(neuron_id, embedding) VALUES (?, ?)",
                 (code_id, serialize_f32([0.31] * EMBED_DIM)))
    conn.execute("""INSERT INTO visual_memories(id, image_path, description, ocr_text, workspace_id)
                    VALUES (?, ?, ?, ?, 'default')""",
                 (visual_id, f"audit/{visual_id}.png", "CLI K2 visual source", "OCR CLI K2"))
    conn.execute("""INSERT INTO causal_edges(id, cause_neuron_id, effect_neuron_id, label, confidence, source)
                    VALUES (?, ?, ?, 'causes', 0.9, 'cli-e2e')""",
                 (edge_id, code_id, code_id))
    conn.commit()
    return code_id, visual_id, edge_id


def _cleanup_cli_auxiliary_sources(conn, seeded_ids: tuple[str, str, str]) -> None:
    """Remove every local record created by this real test in FK-safe order."""
    code_id, visual_id, edge_id = seeded_ids
    conn.execute("DELETE FROM vector_metadata WHERE id IN (?, ?, ?)", seeded_ids)
    conn.execute("DELETE FROM vec_code WHERE symbol_id = ?", (code_id,))
    conn.execute("DELETE FROM vec_visual WHERE image_id = ?", (visual_id,))
    conn.execute("DELETE FROM vec_graph WHERE entity_id = ?", (edge_id,))
    conn.execute("DELETE FROM search_vec WHERE neuron_id = ?", (code_id,))
    conn.execute("DELETE FROM causal_edges WHERE id = ?", (edge_id,))
    conn.execute("DELETE FROM visual_memories WHERE id = ?", (visual_id,))
    conn.execute("DELETE FROM neurons WHERE id = ?", (code_id,))
    conn.commit()


@pytest.mark.real
@pytest.mark.requires_service("milvus", "claude_mem")
def test_vector_sync_cli_exports_all_live_k2_collections_to_milvus():
    """Run the operator-facing command against real DBs and temp Milvus collections."""
    import core.database as db

    claude_mem_db = Path.home() / ".claude-mem" / "claude-mem.db"
    assert Path(db.DB_PATH).exists(), f"hive_mind.db ausente em {db.DB_PATH}"
    assert claude_mem_db.exists(), f"claude-mem.db ausente em {claude_mem_db}"

    token = uuid.uuid4().hex[:12]
    conn = db.get_connection()
    db.ensure_migrations(conn)
    seeded_ids = _seed_cli_auxiliary_sources(conn, token)
    conn.close()
    prefix = f"hm_cli_e2e_{token}_"
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
        conn = db.get_connection()
        try:
            db.ensure_migrations(conn)
            _cleanup_cli_auxiliary_sources(conn, seeded_ids)
        finally:
            conn.close()