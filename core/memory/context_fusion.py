"""
Motor de busca unificado com Context Fusion.

Orquestra backends em paralelo com circuit breaker e global timeout.
Puro — recebe todos os parâmetros como argumentos. O chamador
(sinapse-memory.py) passa suas próprias variáveis mutáveis, garantindo
que monkeypatch.setattr("sinapse_memory._READ_BACKENDS", ...) funcione.
"""

import concurrent.futures
import subprocess
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional
from urllib.error import URLError


def query_vault_knowledge(
    query: str,
    read_backends: List[Callable],
    backend_state: Dict[str, Any],
    max_observations: int,
    max_nodes: int,
    global_query_timeout: float,
    is_healthy_fn: Callable,
    record_result_fn: Callable,
    log_fn: Optional[Callable] = None,
    cloud_enabled: bool = False,
    cloud_query_fn: Optional[Callable] = None,
    api_server_mode: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Orquestra todos os backends de busca em paralelo concorrente.

    Args:
        query: string de busca.
        read_backends: lista de funções backend (pode ser monkeypatched).
        backend_state: dict de estado do circuit breaker.
        max_observations: limite de observações no resultado combinado.
        max_nodes: limite de nodes no resultado combinado.
        global_query_timeout: orçamento total em segundos.
        is_healthy_fn: callable(name, state, log_fn) → bool.
        record_result_fn: callable(name, success, state) → None.
        log_fn: callable(level, event, **kwargs) para logging.
        cloud_enabled: se True e não API server mode, usa cloud.
        cloud_query_fn: callable(query) para cloud mode.
        api_server_mode: se True, não redireciona para cloud.
    """
    if not query or not query.strip():
        return None

    if cloud_enabled and not api_server_mode and cloud_query_fn is not None:
        if log_fn:
            log_fn("info", "query_vault_knowledge_cloud", query=query[:60])
        return cloud_query_fn(query)

    # Filtrar backends saudáveis
    healthy_backends = [
        b for b in read_backends
        if is_healthy_fn(b.__name__, backend_state, log_fn)
    ]
    if not healthy_backends:
        return None

    results: Dict[str, Any] = {}

    def _run_backend(backend_fn: Callable):
        name = backend_fn.__name__
        try:
            res = backend_fn(query)
            return name, res, False
        except (URLError, OSError, subprocess.TimeoutExpired, FileNotFoundError):
            return name, None, True
        except Exception as e:
            if log_fn:
                log_fn("error", "backend_error", backend=name, error=str(e))
            traceback.print_exc(file=sys.stderr)
            return name, None, True

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(healthy_backends)) as executor:
        futures = {executor.submit(_run_backend, b): b for b in healthy_backends}
        done, not_done = concurrent.futures.wait(
            futures,
            timeout=global_query_timeout,
            return_when=concurrent.futures.ALL_COMPLETED,
        )

        for future in done:
            try:
                name, res, failed = future.result()
                if failed:
                    record_result_fn(name, False, backend_state)
                    continue
                record_result_fn(name, True, backend_state)
                if res:
                    has_content = (
                        bool(res.get("observations"))
                        or bool(res.get("nodes"))
                        or bool(res.get("edges"))
                    )
                    if has_content:
                        results[name] = res
                        if log_fn:
                            log_fn("info", "backend_hit", backend=name, query=query[:50])
            except Exception as e:
                if log_fn:
                    log_fn("error", "thread_unhandled_error", error=str(e))

        for future in not_done:
            backend_fn = futures[future]
            name = backend_fn.__name__
            record_result_fn(name, False, backend_state)
            if log_fn:
                log_fn("warn", "query_timeout", backend=name, query=query[:50])

    if not results:
        return None

    if len(results) == 1:
        return list(results.values())[0]

    return _fuse_contexts(results, max_observations, max_nodes)


def _fuse_contexts(
    results: Dict[str, Dict[str, Any]],
    max_observations: int,
    max_nodes: int,
) -> Dict[str, Any]:
    """Fusão híbrida de contexto com deduplicação cross-backend."""
    combined: Dict[str, Any] = {
        "source": "hybrid",
        "observations": [],
        "nodes": [],
        "edges": [],
    }

    hit_sources: List[str] = []
    seen_fs_keys: set = set()
    seen_node_ids: set = set()

    for name, res in results.items():
        hit_sources.append(res.get("source", name))

        for obs in res.get("observations", []):
            key = (
                obs.get("source_file", "")
                or obs.get("title", "")
                or obs.get("content", "")[:40]
            )
            key = key.lower().strip()
            if key and key in seen_fs_keys:
                continue
            if key:
                seen_fs_keys.add(key)
            combined["observations"].append(obs)

        for node in res.get("nodes", []):
            nid = (node.get("id", "") or node.get("label", "")).lower().strip()
            if nid and nid in seen_node_ids:
                continue
            if nid:
                seen_node_ids.add(nid)
            combined["nodes"].append(node)

        combined["edges"].extend(res.get("edges", []))

    combined["source"] = "hybrid (" + ", ".join(hit_sources) + ")"
    combined["observations"] = combined["observations"][:max_observations]
    combined["nodes"] = combined["nodes"][:max_nodes]
    combined["edges"] = combined["edges"][:max_nodes]

    return combined
