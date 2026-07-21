"""Control command dispatch for the daemon.

`ShadowControlDispatcher` is the dispatcher used while the daemon runs in
shadow ownership. It honours only read commands (`ping`, `status`); every
mutation is refused, because shadow must never act (spec Anexo D.4). The
managed dispatcher — which actually starts and stops services — lands in
D008 fatia 2 and is gated by the ownership state, not by this class.
"""
from __future__ import annotations

import json
from pathlib import Path

from hive_mind.daemon.control import ControlRequest, ControlResponse

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
