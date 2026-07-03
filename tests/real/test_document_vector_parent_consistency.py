from __future__ import annotations

import pytest

pytestmark = pytest.mark.real

"""R4.2 — DocumentPipeline consistency test.

Spec: specs/post-audit-stabilization.md R4.2.

Asserts, against the live database:

  - every `document_vectors` row has a valid `document_chunks` reference
  - every `document_chunks` row has a valid `document_memories` reference
  - the audit script's printed counts include 0 orphan vectors after the
    backfill has been run

This is a guard against regression. The backfill script in
`scripts/maintenance/backfill_document_parents_chunks.py` is what closes
the 4968-orphan gap that the audit found.
"""
import subprocess
import sys
from pathlib import Path
def test_no_orphan_document_vectors():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from core.database import get_connection, ensure_migrations

    conn = get_connection()
    try:
        ensure_migrations(conn)
        orphans = conn.execute(
            """
            SELECT COUNT(*) FROM vec_documents v
            WHERE NOT EXISTS (SELECT 1 FROM document_chunks c WHERE c.id = v.chunk_id)
            """
        ).fetchone()[0]
        assert orphans == 0, f"vec_documents has {orphans} orphan rows"
    finally:
        conn.close()
def test_every_chunk_has_parent():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from core.database import get_connection, ensure_migrations

    conn = get_connection()
    try:
        ensure_migrations(conn)
        orphans = conn.execute(
            """
            SELECT COUNT(*) FROM document_chunks c
            WHERE NOT EXISTS (SELECT 1 FROM document_memories m WHERE m.id = c.document_id)
            """
        ).fetchone()[0]
        assert orphans == 0, f"document_chunks has {orphans} rows without a parent"
    finally:
        conn.close()
def test_audit_script_reports_zero_orphans():
    """Run the audit script and parse its output. It MUST report
    vectors_without_chunk: 0 after the backfill."""
    project = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [".venv/bin/python", "scripts/health/audit_document_pipeline_consistency.py"],
        cwd=project, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"audit script failed: {proc.stderr}"
    assert "vectors_without_chunk: 0" in proc.stdout, (
        f"audit reports orphan vectors remaining:\n{proc.stdout}"
    )
    assert "chunks_without_parent: 0" in proc.stdout, (
        f"audit reports chunks without parent:\n{proc.stdout}"
    )
def test_document_query_returns_auditable_citation():
    """R4.2 last bullet: every document query response MUST include
    source_uri, offset_start, offset_end, and a parent reference.

    Calls the real DocumentPipeline and asserts on the first hit's
    citation shape.
    """
    from core.database import get_connection, ensure_migrations
    from core.document_pipeline import DocumentPipeline

    conn = get_connection()
    try:
        ensure_migrations(conn)
        # Use the existing audit-ws test fixture from the prior round if
        # present; otherwise use a generic term and pick whatever hit comes
        # back. The assertion is on shape, not content.
        pipeline = DocumentPipeline(conn, workspace_id="audit-ws")
        hits = pipeline.query("contrato único para vetores documentais",
                              top_k=3, project="Hive-Mind")
        assert hits, "DocumentPipeline returned no hits"
        h = hits[0]
        for field in ("source_uri", "offset_start", "offset_end", "parent"):
            assert field in h, f"hit missing citation field {field!r}: {h}"
    finally:
        conn.close()
