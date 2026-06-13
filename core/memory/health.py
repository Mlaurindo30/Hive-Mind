"""
Health check unificado para o Sinapse Memory plugin.

Puro — recebe todos os parâmetros como argumentos.
"""

import json
import os
import subprocess
from typing import Any, Callable, Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


def check_nmem(nmem_bin: str) -> bool:
    """Verifica se o binário nmem está disponível e executável."""
    return os.path.isfile(nmem_bin) and os.access(nmem_bin, os.X_OK)


def check_graphify(graph_json_path: str) -> bool:
    """Verifica se graph.json existe."""
    return os.path.isfile(graph_json_path)


def check_rtk() -> bool:
    """Verifica se o binário rtk está disponível."""
    try:
        subprocess.run(["rtk", "--version"], capture_output=True, timeout=2)
        return True
    except Exception:
        return False


def check_claude_mem(claude_mem_url: str) -> bool:
    """Verifica se o claude-mem está respondendo."""
    try:
        req = Request(f"{claude_mem_url}/health", method="GET")
        with urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "ok"
    except Exception:
        return False


def get_graph_node_count(graph_json_path: str) -> int:
    """Retorna o número de nodes no graph.json."""
    try:
        with open(graph_json_path) as f:
            return len(json.load(f).get("nodes", []))
    except Exception:
        return 0


def health_check(
    nmem_bin: str,
    graph_json_path: str,
    claude_mem_url: str,
    vault_dir: str,
    read_backends_count: int,
) -> Dict[str, Any]:
    """
    Retorna status completo de todos os backends e componentes.

    Args:
        nmem_bin: caminho para o binário nmem.
        graph_json_path: caminho para graph.json.
        claude_mem_url: URL base do claude-mem.
        vault_dir: caminho para o vault Obsidian.
        read_backends_count: número de backends registrados.
    """
    backends = {
        "neural_memory": check_nmem(nmem_bin),
        "claude_mem": check_claude_mem(claude_mem_url),
        "graphify": check_graphify(graph_json_path),
        "rtk": check_rtk(),
    }
    status: Dict[str, Any] = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "backends": backends,
        "vault": {
            "path": vault_dir,
            "exists": os.path.isdir(vault_dir),
            "graph_nodes": get_graph_node_count(graph_json_path),
        },
        "plugin": {
            "backends_registered": read_backends_count,
        },
    }
    status["healthy"] = all(v for v in backends.values())
    return status
