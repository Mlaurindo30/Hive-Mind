"""Integração: MCP Streamable HTTP server (P7).

Testa scripts/services/sinapse-mcp-http.py com o cliente de teste do aiohttp.
Dois níveis:
  1. Transporte (com handle_request FAKE — determinístico): dispatch de
     request/notification/batch, sessão no initialize, GET→405, JSON ruim→400.
  2. Wiring real (sem fake): initialize e tools/list usam o handle_request real
     de sinapse-mcp.py — são puros (sem backend de rede), provando a integração.

A EXECUÇÃO de uma tool real (sinapse_query etc.) é responsabilidade do
handle_request compartilhado com o stdio, não desta camada HTTP.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("aiohttp")
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

_HTTP_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "services" / "sinapse-mcp-http.py"


def _load_http_module():
    spec = importlib.util.spec_from_file_location("sinapse_mcp_http", _HTTP_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeMCP:
    """handle_request determinístico — isola a camada de transporte."""
    TOOLS = [{"name": "fake_tool", "description": "x", "inputSchema": {}}]

    def handle_request(self, req):
        rid = req.get("id")
        method = req.get("method")
        if rid is None:
            return None  # notificação
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05"}}
        if method == "tools/call":
            return {"jsonrpc": "2.0", "id": rid, "result": {"echo": req.get("params")}}
        return {"jsonrpc": "2.0", "id": rid, "result": {"method": method}}


async def _client(monkeypatch, fake: bool) -> TestClient:
    mod = _load_http_module()
    if fake:
        monkeypatch.setattr(mod, "_MCP", _FakeMCP())
    client = TestClient(TestServer(mod.build_app()))
    await client.start_server()
    return client


# --------------------------------------------------------------------------
# Transporte (fake handle_request)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_initialize_sets_session_header(monkeypatch):
    c = await _client(monkeypatch, fake=True)
    try:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert r.status == 200
        assert r.headers.get("Mcp-Session-Id"), "initialize deve emitir Mcp-Session-Id"
        data = await r.json()
        assert data["result"]["protocolVersion"] == "2024-11-05"
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_tools_call_dispatch(monkeypatch):
    c = await _client(monkeypatch, fake=True)
    try:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                       "params": {"name": "fake_tool", "arguments": {"a": 1}}})
        assert r.status == 200
        data = await r.json()
        assert data["id"] == 7
        assert data["result"]["echo"] == {"name": "fake_tool", "arguments": {"a": 1}}
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_notification_returns_202(monkeypatch):
    c = await _client(monkeypatch, fake=True)
    try:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert r.status == 202
        assert (await r.text()) == ""
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_batch_returns_list_of_responses(monkeypatch):
    c = await _client(monkeypatch, fake=True)
    try:
        r = await c.post("/mcp", json=[
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            {"jsonrpc": "2.0", "method": "notifications/ping"},  # sem id → omitida
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        assert r.status == 200
        data = await r.json()
        assert isinstance(data, list) and len(data) == 2  # notificação não responde
        assert {d["id"] for d in data} == {1, 2}
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_get_mcp_405(monkeypatch):
    c = await _client(monkeypatch, fake=True)
    try:
        r = await c.get("/mcp")
        assert r.status == 405
        assert "POST" in r.headers.get("Allow", "")
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_bad_json_400(monkeypatch):
    c = await _client(monkeypatch, fake=True)
    try:
        r = await c.post("/mcp", data="{nao eh json")
        assert r.status == 400
        data = await r.json()
        assert data["error"]["code"] == -32700
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_delete_terminates_session(monkeypatch):
    c = await _client(monkeypatch, fake=True)
    try:
        init = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        sid = init.headers["Mcp-Session-Id"]
        r = await c.delete("/mcp", headers={"Mcp-Session-Id": sid})
        assert r.status == 200
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_health(monkeypatch):
    c = await _client(monkeypatch, fake=True)
    try:
        r = await c.get("/health")
        assert r.status == 200
        assert (await r.json())["status"] == "ok"
    finally:
        await c.close()


# --------------------------------------------------------------------------
# Wiring real (handle_request real — initialize e tools/list são puros)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_initialize_and_tools_list(monkeypatch):
    c = await _client(monkeypatch, fake=False)
    try:
        init = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init.status == 200
        assert init.headers.get("Mcp-Session-Id")

        tl = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert tl.status == 200
        tools = (await tl.json())["result"]["tools"]
        assert isinstance(tools, list) and len(tools) > 0
        names = {t["name"] for t in tools}
        assert "sinapse_query" in names  # tool canônica do protocolo Hive-Mind
    finally:
        await c.close()
