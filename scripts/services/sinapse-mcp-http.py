#!/usr/bin/env python3
"""MCP server via Streamable HTTP (spec MCP 2025-03-26), pragmatico.

Roda EM PARALELO ao sinapse-mcp.py (stdio) — nao o substitui. Permite
multiplos agentes (Claude Code, Codex, etc.) conectados simultaneamente ao
mesmo cerebro Hive-Mind.

Design (ver docs/10-implementation-roadmap.md §P7):
  - As tools sinapse_* sao todas request/response — nao ha mensagem iniciada
    pelo servidor. Portanto NAO implementamos SSE/server-push: seria stream
    sem nada a transmitir. POST /mcp responde application/json direto.
  - Conformidade Streamable HTTP onde importa para interop com clientes reais:
      * POST /mcp  -> processa JSON-RPC (single ou batch), responde JSON.
                      Notificacoes (sem id) -> 202 Accepted sem corpo.
                      initialize -> gera e devolve header Mcp-Session-Id.
      * GET  /mcp  -> 405 (servidor nao oferece stream SSE; a spec permite).
      * DELETE /mcp-> encerra a sessao (200).
      * GET  /health -> {"status":"ok"} para readiness/systemd.
  - Reusa handle_request/TOOLS do modulo importavel scripts.services.sinapse_mcp
    — fonte unica da logica das tools.

Uso:
    python sinapse-mcp-http.py --port 37703
Env:
    SINAPSE_MCP_HTTP_PORT (default 37703)
    SINAPSE_MCP_HTTP_HOST (default 127.0.0.1)
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from aiohttp import web

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.services import sinapse_mcp as _MCP


def _mcp():
    # Indireção mantida para os testes injetarem um fake via monkeypatch(_MCP).
    return _MCP


# Sessoes emitidas no initialize. Set simples — nao exigimos a sessao em toda
# request (clientes request/response podem nao reenviar), mas a emitimos para
# conformidade e suportamos DELETE para encerrar.
_SESSIONS: set[str] = set()

_JSONRPC_PARSE_ERROR = -32700
_JSONRPC_INVALID_REQUEST = -32600
_JSONRPC_INTERNAL_ERROR = -32603


def _error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _process_one(message: dict) -> dict | None:
    """Despacha uma mensagem JSON-RPC para handle_request. Retorna None para
    notificacoes (sem id) ou quando handle_request nao produz resposta."""
    from core.telemetry import span
    method = message.get("method", "unknown")
    tool_name = "unknown"
    if method == "tools/call":
        tool_name = message.get("params", {}).get("name", "unknown")
    elif method == "initialize":
        tool_name = "initialize"

    span_name = f"mcp_http.{tool_name}" if method == "tools/call" else f"mcp_http.{method}"

    with span(span_name, {"method": method, "tool": tool_name}):
        try:
            return _mcp().handle_request(message)
        except Exception as exc:  # nunca derruba o server por causa de uma request
            return _error(message.get("id"), _JSONRPC_INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")


async def handle_mcp_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response(
            _error(None, _JSONRPC_PARSE_ERROR, "JSON invalido"), status=400
        )

    is_initialize = isinstance(body, dict) and body.get("method") == "initialize"

    # Batch (lista) ou mensagem unica.
    if isinstance(body, list):
        if not body:
            return web.json_response(
                _error(None, _JSONRPC_INVALID_REQUEST, "batch vazio"), status=400
            )
        responses = [r for r in (_process_one(m) for m in body) if r is not None]
        if not responses:  # batch so de notificacoes
            return web.Response(status=202)
        return web.json_response(responses)

    if not isinstance(body, dict):
        return web.json_response(
            _error(None, _JSONRPC_INVALID_REQUEST, "esperado objeto ou array JSON-RPC"),
            status=400,
        )

    result = _process_one(body)
    if result is None:  # notificacao — sem corpo
        return web.Response(status=202)

    headers = {}
    if is_initialize:
        session_id = uuid.uuid4().hex
        _SESSIONS.add(session_id)
        headers["Mcp-Session-Id"] = session_id
    return web.json_response(result, headers=headers)


async def handle_mcp_get(request: web.Request) -> web.Response:
    # Sem SSE: nada a transmitir do servidor. A spec permite 405 aqui.
    return web.Response(
        status=405,
        text="GET /mcp nao suportado: este server nao inicia mensagens (sem SSE).",
        headers={"Allow": "POST, DELETE"},
    )


async def handle_mcp_delete(request: web.Request) -> web.Response:
    session_id = request.headers.get("Mcp-Session-Id")
    if session_id:
        _SESSIONS.discard(session_id)
    return web.Response(status=200)


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "transport": "streamable-http", "sessions": len(_SESSIONS)})


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/mcp", handle_mcp_post)
    app.router.add_get("/mcp", handle_mcp_get)
    app.router.add_delete("/mcp", handle_mcp_delete)
    app.router.add_get("/health", handle_health)
    return app


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("SINAPSE_MCP_HTTP_PORT", "37703")))
    ap.add_argument("--host",
                    default=os.environ.get("SINAPSE_MCP_HTTP_HOST", "127.0.0.1"))
    args = ap.parse_args()
    
    from core.telemetry import init_telemetry, flush_telemetry
    init_telemetry()
    
    print(f"MCP Streamable HTTP em http://{args.host}:{args.port}/mcp", file=sys.stderr)
    try:
        web.run_app(build_app(), host=args.host, port=args.port)
    finally:
        flush_telemetry()
    return 0


if __name__ == "__main__":
    sys.exit(main())
