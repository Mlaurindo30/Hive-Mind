"""R4.1 — DocumentPipeline consistency audit.

Spec: specs/post-audit-stabilization.md R4.1.

Prints, for the live database, the counts of:

  - document_vectors (vec_documents) without a parent (no matching chunk)
  - document_vectors without a chunk
  - chunks without a parent
  - parents without chunks
  - chunks without a vector
  - vectors missing required metadata
  - duplicate hashes
  - rows missing source_uri
  - rows missing workspace_id

Run with:

    .venv/bin/python scripts/health/audit_document_pipeline_consistency.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database import get_connection


def _counts(conn) -> Dict[str, int]:
    out: Dict[str, int] = {}

    out["document_vectors_total"] = (
        conn.execute("SELECT COUNT(*) FROM vec_documents").fetchone()[0]
    )
    out["document_chunks_total"] = (
        conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
    )
    out["document_memories_total"] = (
        conn.execute("SELECT COUNT(*) FROM document_memories").fetchone()[0]
    )

    # vec_documents.chunk_id -> document_chunks.id (parent)
    out["vectors_without_chunk"] = conn.execute(
        """
        SELECT COUNT(*) FROM vec_documents v
        WHERE NOT EXISTS (SELECT 1 FROM document_chunks c WHERE c.id = v.chunk_id)
        """
    ).fetchone()[0]

    # chunks without a document parent
    out["chunks_without_parent"] = conn.execute(
        """
        SELECT COUNT(*) FROM document_chunks c
        WHERE NOT EXISTS (SELECT 1 FROM document_memories m WHERE m.id = c.document_id)
        """
    ).fetchone()[0]

    # parents with no chunks
    out["parents_without_chunks"] = conn.execute(
        """
        SELECT COUNT(*) FROM document_memories m
        WHERE NOT EXISTS (SELECT 1 FROM document_chunks c WHERE c.document_id = m.id)
        """
    ).fetchone()[0]

    # chunks without a vector
    out["chunks_without_vector"] = conn.execute(
        """
        SELECT COUNT(*) FROM document_chunks c
        WHERE NOT EXISTS (SELECT 1 FROM vec_documents v WHERE v.chunk_id = c.id)
        """
    ).fetchone()[0]

    # missing required metadata
    out["vectors_missing_source_uri"] = conn.execute(
        """
        SELECT COUNT(*) FROM vector_metadata
        WHERE collection = 'document_vectors' AND (source_uri IS NULL OR source_uri = '')
        """
    ).fetchone()[0]
    out["vectors_missing_workspace"] = conn.execute(
        """
        SELECT COUNT(*) FROM vector_metadata
        WHERE collection = 'document_vectors' AND (workspace_id IS NULL OR workspace_id = '')
        """
    ).fetchone()[0]
    out["chunks_missing_source_uri"] = conn.execute(
        """
        SELECT COUNT(*) FROM document_chunks
        WHERE source_uri IS NULL OR source_uri = ''
        """
    ).fetchone()[0]
    out["chunks_missing_workspace"] = conn.execute(
        """
        SELECT COUNT(*) FROM document_chunks
        WHERE workspace_id IS NULL OR workspace_id = ''
        """
    ).fetchone()[0]

    # duplicate hashes
    out["duplicate_chunk_hashes"] = conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT hash FROM document_chunks GROUP BY hash HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit DocumentPipeline consistency (R4.1)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    conn = get_connection()
    try:
        result = _counts(conn)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for key, value in sorted(result.items()):
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
