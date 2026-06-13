"""
Backend Graphify: busca estrutural em graph.json.

Puro — recebe todos os parâmetros (incluindo cache mutável), sem globals.
O cache (dict + float) é passado por referência pelo chamador (sinapse-memory.py)
para que monkeypatch.setattr("sinapse_memory._graph_cache", ...) funcione.
"""

import json
import os
import time
from typing import Any, Callable, Dict, List, Optional


def validate_graph_schema(graph: dict) -> bool:
    """Valida que o graph.json tem a estrutura esperada."""
    if not isinstance(graph, dict):
        return False
    nodes = graph.get("nodes")
    links = graph.get("links")
    if not isinstance(nodes, list) or not isinstance(links, list):
        return False
    if nodes:
        required_keys = {"label", "id"}
        if not required_keys.issubset(nodes[0].keys()):
            return False
    return True


def load_graph(
    graph_json_path: str,
    graph_cache: Dict[str, Any],
    graph_cache_time_holder: List[float],
    graph_cache_ttl: int,
) -> Optional[dict]:
    """
    Carrega graph.json com cache TTL.

    Args:
        graph_json_path: caminho para o arquivo graph.json.
        graph_cache: dict de cache (modificado in-place).
        graph_cache_time_holder: lista de um elemento [float] para manter
            o timestamp do cache (mutável por referência).
        graph_cache_ttl: TTL em segundos.
    """
    if not os.path.isfile(graph_json_path):
        return None

    now = time.time()
    if graph_cache and (now - graph_cache_time_holder[0]) < graph_cache_ttl:
        return graph_cache

    try:
        with open(graph_json_path, "r") as f:
            data = json.load(f)
        graph_cache.clear()
        graph_cache.update(data)
        graph_cache_time_holder[0] = now
        return graph_cache
    except (json.JSONDecodeError, OSError):
        return None


def _normalize(text: str) -> str:
    """Remove acentos e normaliza para lowercase."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ASCII", "ignore").decode("ASCII")
    return text.lower()


def backend_graphify(
    query: str,
    graph_json_path: str,
    graph_cache: Dict[str, Any],
    graph_cache_time_holder: List[float],
    graph_cache_ttl: int,
    max_nodes: int,
    log_fn: Optional[Callable] = None,
) -> Optional[Dict[str, Any]]:
    """
    Busca estrutural no knowledge graph (graph.json).

    Args:
        query: string de busca.
        graph_json_path: caminho para graph.json (pode ser monkeypatched).
        graph_cache: dict de cache (passado do módulo pai).
        graph_cache_time_holder: [float] — um elemento contendo o timestamp.
        graph_cache_ttl: TTL do cache em segundos.
        max_nodes: limite de nodes / edges no resultado.
        log_fn: callable(level, event, **kwargs) para logging.
    """
    graph = load_graph(graph_json_path, graph_cache, graph_cache_time_holder, graph_cache_ttl)

    # Retry direto se cache falhou
    if graph is None and os.path.isfile(graph_json_path):
        for attempt in range(3):
            try:
                with open(graph_json_path, "r") as f:
                    graph = json.load(f)
                break
            except (json.JSONDecodeError, OSError):
                if attempt < 2:
                    time.sleep(0.1)
                else:
                    if log_fn:
                        log_fn("error", "graph_json_read_failed", file=graph_json_path)
                    return None

    if graph is None:
        return None

    if not validate_graph_schema(graph):
        if log_fn:
            log_fn("error", "graph_schema_invalid")
        return None

    words = set(_normalize(query).split())
    matched_nodes: List[Dict[str, Any]] = []
    matched_edges: List[Dict[str, Any]] = []

    for node in graph.get("nodes", []):
        label = _normalize(node.get("label") or "")
        node_type = _normalize(node.get("file_type") or "")
        community = _normalize(str(node.get("community", "")))
        if any(w in label or w in node_type or w in community for w in words):
            matched_nodes.append({
                "label": node.get("label"),
                "type": node.get("file_type"),
                "source": node.get("source_file"),
                "community": node.get("community"),
                "score": sum(1 for w in words if w in label),
            })

    matched_nodes.sort(key=lambda n: n["score"], reverse=True)
    matched_nodes = matched_nodes[:max_nodes]

    for link in graph.get("links", []):
        source = _normalize(link.get("source") or "")
        target = _normalize(link.get("target") or "")
        rel = _normalize(link.get("relation") or "")
        if any(w in source or w in target or w in rel for w in words):
            matched_edges.append({
                "source": link.get("source"),
                "target": link.get("target"),
                "relation": link.get("relation"),
            })

    if not matched_nodes and not matched_edges:
        return None

    return {
        "source": "graphify (structural)",
        "nodes": matched_nodes,
        "edges": matched_edges[:max_nodes],
        "query": query,
        "stats": {
            "total_nodes": len(graph.get("nodes", [])),
            "total_edges": len(graph.get("links", [])),
        },
    }
