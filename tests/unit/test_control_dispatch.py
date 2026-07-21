"""D008 (fatia 1) — the daemon's control dispatcher (read-only in shadow).

The dispatcher maps control commands to daemon actions. In shadow ownership
the only honoured commands are read (`ping`, `status`); every mutation
(`start`/`stop`/`restart`/`reload`/`run-job`) is refused, because shadow must
never act (spec Anexo D.4). Managed dispatch lands in D008 fatia 2.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hive_mind.daemon.control import ControlRequest
from hive_mind.daemon.control_dispatch import ShadowControlDispatcher


def _state(tmp_path: Path, ready: bool = True) -> Path:
    (tmp_path / "services.shadow.json").write_text(
        json.dumps(
            {"mode": "shadow", "profile": "local-min", "ready": ready,
             "service_count": 1,
             "services": [{"name": "db", "readiness": "ready" if ready else "not_ready"}]}
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_ping_is_ok(tmp_path):
    dispatch = ShadowControlDispatcher(state_dir=_state(tmp_path))
    resp = dispatch(ControlRequest(command="ping"))
    assert resp.ok is True
    assert resp.data.get("pong") is True


def test_status_returns_shadow_observation(tmp_path):
    dispatch = ShadowControlDispatcher(state_dir=_state(tmp_path))
    resp = dispatch(ControlRequest(command="status"))
    assert resp.ok is True
    assert resp.data["mode"] == "shadow"
    assert resp.data["services"][0]["name"] == "db"


@pytest.mark.parametrize("command", ["start", "stop", "restart", "reload", "run-job"])
def test_mutations_are_refused_in_shadow(tmp_path, command):
    dispatch = ShadowControlDispatcher(state_dir=_state(tmp_path))
    resp = dispatch(ControlRequest(command=command, args={"name": "db"}))
    assert resp.ok is False
    assert "shadow" in resp.error.lower()


def test_unknown_command_is_refused(tmp_path):
    dispatch = ShadowControlDispatcher(state_dir=_state(tmp_path))
    resp = dispatch(ControlRequest(command="frobnicate"))
    assert resp.ok is False
    assert "unknown" in resp.error.lower()


def test_status_without_observation_is_honest(tmp_path):
    dispatch = ShadowControlDispatcher(state_dir=tmp_path)  # no state file
    resp = dispatch(ControlRequest(command="status"))
    assert resp.ok is False
    assert "no shadow" in resp.error.lower() or "not" in resp.error.lower()


def test_shadow_refusal_travels_over_the_real_socket(tmp_path):
    """End-to-end: real transport + real shadow dispatcher, over the wire."""
    import threading

    from hive_mind.daemon.control import ControlClient, ControlServer

    _state(tmp_path)
    server = ControlServer(
        state_dir=tmp_path, dispatch=ShadowControlDispatcher(state_dir=tmp_path)
    )
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.wait_ready(timeout=5)
    try:
        client = ControlClient(state_dir=tmp_path)
        # A read command works...
        assert client.request(ControlRequest(command="status")).ok is True
        # ...a mutation is refused by the shadow policy, over the real socket.
        refused = client.request(ControlRequest(command="stop", args={"name": "db"}))
        assert refused.ok is False
        assert "shadow" in refused.error.lower()
    finally:
        server.shutdown()
        thread.join(timeout=5)
