import json
import os
import pytest
from sinapse_memory import _backend_graphify


class TestBackendGraphify:
    """U1: Backend Graphify — busca estrutural no graph.json"""

    def test_graph_json_missing(self, monkeypatch):
        """U1.1: graph.json ausente retorna None."""
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", "/nonexistent/path.json")
        result = _backend_graphify("query")
        assert result is None

    def test_graph_json_corrupted(self, monkeypatch, tmp_path):
        """U1.2: JSON inválido retorna None."""
        corrupt = tmp_path / "graph.json"
        corrupt.write_text("NOT VALID JSON {{{")
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", str(corrupt))
        result = _backend_graphify("query")
        assert result is None

    def test_empty_query(self):
        """U1.3: Query vazia não causa erro."""
        result = _backend_graphify("")
        assert result is None

    def test_exact_match_found(self, monkeypatch, sample_graph, tmp_path):
        """U1.4: Match exato retorna nodes."""
        gpath = tmp_path / "graph.json"
        gpath.write_text(json.dumps(sample_graph))
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", str(gpath))
        result = _backend_graphify("thoth")
        assert result is not None
        assert len(result["nodes"]) > 0
        assert result["nodes"][0]["label"] == "thoth"

    def test_no_match(self, monkeypatch, sample_graph, tmp_path):
        """U1.5: Query sem match retorna None."""
        gpath = tmp_path / "graph.json"
        gpath.write_text(json.dumps(sample_graph))
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", str(gpath))
        result = _backend_graphify("xyznonexistent123")
        assert result is None

    def test_edge_match(self, monkeypatch, sample_graph, tmp_path):
        """U1.6: Match em edge retorna edges."""
        gpath = tmp_path / "graph.json"
        gpath.write_text(json.dumps(sample_graph))
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", str(gpath))
        result = _backend_graphify("related_to")
        assert result is not None
        assert "edges" in result
        assert len(result["edges"]) > 0

    def test_max_nodes_limit(self, monkeypatch, sample_graph, tmp_path):
        """U1.7: Respeita MAX_NODES."""
        # Cria 20 nodes que dariam match
        for i in range(20):
            sample_graph["nodes"].append({
                "label": f"thoth_{i}", "file_type": "doc",
                "source_file": f"t{i}.md", "id": f"thoth_{i}",
                "community": 1, "norm_label": f"thoth_{i}"
            })
        gpath = tmp_path / "graph.json"
        gpath.write_text(json.dumps(sample_graph))
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", str(gpath))
        monkeypatch.setattr("sinapse_memory.MAX_NODES", 5)
        result = _backend_graphify("thoth")
        assert result is not None
        assert len(result["nodes"]) <= 5

    def test_normalization_cross_idioma(self, monkeypatch, sample_graph, tmp_path):
        """U1.8: Normalização lida com acentos."""
        sample_graph["nodes"].append({
            "label": "João Ação", "file_type": "document",
            "source_file": "joao.md", "id": "joao",
            "community": 5, "norm_label": "joao acao"
        })
        gpath = tmp_path / "graph.json"
        gpath.write_text(json.dumps(sample_graph))
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", str(gpath))
        result = _backend_graphify("joao acao")
        assert result is not None
        # Check that the accent-insensitive match catches at least one node
        labels = [n["label"] for n in result.get("nodes", [])]
        assert len(labels) > 0

    def test_score_ordering(self, monkeypatch, sample_graph, tmp_path):
        """U1.9: Nodes ordenados por score decrescente."""
        gpath = tmp_path / "graph.json"
        gpath.write_text(json.dumps(sample_graph))
        monkeypatch.setattr("sinapse_memory.GRAPH_JSON", str(gpath))
        result = _backend_graphify("thoth")
        if result and result.get("nodes"):
            scores = [n.get("score", 0) for n in result["nodes"]]
            assert scores == sorted(scores, reverse=True)
