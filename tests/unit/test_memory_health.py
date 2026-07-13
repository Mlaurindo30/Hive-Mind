"""Contract tests for the read-backend health report."""

from __future__ import annotations

import json

from core.memory.health import check_graphify


def test_graphify_health_requires_a_non_empty_graph(tmp_path):
    """A placeholder graph must not make the structural backend healthy."""
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")

    assert check_graphify(str(graph)) is False


def test_graphify_health_accepts_graph_with_nodes(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({"nodes": [{"id": "note"}], "links": []}), encoding="utf-8")

    assert check_graphify(str(graph)) is True
