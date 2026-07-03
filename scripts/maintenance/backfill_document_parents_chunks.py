"""R4.3 — DocumentPipeline backfill.

Spec: specs/post-audit-stabilization.md R4.3.

Reconstructs `document_memories` and `document_chunks` rows for orphan
`vec_documents` rows that still carry `source_uri` and a recoverable hash.
The script is idempotent: existing rows are NOT overwritten.

  dry-run   -> print a before/after plan, do not write
  apply     -> require --backup to be present, then write

Usage:

  .venv/bin/python scripts/maintenance/backfill_document_parents_chunks.py --dry-run
  .venv/bin/python scripts/maintenance/backfill_document_parents_chunks.py --apply --backup backups/audit-2026-07-03/hive_mind.db
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database import get_connection, ensure_migrations


def _list_orphans(conn) -> List[dict]:
    return [dict(row) for row in conn.execute(
        """
        SELECT v.chunk_id, m.source_uri, m.workspace_id, m.hash
        FROM vec_documents v
        JOIN vector_metadata m
          ON m.collection = 'document_vectors' AND m.id = v.chunk_id
        WHERE NOT EXISTS (SELECT 1 FROM document_chunks c WHERE c.id = v.chunk_id)
          AND m.source_uri IS NOT NULL AND m.source_uri != ''
        """
    ).fetchall()]


def _resolve_parent_id(conn, source_uri: str, workspace_id: str, hash_value: str) -> str:
    """Return an existing or freshly-inserted document_memories id for the
    source URI. The id is derived deterministically from the source path so
    concurrent calls converge on the same parent without id collisions.
    """
    parent_id = f"doc-{workspace_id}-{abs(hash(source_uri)) % 10_000_000:07d}"
    # 1. Look up by file_path first (the canonical match).
    existing = conn.execute(
        "SELECT id FROM document_memories WHERE file_path = ?", (source_uri,)
    ).fetchone()
    if existing is not None:
        return existing["id"]
    # 2. If a row already lives at the deterministic id, use it.
    by_id = conn.execute(
        "SELECT id FROM document_memories WHERE id = ?", (parent_id,)
    ).fetchone()
    if by_id is not None:
        return by_id["id"]
    # 3. Insert. file_hash is UNIQUE; if it collides, fall through to fetch
    # the existing row.
    parent_hash = hash_value or f"parent-of-{source_uri}"
    try:
        conn.execute(
            """
            INSERT INTO document_memories(id, file_path, file_hash, summary, topics, metadata)
            VALUES (?, ?, ?, '', '[]', '{}')
            """,
            (parent_id, source_uri, parent_hash),
        )
        return parent_id
    except sqlite3.IntegrityError:
        again = conn.execute(
            "SELECT id FROM document_memories WHERE file_path = ?", (source_uri,)
        ).fetchone()
        if again is not None:
            return again["id"]
        by_hash = conn.execute(
            "SELECT id FROM document_memories WHERE file_hash = ?", (parent_hash,)
        ).fetchone()
        if by_hash is not None:
            return by_hash["id"]
        raise RuntimeError(f"could not resolve parent for {source_uri}")


def _backfill_one(conn, chunk_id: str, source_uri: str, workspace_id: str, hash_value: str) -> str:
    document_id = _resolve_parent_id(conn, source_uri, workspace_id, hash_value)
    # Insert the chunk. parent_id is free-form (no FK) — point it at the
    # chunk itself so a query that follows parent_id->chunk_id has a target.
    chunk_hash = hash_value or f"chunk-{chunk_id}"
    conn.execute(
        """
        INSERT OR IGNORE INTO document_chunks(
            id, document_id, parent_id, parent_type, source_uri,
            chunk_index, heading, content, offset_start, offset_end, hash,
            metadata, workspace_id
        ) VALUES (?, ?, ?, 'document', ?, 0, '', '', 0, 0, ?, '{}', ?)
        """,
        (chunk_id, document_id, chunk_id, source_uri, chunk_hash, workspace_id),
    )
    return document_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill document parents/chunks (R4.3)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="plan only, do not write")
    mode.add_argument("--apply", action="store_true", help="apply changes to the live DB")
    parser.add_argument("--backup", help="path to a backup of hive_mind.db (required with --apply)")
    args = parser.parse_args()

    if args.apply and not args.backup:
        parser.error("--apply requires --backup <path>")

    conn = get_connection()
    try:
        ensure_migrations(conn)
        before = _list_orphans(conn)
        plan: List[dict] = []
        for row in before:
            plan.append({
                "chunk_id": row["chunk_id"],
                "source_uri": row["source_uri"],
                "workspace_id": row["workspace_id"] or "default",
                "hash": row["hash"] or "",
            })

        report = {
            "mode": "apply" if args.apply else "dry-run",
            "orphans_found": len(plan),
            "would_backfill": len(plan),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if args.apply:
            backup_path = Path(args.backup)
            if not backup_path.exists():
                print(f"backup not found: {backup_path}", file=sys.stderr)
                return 2
            for row in plan:
                _backfill_one(
                    conn,
                    row["chunk_id"], row["source_uri"], row["workspace_id"], row["hash"],
                )
            conn.commit()
            after = _list_orphans(conn)
            report["orphans_remaining"] = len(after)
            report["rows_written"] = len(plan) - len(after)

        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
