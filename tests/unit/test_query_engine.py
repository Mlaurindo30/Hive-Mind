import json
import pytest
from sinapse_memory import _query_vault_knowledge, _READ_BACKENDS


class TestQueryEngine:
    """U5: Motor de busca unificado"""

    def test_empty_query_returns_none(self):
        """U5.1: Query vazia retorna None."""
        assert _query_vault_knowledge("") is None
        assert _query_vault_knowledge("   ") is None

    def test_null_query_returns_none(self):
        """U5.1b: Query None retorna None."""
        assert _query_vault_knowledge(None) is None

    def test_first_backend_wins(self, monkeypatch):
        """U5.2: Primeiro backend que retorna resultado ganha."""
        def backend1(q):
            return {"source": "backend1", "observations": [{"content": "found"}]}
        def backend2(q):
            return {"source": "backend2", "observations": []}

        monkeypatch.setattr("sinapse_memory._READ_BACKENDS", [backend1, backend2])
        result = _query_vault_knowledge("test")
        assert result is not None
        assert result["source"] == "backend1"

    def test_second_backend_fallback(self, monkeypatch):
        """U5.3: Segundo backend é usado se primeiro falha."""
        def backend1(q):
            return None
        def backend2(q):
            return {"source": "backend2", "observations": [{"content": "found"}]}

        monkeypatch.setattr("sinapse_memory._READ_BACKENDS", [backend1, backend2])
        result = _query_vault_knowledge("test")
        assert result is not None
        assert result["source"] == "backend2"

    def test_bug_in_backend_doesnt_crash(self, monkeypatch):
        """U5.4: Backend com bug (KeyError) não crasha o sistema."""
        def buggy(q):
            raise KeyError("simulated bug")

        def fallback(q):
            return {"source": "fallback", "observations": []}

        monkeypatch.setattr("sinapse_memory._READ_BACKENDS", [buggy, fallback])
        result = _query_vault_knowledge("test")
        assert result is not None
        assert result["source"] == "fallback"

    def test_all_backends_fail_returns_none(self, monkeypatch):
        """U5.5: Todos backends falham → None sem crash."""
        def fail1(q):
            return None
        def fail2(q):
            return None

        monkeypatch.setattr("sinapse_memory._READ_BACKENDS", [fail1, fail2])
        result = _query_vault_knowledge("test")
        assert result is None
