import pytest
from sinapse_memory import _query_vault_knowledge


class TestGracefulDegradation:
    """E2: Sistema funciona com backends falhando."""

    def test_all_backends_fail_gracefully(self, monkeypatch):
        """Todos backends offline → não crasha."""
        def mock_fail(query):
            return None

        monkeypatch.setattr("sinapse_memory._READ_BACKENDS", [mock_fail, mock_fail, mock_fail])
        result = _query_vault_knowledge("test")
        assert result is None

    def test_second_backend_kicks_in(self, monkeypatch):
        """Primeiro backend falha, segundo responde."""
        def fail_first(query):
            return None

        def succeed_second(query):
            return {"source": "mock", "observations": [{"content": "found"}]}

        monkeypatch.setattr("sinapse_memory._READ_BACKENDS", [fail_first, succeed_second])
        result = _query_vault_knowledge("test")
        assert result is not None
        assert result["source"] == "mock"

    def test_bug_in_backend_doesnt_crash(self, monkeypatch):
        """Backend com bug (KeyError) não crasha o sistema."""
        def buggy(query):
            raise KeyError("simulated bug")

        def fallback(query):
            return {"source": "fallback", "observations": []}

        monkeypatch.setattr("sinapse_memory._READ_BACKENDS", [buggy, fallback])
        result = _query_vault_knowledge("test")
        assert result is not None
        assert result["source"] == "fallback"

    def test_all_backends_buggy_still_no_crash(self, monkeypatch):
        """Mesmo com todos backends bugados, sistema retorna None."""
        def bug1(q):
            raise RuntimeError("bug")
        def bug2(q):
            raise ValueError("bug")

        monkeypatch.setattr("sinapse_memory._READ_BACKENDS", [bug1, bug2])
        result = _query_vault_knowledge("test")
        assert result is None
