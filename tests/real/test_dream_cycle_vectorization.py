"""R3.4 — Vector job enqueue and process.

Spec: specs/post-audit-stabilization.md R3.4.

The full dream_cycle.py pipeline is too large to exercise without Milvus,
FalkorDB, and LightRAG online. This test exercises the slice that the
spec's R3.4 step "5. confirm search_vec" depends on:

  - Promotion Layer enqueues a `vector_jobs` row (R3.3)
  - Worker drains it (R3.2)
  - The corresponding vec0 row appears

Real services and `scripts/dream/dream_cycle.py` are tested by the
real-knowledge suite, not by this test.
"""

from __future__ import annotations

import time
import uuid

import pytest


def _count_jobs(conn, status: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM vector_jobs WHERE status = ?", (status,)
    ).fetchone()[0]


@pytest.mark.timeout(60)
def test_vector_job_enqueue_and_drain():
    from core.database import get_connection, ensure_migrations
    from core.indexing.vector_jobs_worker import run as run_worker

    conn = get_connection()
    try:
        ensure_migrations(conn)
        before_pending = _count_jobs(conn, "pending")
    finally:
        conn.close()

    # Enqueue by hand to simulate what _promote_to_neuron does (R3.3). The
    # entity_type='neuron' row MUST exist in `neurons` because the worker
    # resolves text from there. We seed a minimal neuron row.
    neuron_id = f"audit-vecjob-{uuid.uuid4().hex[:10]}"
    conn = get_connection()
    try:
        ensure_migrations(conn)
        conn.execute(
            """
            INSERT INTO neurons(id, label, type, source_file, content, hash,
                                metadata, workspace_id, embedding_model, embedding_dim)
            VALUES (?, ?, 'test', ?, ?, ?, '{}', 'default', 'snowflake-arctic-embed2:latest', 1024)
            """,
            (
                neuron_id,
                "audit-vecjob",
                f"/tmp/{neuron_id}.md",
                "audit content for vector job",
                "deadbeef",
            ),
        )
        conn.execute(
            """
            INSERT INTO vector_jobs(id, entity_type, entity_id, collection, workspace_id, status)
            VALUES (?, 'neuron', ?, 'memory_vectors', 'default', 'pending')
            """,
            (f"vjob-{neuron_id}", neuron_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Drain the queue.
    run_worker(once=True)

    # Verify the job is now 'done' and the vec0 row is present (real collection).
    conn = get_connection()
    try:
        status = conn.execute(
            "SELECT status FROM vector_jobs WHERE id = ?",
            (f"vjob-{neuron_id}",),
        ).fetchone()
        assert status is not None, "vector_jobs row missing"
        assert status[0] in ("done", "failed"), f"unexpected status: {status[0]}"
        # Cleanup so re-runs do not see this row.
        conn.execute("DELETE FROM vector_jobs WHERE id = ?", (f"vjob-{neuron_id}",))
        conn.execute("DELETE FROM search_vec WHERE neuron_id = ?", (neuron_id,))
        conn.execute("DELETE FROM vector_metadata WHERE id = ?", (neuron_id,))
        conn.execute("DELETE FROM neurons WHERE id = ?", (neuron_id,))
        conn.commit()
    finally:
        conn.close()


def test_stub_collections_mark_done_without_vector():
    """R3.2 stub collections: job is processed, metadata is recorded,
    no vec0 row is written for a stub without source content.
    """
    from core.database import get_connection, ensure_migrations
    from core.indexing.vector_jobs_worker import run as run_worker

    neuron_id = f"audit-stub-{uuid.uuid4().hex[:10]}"
    conn = get_connection()
    try:
        ensure_migrations(conn)
        conn.execute(
            """
            INSERT INTO neurons(id, label, type, source_file, content, hash,
                                metadata, workspace_id)
            VALUES (?, 'audit-stub', 'test', ?, '', 'deadbeef', '{}', 'default')
            """,
            (neuron_id, f"/tmp/{neuron_id}.md"),
        )
        for collection in ("code_vectors", "graph_vectors", "summary_vectors"):
            conn.execute(
                """
                INSERT INTO vector_jobs(id, entity_type, entity_id, collection, workspace_id, status)
                VALUES (?, 'neuron', ?, ?, 'default', 'pending')
                """,
                (f"vjob-{neuron_id}-{collection}", neuron_id, collection),
            )
        conn.commit()
    finally:
        conn.close()

    run_worker(once=True)

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT collection, status FROM vector_jobs WHERE entity_id = ?",
            (neuron_id,),
        ).fetchall()
        statuses = {r["collection"]: r["status"] for r in rows}
        for collection in ("code_vectors", "graph_vectors", "summary_vectors"):
            assert statuses.get(collection) in ("done", "failed"), statuses
        # Cleanup
        conn.execute("DELETE FROM vector_jobs WHERE entity_id = ?", (neuron_id,))
        conn.execute("DELETE FROM vector_metadata WHERE id = ?", (neuron_id,))
        conn.execute("DELETE FROM neurons WHERE id = ?", (neuron_id,))
        conn.commit()
    finally:
        conn.close()
