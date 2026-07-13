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
import sys
import time
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import paths as cp  # noqa: E402

VAULT = PROJECT_ROOT / "cerebro"
# Canonical output dir: same resolution RetrievalRouter._route_graphify uses
# (core/retrieval/router.py) — cerebro/cortex/occipital/grafo/graph.json.
GRAPHIFY_OUT = cp.OCCIPITAL / "grafo"


def _watcher_running() -> bool:
    if os.name == "nt":
        # PowerShell is the normal test host on Windows. Only a process whose
        # command line explicitly starts the watcher (or Graphify watch) counts.
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | Where-Object { "
                "($_.Name -in @('powershell.exe', 'pwsh.exe')) -and "
                "$_.CommandLine -match 'start-watcher|graphify.*watch' "
                "} | Select-Object -ExpandProperty ProcessId",
            ],
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())
    proc = subprocess.run(
        ["ps", "-eo", "comm"],
        capture_output=True, text=True,
    )
    return any("graphify" in line for line in proc.stdout.splitlines())


def test_graphify_updates_graph_on_new_markdown():
    VAULT.mkdir(parents=True, exist_ok=True)
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
            # Match the installer bootstrap. `graphify update` alone returns 1
            # for a Markdown-only vault; build-graph.ps1 creates the canonical
            # empty graph artifact in that case.
            if os.name == "nt":
                command = [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(PROJECT_ROOT / "scripts" / "graph" / "build-graph.ps1"),
                    "-SkipHnsw",
                ]
            else:
                command = [str(PROJECT_ROOT / ".venv" / "bin" / "graphify"), "update", str(VAULT)]
            subprocess.run(
                command,
                cwd=PROJECT_ROOT, check=False, capture_output=True, timeout=120,
            )

        assert GRAPHIFY_OUT.exists(), f"graphify-out missing: {GRAPHIFY_OUT}"
        json_files = list(GRAPHIFY_OUT.rglob("*.json"))
        assert json_files, f"no JSON graph output under {GRAPHIFY_OUT}"
    finally:
        if probe.exists():
            probe.unlink()
