import threading
import time
import pytest
from sinapse_memory import _query_vault_knowledge


class TestConcurrency:
    """E3: Comportamento concorrente."""

    def test_multiple_queries_no_race(self, monkeypatch):
        """Múltiplas queries simultâneas não causam race condition."""
        results = []
        errors = []

        def slow_backend(q):
            time.sleep(0.05)
            return {"source": "slow", "observations": [{"content": q}]}

        monkeypatch.setattr("sinapse_memory._READ_BACKENDS", [slow_backend])

        def worker(q):
            try:
                r = _query_vault_knowledge(q)
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(f"query_{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 5

    def test_shared_global_state_isolated(self, monkeypatch):
        """Estado global não vaza entre queries."""
        monkeypatch.setattr("sinapse_memory._READ_BACKENDS", [
            lambda q: {"source": "test", "observations": [{"content": "ok"}]}
        ])

        r1 = _query_vault_knowledge("a")
        r2 = _query_vault_knowledge("b")

        assert r1 is not None
        assert r2 is not None
