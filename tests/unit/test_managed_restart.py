"""D008 (fatia 3) — restart policy monitor.

The managed supervisor watches its processes and, per each service's
restart_policy, restarts one that exits. Proven with synthetic services:
a process that exits quickly is restarted under `on-failure`/`always`, and
left alone under `never`. A restart_limit caps the attempts.
"""
from __future__ import annotations

import sys
import time

import pytest

from hive_mind.daemon.manifest import RuntimeManifest
from hive_mind.daemon.managed import ManagedSupervisor

# Exits immediately with a failure code.
FAIL_FAST = [sys.executable, "-c", "raise SystemExit(1)"]
SUCCESS_FAST = [sys.executable, "-c", "raise SystemExit(0)"]
# Idles until killed.
IDLE = [sys.executable, "-c", "import time\nwhile True: time.sleep(0.1)"]


def _manifest(services) -> RuntimeManifest:
    return RuntimeManifest.model_validate(
        {"schema_version": 3, "profile": "local-min", "services": services}
    )


def _svc(name, command, order, **extra) -> dict:
    return {"name": name, "command": command, "startup_order": order, **extra}


def _wait_for(predicate, timeout=6.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_on_failure_service_is_restarted(tmp_path):
    manifest = _manifest(
        [_svc("flaky", FAIL_FAST, 1, restart_policy="on-failure",
              restart_delay_seconds=0, restart_limit=5)]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    sup.start_all()
    sup.start_monitor(poll_interval=0.1)
    try:
        # It exits immediately; the monitor must restart it at least once.
        assert _wait_for(lambda: sup.restart_count("flaky") >= 1)
    finally:
        sup.stop_monitor()
        sup.stop_all()


def test_never_policy_is_not_restarted(tmp_path):
    manifest = _manifest(
        [_svc("oneshot", FAIL_FAST, 1, restart_policy="never")]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    sup.start_all()
    sup.start_monitor(poll_interval=0.1)
    try:
        time.sleep(1.0)
        assert sup.restart_count("oneshot") == 0
        assert sup.status()["services"]["oneshot"]["state"] in {"exited", "stopped"}
    finally:
        sup.stop_monitor()
        sup.stop_all()


def test_on_failure_does_not_restart_a_clean_exit(tmp_path):
    manifest = _manifest(
        [_svc("oneshot", SUCCESS_FAST, 1, restart_policy="on-failure",
              restart_delay_seconds=0, restart_limit=5)]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    sup.start_all()
    sup.start_monitor(poll_interval=0.05)
    try:
        time.sleep(0.4)
        assert sup.restart_count("oneshot") == 0
        assert sup.status()["services"]["oneshot"]["returncode"] == 0
    finally:
        sup.stop_monitor()
        sup.stop_all()


def test_restart_delay_uses_capped_exponential_backoff(tmp_path):
    manifest = _manifest(
        [_svc("flaky", FAIL_FAST, 1, restart_policy="always",
              restart_delay_seconds=2, restart_max_delay_seconds=5,
              restart_limit=5)]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    managed = sup._services["flaky"]

    assert sup._restart_delay_seconds(managed) == 2
    managed.restarts = 1
    assert sup._restart_delay_seconds(managed) == 4
    managed.restarts = 2
    assert sup._restart_delay_seconds(managed) == 5


def test_first_restart_waits_the_configured_initial_delay(tmp_path):
    manifest = _manifest(
        [_svc("flaky", FAIL_FAST, 1, restart_policy="always",
              restart_delay_seconds=1, restart_max_delay_seconds=5,
              restart_limit=5)]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    sup.start_all()
    sup.start_monitor(poll_interval=0.02)
    try:
        time.sleep(0.25)
        assert sup.restart_count("flaky") == 0
        assert _wait_for(lambda: sup.restart_count("flaky") >= 1, timeout=2.0)
    finally:
        sup.stop_monitor()
        sup.stop_all()


def test_restart_limit_caps_attempts(tmp_path):
    manifest = _manifest(
        [_svc("crashloop", FAIL_FAST, 1, restart_policy="always",
              restart_delay_seconds=0, restart_limit=3)]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    sup.start_all()
    sup.start_monitor(poll_interval=0.05)
    try:
        # Restarts should stop at the limit, not run away.
        assert _wait_for(lambda: sup.restart_count("crashloop") >= 3, timeout=6)
        time.sleep(0.8)
        assert sup.restart_count("crashloop") <= 3
    finally:
        sup.stop_monitor()
        sup.stop_all()


def test_healthy_service_is_not_restarted(tmp_path):
    manifest = _manifest(
        [_svc("stable", IDLE, 1, restart_policy="always",
              restart_delay_seconds=0, restart_limit=5)]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    sup.start_all()
    sup.start_monitor(poll_interval=0.1)
    try:
        time.sleep(1.0)
        assert sup.restart_count("stable") == 0
        assert sup.status()["services"]["stable"]["state"] == "running"
    finally:
        sup.stop_monitor()
        sup.stop_all()


def test_stop_monitor_is_idempotent(tmp_path):
    manifest = _manifest([_svc("idle", IDLE, 1, restart_policy="never")])
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    sup.start_all()
    sup.start_monitor(poll_interval=0.1)
    sup.stop_monitor()
    sup.stop_monitor()  # must not raise
    sup.stop_all()


def test_intentional_stop_does_not_trigger_restart(tmp_path):
    """Stopping a service must not be seen as a crash by the monitor."""
    manifest = _manifest(
        [_svc("svc", IDLE, 1, restart_policy="always",
              restart_delay_seconds=0, restart_limit=5)]
    )
    sup = ManagedSupervisor(manifest, state_dir=tmp_path)
    sup.start_all()
    sup.start_monitor(poll_interval=0.1)
    try:
        sup.stop("svc")
        time.sleep(0.8)
        assert sup.restart_count("svc") == 0
        assert sup.status()["services"]["svc"]["state"] == "stopped"
    finally:
        sup.stop_monitor()
        sup.stop_all()
