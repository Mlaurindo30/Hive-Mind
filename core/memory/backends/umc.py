"""
Backend UMC: Unified Memory Core (busca híbrida texto + vetores).

Todas as funções são puras — recebem config como parâmetros, sem globals.
"""

from typing import Any, Callable, Dict, List, Optional


def backend_umc(
    query: str,
    umc_query_hybrid: Optional[Callable],
    max_nodes: int,
    observation_chars: int,
    log_fn: Optional[Callable] = None,
) -> Optional[Dict[str, Any]]:
    """
    Busca principal no Unified Memory Core (UMC).
    Combina FTS5 (texto) e sqlite-vec (semântica) nativamente.

    Args:
        query: string de busca.
        umc_query_hybrid: função importada de core.database (ou None se indisponível).
        max_nodes: limite de resultados.
        observation_chars: máximo de caracteres por observação.
        log_fn: callable(level, event, **kwargs) para logging.
    """
    if umc_query_hybrid is None:
        return None

    try:
        results: List[Dict[str, Any]] = umc_query_hybrid(query, limit=max_nodes)
        if results:
            observations = [
                {
                    "title": r.get("label", ""),
                    "content": r.get("content", "")[:observation_chars],
                    "source_file": r.get("source_file", ""),
                    "type": r.get("type", "neuron"),
                }
                for r in results
            ]
            return {
                "source": "Unified Memory Core (UMC)",
                "observations": observations,
                "query": query,
            }
    except Exception as e:
        if log_fn:
            log_fn("error", "backend_umc_failed", error=str(e))

    return None
