from __future__ import annotations

import importlib.util
import os
import threading
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
        """Stand-in for SeenStore: the transport touches and dedupes through it."""

        def __init__(self):
            self.seen = set()

        def touch(self, platform, sid):
            pass

        def contains(self, platform, sid, digest):
            return digest in self.seen

        def add(self, platform, sid, digest):
            self.seen.add(digest)

        def close(self):
            pass

    def ingest(provider, session, store, **_kwargs):
        delivered.append((provider, session["sid"]))
        return 1

    # Intercepta o ingest nativo — o entrypoint deixou de resolver
    # identidade por conta própria em D004-R2.
    monkeypatch.setattr(module.capture, "ingest", ingest)
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
        """Stand-in for SeenStore: the transport touches and dedupes through it."""

        def __init__(self):
            self.seen = set()

        def touch(self, platform, sid):
            pass

        def contains(self, platform, sid, digest):
            return digest in self.seen

        def add(self, platform, sid, digest):
            self.seen.add(digest)

        def close(self):
            pass

    daemon = module.RealtimeCapture({}, Store())
    change = SourceChange("ghost", tmp_path / "nope.jsonl", time.time())
    assert daemon.handle_change(change) == 0


def test_main_starts_live_sources_before_running_startup_catch_up(monkeypatch):
    """A locked historical post must not leave new prompts unwatched."""
    module = load_capture_realtime()
    live_started = threading.Event()

    class FakeStore:
        def close(self):
            pass

    class FakeDaemon:
        def __init__(self, *_args, **_kwargs):
            pass

        def catch_up(self):
            assert live_started.is_set()
            return 0

        def handle_change(self, _change):
            return 0

    class FakeWatcher:
        def __init__(self, *_args):
            pass

        def start(self):
            live_started.set()

        def stop(self):
            pass

        def watch_roots(self):
            return []

    class FakeReconciler:
        def __init__(self, *_args, **_kwargs):
            pass

        def scan_once(self):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(module.core, "SeenStore", FakeStore)
    monkeypatch.setattr(module, "RealtimeCapture", FakeDaemon)
    monkeypatch.setattr(module, "WatchdogSource", FakeWatcher)
    monkeypatch.setattr(module, "PollingReconciler", FakeReconciler)
    monkeypatch.setattr(module, "_write_pid_file", lambda: None)
    monkeypatch.setattr(module, "_remove_pid_file", lambda: None)
    monkeypatch.setattr(
        module.time, "sleep", lambda _seconds: (_ for _ in ()).throw(
            KeyboardInterrupt
        )
    )

    assert module.main() == 0


def test_catch_up_reparses_all_reparse_sources_even_when_old(tmp_path: Path, monkeypatch):
    module = load_capture_realtime()
    old_file = tmp_path / "historic.db"
    old_file.write_text("placeholder", encoding="utf-8")
    old = time.time() - (5 * 3600)
    os.utime(old_file, (old, old))

    parsed_paths: list[Path] = []
    delivered: list[str] = []

    def parser(path):
        parsed_paths.append(Path(path))
        return [{"sid": "historic-session", "prompt": "old", "turns": []}]

    def ingest(provider, session, *_args, **_kwargs):
        delivered.append(f"{provider}:{session['sid']}")
        return 1

    monkeypatch.setattr(module.capture, "ingest", ingest)
    registry = {
        "antigravity": {
            "owner": "realtime",
            "mode": "reparse",
            "parser": parser,
            "sources": [str(old_file)],
        }
    }
    daemon = module.RealtimeCapture(registry, object(), clock=time.time)

    assert daemon.catch_up() == 1
    assert parsed_paths == [old_file]
    assert delivered == ["antigravity:historic-session"]


def test_catch_up_drops_parser_time_cutoff_for_reparse_sources(tmp_path: Path, monkeypatch):
    module = load_capture_realtime()
    old_file = tmp_path / "historic.db"
    old_file.write_text("placeholder", encoding="utf-8")

    seen_cutoffs: list[int] = []

    def parser(_path):
        seen_cutoffs.append(module.core.SESSION_CUTOFF_MS)
        return [{"sid": "historic-session", "prompt": "old", "turns": []}]

    monkeypatch.setattr(module.capture, "ingest", lambda *_a, **_k: 1)
    registry = {
        "kilo": {
            "owner": "realtime",
            "mode": "reparse",
            "parser": parser,
            "sources": [str(old_file)],
        }
    }
    daemon = module.RealtimeCapture(registry, object(), clock=time.time)

    assert daemon.catch_up() == 1
    assert seen_cutoffs == [0]


def test_slow_provider_does_not_block_another_provider(tmp_path: Path, monkeypatch):
    module = load_capture_realtime()
    slow_file = tmp_path / "slow.jsonl"
    fast_file = tmp_path / "fast.jsonl"
    slow_file.write_text("{}", encoding="utf-8")
    fast_file.write_text("{}", encoding="utf-8")
    slow_started = threading.Event()
    release_slow = threading.Event()
    fast_finished = threading.Event()

    def slow_parser(_path):
        slow_started.set()
        assert release_slow.wait(5)
        return [{"sid": "slow", "prompt": "slow", "turns": []}]

    def fast_parser(_path):
        return [{"sid": "fast", "prompt": "fast", "turns": []}]

    monkeypatch.setattr(module.capture, "ingest", lambda *_a, **_k: 1)
    registry = {
        "slow": {"parser": slow_parser, "sources": [str(slow_file)]},
        "fast": {"parser": fast_parser, "sources": [str(fast_file)]},
    }
    daemon = module.RealtimeCapture(registry, object())
    slow_thread = threading.Thread(
        target=daemon.handle_change,
        args=(SourceChange("slow", slow_file, time.time()),),
    )
    fast_thread = threading.Thread(
        target=lambda: (
            daemon.handle_change(SourceChange("fast", fast_file, time.time())),
            fast_finished.set(),
        ),
    )

    slow_thread.start()
    assert slow_started.wait(2)
    fast_thread.start()
    try:
        assert fast_finished.wait(1), "provider rápido ficou preso atrás do provider lento"
    finally:
        release_slow.set()
        slow_thread.join(5)
        fast_thread.join(5)


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
        """Stand-in for SeenStore: the transport touches and dedupes through it."""

        def __init__(self):
            self.seen = set()

        def touch(self, platform, sid):
            pass

        def contains(self, platform, sid, digest):
            return digest in self.seen

        def add(self, platform, sid, digest):
            self.seen.add(digest)

        def close(self):
            pass

    monkeypatch.setattr(module.capture, "ingest",
                        lambda *_a, **_k: 1)
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


def test_main_primes_reconciler_only_after_catch_up(monkeypatch):
    module = load_capture_realtime()
    events: list[str] = []

    class FakeStore:
        def close(self):
            events.append("store.close")

    class FakeDaemon:
        def __init__(self, *_args, **_kwargs):
            pass

        def catch_up(self):
            events.append("catch_up")
            return 0

        def handle_change(self, _change):
            return 0

    class FakeWatcher:
        def __init__(self, *_args):
            pass

        def start(self):
            events.append("watcher.start")

        def stop(self):
            events.append("watcher.stop")

        def watch_roots(self):
            return []

    class FakeReconciler:
        def __init__(self, *_args, **_kwargs):
            pass

        def scan_once(self):
            events.append("reconciler.scan_once")

        def start(self):
            events.append("reconciler.start")

        def stop(self):
            events.append("reconciler.stop")

    monkeypatch.setattr(module.core, "SeenStore", FakeStore)
    monkeypatch.setattr(module, "RealtimeCapture", FakeDaemon)
    monkeypatch.setattr(module, "WatchdogSource", FakeWatcher)
    monkeypatch.setattr(module, "PollingReconciler", FakeReconciler)
    monkeypatch.setattr(module, "_write_pid_file", lambda: None)
    monkeypatch.setattr(module, "_remove_pid_file", lambda: None)
    monkeypatch.setattr(
        module.time, "sleep", lambda _seconds: (_ for _ in ()).throw(
            KeyboardInterrupt
        )
    )

    assert module.main() == 0
    assert events.index("catch_up") < events.index("reconciler.scan_once")
    assert events.index("reconciler.scan_once") < events.index("reconciler.start")

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
