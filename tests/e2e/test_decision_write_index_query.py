"""R2.4 — Decision write path closes end-to-end.

Spec: specs/post-audit-stabilization.md R2.4.

This is the audit fixture. It does NOT delete artifacts because
`sinapse_save_decision` writes to a real path. The fixture writes to a
unique per-run title so re-runs do not collide and the existing
save_decision does not deduplicate.
"""

from __future__ import annotations

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

    # Spec R2.4 step 1+2: confirm file exists with valid frontmatter.
    written = _find_written_path(title)
    assert written is not None, f"no Markdown file for title {title}"
    body = written.read_text(encoding="utf-8")
    assert body.startswith("---"), f"frontmatter missing in {written}"
    assert "tags: [decision]" in body
    assert "status: active" in body

    # R2.4 step 3: confirm a neurons row exists for this file.
    from core.database import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, hash, workspace_id FROM neurons WHERE source_file = ?",
            (str(written),),
        ).fetchone()
        assert row is not None, f"no neurons row for {written}"
        neuron_id = row["id"]
        # R2.4 step 4: FTS row.
        fts = conn.execute(
            "SELECT 1 FROM search_fts WHERE neuron_id = ?", (neuron_id,)
        ).fetchone()
        assert fts is not None, f"no FTS row for {neuron_id}"
    finally:
        conn.close()


def _find_written_path(title: str) -> Path | None:
    from core import paths as cp
    # The decision path lives somewhere under FRONTAL/trabalho/ativo; we walk
    # the directory rather than coupling to a single subpath.
    base = Path(cp.CORTEX) if hasattr(cp, "CORTEX") else Path("cerebro/cortex")
    candidates = list(base.rglob(f"*{title}*.md"))
    if candidates:
        return candidates[0]
    # Fallback: scan the whole tree for the title token.
    candidates = list(Path("cerebro").rglob("*.md")) if Path("cerebro").exists() else []
    for c in candidates:
        if title in c.read_text(encoding="utf-8", errors="ignore")[:4000]:
            return c
    return None
