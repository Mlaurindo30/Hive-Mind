"""Control command dispatch for the daemon."""
from __future__ import annotations

import json
from pathlib import Path

from hive_mind.daemon.control import ControlRequest, ControlResponse
from hive_mind.daemon.managed import ManagedSupervisor
from hive_mind.daemon.state import read_state

_MUTATIONS = {"start", "stop", "restart", "reload", "run-job"}
SHADOW_STATE_FILENAME = "services.shadow.json"


class ShadowControlDispatcher:
    def __init__(self, state_dir: Path | str) -> None:
        self.state_dir = Path(state_dir)

    def __call__(self, request: ControlRequest) -> ControlResponse:
        command = request.command
        if command == "ping":
            return ControlResponse(ok=True, data={"pong": True})
        if command == "status":
            return self._status()
        if command in _MUTATIONS:
            return ControlResponse(
                ok=False,
                error=(
                    f"refused: '{command}' mutates services, but the daemon is in "
                    "shadow ownership and must not act (spec Anexo D.4). "
                    "Managed operations arrive in D008."
                ),
            )
        return ControlResponse(ok=False, error=f"unknown command: {command}")

    def _status(self) -> ControlResponse:
        state_file = self.state_dir / SHADOW_STATE_FILENAME
        if not state_file.exists():
            return ControlResponse(
                ok=False,
                error="no shadow observation yet; run `hive-mindd run --shadow`",
            )
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return ControlResponse(ok=False, error=f"cannot read shadow state: {exc}")
        return ControlResponse(ok=True, data=state)


class ManagedControlDispatcher:
    def __init__(self, supervisor: ManagedSupervisor, state_dir: Path | str) -> None:
        self.supervisor = supervisor
        self.state_dir = Path(state_dir)

    def __call__(self, request: ControlRequest) -> ControlResponse:
        command = request.command
        args = request.args or {}
        if command == "ping":
            return ControlResponse(ok=True, data={"pong": True})
        if command == "status":
            return self._status()
        if command == "start":
            return self._start(args)
        if command == "stop":
            return self._stop(args)
        if command == "restart":
            return self._restart(args)
        if command == "reload":
            return self._status()
        if command == "run-job":
            return ControlResponse(ok=False, error="run-job not implemented in managed mode")
        return ControlResponse(ok=False, error=f"unknown command: {command}")

    def _status(self) -> ControlResponse:
        return ControlResponse(ok=True, data=self.supervisor.status())

    def _start(self, args: dict) -> ControlResponse:
        name = args.get("name")
        if name:
            self.supervisor.start(str(name))
        else:
            self.supervisor.start_all()
        return self._status()

    def _stop(self, args: dict) -> ControlResponse:
        name = args.get("name")
        if name:
            self.supervisor.stop(str(name))
        else:
            self.supervisor.stop_all()
        return self._status()

    def _restart(self, args: dict) -> ControlResponse:
        name = args.get("name")
        if name:
            self.supervisor.stop(str(name))
            self.supervisor.start(str(name))
        else:
            self.supervisor.stop_all()
            self.supervisor.start_all()
        return self._status()
