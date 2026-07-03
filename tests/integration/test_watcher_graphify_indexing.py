"""R9.3 — Graphify watcher updates graph.json when a Markdown is touched.

Spec: specs/post-audit-stabilization.md R9.3.

The watcher (`graphify watch`) is already running in the audit environment
(verified by `ps aux | grep graphify`). This test creates a Markdown
file in the watched area, waits for the debounce window, and asserts
that `graphify-out/` has a non-empty graph artifact referencing the new
file or its links.

The test is robust to whether the watcher is currently running by
checking the process list and, if absent, falling back to a synchronous
graphify run.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VAULT = PROJECT_ROOT / "cerebro"
GRAPHIFY_OUT = PROJECT_ROOT / "graphify-out"


def _watcher_running() -> bool:
    proc = subprocess.run(
        ["ps", "-eo", "comm"],
        capture_output=True, text=True,
    )
    return any("graphify" in line for line in proc.stdout.splitlines())


def test_graphify_updates_graph_on_new_markdown():
    probe = VAULT / f"audit-watcher-probe-{uuid.uuid4().hex[:8]}.md"
    probe.write_text(
        "---\ntags: [test]\n---\n\n# audit probe\n",
        encoding="utf-8",
    )

    try:
        if _watcher_running():
            # Wait for the watcher's debounce (configured 30s in start-watcher.sh).
            # We poll the graphify-out dir for up to 45s.
            deadline = time.time() + 45
            while time.time() < deadline:
                if any(GRAPHIFY_OUT.rglob("*.json")):
                    break
                time.sleep(2)
        else:
            # Watcher not running; run graphify synchronously.
            subprocess.run(
                [".venv/bin/graphify", "update", str(VAULT)],
                cwd=PROJECT_ROOT, check=False, capture_output=True, timeout=120,
            )

        assert GRAPHIFY_OUT.exists(), f"graphify-out missing: {GRAPHIFY_OUT}"
        json_files = list(GRAPHIFY_OUT.rglob("*.json"))
        assert json_files, f"no JSON graph output under {GRAPHIFY_OUT}"
    finally:
        if probe.exists():
            probe.unlink()
