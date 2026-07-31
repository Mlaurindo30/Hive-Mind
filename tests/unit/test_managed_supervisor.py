"""D008 (fatia 2) — ManagedSupervisor starts and stops real processes.

Proven with synthetic services (a trivial Python process), never a cutover
on the active runtime. The supervisor owns the process lifecycle: start in
dependency/startup order, track PIDs, stop cleanly, report status.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from hive_mind.daemon.manifest import RuntimeManifest
from hive_mind.daemon.managed import ManagedSupervisor

# A synthetic service: a python process that idles until killed.
IDLE = [sys.executable, "-c", "import time\nwhile True: time.sleep(0.2)"]
# A synthetic service that exits immediately (to exercise failure/restart).
QUICK_EXIT = [sys.executable, "-c", "raise SystemExit(0)"]


def _manifest(services) -> RuntimeManifest:
    return RuntimeManifest.model_validate(
        {"schema_version": 3, "profile": "local-min", "services": services}
    )


def _svc(name, command, order, **extra) -> dict:
    return {"name": name, "command": command, "startup_order": order, **extra}


def test_start_launches_the_process(tmp_path):
    manifest = _manifest([_svc("idle", IDLE, 1, restart_policy="never")])
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    try:
        sup.start_all()
        status = sup.status()
        assert status["services"]["idle"]["state"] == "running"
        assert status["services"]["idle"]["pid"] > 0
    finally:
        sup.stop_all()


def test_stop_terminates_the_process(tmp_path):
    manifest = _manifest([_svc("idle", IDLE, 1, restart_policy="never")])
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    sup.start_all()
    pid = sup.status()["services"]["idle"]["pid"]
    sup.stop_all()
    assert sup.status()["services"]["idle"]["state"] == "stopped"
    # The PID is really gone.
    assert not _pid_alive(pid)


def test_services_start_in_startup_order(tmp_path):
    manifest = _manifest(
        [
            _svc("second", IDLE, 20, restart_policy="never"),
            _svc("first", IDLE, 10, restart_policy="never"),
        ]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    try:
        order = sup.start_all()
        assert order == ["first", "second"]
    finally:
        sup.stop_all()


def test_dependency_is_started_before_dependent(tmp_path):
    manifest = _manifest(
        [
            _svc("api", IDLE, 5, dependencies=["db"], restart_policy="never"),
            _svc("db", IDLE, 10, restart_policy="never"),
        ]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    try:
        order = sup.start_all()
        assert order.index("db") < order.index("api")
    finally:
        sup.stop_all()


def test_start_one_and_stop_one(tmp_path):
    manifest = _manifest([_svc("idle", IDLE, 1, restart_policy="never")])
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    try:
        sup.start("idle")
        assert sup.status()["services"]["idle"]["state"] == "running"
        sup.stop("idle")
        assert sup.status()["services"]["idle"]["state"] == "stopped"
    finally:
        sup.stop_all()


def test_stop_all_is_idempotent(tmp_path):
    manifest = _manifest([_svc("idle", IDLE, 1, restart_policy="never")])
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    sup.start_all()
    sup.stop_all()
    sup.stop_all()  # must not raise
    assert sup.status()["services"]["idle"]["state"] == "stopped"


def test_managed_state_is_persisted_separately_from_shadow(tmp_path):
    manifest = _manifest([_svc("idle", IDLE, 1, restart_policy="never")])
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    try:
        sup.start_all()
        assert (tmp_path / "services.managed.json").exists()
        # Shadow state is a different file; managed must not write to it.
        assert not (tmp_path / "services.shadow.json").exists()
    finally:
        sup.stop_all()


def test_start_unknown_service_raises(tmp_path):
    manifest = _manifest([_svc("idle", IDLE, 1, restart_policy="never")])
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    with pytest.raises(KeyError):
        sup.start("nonexistent")


def test_generic_python_command_is_canonicalized_to_project_venv(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    scripts_dir = project_root / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    python_name = "python.exe" if sys.platform == "win32" else "python"
    canonical_python = scripts_dir / python_name
    scripts_dir.mkdir(parents=True)
    canonical_python.write_text("")

    calls = {}

    class DummyProcess:
        pid = 12345

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

    def fake_popen(command, cwd=None, env=None, creationflags=0, **kwargs):
        calls["command"] = command
        calls["cwd"] = cwd
        calls["env"] = env
        calls["creationflags"] = creationflags
        return DummyProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    manifest = _manifest(
        [
            _svc(
                "capture",
                ["python", "-m", "hive_mind.services.capture_realtime"],
                1,
                working_directory=str(project_root),
                restart_policy="never",
            )
        ]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path / "state")
    sup.start_all()

    assert calls["command"][0] == str(canonical_python)
    assert calls["cwd"] == str(project_root.resolve())
    if sys.platform == "win32":
        assert calls["creationflags"] == (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )


@pytest.mark.parametrize("command_name", ["python", "python3"])
def test_generic_windows_python_never_resolves_to_pythonw(tmp_path, monkeypatch, command_name):
    project_root = tmp_path / "project"
    scripts_dir = project_root / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    python = scripts_dir / "python.exe"
    pythonw = scripts_dir / "pythonw.exe"
    python.write_text("")
    pythonw.write_text("")

    manifest = _manifest([
        _svc("capture", [command_name, "-m", "example"], 1,
             working_directory=str(project_root), restart_policy="never")
    ])
    supervisor = ManagedSupervisor(manifest, state_dir=tmp_path / "state")
    monkeypatch.setattr(sys, "platform", "win32")

    assert supervisor._canonicalize_command(manifest.services[0])[0] == str(python)


@pytest.mark.parametrize("command_name", ["python", "python3"])
def test_generic_windows_python_stays_project_local_when_venv_is_missing(
    tmp_path, monkeypatch, command_name
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    manifest = _manifest([
        _svc("capture", [command_name, "-m", "example"], 1,
             working_directory=str(project_root), restart_policy="never")
    ])
    supervisor = ManagedSupervisor(manifest, state_dir=tmp_path / "state")
    monkeypatch.setattr(sys, "platform", "win32")

    assert supervisor._canonicalize_command(manifest.services[0])[0] == str(
        project_root / ".venv" / "Scripts" / "python.exe"
    )


def test_managed_services_receive_the_portable_claude_mem_database_default(tmp_path, monkeypatch):
    captured = {}

    class DummyProcess:
        pid = 12345

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

    def fake_popen(command, cwd=None, env=None, creationflags=0, **kwargs):
        captured["env"] = env
        return DummyProcess()

    monkeypatch.delenv("CLAUDE_MEM_DB", raising=False)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0)
    )
    manifest = _manifest([_svc("vec", IDLE, 1, restart_policy="never")])
    supervisor = ManagedSupervisor(manifest, state_dir=tmp_path / "state")
    try:
        supervisor.start_all()
        assert captured["env"]["CLAUDE_MEM_DB"] == str(
            Path.home() / ".claude-mem" / "claude-mem.db"
        )
    finally:
        supervisor.stop_all()


def test_windows_stop_terminates_the_entire_service_tree_hidden(tmp_path, monkeypatch):
    calls = []

    class DummyProcess:
        pid = 4321

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: DummyProcess())
    monkeypatch.setattr(subprocess, "run", fake_run)
    manifest = _manifest([_svc("worker", IDLE, 1, restart_policy="never")])
    supervisor = ManagedSupervisor(manifest, state_dir=tmp_path / "state")
    supervisor.start_all()
    supervisor.stop_all()

    assert calls[0][0] == ["taskkill.exe", "/PID", "4321", "/T", "/F"]
    assert calls[0][1]["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_supervisor_refreshes_live_state_before_the_post_reboot_ttl_expires(tmp_path):
    manifest = _manifest([_svc("idle", IDLE, 1, restart_policy="never")])
    supervisor = ManagedSupervisor(manifest, state_dir=tmp_path / "state")
    supervisor._last_persist_at = 0.0

    assert supervisor._needs_state_refresh(now=60.0) is True
    assert supervisor._needs_state_refresh(now=59.0) is False


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return exit_code.value == 259  # STILL_ACTIVE
    try:
        import os

        os.kill(pid, 0)
        return True
    except OSError:
        return False
