from __future__ import annotations

from core.memory.context_fusion import query_vault_knowledge


def _healthy(_name, _state, _log):
    return True


def _record(_name, _ok, _state):
    return None


def test_query_vault_knowledge_exposes_latency_for_single_backend_hit():
    def backend_a(_query):
        return {"source": "backend-a", "observations": [{"content": "x"}]}

    result = query_vault_knowledge(
        query="health",
        read_backends=[backend_a],
        backend_state={},
        max_observations=5,
        max_nodes=5,
        global_query_timeout=1.0,
        is_healthy_fn=_healthy,
        record_result_fn=_record,
        log_fn=None,
    )

    assert result is not None
    assert "latency_ms_by_backend" in result
    assert "query_latency_ms" in result
    assert "backend_a" in result["latency_ms_by_backend"]


def test_query_vault_knowledge_exposes_latency_for_hybrid_fusion():
    def backend_a(_query):
        return {"source": "backend-a", "observations": [{"content": "a"}]}

    def backend_b(_query):
        return {"source": "backend-b", "observations": [{"content": "b"}]}

    result = query_vault_knowledge(
        query="health",
        read_backends=[backend_a, backend_b],
        backend_state={},
        max_observations=5,
        max_nodes=5,
        global_query_timeout=1.0,
        is_healthy_fn=_healthy,
        record_result_fn=_record,
        log_fn=None,
    )

    assert result is not None
    assert result["source"].startswith("hybrid")
    assert "latency_ms_by_backend" in result
    assert "backend_a" in result["latency_ms_by_backend"]
    assert "backend_b" in result["latency_ms_by_backend"]
    assert isinstance(result["query_latency_ms"], float)

import time


def test_query_vault_knowledge_returns_on_global_timeout_without_waiting_for_backend():
    def fast_backend(_query):
        return {"source": "fast", "observations": [{"content": "fast"}]}

    def blocked_backend(_query):
        time.sleep(0.30)
        return {"source": "blocked", "observations": [{"content": "late"}]}

    started = time.perf_counter()
    result = query_vault_knowledge(
        query="health",
        read_backends=[fast_backend, blocked_backend],
        backend_state={},
        max_observations=5,
        max_nodes=5,
        global_query_timeout=0.03,
        is_healthy_fn=_healthy,
        record_result_fn=_record,
        log_fn=None,
    )
    elapsed = time.perf_counter() - started

    assert result is not None
    assert elapsed < 0.15
    assert result["latency_ms_by_backend"]["blocked_backend"] == 30.0