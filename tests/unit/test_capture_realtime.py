from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path

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


def test_source_change_uses_linux_compatible_direct_ingest_once(tmp_path: Path, monkeypatch):
    module = load_capture_realtime()
    transcript = tmp_path / "transcript_full.jsonl"
    transcript.write_text('{"type":"USER_INPUT"}\n', encoding="utf-8")

    parsed_paths: list[Path] = []
    delivered: list[tuple[str, str]] = []

    def parser(path):
        parsed_paths.append(Path(path))
        return [{
            "sid": "sess-1",
            "prompt": "hello world",
            "prompts": ["hello world"],
            "turns": [{
                "tool_name": "Shell",
                "tool_input": {"command": "ls"},
                "tool_response": "ok",
            }],
            "last": "done",
        }]

    class Store:
        def close(self):
            pass

    def ingest(provider, session, store):
        delivered.append((provider, session["sid"]))
        return 1

    monkeypatch.setattr(module.core, "ingest", ingest)
    registry = {
        "antigravity": {
            "owner": "realtime",
            "mode": "reparse",
            "parser": parser,
            "watch": [str(tmp_path)],
            "sources": [str(transcript)],
        }
    }
    daemon = module.RealtimeCapture(registry, Store())
    change = SourceChange("antigravity", transcript, time.time())

    assert daemon.handle_change(change) == 1
    assert parsed_paths == [transcript]
    assert delivered == [("antigravity", "sess-1")]


def test_unknown_provider_change_is_ignored(tmp_path: Path):
    module = load_capture_realtime()

    class Store:
        def close(self):
            pass

    daemon = module.RealtimeCapture({}, Store())
    change = SourceChange("ghost", tmp_path / "nope.jsonl", time.time())
    assert daemon.handle_change(change) == 0


def test_sqlite_wal_change_reparses_canonical_database(tmp_path: Path, monkeypatch):
    module = load_capture_realtime()
    database = tmp_path / "session-store.db"
    wal = tmp_path / "session-store.db-wal"
    database.write_bytes(b"sqlite")
    wal.write_bytes(b"wal")
    old = time.time() - 3600
    os.utime(database, (old, old))

    parsed_paths: list[Path] = []

    def parser(path):
        parsed_paths.append(Path(path))
        return [{"sid": "copilot-1", "prompt": "real prompt", "turns": []}]

    class Store:
        def close(self):
            pass

    monkeypatch.setattr(module.core, "ingest", lambda provider, session, store: 1)
    registry = {
        "copilot": {
            "owner": "realtime",
            "mode": "reparse",
            "parser": parser,
            "watch": [str(tmp_path)],
            "sources": [str(database)],
        }
    }
    daemon = module.RealtimeCapture(registry, Store(), clock=time.time)

    assert daemon.handle_change(SourceChange("copilot", wal, time.time())) == 1
    assert parsed_paths == [database]

def test_structured_log_is_safe_on_strict_cp1252_console(monkeypatch):
    module = load_capture_realtime()

    class StrictCp1252Stream:
        def __init__(self):
            self.parts = []

        def write(self, text):
            text.encode("cp1252", errors="strict")
            self.parts.append(text)
            return len(text)

        def flush(self):
            return None

    stream = StrictCp1252Stream()
    monkeypatch.setattr(module.sys, "stderr", stream)

    module.log_event("warning", "unicode_diagnostic", detail="⚠ caminho ç")

    record = __import__("json").loads("".join(stream.parts))
    assert record["detail"] == "⚠ caminho ç"
