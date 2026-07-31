"""D007 (fatia 3) — `hive-mind service status` reads the daemon state.

A read-only CLI view of what the daemon observed, without curl. Reads
the best available state file in `state_dir`; never starts, stops or mutates
anything.
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


def test_status_prefers_managed_state_when_both_exist(tmp_path, capsys):
    _write_state(tmp_path)
    (tmp_path / "services.managed.json").write_text(
        json.dumps(
            {
                "mode": "managed",
                "profile": "local-min",
                "ready": True,
                "services": {
                    "db": {"state": "running", "ownership": "managed", "required": True},
                },
            }
        ),
        encoding="utf-8",
    )
    code = main(["service", "status", "--state-dir", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["mode"] == "managed"


def test_status_uses_live_managed_control_state_when_available(
    tmp_path, capsys, monkeypatch
):
    _write_state(tmp_path)
    (tmp_path / "services.managed.json").write_text(
        json.dumps(
            {
                "mode": "managed",
                "profile": "local-min",
                "services": {
                    "api": {"state": "exited", "ownership": "managed", "required": True},
                },
            }
        ),
        encoding="utf-8",
    )

    class _FakeResponse:
        ok = True
        data = {
            "mode": "managed",
            "profile": "local-min",
            "services": {
                "api": {"state": "running", "ownership": "managed", "required": True},
            },
        }

    class _FakeClient:
        def __init__(self, state_dir):
            self.state_dir = state_dir

        def request(self, request, timeout):
            assert request.command == "status"
            assert timeout == 3.0
            return _FakeResponse()

    import hive_mind.daemon.control as control_mod

    monkeypatch.setattr(control_mod, "ControlClient", _FakeClient)

    code = main(["service", "status", "--state-dir", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["services"]["api"]["state"] == "running"


def test_status_falls_back_to_legacy_supervisor_state(tmp_path, capsys):
    root = tmp_path
    state_dir = root / ".hive-mind" / "state"
    legacy_dir = root / "logs" / "supervisor"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "manifest.json").write_text(
        json.dumps(
            {
                "services": [
                    {"name": "sinapse-api", "required": True},
                    {"name": "sinapse-mcp-http", "required": False},
                ]
            }
        ),
        encoding="utf-8",
    )
    (legacy_dir / "state.json").write_text(
        json.dumps(
            {
                "sinapse-api": {
                    "state": "healthy",
                    "updated_at": "2026-07-28T00:00:00Z",
                    "pid": 1234,
                },
                "sinapse-mcp-http": {
                    "state": "healthy",
                    "updated_at": "2026-07-28T00:00:01Z",
                    "pid": 5678,
                },
            }
        ),
        encoding="utf-8",
    )

    code = main(["service", "status", "--state-dir", str(state_dir), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["mode"] == "legacy-supervisor"
    assert payload["services"]["sinapse-api"]["state"] == "running"
    assert payload["services"]["sinapse-api"]["required"] is True
    assert payload["services"]["sinapse-mcp-http"]["required"] is False


def test_status_prefers_legacy_state_when_managed_file_is_stale_and_no_control(
    tmp_path, capsys
):
    root = tmp_path
    state_dir = root / ".hive-mind" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "services.managed.json").write_text(
        json.dumps(
            {
                "mode": "managed",
                "profile": "local-min",
                "services": {
                    "sinapse-api": {
                        "state": "exited",
                        "ownership": "managed",
                        "required": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    legacy_dir = root / "logs" / "supervisor"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "manifest.json").write_text(
        json.dumps({"services": [{"name": "sinapse-api", "required": True}]}),
        encoding="utf-8",
    )
    (legacy_dir / "state.json").write_text(
        json.dumps(
            {
                "sinapse-api": {
                    "state": "healthy",
                    "updated_at": "2026-07-28T00:00:00Z",
                    "pid": 1234,
                }
            }
        ),
        encoding="utf-8",
    )

    code = main(["service", "status", "--state-dir", str(state_dir), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["mode"] == "legacy-supervisor"
    assert payload["services"]["sinapse-api"]["state"] == "running"
