import os
import json
import pytest
from sinapse_memory import _load_graph


class TestCron:
    """I4: Testes de interação com cron/build"""

    def test_graph_cache_load(self, monkeypatch, sample_graph, tmp_path):
        """I4.1: Cache carrega graph.json corretamente."""
        gfile = tmp_path / "graph.json"
        gfile.write_text(json.dumps(sample_graph))
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", str(gfile))
        # Clear cache
        monkeypatch.setattr("sinapse_memory._graph_cache", {})
        monkeypatch.setattr("sinapse_memory._graph_cache_time", 0)
        graph = _load_graph()
        assert graph is not None
        assert "nodes" in graph
        assert len(graph["nodes"]) >= 3

    def test_graph_cache_hit(self, monkeypatch, sample_graph, tmp_path):
        """I4.2: Cache serve resultado sem re-leitura."""
        gfile = tmp_path / "graph.json"
        gfile.write_text(json.dumps(sample_graph))
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", str(gfile))
        monkeypatch.setattr("sinapse_memory._graph_cache", {})

        # First load
        g1 = _load_graph()
        # Modify file on disk but should still hit cache
        gfile.write_text(json.dumps({"nodes": [], "links": []}))
        # Set TTL high so cache doesn't expire
        monkeypatch.setattr("sinapse_memory._GRAPH_CACHE_TTL", 9999)
        g2 = _load_graph()
        # Should still return original (cached)
        assert len(g2["nodes"]) == len(g1["nodes"])

    def test_graph_json_missing(self, monkeypatch):
        """I4.3: graph.json ausente → None."""
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", "/nonexistent/graph.json")
        monkeypatch.setattr("sinapse_memory._graph_cache", {})
        monkeypatch.setattr("sinapse_memory._graph_cache_time", 0)
        result = _load_graph()
        assert result is None
