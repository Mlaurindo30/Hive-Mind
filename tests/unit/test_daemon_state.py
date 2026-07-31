from __future__ import annotations

import json
from datetime import datetime, timezone

from hive_mind.daemon.managed import ManagedSupervisor
from hive_mind.daemon.manifest import RuntimeManifest
from hive_mind.daemon.state import read_state


def test_read_state_prefers_managed_over_shadow(tmp_path):
    (tmp_path / "services.shadow.json").write_text(
        json.dumps({"mode": "shadow", "ready": False}), encoding="utf-8"
    )
    (tmp_path / "services.managed.json").write_text(
        json.dumps({"mode": "managed", "ready": True}), encoding="utf-8"
    )

    state = read_state(tmp_path)

    assert state is not None
    assert state["mode"] == "managed"


def test_read_state_falls_back_to_shadow(tmp_path):
    (tmp_path / "services.shadow.json").write_text(
        json.dumps({"mode": "shadow", "ready": True}), encoding="utf-8"
    )

    state = read_state(tmp_path)

    assert state is not None
    assert state["mode"] == "shadow"


def test_managed_supervisor_persists_its_identity_and_timestamps(tmp_path):
    supervisor = ManagedSupervisor(RuntimeManifest(profile="local-min", services=[]), tmp_path)

    supervisor._persist()

    state = json.loads((tmp_path / "services.managed.json").read_text(encoding="utf-8"))
    assert state["supervisor_pid"] > 0
    assert datetime.fromisoformat(state["started_at"]).tzinfo is not None
    assert datetime.fromisoformat(state["updated_at"]).tzinfo is not None
    assert datetime.fromisoformat(state["updated_at"]) >= datetime.fromisoformat(state["started_at"])
