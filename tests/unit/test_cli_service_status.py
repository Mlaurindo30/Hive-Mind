"""D007 (fatia 3) — `hive-mind service status` reads the shadow state.

A read-only CLI view of what the daemon observed, without curl. Reads
`state_dir/services.shadow.json`; never starts, stops or mutates anything.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hive_mind.cli import main


def _write_state(state_dir: Path, ready: bool = True) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "services.shadow.json").write_text(
        json.dumps(
            {
                "mode": "shadow",
                "profile": "local-min",
                "service_count": 2,
                "ready": ready,
                "services": [
                    {"name": "db", "ownership": "legacy", "required": True,
                     "readiness": "ready" if ready else "not_ready",
                     "startup_order": 10, "dependencies": []},
                    {"name": "api", "ownership": "legacy", "required": False,
                     "readiness": "ready", "startup_order": 20,
                     "dependencies": ["db"]},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_status_text_lists_services(tmp_path, capsys):
    _write_state(tmp_path)
    code = main(["service", "status", "--state-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "db" in out
    assert "api" in out
    assert "shadow" in out.lower()


def test_status_json_is_machine_readable(tmp_path, capsys):
    _write_state(tmp_path, ready=False)
    code = main(["service", "status", "--state-dir", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["ready"] is False
    assert {s["name"] for s in payload["services"]} == {"db", "api"}


def test_status_without_state_reports_no_observation(tmp_path, capsys):
    code = main(["service", "status", "--state-dir", str(tmp_path)])
    err = capsys.readouterr().err
    # No shadow pass yet: clear message, non-zero, never a fake "healthy".
    assert code == 1
    assert "shadow" in err.lower() or "no" in err.lower()


def test_status_never_mutates_state_dir(tmp_path):
    _write_state(tmp_path)
    before = {p.name for p in tmp_path.iterdir()}
    main(["service", "status", "--state-dir", str(tmp_path)])
    after = {p.name for p in tmp_path.iterdir()}
    assert before == after
