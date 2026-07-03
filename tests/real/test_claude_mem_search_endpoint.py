"""R6.1 — Claude Mem HTTP search returns results consistent with local FTS.

Spec: specs/post-audit-stabilization.md R6.1.

Picks a term that the local SQLite FTS finds in `~/.claude-mem/claude-mem.db`,
calls the HTTP `/api/search` endpoint, and asserts the response is
non-empty. If the endpoint is unreachable or returns 0, the test FAILS.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


CM_DB = Path(os.environ.get("CLAUDE_MEM_DB", os.path.expanduser("~/.claude-mem/claude-mem.db")))
ENDPOINT = os.environ.get("CLAUDE_MEM_HTTP", "http://127.0.0.1:37700/api/search")


def _local_fts_terms() -> list[str]:
    if not CM_DB.exists():
        return []
    conn = sqlite3.connect(str(CM_DB))
    try:
        rows = conn.execute(
            """
            SELECT title FROM observations
            WHERE title IS NOT NULL AND length(title) > 3
            ORDER BY rowid DESC
            LIMIT 20
            """
        ).fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows]


def _http_search(term: str) -> tuple[int, str]:
    try:
        url = f"{ENDPOINT}?query={urllib.parse.quote(term)}&limit=5"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return 0, f"transport-error: {e}"


def test_http_search_returns_at_least_one_match():
    terms = _local_fts_terms()
    assert terms, f"no FTS titles available in {CM_DB}"
    for term in terms[:10]:
        status, body = _http_search(term)
        if status == 200 and "Found 0" not in body and "result" in body.lower():
            return
    pytest.fail(
        f"no term out of {len(terms[:10])} produced an HTTP /api/search match. "
        f"Endpoint at {ENDPOINT} returned empty for all probed terms."
    )


def test_http_search_payload_shape():
    terms = _local_fts_terms()
    if not terms:
        pytest.skip("no FTS titles available")
    status, body = _http_search(terms[0])
    if status != 200:
        pytest.skip(f"endpoint unreachable: {status} {body[:200]}")
    assert body.lstrip().startswith("{") or body.lstrip().startswith("["), (
        f"unexpected payload shape: {body[:200]!r}"
    )
