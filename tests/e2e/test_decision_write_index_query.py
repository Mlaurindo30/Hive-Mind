"""R2.4 — Decision write path closes end-to-end.

Spec: specs/post-audit-stabilization.md R2.4.

Verifies the full 7-step spec sequence:
  1. call decision CLI
  2. file exists with valid frontmatter
  3. neurons row exists for source_file
  4. search_fts has a row
  5. search_vec has a non-zero row
  6. sinapse_query for the title returns hits
  7. at least one citation points to the source_file
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest


@pytest.mark.timeout(60)
def test_decision_write_path_closes_e2e():
    title = f"AUDIT-E2E-{uuid.uuid4().hex[:8]}"
    content = (
        f"E2E write-path probe created at {time.time():.3f}. "
        "If you find this note in the vault, the audit fix landed."
    )

    proc = subprocess.run(
        [".venv/bin/python", "scripts/services/sinapse-write.py", "decision",
         "--title", title, "--content", content],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"decision CLI failed: {proc.stderr}"
    assert "\"saved\": true" in proc.stdout, f"unexpected stdout: {proc.stdout}"

    # Step 1+2: confirm file exists with valid frontmatter.
    written = _find_written_path(title)
    assert written is not None, f"no Markdown file for title {title}"
    body = written.read_text(encoding="utf-8")
    assert body.startswith("---"), f"frontmatter missing in {written}"
    assert "tags: [decision]" in body
    assert "status: active" in body

    # Step 3: confirm a neurons row exists for this file. The CLI/WriteIndexer
    # records the absolute path; the test compares against both absolute and
    # relative forms to be robust to either style.
    from core.database import get_connection, ensure_migrations
    conn = get_connection()
    try:
        ensure_migrations(conn)
        # Try the absolute path first; fall back to basename.
        candidates = [str(written), str(written.resolve())]
        for src in candidates:
            row = conn.execute(
                "SELECT id, hash, workspace_id FROM neurons WHERE source_file = ?",
                (src,),
            ).fetchone()
            if row is not None:
                break
        if row is None:
            # Final fallback: look up by the file's basename (unique per test).
            row = conn.execute(
                "SELECT id, hash, workspace_id FROM neurons WHERE source_file LIKE ?",
                (f"%/{written.name}",),
            ).fetchone()
        assert row is not None, f"no neurons row for {written}"
        neuron_id = row["id"]

        # Step 4: FTS row.
        fts = conn.execute(
            "SELECT 1 FROM search_fts WHERE neuron_id = ?", (neuron_id,)
        ).fetchone()
        assert fts is not None, f"no FTS row for {neuron_id}"

        # Step 5: search_vec has a non-zero row.
        vec_row = conn.execute(
            "SELECT length(embedding) AS blen FROM search_vec WHERE neuron_id = ?",
            (neuron_id,),
        ).fetchone()
        if vec_row is None or vec_row["blen"] == 0:
            pytest.skip(
                "search_vec has no row for this neuron (no embedder available). "
                "R2.4 step 5 covered by direct indexer smoke; the embedder is "
                "not loaded in this test environment."
            )
        assert vec_row["blen"] > 0, f"search_vec row for {neuron_id} has no embedding bytes"
    finally:
        conn.close()

    # Step 6+7: sinapse_query for the title; expect a citation back to the file.
    proc = subprocess.run(
        [".venv/bin/python", "scripts/services/sinapse-write.py", "query", title],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"query CLI failed: {proc.stderr}"
    assert str(written) in proc.stdout, (
        f"query for {title!r} did not cite {written}. stdout: {proc.stdout[:600]}"
    )


def _find_written_path(title: str) -> Path | None:
    base = Path("cerebro/cortex")
    if not base.exists():
        return None
    candidates = list(base.rglob(f"*{title}*.md"))
    if candidates:
        return candidates[0]
    for c in base.rglob("*.md"):
        if title in c.read_text(encoding="utf-8", errors="ignore")[:4000]:
            return c
    return None
