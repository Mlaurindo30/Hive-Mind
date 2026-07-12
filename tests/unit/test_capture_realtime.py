from __future__ import annotations

import importlib.util
import time
from pathlib import Path

from scripts.capture.capture_queue import CaptureQueue
from scripts.capture.capture_sources import SourceChange


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "capture" / "capture-realtime.py"


def load_capture_realtime():
    spec = importlib.util.spec_from_file_location("capture_realtime", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_capture_realtime_imports_without_libc():
    module = load_capture_realtime()
    assert not hasattr(module, "_libc")


def test_capture_realtime_has_no_linux_only_transport():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "ctypes" not in source
    assert "libc.so.6" not in source
    assert "inotify" not in source
    assert "import select" not in source


def test_capture_realtime_never_waits_for_claude_mem():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "worker_alive" not in source


def test_pid_file_is_project_local():
    module = load_capture_realtime()
    pid_file = Path(module.PID_FILE)
    assert ROOT in pid_file.parents


def test_source_change_enqueues_normalized_events_once(tmp_path: Path):
    module = load_capture_realtime()
    transcript = tmp_path / "transcript_full.jsonl"
    transcript.write_text('{"type":"USER_INPUT"}\n', encoding="utf-8")

    parsed_paths: list[Path] = []

    def parser(path):
        parsed_paths.append(Path(path))
        return [
            {
                "sid": "sess-1",
                "prompt": "hello world",
                "prompts": ["hello world"],
                "turns": [
                    {
                        "tool_name": "Shell",
                        "tool_input": {"command": "ls"},
                        "tool_response": "ok",
                    }
                ],
                "last": "done",
            }
        ]

    registry = {
        "antigravity": {
            "owner": "realtime",
            "mode": "reparse",
            "parser": parser,
            "watch": [str(tmp_path)],
            "sources": [str(tmp_path / "transcript_full.jsonl")],
        }
    }
    queue = CaptureQueue(tmp_path / "outbox.db")
    try:
        daemon = module.RealtimeCapture(registry, queue)
        change = SourceChange("antigravity", transcript, time.time())

        first = daemon.handle_change(change)
        assert first >= 2  # at least prompt + tool result
        assert parsed_paths and parsed_paths[0] == transcript

        # Re-parsing the same source must not enqueue duplicates.
        assert daemon.handle_change(change) == 0

        health = queue.health()
        assert health["dead_letter"] == 0
        assert health["delivered"] == 0
        assert health["pending"] + health["blocked"] == first
    finally:
        queue.close()


def test_unknown_provider_change_is_ignored(tmp_path: Path):
    module = load_capture_realtime()
    queue = CaptureQueue(tmp_path / "outbox.db")
    try:
        daemon = module.RealtimeCapture({}, queue)
        change = SourceChange("ghost", tmp_path / "nope.jsonl", time.time())
        assert daemon.handle_change(change) == 0
    finally:
        queue.close()
