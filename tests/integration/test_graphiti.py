"""Testes do cliente Graphiti P2 (integrations/graphiti/client.py).

Verifica:
  - graphiti_available() retorna False quando FalkorDB offline
  - push_neuron() retorna True via fallback (escreve JSON-lines) quando offline
  - search_graph() retorna [] quando FalkorDB offline
  - Testes live (skip se FalkorDB não estiver rodando)
  - Robustez: smoke test, circuit breaker, retry com backoff
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from integrations.graphiti import (
    _build_client,
    _circuit_record_failure,
    _circuit_record_success,
    _fallback_append,
    _fallback_dir,
    _fallback_path,
    _fallback_search,
    _graphiti,
    _retry_with_backoff,
    assert_health,
    circuit_state,
    graphiti_available,
    ollama_model_exists,
    push_neuron,
    reset_circuit,
    search_graph,
)
import integrations.graphiti as gc


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the graphiti singleton before each test to prevent state leakage."""
    original = gc.client._graphiti
    gc.client._graphiti = None
    yield
    gc.client._graphiti = original


# ---------------------------------------------------------------------------
# Testes offline (sempre rodam)
# ---------------------------------------------------------------------------

def test_graphiti_available_offline(monkeypatch):
    """graphiti_available() → False quando FalkorDB não responde."""
    import falkordb

    def _raise(*_a, **_kw):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(falkordb, "FalkorDB", _raise)
    assert gc.graphiti_available() is False


def test_push_neuron_offline_uses_fallback(monkeypatch, tmp_path):
    """push_neuron() → True via fallback (escreve no JSON-lines) quando FalkorDB offline.

    Contrato mudou: antes retornava False silenciosamente. Agora o cérebro
    preserva o neurônio no arquivo do lóbulo temporal para não perder dados.
    """
    fallback = tmp_path / "grafo.jsonl"
    monkeypatch.setenv("HIVE_TEMPORAL_GRAFO", str(fallback))
    monkeypatch.setattr(gc.client, "graphiti_available", lambda: False)
    gc.reset_circuit()

    result = gc.push_neuron("n001", "test content")
    assert result is True
    assert fallback.exists()
    assert "n001" in fallback.read_text()


def test_search_graph_offline(monkeypatch):
    """search_graph() → [] quando FalkorDB offline."""
    monkeypatch.setattr(gc.client, "graphiti_available", lambda: False)
    assert gc.search_graph("test query") == []


def test_push_neuron_swallows_errors(monkeypatch):
    """push_neuron() retorna False (nunca lança) mesmo com erro inesperado."""
    monkeypatch.setattr(gc.client, "graphiti_available", lambda: True)

    def _raise(*_a, **_kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(gc.client, "_run_async", _raise)
    result = gc.push_neuron("n002", "content", source="test")
    assert result is False


def test_search_graph_swallows_errors(monkeypatch):
    """search_graph() retorna [] (nunca lança) mesmo com erro inesperado."""
    async def _raise(*_a, **_kw):
        raise RuntimeError("boom")

    mock_client = MagicMock()
    mock_client.search = _raise
    monkeypatch.setattr(gc.client, "_graphiti", mock_client)
    monkeypatch.setattr(gc.client, "graphiti_available", lambda: True)
    result = gc.search_graph("test")
    assert result == []


def test_graphiti_retry_logs_go_to_stderr(monkeypatch, capsys):
    """Logs de retry não podem poluir stdout de CLIs que retornam JSON."""
    monkeypatch.setenv("HIVE_GRAPHITI_RETRIES", "1")
    gc.reset_circuit()

    def _raise():
        raise ConnectionError("boom")

    ok, result = gc._retry_with_backoff(_raise)

    captured = capsys.readouterr()
    assert ok is False
    assert isinstance(result, ConnectionError)
    assert captured.out == ""
    assert "[graphiti]" in captured.err


def test_graphiti_redisearch_syntax_error_is_not_retried(monkeypatch):
    monkeypatch.setenv("HIVE_GRAPHITI_RETRIES", "3")
    calls = []

    def _raise():
        calls.append("call")
        raise RuntimeError("RediSearch: Syntax error at offset 51 near endpoint")

    ok, error = gc._retry_with_backoff(_raise)

    assert ok is False
    assert len(calls) == 1
    assert "RediSearch" in str(error)


def test_run_async_enforces_operation_timeout(monkeypatch):
    """Graphiti push/search não pode travar o Dream Cycle indefinidamente."""
    monkeypatch.setenv("HIVE_GRAPHITI_OP_TIMEOUT", "0.01")

    async def _slow():
        await asyncio.sleep(1)

    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        gc.client._run_async(lambda: _slow())
    assert time.monotonic() - started < 0.5


def test_build_client_uses_env(monkeypatch):
    """_build_client() lê variáveis de ambiente corretamente."""
    monkeypatch.setenv("FALKORDB_HOST", "db.example.com")
    monkeypatch.setenv("FALKORDB_PORT", "6380")
    monkeypatch.setenv("FALKORDB_DB", "testdb")
    monkeypatch.setenv("GRAPHITI_LLM_MODEL", "test-model")
    monkeypatch.setenv("GRAPHITI_EMBED_MODEL", "test-embed")

    captured = {}

    def _fake_driver(host, port, username, password, database):
        captured["host"] = host
        captured["port"] = port
        captured["database"] = database
        return MagicMock()

    from graphiti_core.driver import falkordb_driver as fdr

    monkeypatch.setattr(fdr, "FalkorDriver", _fake_driver)

    import graphiti_core as gcore

    monkeypatch.setattr(gcore, "Graphiti", lambda **kw: MagicMock())

    try:
        gc._build_client()
    except Exception:
        pass

    assert captured.get("host") == "db.example.com"
    assert captured.get("port") == 6380
    assert captured.get("database") == "testdb"


# ---------------------------------------------------------------------------
# Testes live (skip se FalkorDB não estiver rodando)
# ---------------------------------------------------------------------------

def _is_falkordb_alive() -> bool:
    return gc.graphiti_available()


@pytest.mark.skipif(not _is_falkordb_alive(), reason="FalkorDB não está rodando em localhost:6379")
def test_live_graphiti_available():
    assert gc.graphiti_available() is True


@pytest.mark.skipif(not _is_falkordb_alive(), reason="FalkorDB não está rodando em localhost:6379")
def test_live_push_neuron():
    result = gc.push_neuron("test-neuron-p2-integration", "Teste P2: graphiti + FalkorDB integração.", source="test")
    assert result is True


@pytest.mark.skipif(not _is_falkordb_alive(), reason="FalkorDB não está rodando em localhost:6379")
def test_live_search_graph():
    results = gc.search_graph("graphiti FalkorDB integração", num_results=5)
    assert isinstance(results, list)
    for r in results:
        assert "fact" in r
        assert "uuid" in r


# ---------------------------------------------------------------------------
# Testes de robustez (4 pontos)
# ---------------------------------------------------------------------------

def test_ollama_model_exists_unknown_returns_false():
    """ollama_model_exists() → False para modelo que não está no Ollama."""
    result = gc.ollama_model_exists("definitely-not-installed-xyz-model-zzz")
    assert result is False


def test_circuit_breaker_opens_after_failures():
    """Circuit breaker abre após HIVE_GRAPHITI_CB_FAILS falhas consecutivas."""
    gc.reset_circuit()

    # Forçar 3 falhas via _retry_with_backoff
    for _ in range(3):
        def _runner():
            import asyncio

            async def _raise():
                raise RuntimeError("boom")

            return asyncio.run(_raise())

        gc._retry_with_backoff(_runner)

    state = gc.circuit_state()
    assert state["open"] is True
    assert state["consecutive_failures"] >= 3
    assert state["remaining_s"] > 0

    # graphiti_available deve retornar False durante cooldown
    # (o circuit está aberto, então retorna False sem tentar FalkorDB)
    assert gc.graphiti_available() is False

    # Reset
    gc.reset_circuit()
    assert gc.circuit_state()["open"] is False


def test_circuit_breaker_resets_on_success():
    """Circuit breaker reseta consecutive_failures após sucesso."""
    gc.reset_circuit()

    # 2 falhas
    for _ in range(2):
        def _runner():
            import asyncio

            async def _raise():
                raise RuntimeError("boom")

            return asyncio.run(_raise())

        gc._retry_with_backoff(_runner)

    assert gc.circuit_state()["consecutive_failures"] == 2

    # 1 sucesso
    def _ok():
        return "ok"

    gc._retry_with_backoff(_ok)
    assert gc.circuit_state()["consecutive_failures"] == 0
    assert gc.circuit_state()["open"] is False


def test_push_neuron_fallback_when_falkordb_offline(tmp_path, monkeypatch):
    """push_neuron escreve no JSON-lines do lóbulo temporal quando FalkorDB offline."""
    gc.reset_circuit()
    fallback_path = tmp_path / "grafo.jsonl"
    monkeypatch.setenv("HIVE_TEMPORAL_GRAFO", str(fallback_path))
    monkeypatch.setattr(gc.client, "graphiti_available", lambda: False)

    result = gc.push_neuron("test-fallback-1", "conteudo do neuronio")
    assert result is True, f"push_neuron deveria ter sucesso via fallback"

    assert fallback_path.exists()
    content = fallback_path.read_text()
    assert "test-fallback-1" in content
    assert '"fallback": true' in content

    # Search também usa fallback
    results = gc.search_graph("conteudo")
    assert len(results) >= 1
    assert results[0]["uuid"] == "neuron:test-fallback-1"


def test_assert_health_returns_dict(monkeypatch):
    """assert_health() retorna dict estruturado (mesmo sem FalkorDB/Ollama)."""
    gc.reset_circuit()
    monkeypatch.setattr(gc.client, "graphiti_available", lambda: False)
    monkeypatch.setattr(gc.client, "ollama_model_exists", lambda m: False)

    health = gc.assert_health()
    assert "falkordb" in health
    assert health["falkordb"] is False
    assert "llm_model" in health
    assert "embed_model" in health
    assert "circuit" in health
    assert "errors" in health
    assert len(health["errors"]) >= 1  # FalkorDB + 2 modelos ausentes
