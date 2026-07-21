"""Managed supervisor (spec F4): owns the service process lifecycle.

Starts and stops real processes declared in the manifest, in dependency and
startup order, tracks their PIDs, and persists managed state separately from
shadow state (`services.managed.json`, never `services.shadow.json`).

This is the mechanism the cutover (F4/D010) uses to move a service from
`legacy`/`shadow` to `managed`. It is exercised with synthetic services in
tests; a cutover on the active runtime is a separate, human-gated step.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from hive_mind.daemon.manifest import RuntimeManifest, ServiceSpec

MANAGED_STATE_FILENAME = "services.managed.json"
_STOP_GRACE_SECONDS = 10


class _Managed:
    __slots__ = ("spec", "process", "state", "restarts", "intentional_stop", "next_restart_at")

    def __init__(self, spec: ServiceSpec) -> None:
        self.spec = spec
        self.process: subprocess.Popen | None = None
        self.state = "stopped"
        self.restarts = 0
        self.intentional_stop = False
        self.next_restart_at = 0.0


class ManagedSupervisor:
    """Starts/stops real service processes in dependency order."""

    def __init__(self, manifest: RuntimeManifest, state_dir: Path | str) -> None:
        self.manifest = manifest
        self.state_dir = Path(state_dir)
        self._services: dict[str, _Managed] = {
            s.name: _Managed(s) for s in manifest.services
        }
        self._lock = threading.RLock()
        self._monitor: threading.Thread | None = None
        self._monitor_stop = threading.Event()

    # -- ordering -----------------------------------------------------------
    def _startup_order(self) -> list[str]:
        """Topological order honouring dependencies, tie-broken by
        startup_order then name."""
        specs = {name: m.spec for name, m in self._services.items()}
        ordered: list[str] = []
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in ordered or name not in specs:
                return
            if name in visiting:
                raise ValueError(f"dependency cycle involving {name!r}")
            visiting.add(name)
            for dep in sorted(specs[name].dependencies):
                visit(dep)
            visiting.discard(name)
            ordered.append(name)

        for name in sorted(specs, key=lambda n: (specs[n].startup_order, n)):
            visit(name)
        return ordered

    # -- lifecycle ----------------------------------------------------------
    def start(self, name: str) -> None:
        if name not in self._services:
            raise KeyError(name)
        with self._lock:
            managed = self._services[name]
            if managed.process is not None and managed.process.poll() is None:
                return  # already running
            managed.intentional_stop = False
            self._spawn(managed)
            self._persist()

    def _spawn(self, managed: _Managed) -> None:
        spec = managed.spec
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        managed.process = subprocess.Popen(  # noqa: S603 - commands come from the trusted manifest
            spec.command,
            cwd=spec.working_directory or None,
            env={**os.environ, **spec.env},
            creationflags=creationflags,
        )
        managed.state = "running"

    def start_all(self) -> list[str]:
        order = self._startup_order()
        for name in order:
            self.start(name)
        return order

    def stop(self, name: str) -> None:
        if name not in self._services:
            raise KeyError(name)
        with self._lock:
            managed = self._services[name]
            managed.intentional_stop = True  # tell the monitor this is not a crash
            proc = managed.process
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=_STOP_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=_STOP_GRACE_SECONDS)
            managed.process = None
            managed.state = "stopped"
            self._persist()

    def stop_all(self) -> None:
        # Stop in reverse startup order so dependents die before dependencies.
        for name in reversed(self._startup_order()):
            self.stop(name)

    # -- restart monitor ----------------------------------------------------
    def start_monitor(self, poll_interval: float = 1.0) -> None:
        """Watch managed processes and restart per restart_policy."""
        if self._monitor is not None:
            return
        self._monitor_stop.clear()
        self._monitor = threading.Thread(
            target=self._monitor_loop, args=(poll_interval,), daemon=True
        )
        self._monitor.start()

    def stop_monitor(self) -> None:
        if self._monitor is None:
            return
        self._monitor_stop.set()
        self._monitor.join(timeout=_STOP_GRACE_SECONDS)
        self._monitor = None

    def restart_count(self, name: str) -> int:
        return self._services[name].restarts

    def _should_restart(self, managed: _Managed) -> bool:
        policy = managed.spec.restart_policy
        if managed.intentional_stop or policy == "never":
            return False
        if managed.restarts >= managed.spec.restart_limit:
            return False
        return policy in ("always", "on-failure")

    def _monitor_loop(self, poll_interval: float) -> None:
        while not self._monitor_stop.is_set():
            with self._lock:
                for managed in self._services.values():
                    proc = managed.process
                    if proc is None or proc.poll() is None:
                        continue  # not started, or still alive
                    # The process exited on its own.
                    managed.state = "exited"
                    if not self._should_restart(managed):
                        continue
                    if time.monotonic() < managed.next_restart_at:
                        continue
                    managed.restarts += 1
                    managed.next_restart_at = (
                        time.monotonic() + managed.spec.restart_delay_seconds
                    )
                    self._spawn(managed)
                    self._persist()
            self._monitor_stop.wait(poll_interval)

    # -- introspection ------------------------------------------------------
    def status(self) -> dict:
        with self._lock:
            services = {}
            for name, managed in self._services.items():
                proc = managed.process
                alive = proc is not None and proc.poll() is None
                services[name] = {
                    "state": "running" if alive else ("stopped" if proc is None else "exited"),
                    "pid": proc.pid if alive else None,
                    "returncode": None if alive or proc is None else proc.returncode,
                    "ownership": "managed",
                    "required": managed.spec.required,
                    "restarts": managed.restarts,
                }
            return {"mode": "managed", "profile": self.manifest.profile, "services": services}

    def _persist(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        target = self.state_dir / MANAGED_STATE_FILENAME
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.status(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, target)
