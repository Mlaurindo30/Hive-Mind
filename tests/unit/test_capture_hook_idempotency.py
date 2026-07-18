from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from scripts.capture.capture_queue import CaptureQueue


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "capture" / "capture-hook.py"


def _load_hook_module():
    spec = importlib.util.spec_from_file_location("capture_hook_idempotency", HOOK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_replayed_hook_callback_enqueues_only_one_event(tmp_path, monkeypatch) -> None:
    module = _load_hook_module()
    db_path = tmp_path / "capture.db"
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(db_path))
    monkeypatch.setenv(
        "HIVE_CAPTURE_CONTEXT_DB", str(tmp_path / "capture-context.db")
    )
    payload = json.dumps(
        {
            "session_id": "session-1",
            "cwd": "D:/Hive-Mind",
            "prompt": "AUDIT-CAPTURE-CODEX-stable",
            "event_id": "native-hook-event-1",
        }
    ).encode("utf-8")

    assert module.process("codex", "prompt", payload)["enqueued"] is True
    assert module.process("codex", "prompt", payload)["enqueued"] is False

    queue = CaptureQueue(db_path)
    try:
        assert queue.health()["pending"] == 1
    finally:
        queue.close()
