from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hive_mind.maintenance import windows_runtime


def _result(*args: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout="", stderr="failed")


def test_registration_validates_gui_launchers_before_scheduler_calls(tmp_path, monkeypatch):
    calls: list[tuple[str, ...]] = []

    def invalid_gui_launchers(root):
        raise RuntimeError("GUI launcher must use PE Subsystem 2")

    monkeypatch.setattr(
        windows_runtime, "validate_gui_launchers", invalid_gui_launchers, raising=False
    )
    monkeypatch.setattr(
        windows_runtime,
        "_run_schtasks",
        lambda *args: calls.append(args) or _result(*args),
    )

    with pytest.raises(RuntimeError, match="PE Subsystem 2"):
        windows_runtime.register_windows_runtime(root=tmp_path, apply=True)

    assert calls == []


def test_failed_registration_restores_every_exported_task_xml(tmp_path, monkeypatch):
    prior = {
        "HiveMind-Supervisor": "<Task><old>supervisor</old></Task>",
        "HiveMind-PostRebootValidation": "<Task><old>post-reboot</old></Task>",
    }
    creates: list[tuple[str, str]] = []

    monkeypatch.setattr(
        windows_runtime, "validate_gui_launchers", lambda root: (), raising=False
    )
    monkeypatch.setattr(windows_runtime, "_task_query_xml", lambda name: prior[name])

    def fake_schtasks(*args: str):
        if args[:1] != ("/create",):
            return _result(*args)
        task_name = args[args.index("/tn") + 1]
        xml_path = Path(args[args.index("/xml") + 1])
        creates.append((task_name, xml_path.read_text(encoding="utf-16")))
        replacement_count = sum(1 for _, xml in creates if "<old>" not in xml)
        if task_name == "HiveMind-PostRebootValidation" and replacement_count == 2:
            return _result(*args, returncode=1)
        return _result(*args)

    monkeypatch.setattr(windows_runtime, "_run_schtasks", fake_schtasks)

    with pytest.raises(RuntimeError, match="HiveMind-PostRebootValidation"):
        windows_runtime.register_windows_runtime(root=tmp_path, apply=True)

    restored = {name: xml for name, xml in creates if "<old>" in xml}
    assert restored == prior


def test_successful_registration_keeps_task_xml_rollback_exports(tmp_path, monkeypatch):
    prior = {
        "HiveMind-Supervisor": "<Task><old>supervisor</old></Task>",
        "HiveMind-PostRebootValidation": "<Task><old>post-reboot</old></Task>",
    }

    monkeypatch.setattr(
        windows_runtime, "validate_gui_launchers", lambda root: (), raising=False
    )
    monkeypatch.setattr(windows_runtime, "_task_query_xml", lambda name: prior[name])
    monkeypatch.setattr(windows_runtime, "_run_schtasks", lambda *args: _result(*args))

    windows_runtime.register_windows_runtime(root=tmp_path, apply=True)

    exports = list(
        (tmp_path / ".hive-mind" / "backups" / "windows-runtime").rglob("*.backup.xml")
    )
    assert {path.name for path in exports} == {
        "HiveMind-Supervisor.backup.xml",
        "HiveMind-PostRebootValidation.backup.xml",
    }
    assert {path.read_text(encoding="utf-16") for path in exports} == set(prior.values())


def test_failed_task_xml_export_aborts_before_any_task_replacement(tmp_path, monkeypatch):
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(
        windows_runtime, "validate_gui_launchers", lambda root: (), raising=False
    )

    def fake_schtasks(*args: str):
        calls.append(args)
        if args[:1] == ("/query",):
            return _result(*args, returncode=1)
        raise AssertionError(f"unexpected Scheduler mutation: {args}")

    monkeypatch.setattr(windows_runtime, "_run_schtasks", fake_schtasks)

    with pytest.raises(RuntimeError, match="export.*HiveMind-Supervisor"):
        windows_runtime.register_windows_runtime(root=tmp_path, apply=True)

    assert calls == [
        ("/query", "/tn", "HiveMind-Supervisor", "/xml", "ONE"),
    ]
