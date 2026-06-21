from __future__ import annotations

import os
import time
from pathlib import Path

import importlib.util


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "capture" / "capture-realtime.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("capture_realtime", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_dir_has_recent_source_when_directory_mtime_is_stale(tmp_path: Path) -> None:
    mod = _load_module()
    session_dir = tmp_path / "sessions" / "2026" / "06" / "20"
    session_dir.mkdir(parents=True)
    transcript = session_dir / "rollout-real.jsonl"
    transcript.write_text("{}\n")

    now = time.time()
    stale = now - 4 * 3600
    recent = now - 30
    os.utime(session_dir, (stale, stale))
    os.utime(transcript, (recent, recent))

    assert session_dir.stat().st_mtime < now - 2 * 3600
    assert mod._dir_has_recent_source(str(session_dir), now - 2 * 3600)
