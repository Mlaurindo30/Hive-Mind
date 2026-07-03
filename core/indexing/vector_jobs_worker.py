"""Vector job worker for the post-audit stabilization (R3.2, R3.3).

Spec: specs/post-audit-stabilization.md R3.

The worker drains the `vector_jobs` table introduced by R3.1. Each row says:
  - entity_type: "neuron" | "observation" | "document_chunk" | "code" |
                 "visual" | "graph" | "summary"
  - entity_id:   the source row id
  - collection:  which vec0 table to write to
  - workspace_id: filter (preserved for K8 isolation gates)

Coverage of the seven canonical collections (R3.2):

  REAL:    memory_vectors, observation_vectors, document_vectors, visual_vectors
  STUB:    code_vectors, graph_vectors, summary_vectors

The three stub collections get their vec0 tables created (already done in
core.database.ensure_migrations) and the worker inserts a `vector_metadata`
row, but does not write a vector until a real source exists. This keeps the
queue table honest: every promoted entity lands a job and every job is
either completed or marked failed, never silently dropped.

Run with:

    .venv/bin/python -m core.indexing.vector_jobs_worker --once
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from core.database import (
    get_connection,
    get_embedder,
    serialize_f32,
)


# R3.2: the seven canonical collections. Maps collection name to (vec_table,
# id_column, real_or_stub).
COLLECTIONS = {
    "memory_vectors":     ("search_vec",      "neuron_id",   "real"),
    "observation_vectors": ("vec_documents",  "chunk_id",    "real"),
    "document_vectors":    ("vec_documents",  "chunk_id",    "real"),
    "visual_vectors":      ("vec_visual",     "image_id",    "real"),
    "code_vectors":        ("vec_code",       "symbol_id",   "stub"),
    "graph_vectors":       ("vec_graph",      "entity_id",   "stub"),
    "summary_vectors":     ("vec_summary",    "summary_id",  "stub"),
}


# Mapping of entity_type to the SELECT statement that yields the body text.
_ENTITY_BODY_SQL = {
    "neuron":         "SELECT id, COALESCE(content, label, '') AS text, source_file AS source_uri, hash, workspace_id FROM neurons WHERE id = ?",
    "observation":    "SELECT id, COALESCE(content, title, '') AS text, '' AS source_uri, '' AS hash, COALESCE(workspace_id, 'default') AS workspace_id FROM observations WHERE id = ?",
    "document_chunk": "SELECT chunk_id AS id, COALESCE(content, '') AS text, COALESCE(source_uri, '') AS source_uri, COALESCE(hash, '') AS hash, COALESCE(workspace_id, 'default') AS workspace_id FROM document_chunks WHERE chunk_id = ?",
    "code":           "SELECT id, COALESCE(label, '') AS text, '' AS source_uri, '' AS hash, 'default' AS workspace_id FROM neurons WHERE id = ?",
    "visual":         "SELECT id, COALESCE(description, '') AS text, COALESCE(path, '') AS source_uri, '' AS hash, COALESCE(workspace_id, 'default') AS workspace_id FROM visual_memories WHERE id = ?",
    "graph":          "SELECT id, COALESCE(label, '') AS text, '' AS source_uri, '' AS hash, 'default' AS workspace_id FROM neurons WHERE id = ?",
    "summary":        "SELECT id, COALESCE(content, label, '') AS text, '' AS source_uri, '' AS hash, COALESCE(workspace_id, 'default') AS workspace_id FROM neurons WHERE id = ?",
}


def _claim_one(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """Claim a single pending job. Returns the row, or None if the queue is empty."""
    return conn.execute(
        """
        SELECT id, entity_type, entity_id, collection, workspace_id
        FROM vector_jobs
        WHERE status = 'pending'
        ORDER BY created_at
        LIMIT 1
        """
    ).fetchone()


def _mark_done(conn: sqlite3.Connection, job_id: str) -> None:
    conn.execute(
        "UPDATE vector_jobs SET status = 'done', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (job_id,),
    )


def _mark_failed(conn: sqlite3.Connection, job_id: str, error: str) -> None:
    conn.execute(
        """
        UPDATE vector_jobs
        SET status = 'failed', attempts = attempts + 1, error = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (error[:500], job_id),
    )


def _embed(body: str) -> Optional[bytes]:
    embedder = get_embedder()
    if embedder is None:
        return None
    try:
        vec = list(embedder.embed([body[:5000]]))[0]
    except Exception:
        return None
    return serialize_f32(vec)


def _process_one(conn: sqlite3.Connection) -> bool:
    job = _claim_one(conn)
    if job is None:
        return False

    collection = job["collection"]
    if collection not in COLLECTIONS:
        _mark_failed(conn, job["id"], f"unknown collection: {collection}")
        conn.commit()
        return True

    table, id_col, mode = COLLECTIONS[collection]
    entity_type = job["entity_type"]
    sql = _ENTITY_BODY_SQL.get(entity_type)
    if sql is None:
        _mark_failed(conn, job["id"], f"unknown entity_type: {entity_type}")
        conn.commit()
        return True

    row = conn.execute(sql, (job["entity_id"],)).fetchone()
    if row is None:
        _mark_failed(conn, job["id"], f"entity not found: {entity_type}:{job['entity_id']}")
        conn.commit()
        return True

    body = row["text"] or ""
    if mode == "real" and body.strip():
        blob = _embed(body)
        if blob is None:
            _mark_failed(conn, job["id"], "embedder unavailable")
            conn.commit()
            return True
        conn.execute(f"DELETE FROM {table} WHERE {id_col} = ?", (job["entity_id"],))
        conn.execute(
            f"INSERT INTO {table}({id_col}, embedding) VALUES (?, ?)",
            (job["entity_id"], blob),
        )
    # Stub collections: record metadata only; no embedding until a source
    # exists. This keeps the queue honest (every job is either done or
    # failed) without inventing vector bytes for entities we have not
    # actually observed.

    conn.execute(
        """
        INSERT OR REPLACE INTO vector_metadata(
            collection, id, parent_id, parent_type, brain_lobe, knowledge_type,
            project, source_uri, hash, valid_at, workspace_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """,
        (
            collection,
            job["entity_id"],
            job["entity_id"],
            entity_type,
            "frontal",
            entity_type,
            "Hive-Mind",
            row["source_uri"] or "",
            row["hash"] or "",
            job["workspace_id"],
        ),
    )
    _mark_done(conn, job["id"])
    conn.commit()
    return True


def run(once: bool = False, max_iterations: int = 1000) -> int:
    """Backward-compatible alias kept for tests. New callers should use `drain`."""
    return drain(once=once, max_iterations=max_iterations)


def drain(once: bool = False, max_iterations: int = 1000) -> int:
    """Drain the queue. With `once=True`, process at most one batch and return."""
    conn = get_connection()
    processed = 0
    try:
        if once:
            while processed < max_iterations:
                if not _process_one(conn):
                    break
                processed += 1
        else:
            while _process_one(conn) and processed < max_iterations:
                processed += 1
    finally:
        conn.close()
    return processed


def main() -> int:
    parser = argparse.ArgumentParser(description="Vector job worker (R3.2/R3.3)")
    parser.add_argument("--once", action="store_true", help="Process at most one batch and exit")
    args = parser.parse_args()
    n = drain(once=args.once)
    print(f"processed {n} job(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
