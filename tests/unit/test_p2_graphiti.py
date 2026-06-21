"""Testes do cliente Graphiti P2 (core/graphiti_client.py).

Verifica:
  - graphiti_available() retorna False quando FalkorDB offline
  - push_neuron() retorna False quando FalkorDB offline
  - search_graph() retorna [] quando FalkorDB offline
  - Testes live (skip se FalkorDB não estiver rodando)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import graphiti_client as gc


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the graphiti singleton before each test to prevent state leakage."""
    original = gc._graphiti
    gc._graphiti = None
    yield
    gc._graphiti = original


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


def test_push_neuron_offline(monkeypatch):
    """push_neuron() → False quando FalkorDB offline."""
    monkeypatch.setattr(gc, "graphiti_available", lambda: False)
    assert gc.push_neuron("n001", "test content") is False


def test_search_graph_offline(monkeypatch):
    """search_graph() → [] quando FalkorDB offline."""
    monkeypatch.setattr(gc, "graphiti_available", lambda: False)
    assert gc.search_graph("test query") == []


def test_push_neuron_swallows_errors(monkeypatch):
    """push_neuron() retorna False (nunca lança) mesmo com erro inesperado."""
    monkeypatch.setattr(gc, "graphiti_available", lambda: True)

    mock_client = MagicMock()
    mock_client.add_episode.side_effect = RuntimeError("boom")
    monkeypatch.setattr(gc, "_graphiti", mock_client)

    # asyncio.run() will call mock_client.add_episode as coroutine — patch properly
    import asyncio

    async def _raise(*_a, **_kw):
        raise RuntimeError("boom")

    mock_client.add_episode = _raise
    result = gc.push_neuron("n002", "content", source="test")
    assert result is False


def test_search_graph_swallows_errors(monkeypatch):
    """search_graph() retorna [] (nunca lança) mesmo com erro inesperado."""
    monkeypatch.setattr(gc, "graphiti_available", lambda: True)

    import asyncio

    async def _raise(*_a, **_kw):
        raise RuntimeError("boom")

    mock_client = MagicMock()
    mock_client.search = _raise
    monkeypatch.setattr(gc, "_graphiti", mock_client)
    result = gc.search_graph("test")
    assert result == []


def test_build_client_uses_env(monkeypatch):
    """_build_client() lê variáveis de ambiente corretamente."""
    monkeypatch.setenv("FALKORDB_HOST", "db.example.com")
    monkeypatch.setenv("FALKORDB_PORT", "6380")
    monkeypatch.setenv("FALKORDB_DB", "testdb")
    monkeypatch.setenv("GRAPHITI_LLM_MODEL", "test-model")
    monkeypatch.setenv("GRAPHITI_EMBED_MODEL", "test-embed")

    captured = {}

    def _fake_graphiti(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    from graphiti_core.driver import falkordb_driver as fdr

    original_driver = fdr.FalkorDriver

    def _fake_driver(host, port, username, password, database):
        captured["host"] = host
        captured["port"] = port
        captured["database"] = database
        return MagicMock()

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
    result = gc.push_neuron("test-neuron-p2", "Teste P2: graphiti + FalkorDB integração.", source="test")
    assert result is True


@pytest.mark.skipif(not _is_falkordb_alive(), reason="FalkorDB não está rodando em localhost:6379")
def test_live_search_graph():
    results = gc.search_graph("graphiti FalkorDB integração", num_results=5)
    assert isinstance(results, list)
    for r in results:
        assert "fact" in r
        assert "uuid" in r
