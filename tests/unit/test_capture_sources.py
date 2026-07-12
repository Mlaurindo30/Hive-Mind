from __future__ import annotations

import time
from pathlib import Path

from scripts.capture.capture_sources import (
    PollingReconciler,
    SourceChange,
    WatchdogSource,
    nearest_existing_ancestor,
)


def test_source_change_shape(tmp_path: Path):
    change = SourceChange("codex", tmp_path / "rollout.jsonl", 123.0)
    assert change.provider == "codex"
    assert change.path == tmp_path / "rollout.jsonl"
    assert change.detected_at == 123.0


def test_polling_detects_rewritten_transcript_once(tmp_path: Path):
    transcript = tmp_path / "transcript_full.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    changes = []
    source = PollingReconciler(
        {"antigravity": [str(transcript)]},
        lambda change: changes.append(change),
        interval=0,
    )
    source.scan_once()
    transcript.write_text('{"type":"USER_INPUT"}\n', encoding="utf-8")
    source.scan_once()
    source.scan_once()
    assert [(change.provider, change.path) for change in changes] == [
        ("antigravity", transcript)
    ]


def test_polling_detects_new_file_after_priming(tmp_path: Path):
    changes = []
    source = PollingReconciler(
        {"kimi": [str(tmp_path / "*" / "context.jsonl")]},
        lambda change: changes.append(change),
        interval=0,
    )
    source.scan_once()  # priming scan: nothing exists yet
    session = tmp_path / "sess-1"
    session.mkdir()
    context = session / "context.jsonl"
    context.write_text("{}\n", encoding="utf-8")
    source.scan_once()
    source.scan_once()
    assert [(change.provider, change.path) for change in changes] == [
        ("kimi", context)
    ]


def test_nearest_existing_ancestor_resolves_non_glob_dir(tmp_path: Path):
    base = tmp_path / "sessions"
    base.mkdir()
    pattern = str(base / "*" / "*" / "rollout-*.jsonl")
    assert nearest_existing_ancestor(pattern) == base

    missing = str(tmp_path / "missing" / "*" / "x.jsonl")
    assert nearest_existing_ancestor(missing) == tmp_path


def test_watchdog_coalesces_burst_into_single_change(tmp_path: Path):
    changes = []
    source = WatchdogSource(
        {"antigravity": [str(tmp_path)]},
        lambda change: changes.append(change),
        coalesce_seconds=0.2,
    )
    path = tmp_path / "transcript_full.jsonl"
    source.record(("antigravity",), path)
    source.record(("antigravity",), path)
    source.record(("antigravity",), path)
    deadline = time.time() + 5
    while not changes and time.time() < deadline:
        time.sleep(0.05)
    time.sleep(0.5)  # settle: no second flush may appear
    source.stop()
    assert [(change.provider, change.path) for change in changes] == [
        ("antigravity", path)
    ]


def test_watchdog_observer_detects_real_writes(tmp_path: Path):
    changes = []
    source = WatchdogSource(
        {"kimi": [str(tmp_path / "*" / "context.jsonl")]},
        lambda change: changes.append(change),
        coalesce_seconds=0.1,
    )
    source.start()
    try:
        time.sleep(0.5)  # let the observer arm its watches
        session = tmp_path / "sess-1"
        session.mkdir()
        (session / "context.jsonl").write_text("{}\n", encoding="utf-8")
        deadline = time.time() + 10
        while not changes and time.time() < deadline:
            time.sleep(0.05)
    finally:
        source.stop()
    assert changes, "watchdog observer reported no changes"
    assert {change.provider for change in changes} == {"kimi"}
