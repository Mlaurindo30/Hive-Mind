"""D008 (fatia 1) — authenticated control socket (spec §15.2, §15.3).

Mutations (start/stop/restart/reload/run-job) go through a local control
channel, never HTTP. The transport is a Windows named pipe or a POSIX Unix
socket; both are restricted to the local user. This suite exercises the
request/response protocol over the real transport with an in-process client.
"""
from __future__ import annotations

import json
import threading

import pytest

from hive_mind.daemon.control import (
    ControlServer,
    ControlClient,
    ControlRequest,
    ControlResponse,
)


class _Dispatcher:
    """Records commands and returns canned responses; never touches services."""

    def __init__(self) -> None:
        self.calls: list[ControlRequest] = []

    def __call__(self, request: ControlRequest) -> ControlResponse:
        self.calls.append(request)
        if request.command == "status":
            return ControlResponse(ok=True, data={"services": []})
        if request.command == "ping":
            return ControlResponse(ok=True, data={"pong": True})
        return ControlResponse(ok=False, error=f"unknown command: {request.command}")


@pytest.fixture
def server(tmp_path):
    dispatcher = _Dispatcher()
    srv = ControlServer(state_dir=tmp_path, dispatch=dispatcher)
    srv.start()
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    srv.wait_ready(timeout=5)
    yield srv, dispatcher
    srv.shutdown()
    thread.join(timeout=5)


def test_ping_roundtrips(server, tmp_path):
    srv, dispatcher = server
    client = ControlClient(state_dir=tmp_path)
    resp = client.request(ControlRequest(command="ping"))
    assert resp.ok is True
    assert resp.data == {"pong": True}
    assert [c.command for c in dispatcher.calls] == ["ping"]


def test_status_command_dispatches(server, tmp_path):
    srv, dispatcher = server
    client = ControlClient(state_dir=tmp_path)
    resp = client.request(ControlRequest(command="status"))
    assert resp.ok is True
    assert "services" in resp.data


def test_unknown_command_is_rejected_not_crashed(server, tmp_path):
    srv, dispatcher = server
    client = ControlClient(state_dir=tmp_path)
    resp = client.request(ControlRequest(command="frobnicate"))
    assert resp.ok is False
    assert "unknown command" in resp.error


def test_request_carries_arguments(server, tmp_path):
    srv, dispatcher = server
    client = ControlClient(state_dir=tmp_path)
    client.request(ControlRequest(command="status", args={"name": "db"}))
    assert dispatcher.calls[-1].args == {"name": "db"}


def test_request_response_are_json_serializable():
    req = ControlRequest(command="start", args={"name": "api"})
    back = ControlRequest.from_json(req.to_json())
    assert back.command == "start"
    assert back.args == {"name": "api"}

    resp = ControlResponse(ok=True, data={"x": 1})
    back_r = ControlResponse.from_json(resp.to_json())
    assert back_r.ok is True
    assert back_r.data == {"x": 1}


def test_client_without_server_fails_cleanly(tmp_path):
    client = ControlClient(state_dir=tmp_path)
    with pytest.raises(ConnectionError):
        client.request(ControlRequest(command="ping"))
