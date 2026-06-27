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


def check_filesystem(vault_dir: str) -> bool:
    """Verifica se o vault anatômico existe."""
    return os.path.isdir(vault_dir)


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


def check_sqlite_vec(vec_worker_url: str) -> bool:
    """Verifica se o sqlite-vec worker está respondendo."""
    try:
        req = Request(f"{vec_worker_url}/health", method="GET")
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
    *,
    umc_available: bool = False,
    vec_worker_url: str = "http://127.0.0.1:37701",
    graphiti_available_fn: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """
    Retorna status dos read-backends do sinapse_query e componentes auxiliares.

    Args:
        nmem_bin: caminho para o binário nmem.
        graph_json_path: caminho para graph.json.
        claude_mem_url: URL base do claude-mem.
        vault_dir: caminho para o vault Obsidian.
        read_backends_count: número de backends registrados.
        umc_available: True quando o backend UMC/query_hybrid está importável.
        vec_worker_url: URL base do worker sqlite-vec.
        graphiti_available_fn: callable que checa FalkorDB/Graphiti.
    """
    graphify_ok = check_graphify(graph_json_path)
    claude_mem_ok = check_claude_mem(claude_mem_url)
    neural_ok = check_nmem(nmem_bin)
    sqlite_vec_ok = check_sqlite_vec(vec_worker_url)
    filesystem_ok = check_filesystem(vault_dir)
    try:
        graphiti_ok = bool(graphiti_available_fn()) if graphiti_available_fn else False
    except Exception:
        graphiti_ok = False

    read_backends = {
        "umc": bool(umc_available),
        "neural_memory": neural_ok,
        "sqlite_vec": sqlite_vec_ok,
        "claude_mem": claude_mem_ok,
        "graphify": graphify_ok,
        "graphiti": graphiti_ok,
        "filesystem": filesystem_ok,
    }
    components = {
        "neural_memory": check_nmem(nmem_bin),
        "claude_mem": claude_mem_ok,
        "sqlite_vec_worker": sqlite_vec_ok,
        "graphify_graph": graphify_ok,
        "graphiti": graphiti_ok,
        "rtk": check_rtk(),
    }
    status: Dict[str, Any] = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        # Compatibilidade: callers antigos leem status["backends"].
        # A partir de agora este campo é o contrato correto dos 7
        # read-backends do sinapse_query, sem RTK.
        "backends": read_backends,
        "read_backends": read_backends,
        "components": components,
        "vault": {
            "path": vault_dir,
            "exists": os.path.isdir(vault_dir),
            "graph_nodes": get_graph_node_count(graph_json_path),
        },
        "plugin": {
            "backends_registered": read_backends_count,
        },
    }
    status["healthy"] = all(v for v in read_backends.values())
    status["components_healthy"] = all(v for v in components.values())
    return status
