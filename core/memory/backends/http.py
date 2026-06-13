"""
Backends HTTP: claude-mem (semântico/FTS5) e sqlite-vec (semântico nativo).

Puro — recebe todos os parâmetros, sem acessar globals de outros módulos.
`urlopen_fn` é passado como parâmetro para permitir mock em testes via
patch("sinapse_memory.urlopen").
"""

import json
from typing import Any, Callable, Dict, Optional
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen as _default_urlopen


def backend_sqlite_vec(
    query: str,
    vec_worker_url: str,
    timeout: int,
    max_observations: int,
    semantic_context_chars: int,
    log_fn: Optional[Callable] = None,
    urlopen_fn: Callable = _default_urlopen,
) -> Optional[Dict[str, Any]]:
    """
    Busca semântica via sqlite-vec worker (nativo, zero Python MCP).

    Args:
        urlopen_fn: injetável para testes (padrão: urllib.request.urlopen).
    """
    try:
        req = Request(
            f"{vec_worker_url}/api/context/semantic",
            data=json.dumps({"query": query}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen_fn(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            context = data.get("context", "")
            count = data.get("count", 0)
            if context and count > 0:
                return {
                    "source": "sqlite-vec (semantic)",
                    "observations": [{"content": context[:semantic_context_chars]}],
                    "count": count,
                    "query": query,
                }
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        pass

    return None


def backend_claude_mem(
    query: str,
    claude_mem_url: str,
    timeout: int,
    max_observations: int,
    observation_chars: int,
    semantic_context_chars: int,
    log_fn: Optional[Callable] = None,
    urlopen_fn: Callable = _default_urlopen,
) -> Optional[Dict[str, Any]]:
    """
    Busca semântica no claude-mem via HTTP API.
    Tenta /api/context/semantic primeiro (Chroma), fallback /api/search (FTS5).

    Args:
        urlopen_fn: injetável para testes (padrão: urllib.request.urlopen).
    """
    # Tenta Chroma (semântico)
    try:
        req = Request(
            f"{claude_mem_url}/api/context/semantic",
            data=json.dumps({"query": query}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen_fn(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            context = data.get("context", "")
            count = data.get("count", 0)
            if context and count > 0:
                return {
                    "source": "claude-mem (semantic)",
                    "observations": [{"content": context[:semantic_context_chars]}],
                    "count": count,
                    "query": query,
                }
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        pass

    # Fallback: busca FTS5 textual
    try:
        encoded_query = quote(query)
        req = Request(
            f"{claude_mem_url}/api/search?query={encoded_query}",
            method="GET",
        )
        with urlopen_fn(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("items", [])
            if items:
                return {
                    "source": "claude-mem (FTS5)",
                    "observations": [
                        {
                            "title": i.get("title", ""),
                            "content": i.get("excerpt", "")[:observation_chars],
                        }
                        for i in items[:max_observations]
                    ],
                    "count": len(items),
                    "query": query,
                }
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        pass

    return None
