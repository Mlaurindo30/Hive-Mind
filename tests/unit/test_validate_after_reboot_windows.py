"""Regression tests for the Windows post-reboot validator."""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hive_mind.validation.post_reboot_windows import validate_live_runtime


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "health" / "validate_after_reboot_windows.py"
SPEC = importlib.util.spec_from_file_location("validate_after_reboot_windows", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_main_fails_and_records_runtime_path_findings(tmp_path, monkeypatch):
    finding = {
        "source": "process:42:command_line",
        "value": r"D:\Hive-Mind-Archive\worker.py",
        "normalized_value": "d:/hive-mind-archive/worker.py",
        "reason": "forbidden_path_family",
        "matched": "hive-mind-archive",
    }
    class Runtime:
        status = "pass"
        checks = {"fresh_managed_state": True}
        failures = ()
        supervisor_pid = 100
        services = ("worker",)
        state_path = str(tmp_path / ".hive-mind" / "state" / "services.managed.json")

    monkeypatch.setattr(MODULE, "validate_live_runtime", lambda _root: Runtime())
    monkeypatch.setattr(MODULE, "audit_runtime_paths", lambda _root: [finding])

    assert MODULE.main(tmp_path) == 1
    report = json.loads((tmp_path / "logs" / "post-reboot-validation.json").read_text(encoding="utf-8"))
    assert report["checks"]["canonical_runtime_paths"] is False
    assert report["runtime_path_findings"] == [finding]
    assert report["status"] == "fail"


def test_post_reboot_waits_for_fresh_supervisor_state(monkeypatch, tmp_path):
    class Runtime:
        def __init__(self, status: str, failures: tuple[str, ...]):
            self.status = status
            self.failures = failures

    reports = [
        Runtime("fail", ("dead_supervisor", "dead_child:sinapse-claude-mem")),
        Runtime("pass", ()),
    ]
    sleeps: list[float] = []
    monkeypatch.setattr(MODULE, "validate_live_runtime", lambda _root: reports.pop(0))

    result = MODULE._validate_after_boot_converges(
        tmp_path,
        wait_seconds=5,
        poll_seconds=0.1,
        sleep=sleeps.append,
    )

    assert result.status == "pass"
    assert sleeps == [0.1]


def _write_managed_state(root: Path, payload: dict) -> None:
    state_dir = root / ".hive-mind" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "services.managed.json").write_text(json.dumps(payload), encoding="utf-8")


def _fresh_state(**overrides: object) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    state: dict = {
        "mode": "managed",
        "supervisor_pid": 100,
        "started_at": now,
        "updated_at": now,
        "services": {
            "sqlite-vec-worker": {
                "pid": 101,
                "state": "running",
                "required": True,
                "readiness": "ready",
            }
        },
    }
    state.update(overrides)
    return state


def _processes() -> dict[int, int | None]:
    return {100: 1, 101: 100}


def test_validate_live_runtime_accepts_fresh_owned_ready_state(tmp_path):
    _write_managed_state(tmp_path, _fresh_state())

    report = validate_live_runtime(tmp_path, process_parents=_processes())

    assert report.status == "pass"
    assert report.checks["fresh_managed_state"] is True
    assert report.checks["managed_children_owned"] is True


def test_validate_live_runtime_rejects_stale_state(tmp_path):
    state = _fresh_state(updated_at=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat())
    _write_managed_state(tmp_path, state)

    report = validate_live_runtime(tmp_path, process_parents=_processes(), max_age_seconds=60)

    assert report.status == "fail"
    assert "stale_managed_state" in report.failures


def test_validate_live_runtime_rejects_dead_supervisor_pid_mismatch_dead_and_orphan_children(tmp_path):
    cases = [
        ({101: 100}, "dead_supervisor"),
        ({100: 1, 101: 99}, "orphan_child:sqlite-vec-worker"),
        ({100: 1}, "dead_child:sqlite-vec-worker"),
    ]
    for index, (process_parents, expected_failure) in enumerate(cases):
        root = tmp_path / str(index)
        _write_managed_state(root, _fresh_state())

        report = validate_live_runtime(root, process_parents=process_parents)

        assert report.status == "fail"
        assert expected_failure in report.failures


def test_validate_live_runtime_rejects_unhealthy_required_service_and_missing_child_pid(tmp_path):
    state = _fresh_state(
        services={
            "sqlite-vec-worker": {
                "state": "running",
                "required": True,
                "readiness": "failed",
            }
        }
    )
    _write_managed_state(tmp_path, state)

    report = validate_live_runtime(tmp_path, process_parents={100: 1})

    assert report.status == "fail"
    assert "unhealthy_required_service:sqlite-vec-worker" in report.failures
    assert "missing_child_pid:sqlite-vec-worker" in report.failures


def test_validate_live_runtime_rejects_dead_or_orphan_nonrequired_child(tmp_path):
    state = _fresh_state(
        services={
            "sqlite-vec-worker": {
                "pid": 101,
                "state": "running",
                "required": True,
                "readiness": "ready",
            },
            "auxiliary": {
                "pid": 102,
                "state": "running",
                "required": False,
                "readiness": "ready",
            },
        }
    )
    _write_managed_state(tmp_path, state)

    report = validate_live_runtime(
        tmp_path,
        process_parents={100: 1, 101: 100, 102: 99},
    )

    assert report.status == "fail"
    assert "orphan_child:auxiliary" in report.failures


def test_validate_live_runtime_ignores_exited_nonrequired_service(tmp_path):
    state = _fresh_state(
        services={
            "sqlite-vec-worker": {
                "pid": 101,
                "state": "running",
                "required": True,
                "readiness": "ready",
            },
            "optional-api": {
                "pid": None,
                "state": "exited",
                "required": False,
            },
        }
    )
    _write_managed_state(tmp_path, state)

    report = validate_live_runtime(tmp_path, process_parents={100: 1, 101: 100})

    assert report.status == "pass"
    assert report.checks["managed_children_owned"] is True


def test_subprocess_fallbacks_are_hidden(monkeypatch):
    calls = []

    def runner(*args, **kwargs):
        calls.append(kwargs)
        class Result:
            returncode = 0
            stdout = "{}"
        return Result()

    monkeypatch.setattr(MODULE.subprocess, "run", runner)
    MODULE.task_exists("HiveMind-Supervisor")

    audit_spec = importlib.util.spec_from_file_location(
        "audit_runtime_paths_windows", ROOT / "scripts" / "health" / "audit_runtime_paths_windows.py"
    )
    audit_module = importlib.util.module_from_spec(audit_spec)
    assert audit_spec.loader is not None
    audit_spec.loader.exec_module(audit_module)
    monkeypatch.setattr(audit_module.os, "name", "nt")
    audit_module.collect_windows_snapshot(runner=runner)

    no_window = getattr(MODULE.subprocess, "CREATE_NO_WINDOW", 0)
    assert all(kwargs["creationflags"] == no_window for kwargs in calls)
