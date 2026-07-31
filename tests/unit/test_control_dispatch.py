from __future__ import annotations

import json

from hive_mind.daemon.control import ControlRequest
from hive_mind.daemon.control_dispatch import ManagedControlDispatcher


class _SupervisorStub:
    def status(self):
        return {
            "mode": "managed",
            "profile": "local-min",
            "services": {
                "api": {"state": "running", "ownership": "managed", "required": True},
            },
        }


def test_managed_dispatcher_status_uses_live_supervisor_state(tmp_path):
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

    dispatcher = ManagedControlDispatcher(_SupervisorStub(), tmp_path)
    response = dispatcher(ControlRequest(command="status"))

    assert response.ok is True
    assert response.data["services"]["api"]["state"] == "running"
