"""
Health check unificado para o Sinapse Memory plugin.

Puro — recebe todos os parâmetros como argumentos.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable, Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


def check_nmem(nmem_bin: str) -> bool:
    """Verifica se o binário nmem está disponível e executável."""
    return os.path.isfile(nmem_bin) and os.access(nmem_bin, os.X_OK)


def check_graphify(graph_json_path: str) -> bool:
    """Verify that the structural graph is readable and contains nodes."""
    return get_graph_node_count(graph_json_path) > 0


def check_filesystem(vault_dir: str) -> bool:
    """Verifica se o vault anatômico existe."""
    return os.path.isdir(vault_dir)


def check_rtk() -> bool:
    """Verifica se o binário rtk está disponível."""
    candidates = []
    which_rtk = shutil.which("rtk")
    if which_rtk:
        candidates.append(which_rtk)
    sinapse_home = os.environ.get("SINAPSE_HOME")
    if sinapse_home:
        candidates.append(str(Path(sinapse_home) / "integrations" / "rtk" / "target" / "release" / ("rtk.exe" if os.name == "nt" else "rtk")))
    candidates.append(str(Path(__file__).resolve().parents[2] / "integrations" / "rtk" / "target" / "release" / ("rtk.exe" if os.name == "nt" else "rtk")))
    try:
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                result = subprocess.run([candidate, "--version"], capture_output=True, timeout=2)
                if result.returncode == 0:
                    return True
    except Exception:
        pass
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
    try:
        from core.auth import load_env

        load_env()
    except Exception:
        pass

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
    try:
        from core.database import get_connection
        from scripts.health.knowledge_health import (
            compute_knowledge_health,
            evaluate_fail_closed,
        )

        conn = get_connection()
        try:
            knowledge = compute_knowledge_health(conn, prune_orphans=False, quick=True)
            knowledge["failures"] = evaluate_fail_closed(knowledge)
            status["knowledge_health"] = knowledge
        finally:
            conn.close()
    except Exception as exc:
        status["knowledge_health"] = {
            "status": "unavailable",
            "error": str(exc),
        }

    # Model Gateway (Priority 1) — always present, even disabled, per
    # specs/model-gateway.md Requirement 25. Probing live endpoints only
    # happens when the gateway is actually enabled, so a disabled gateway
    # never adds network latency to this health check.
    try:
        from core.model_gateway import ModelGateway, gateway_enabled

        gw_enabled = gateway_enabled()
        gateway = ModelGateway.from_config()
        if gw_enabled:
            gw_health = gateway.health()
            status["model_gateway"] = {
                "enabled": True,
                "models_total": gw_health["models_total"],
                "healthy": gw_health["healthy"],
                "unhealthy": gw_health["unhealthy"],
                "default_roles": gw_health["default_roles"],
            }
        else:
            status["model_gateway"] = {
                "enabled": False,
                "models_total": len(gateway.registry.list_models()),
                "healthy": 0,
                "unhealthy": 0,
                "default_roles": {},
            }
    except Exception as exc:
        status["model_gateway"] = {
            "enabled": False, "models_total": 0, "healthy": 0,
            "unhealthy": 0, "default_roles": {}, "error": str(exc),
        }

    status["healthy"] = all(v for v in read_backends.values())
    status["components_healthy"] = all(v for v in components.values())
    return status
