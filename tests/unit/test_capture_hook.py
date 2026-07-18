"""Task 7 — non-blocking provider capture hook entrypoint.

The hook must always exit zero, never touch the network, and only append
sanitized events to the durable ``CaptureQueue`` outbox.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.capture.capture_queue import CaptureQueue


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "capture" / "capture-hook.py"
MAX_STDIN_BYTES = 2 * 1024 * 1024


def run_hook(
    provider: str,
    event_type: str,
    payload: dict | None,
    *,
    raw_stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
    return subprocess.run(
        [
            sys.executable,
            str(HOOK),
            "--provider",
            provider,
            "--event-type",
            event_type,
        ],
        input=stdin,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        cwd=str(ROOT),
        timeout=60,
    )


def _drain_health(db_path: Path) -> dict[str, int]:
    queue = CaptureQueue(db_path)
    try:
        return queue.health()
    finally:
        queue.close()


def _first_pending_content(db_path: Path) -> str:
    queue = CaptureQueue(db_path)
    try:
        return queue.pending(1)[0].event.content
    finally:
        queue.close()


def test_hook_succeeds_when_worker_is_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(tmp_path / "capture.db"))
    result = run_hook("codex", "prompt", {"session_id": "s", "prompt": "hello"})
    assert result.returncode == 0
    assert CaptureQueue(tmp_path / "capture.db").health()["pending"] == 1


def test_hook_prints_one_compact_json_result(tmp_path, monkeypatch):
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(tmp_path / "capture.db"))
    result = run_hook("claude", "prompt", {"session_id": "s", "prompt": "hi"})
    assert result.returncode == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["ok"] is True
    assert parsed["enqueued"] is True


def test_hook_redacts_secrets_before_enqueue(tmp_path, monkeypatch):
    db_path = tmp_path / "capture.db"
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(db_path))
    token = "ghp_" + "a" * 36
    result = run_hook(
        "codex",
        "prompt",
        {"session_id": "s", "prompt": f"use this token {token} please"},
    )
    assert result.returncode == 0
    content = _first_pending_content(db_path)
    assert token not in content
    assert "[REDACTED" in content


def test_hook_rejects_oversized_stdin_before_parsing(tmp_path, monkeypatch):
    db_path = tmp_path / "capture.db"
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(db_path))
    oversized = "x" * (MAX_STDIN_BYTES + 1)
    result = run_hook("codex", "prompt", None, raw_stdin=oversized)
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert parsed["ok"] is False
    assert _drain_health(db_path)["pending"] == 0


def test_hook_exits_zero_on_invalid_json(tmp_path, monkeypatch):
    db_path = tmp_path / "capture.db"
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(db_path))
    result = run_hook("codex", "prompt", None, raw_stdin="{not valid json")
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert parsed["ok"] is False
    assert _drain_health(db_path)["pending"] == 0


def test_hook_maps_tool_result_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "capture.db"
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(db_path))
    result = run_hook(
        "claude",
        "tool_result",
        {
            "session_id": "s",
            "cwd": str(ROOT),
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {"stdout": "files"},
        },
    )
    assert result.returncode == 0
    content = _first_pending_content(db_path)
    assert "Bash" in content
    assert "files" in content


def test_hook_replay_is_idempotent_and_preserves_context(tmp_path, monkeypatch):
    db_path = tmp_path / "capture.db"
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(db_path))
    payload = {
        "session_id": "s",
        "event_id": "native-event-1",
        "timestamp": "2026-07-17T12:00:00Z",
        "cwd": r"C:\\work\\project",
        "project": "project",
        "prompt": "same event",
    }
    assert json.loads(run_hook("codex", "prompt", payload).stdout)["enqueued"] is True
    assert json.loads(run_hook("codex", "prompt", payload).stdout)["enqueued"] is False

    queue = CaptureQueue(db_path)
    try:
        item = queue.pending(1)[0]
        assert item.event.event_id == "native-event-1"
        assert item.event.project == "project"
        assert item.event.cwd == r"C:\\work\\project"
    finally:
        queue.close()
