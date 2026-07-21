"""D008 (fatia 2) — ManagedSupervisor starts and stops real processes.

Proven with synthetic services (a trivial Python process), never a cutover
on the active runtime. The supervisor owns the process lifecycle: start in
dependency/startup order, track PIDs, stop cleanly, report status.
"""
from __future__ import annotations

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
