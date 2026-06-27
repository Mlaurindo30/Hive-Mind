"""Gap tests for MCP Streamable HTTP server (P7).

Coberturas adicionadas sobre test_mcp_http.py:
  - Concorrencia: N requests simultaneos (criterio de pronto P7)
  - Sessoes: unicidade de IDs e contagem via /health
  - DELETE verifica decremento via /health
  - DELETE com sessao desconhecida -> 200
  - Batch so de notificacoes -> 202
  - Batch vazio -> 400 / -32600
  - Body JSON que nao e dict nem list (int, string) -> 400 / -32600
  - Excecao em handle_request -> -32603 sem derrubar o server
  - Server sobrevive excecao e continua respondendo

Padroes:
  - TestClient(TestServer(mod.build_app())) com modulo fresco por teste
  - monkeypatch em mod._MCP para isolar a camada de transporte
  - _FakeErrorMCP para testar o caminho de excecao em _process_one
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("aiohttp")
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

_HTTP_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "services" / "sinapse-mcp-http.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_http_module():
    """Carrega um modulo fresco a cada chamada — _SESSIONS e _MCP zerados."""
    spec = importlib.util.spec_from_file_location("sinapse_mcp_http", _HTTP_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeMCP:
    """handle_request deterministico — isola a camada de transporte."""

    TOOLS = [{"name": "fake_tool", "description": "x", "inputSchema": {}}]

    def handle_request(self, req):
        rid = req.get("id")
        method = req.get("method")
        if rid is None:
            return None  # notificacao — sem resposta
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05"}}
        return {"jsonrpc": "2.0", "id": rid, "result": {"method": method}}


class _FakeErrorMCP:
    """handle_request que sempre levanta — testa o isolamento de excecao em _process_one."""

    def handle_request(self, req):
        raise RuntimeError("simulated internal error")


async def _client(monkeypatch, fake_cls=_FakeMCP) -> TestClient:
    mod = _load_http_module()
    monkeypatch.setattr(mod, "_MCP", fake_cls())
    client = TestClient(TestServer(mod.build_app()))
    await client.start_server()
    return client


# ---------------------------------------------------------------------------
# Sessoes: unicidade e contagem via /health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_two_initializes_produce_different_session_ids(monkeypatch):
    """should produce unique Mcp-Session-Id when initialize is called twice"""
    c = await _client(monkeypatch)
    try:
        r1 = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        r2 = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}})
        sid1 = r1.headers["Mcp-Session-Id"]
        sid2 = r2.headers["Mcp-Session-Id"]
        assert sid1 != sid2
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_health_sessions_starts_at_zero(monkeypatch):
    """should report sessions=0 when no initialize has been called"""
    c = await _client(monkeypatch)
    try:
        r = await c.get("/health")
        data = await r.json()
        assert data["sessions"] == 0
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_health_reflects_session_count_after_initialize(monkeypatch):
    """should increment sessions count in /health after each initialize"""
    c = await _client(monkeypatch)
    try:
        await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        h1 = await (await c.get("/health")).json()
        assert h1["sessions"] == 1

        await c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}})
        h2 = await (await c.get("/health")).json()
        assert h2["sessions"] == 2
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_delete_decrements_session_count_in_health(monkeypatch):
    """should decrement sessions in /health after DELETE /mcp with valid session"""
    c = await _client(monkeypatch)
    try:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        sid = r.headers["Mcp-Session-Id"]

        assert (await (await c.get("/health")).json())["sessions"] == 1

        await c.delete("/mcp", headers={"Mcp-Session-Id": sid})

        assert (await (await c.get("/health")).json())["sessions"] == 0
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_delete_unknown_session_returns_200(monkeypatch):
    """should return 200 when DELETE is called with an unknown session ID"""
    c = await _client(monkeypatch)
    try:
        r = await c.delete("/mcp", headers={"Mcp-Session-Id": "nonexistent-deadbeef"})
        assert r.status == 200
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_delete_without_session_header_returns_200(monkeypatch):
    """should return 200 when DELETE is called without Mcp-Session-Id header"""
    c = await _client(monkeypatch)
    try:
        r = await c.delete("/mcp")
        assert r.status == 200
    finally:
        await c.close()


# ---------------------------------------------------------------------------
# Batch: casos nao cobertos pelos testes originais
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_only_notifications_returns_202(monkeypatch):
    """should return 202 with empty body when batch contains only notifications"""
    c = await _client(monkeypatch)
    try:
        r = await c.post("/mcp", json=[
            {"jsonrpc": "2.0", "method": "notifications/ping"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        ])
        assert r.status == 202
        assert (await r.text()) == ""
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_batch_empty_returns_400_invalid_request(monkeypatch):
    """should return 400 with error code -32600 when batch is an empty array"""
    c = await _client(monkeypatch)
    try:
        r = await c.post("/mcp", json=[])
        assert r.status == 400
        data = await r.json()
        assert data["error"]["code"] == -32600
    finally:
        await c.close()


# ---------------------------------------------------------------------------
# Erros JSON-RPC: body valido mas nao dict nem list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_body_integer_returns_400_invalid_request(monkeypatch):
    """should return 400/-32600 when body is a JSON integer"""
    c = await _client(monkeypatch)
    try:
        r = await c.post("/mcp", json=42)
        assert r.status == 400
        data = await r.json()
        assert data["error"]["code"] == -32600
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_body_string_returns_400_invalid_request(monkeypatch):
    """should return 400/-32600 when body is a JSON string"""
    c = await _client(monkeypatch)
    try:
        r = await c.post("/mcp", json="hello")
        assert r.status == 400
        data = await r.json()
        assert data["error"]["code"] == -32600
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_body_boolean_returns_400_invalid_request(monkeypatch):
    """should return 400/-32600 when body is a JSON boolean"""
    c = await _client(monkeypatch)
    try:
        r = await c.post("/mcp", json=True)
        assert r.status == 400
        data = await r.json()
        assert data["error"]["code"] == -32600
    finally:
        await c.close()


# ---------------------------------------------------------------------------
# Robustez: excecao em handle_request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exception_in_handle_request_returns_internal_error(monkeypatch):
    """should return -32603 in body (not crash) when handle_request raises"""
    c = await _client(monkeypatch, _FakeErrorMCP)
    try:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 99, "method": "tools/list"})
        assert r.status == 200
        data = await r.json()
        assert data["error"]["code"] == -32603
        assert data["id"] == 99
        assert "RuntimeError" in data["error"]["message"]
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_server_survives_exception_and_continues_serving(monkeypatch):
    """should continue processing requests after handle_request raises"""
    c = await _client(monkeypatch, _FakeErrorMCP)
    try:
        r1 = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert r1.status == 200
        assert (await r1.json())["error"]["code"] == -32603

        # O server ainda deve estar de pe
        r2 = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert r2.status == 200
        assert (await r2.json())["error"]["code"] == -32603
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_exception_in_batch_item_returns_partial_errors(monkeypatch):
    """should return error -32603 for each item in batch when handle_request raises"""
    c = await _client(monkeypatch, _FakeErrorMCP)
    try:
        r = await c.post("/mcp", json=[
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call"},
        ])
        assert r.status == 200
        data = await r.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert all(item["error"]["code"] == -32603 for item in data)
        assert {item["id"] for item in data} == {1, 2}
    finally:
        await c.close()


# ---------------------------------------------------------------------------
# Concorrencia: CRITERIO DE PRONTO P7
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_requests_all_succeed(monkeypatch):
    """should handle N simultaneous requests without conflict or dropped responses"""
    N = 20
    c = await _client(monkeypatch)
    try:
        async def post_one(i: int):
            return await c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": i, "method": "tools/list"},
            )

        responses = await asyncio.gather(*[post_one(i) for i in range(N)])

        assert all(r.status == 200 for r in responses), (
            "todas as requests concorrentes devem retornar 200"
        )
        bodies = await asyncio.gather(*[r.json() for r in responses])
        ids_received = {b["id"] for b in bodies}
        assert ids_received == set(range(N)), (
            "cada request deve receber resposta com seu proprio id"
        )
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_concurrent_initialize_produces_unique_session_ids(monkeypatch):
    """should produce N distinct Mcp-Session-Id values under N concurrent initializes"""
    N = 10
    c = await _client(monkeypatch)
    try:
        async def init_one(i: int):
            return await c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": i, "method": "initialize", "params": {}},
            )

        responses = await asyncio.gather(*[init_one(i) for i in range(N)])

        assert all(r.status == 200 for r in responses)
        session_ids = {r.headers["Mcp-Session-Id"] for r in responses}
        assert len(session_ids) == N, (
            f"esperava {N} IDs unicos de sessao, obteve {len(session_ids)}"
        )

        health = await (await c.get("/health")).json()
        assert health["sessions"] == N
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_concurrent_mixed_methods_no_cross_contamination(monkeypatch):
    """should route concurrent heterogeneous requests to correct handlers without mixing"""
    c = await _client(monkeypatch)
    try:
        async def do_init():
            return await c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )

        async def do_tools_list():
            return await c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )

        async def do_notification():
            return await c.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/ping"},
            )

        async def do_health():
            return await c.get("/health")

        r_init, r_list, r_notif, r_health = await asyncio.gather(
            do_init(), do_tools_list(), do_notification(), do_health()
        )

        assert r_init.status == 200
        assert r_init.headers.get("Mcp-Session-Id"), "initialize deve emitir Mcp-Session-Id"
        assert (await r_init.json())["id"] == 1

        assert r_list.status == 200
        assert (await r_list.json())["id"] == 2

        assert r_notif.status == 202

        assert r_health.status == 200
        assert (await r_health.json())["status"] == "ok"
    finally:
        await c.close()
