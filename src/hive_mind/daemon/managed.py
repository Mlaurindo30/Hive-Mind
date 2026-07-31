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
from datetime import datetime, timezone
from pathlib import Path

from hive_mind.daemon.manifest import RuntimeManifest, ServiceSpec

MANAGED_STATE_FILENAME = "services.managed.json"
_STOP_GRACE_SECONDS = 10
_STATE_REFRESH_SECONDS = 60


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
        self._started_at = datetime.now(timezone.utc)
        self._last_persist_at = time.monotonic()

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

    def _resolve_working_directory(self, spec: ServiceSpec) -> Path | None:
        if not spec.working_directory:
            return None
        return Path(spec.working_directory).resolve()

    def _canonicalize_command(self, spec: ServiceSpec) -> list[str]:
        command = list(spec.command)
        if not command:
            return command
        executable = command[0]
        if executable not in {"python", "python3", "hive-mind", "hive-mindd"}:
            return command

        cwd = self._resolve_working_directory(spec) or Path.cwd()
        venv_dir = cwd / ".venv"
        if sys.platform == "win32":
            bin_dir = venv_dir / "Scripts"
            replacements = {
                "python": bin_dir / "python.exe",
                "python3": bin_dir / "python.exe",
                "hive-mind": bin_dir / "hive-mind.exe",
                "hive-mindd": bin_dir / "hive-mindd.exe",
            }
        else:
            bin_dir = venv_dir / "bin"
            replacements = {
                "python": bin_dir / "python",
                "python3": bin_dir / "python3",
                "hive-mind": bin_dir / "hive-mind",
                "hive-mindd": bin_dir / "hive-mindd",
            }
        candidate = replacements[executable]
        if sys.platform == "win32" and executable in {"python", "python3"}:
            command[0] = str(candidate)
            return command
        if candidate.exists():
            command[0] = str(candidate)
        return command

    def _spawn(self, managed: _Managed) -> None:
        spec = managed.spec
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        cwd = self._resolve_working_directory(spec)
        environment = {
            "CLAUDE_MEM_DB": str(Path.home() / ".claude-mem" / "claude-mem.db"),
            **os.environ,
            **spec.env,
        }
        managed.process = subprocess.Popen(  # noqa: S603 - commands come from the trusted manifest
            self._canonicalize_command(spec),
            cwd=str(cwd) if cwd is not None else None,
            env=environment,
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
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
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
        if policy == "on-failure":
            process = managed.process
            return process is not None and process.returncode not in (None, 0)
        return policy == "always"

    def _restart_delay_seconds(self, managed: _Managed) -> int:
        """Return the delay for the next restart, capped exponentially."""
        base_delay = managed.spec.restart_delay_seconds
        maximum = managed.spec.restart_max_delay_seconds
        return min(base_delay * (2 ** managed.restarts), maximum)

    def _needs_state_refresh(self, *, now: float | None = None) -> bool:
        return (now if now is not None else time.monotonic()) - self._last_persist_at >= _STATE_REFRESH_SECONDS

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
                    now = time.monotonic()
                    if managed.next_restart_at == 0.0:
                        managed.next_restart_at = now + self._restart_delay_seconds(managed)
                        self._persist()
                        continue
                    if now < managed.next_restart_at:
                        continue
                    managed.restarts += 1
                    managed.next_restart_at = 0.0
                    self._spawn(managed)
                    self._persist()
                if self._needs_state_refresh():
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
            return {
                "mode": "managed",
                "profile": self.manifest.profile,
                "supervisor_pid": os.getpid(),
                "started_at": self._started_at.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "services": services,
            }

    def _persist(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        target = self.state_dir / MANAGED_STATE_FILENAME
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.status(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, target)
        self._last_persist_at = time.monotonic()
