"""
Sinapse Agent — Plugin de Memória para Hermes
=====================================================
Integração bidirecional entre Hermes, Obsidian vault, Graphify, claude-mem e NeuralMemory.

Este módulo é o orquestrador: mantém todos os globals mutáveis e delega
a lógica pura para core.memory.*. Esta separação garante que:
  - os testes podem monkeypatch globals aqui (sinapse_memory.X = ...)
  - as funções lêem os valores atualizados no momento da chamada
  - core.memory permanece testável de forma independente

Todo código novo deve importar de core.memory diretamente.
"""

import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Raiz do projeto — fonte única de verdade
# ---------------------------------------------------------------------------

# _PROJECT_ROOT é sempre derivado de __file__ para garantir que core.* seja
# importável mesmo quando SINAPSE_HOME aponta para um vault temporário.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# SINAPSE_HOME pode ser sobrescrito via env var (para testes com vault temporário)
# mas NÃO deve alterar o Python path de importação de pacotes.
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", _PROJECT_ROOT)

# Garante que a raiz do projeto está no path para importar core.*
# (usa _PROJECT_ROOT, não SINAPSE_HOME)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.memory.state import build_runtime_state, RuntimeState

# Importa o core do UMC (opcional)
try:
    from core.database import query_hybrid as _umc_query_hybrid
except ImportError:
    _umc_query_hybrid = None

# ---------------------------------------------------------------------------
# Configuração — globals mutáveis (monkeypatched pelos testes)
# ---------------------------------------------------------------------------

VAULT_DIR = os.path.join(SINAPSE_HOME, "cerebro")
GRAPH_JSON = os.path.join(VAULT_DIR, "graphify-out", "graph.json")  # graphify ainda escreve aqui
# Paths anatômicos (modelo cérebro — ver docs/08-memoria-viva-design.md):
DECISIONS_DIR = os.path.join(VAULT_DIR, "cortex", "frontal", "trabalho", "ativo")
MEMORY_FILE = os.path.join(VAULT_DIR, "cortex", "frontal", "brain", "Current State.md")
PROJECTS_DIR = os.path.join(VAULT_DIR, "cortex", "frontal", "trabalho", "ativo")
PATTERNS_FILE = os.path.join(VAULT_DIR, "cerebelo", "padroes", "Patterns.md")

CLAUDE_MEM_URL = "http://127.0.0.1:37700"
CLAUDE_MEM_TIMEOUT = 3
NMEM_BIN = os.path.expanduser("~/.local/bin/nmem")
NMEM_TIMEOUT = 5
VEC_WORKER_URL = "http://127.0.0.1:37701"

# Graphiti (orgão do lóbulo temporal) — FalkorDB + Ollama.
# Quando FalkorDB está offline, search_graph() cai para o fallback JSON-lines
# automaticamente; o cérebro não perde a capacidade de responder.
GRAPHITI_TIMEOUT = 3
GRAPHITI_MAX_RESULTS = 10

GLOBAL_QUERY_TIMEOUT = 8
MAX_CONTEXT_CHARS = 3000
MAX_NODES = 5
MAX_OBSERVATIONS = 5
OBSERVATION_CHARS = 300
SEMANTIC_CONTEXT_CHARS = 500

_DEFAULT_DECISION_TOOLS = {"memory_add", "observation_add", "mcp_claude_mem_memory_add"}
_custom_tools = os.environ.get("SINAPSE_DECISION_TOOLS", "")
DECISION_TOOLS = (
    {t.strip() for t in _custom_tools.split(",")} if _custom_tools else _DEFAULT_DECISION_TOOLS
)

_DEFAULT_LEARNING_SIGNALS = [
    "aprendizado", "aprendizagem", "lição", "lição aprendida",
    "descoberta", "padrão identificado",
    "learning", "insight", "pattern", "lesson",
    "lesson learned", "takeaway", "finding", "aha",
    "note to self", "tl;dr",
    "aprendizaje", "lección", "descubrimiento",
]
_custom_signals = os.environ.get("SINAPSE_LEARNING_SIGNALS", "")
LEARNING_SIGNALS = (
    [s.strip().lower() for s in _custom_signals.split(",")] if _custom_signals else _DEFAULT_LEARNING_SIGNALS
)

DRY_RUN = os.environ.get("SINAPSE_DRY_RUN", "").lower() in ("1", "true", "yes")
_LOG_JSON = os.environ.get("SINAPSE_LOG_JSON", "").lower() in ("1", "true", "yes")
API_SERVER_MODE = False

# ---------------------------------------------------------------------------
# Cache de backends (mutáveis — monkeypatched pelos testes)
# ---------------------------------------------------------------------------

_backend_state: Dict[str, Dict[str, Any]] = {}
_graph_cache: Dict[str, Any] = {}
_graph_cache_time: float = 0
_GRAPH_CACHE_TTL = 60

_FS_CACHE: Dict[str, Any] = {}
_FS_CACHE_TIME: float = 0
_FS_CACHE_TTL = 30

_READ_BACKENDS: List[Callable] = []

# Buffers de sessão
_session_decisions: List[str] = []
_session_learnings: List[str] = []


def _sync_runtime_state() -> RuntimeState:
    """Materializa estado explícito a partir dos globals legados do módulo."""
    return build_runtime_state(
        backend_state=_backend_state,
        graph_cache=_graph_cache,
        graph_cache_time=_graph_cache_time,
        fs_cache=_FS_CACHE,
        fs_cache_time=_FS_CACHE_TIME,
        read_backends=_READ_BACKENDS,
        session_decisions=_session_decisions,
        session_learnings=_session_learnings,
        api_server_mode=API_SERVER_MODE,
    )

# ---------------------------------------------------------------------------
# Config YAML
# ---------------------------------------------------------------------------

from core.memory.config import load_yaml_config
_config = load_yaml_config(SINAPSE_HOME)

# ---------------------------------------------------------------------------
# Logging — wrapper que usa o _LOG_JSON do módulo atual
# ---------------------------------------------------------------------------

from core.memory.config import log as _core_log


def _log(level: str, event: str, **kwargs: Any) -> None:
    _core_log(level, event, log_json=_LOG_JSON, **kwargs)


# ---------------------------------------------------------------------------
# Cloud request helper (local — acessa _config e globals deste módulo)
# ---------------------------------------------------------------------------


def _cloud_request(endpoint: str, method: str = "POST", data: Optional[dict] = None) -> Any:
    """Realiza requisição HTTP para a API de Nuvem do Sinapse Agent."""
    cloud_cfg = _config.get("cloud", {})
    url_base = cloud_cfg.get("url", "http://localhost:37702").rstrip("/")
    url = f"{url_base}/api/v1/{endpoint.lstrip('/')}"

    api_key_raw = cloud_cfg.get("api_key", "")
    api_key = api_key_raw
    if api_key_raw:
        match = re.match(r"^\$?\{?([A-Za-z0-9_]+)\}?$", str(api_key_raw))
        if match:
            resolved = os.environ.get(match.group(1))
            if resolved:
                api_key = resolved
    if not api_key:
        api_key = os.environ.get("SINAPSE_API_KEY")
    if not api_key:
        _log("error", "cloud_api_key_missing", hint="configure cloud.api_key no sinapse.yaml ou SINAPSE_API_KEY")
        return None

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    req = Request(url, data=payload, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            res_data = resp.read().decode("utf-8")
            return json.loads(res_data) if res_data else None
    except (URLError, Exception) as e:
        _log("error", "cloud_request_failed", url=url, error=str(e))
        return None


# ---------------------------------------------------------------------------
# Circuit breaker — wrappers que passam o _backend_state deste módulo
# ---------------------------------------------------------------------------

from core.memory.circuit_breaker import is_backend_healthy as _cb_healthy
from core.memory.circuit_breaker import record_backend_result as _cb_record


def _is_backend_healthy(name: str) -> bool:
    return _cb_healthy(name, _backend_state, _log)


def _record_backend_result(name: str, success: bool) -> None:
    _cb_record(name, success, _backend_state)


# ---------------------------------------------------------------------------
# UMC save observation (acessa core.database diretamente)
# ---------------------------------------------------------------------------


def _umc_save_observation(title: str, content: str, obs_type: str = "event",
                          session_id: str = None, project: str = None) -> bool:
    if DRY_RUN:
        return True
    try:
        if SINAPSE_HOME not in sys.path:
            sys.path.insert(0, SINAPSE_HOME)
        from core.database import get_connection, execute_insert
        conn = get_connection()
        execute_insert(conn, "observations", {
            "title": title, "content": content, "type": obs_type,
            "session_id": session_id, "project": project,
        })
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _log("error", "umc_save_observation_failed", error=str(e))
        return False


# ---------------------------------------------------------------------------
# Backends — closures que lêem globals deste módulo no momento da chamada
# ---------------------------------------------------------------------------

from core.memory.backends.umc import backend_umc as _core_backend_umc
from core.memory.backends.neural_memory import backend_neural_memory as _core_backend_nmem
from core.memory.backends.http import backend_claude_mem as _core_backend_claude_mem
from core.memory.backends.http import backend_sqlite_vec as _core_backend_sqlite_vec
from core.memory.backends.graphify import backend_graphify as _core_backend_graphify
from core.memory.backends.graphify import load_graph as _core_load_graph
from core.memory.backends.graphify import validate_graph_schema as _validate_graph_schema
from core.memory.backends.filesystem import backend_filesystem as _core_backend_filesystem
from core.memory.backends.filesystem import fs_cache_put as _fs_cache_put


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ASCII", "ignore").decode("ASCII")
    return text.lower()


def _backend_umc(query: str) -> Optional[Dict[str, Any]]:
    return _core_backend_umc(query, _umc_query_hybrid, MAX_NODES, OBSERVATION_CHARS, _log)


def _backend_neural_memory(query: str) -> Optional[Dict[str, Any]]:
    return _core_backend_nmem(query, NMEM_BIN, NMEM_TIMEOUT, MAX_OBSERVATIONS, _log)


def _backend_sqlite_vec(query: str) -> Optional[Dict[str, Any]]:
    return _core_backend_sqlite_vec(
        query, VEC_WORKER_URL, CLAUDE_MEM_TIMEOUT, MAX_OBSERVATIONS, SEMANTIC_CONTEXT_CHARS, _log,
        urlopen_fn=urlopen,
    )


def _backend_claude_mem(query: str) -> Optional[Dict[str, Any]]:
    return _core_backend_claude_mem(
        query, CLAUDE_MEM_URL, CLAUDE_MEM_TIMEOUT, MAX_OBSERVATIONS, OBSERVATION_CHARS, SEMANTIC_CONTEXT_CHARS, _log,
        urlopen_fn=urlopen,
    )


def _load_graph() -> Optional[dict]:
    """Carrega graph.json com cache TTL. Atualiza os globals deste módulo."""
    global _graph_cache, _graph_cache_time
    holder = [_graph_cache_time]
    result = _core_load_graph(GRAPH_JSON, _graph_cache, holder, _GRAPH_CACHE_TTL)
    _graph_cache_time = holder[0]
    return result


def _backend_graphify(query: str) -> Optional[Dict[str, Any]]:
    global _graph_cache, _graph_cache_time
    holder = [_graph_cache_time]
    result = _core_backend_graphify(
        query, GRAPH_JSON, _graph_cache, holder, _GRAPH_CACHE_TTL, MAX_NODES, _log,
    )
    _graph_cache_time = holder[0]
    return result


def _backend_filesystem(query: str) -> Optional[Dict[str, Any]]:
    global _FS_CACHE, _FS_CACHE_TIME
    holder = [_FS_CACHE_TIME]
    result = _core_backend_filesystem(
        query, VAULT_DIR, _FS_CACHE, holder, _FS_CACHE_TTL,
        MAX_OBSERVATIONS, OBSERVATION_CHARS, _backend_umc, _log,
    )
    _FS_CACHE_TIME = holder[0]
    return result


def _backend_graphiti(query: str) -> Optional[Dict[str, Any]]:
    """Busca temporal com causalidade no Graphiti (orgão do lóbulo temporal).

    Contrato idêntico ao `backend_claude_mem` / `backend_graphify`:
    retorna dict {source, observations, count, query} ou None quando
    o FalkorDB está offline e o fallback também não tem o termo.

    Quando o FalkorDB responde, observations é a lista de edges com
    fact, valid_at, invalid_at, uuid. Quando cai no fallback JSON-lines
    (no proprio cortex/temporal/_global/), observations também é uma
    lista de edges (mesmo schema). Quando nem FalkorDB nem fallback
    retornam nada, retorna None — o orquestrador pula silenciosamente.
    """
    try:
        from integrations.graphiti import search_graph
    except ImportError:
        # integrations/graphiti nao clonado: pula silenciosamente.
        return None
    try:
        edges = search_graph(query, num_results=GRAPHITI_MAX_RESULTS)
    except Exception as e:
        _log("warning", "graphiti backend failed", query=query, error=str(e))
        return None
    if not edges:
        return None
    observations = [
        {
            "content": (e.get("fact") or "")[:OBSERVATION_CHARS],
            "uuid": e.get("uuid", ""),
            "valid_at": e.get("valid_at", ""),
            "invalid_at": e.get("invalid_at", ""),
        }
        for e in edges
    ]
    return {
        "source": "graphiti (temporal)",
        "observations": observations,
        "count": len(observations),
        "query": query,
    }


# Registra backends na ordem de prioridade
def register_backend(fn: Callable) -> None:
    """Registra um backend de busca. Ordem de registro = prioridade."""
    if fn not in _READ_BACKENDS:
        _READ_BACKENDS.append(fn)


register_backend(_backend_umc)
register_backend(_backend_neural_memory)
register_backend(_backend_sqlite_vec)
register_backend(_backend_claude_mem)
register_backend(_backend_graphify)
register_backend(_backend_graphiti)   # lóbulo temporal — causalidade com validade
register_backend(_backend_filesystem)


# ---------------------------------------------------------------------------
# Motor de busca unificado — lê _READ_BACKENDS e outros globals no call-time
# ---------------------------------------------------------------------------

from core.memory.context_fusion import query_vault_knowledge as _core_query_vault


def _query_vault_knowledge(query: str) -> Optional[Dict[str, Any]]:
    """Orquestra todos os backends em paralelo com circuit breaker e global timeout."""
    runtime = _sync_runtime_state()
    cloud_enabled = bool(_config.get("cloud", {}).get("enabled"))
    return _core_query_vault(
        query=query,
        read_backends=runtime.read_backends,
        backend_state=runtime.backend_state,
        max_observations=MAX_OBSERVATIONS,
        max_nodes=MAX_NODES,
        global_query_timeout=GLOBAL_QUERY_TIMEOUT,
        is_healthy_fn=_cb_healthy,
        record_result_fn=_cb_record,
        log_fn=_log,
        cloud_enabled=cloud_enabled,
        cloud_query_fn=lambda q: _cloud_request("query", method="POST", data={"query": q}),
        api_server_mode=runtime.api_server_mode,
    )


# ---------------------------------------------------------------------------
# Write helpers — lêem globals deste módulo no call-time
# ---------------------------------------------------------------------------

from core.memory.writers import atomic_write as _atomic_write
from core.memory.writers import sanitize_slug as _sanitize_slug
from core.memory.writers import validate_frontmatter_yaml as _validate_frontmatter_yaml
from core.memory.writers import save_decision as _core_save_decision
from core.memory.writers import save_learning as _core_save_learning
from core.memory.writers import update_current_state as _core_update_current_state


def _save_decision(title: str, content: str) -> Optional[str]:
    return _core_save_decision(
        title, content, DECISIONS_DIR, DRY_RUN, _log, _umc_save_observation,
        bool(_config.get("cloud", {}).get("enabled")), API_SERVER_MODE, _cloud_request,
    )


def _save_learning(title: str, content: str) -> Optional[str]:
    return _core_save_learning(
        title, content, PATTERNS_FILE, DRY_RUN, _log, _umc_save_observation,
        bool(_config.get("cloud", {}).get("enabled")), API_SERVER_MODE, _cloud_request,
    )


def _update_current_state(decisions: List[str], learnings: List[str], summary: str) -> None:
    _core_update_current_state(
        decisions, learnings, summary, MEMORY_FILE, DRY_RUN, _log,
        bool(_config.get("cloud", {}).get("enabled")), API_SERVER_MODE, _cloud_request,
    )


# ---------------------------------------------------------------------------
# Hooks — lêem globals deste módulo no call-time
# ---------------------------------------------------------------------------

from core.memory.hooks import (
    format_context as _format_context_pure,
    pre_prompt_build as _core_pre_prompt_build,
    post_tool_use as _core_post_tool_use,
    post_session_end as _core_post_session_end,
    on_session_finalize as _core_on_session_finalize,
)


def _format_context(ctx: Dict[str, Any]) -> str:
    return _format_context_pure(ctx, MAX_CONTEXT_CHARS)


def _pre_prompt_build(user_message: str = "", system_message: str = "",
                      memory_context: str = "", **_kwargs: Any) -> Dict[str, Any]:
    return _core_pre_prompt_build(
        user_message, system_message, _query_vault_knowledge, MAX_CONTEXT_CHARS, _log,
    )


def _post_tool_use(tool_name: str = "", tool_args: Optional[Dict[str, Any]] = None,
                   tool_result: Any = None, **_kwargs: Any) -> None:
    runtime = _sync_runtime_state()
    _core_post_tool_use(
        tool_name, tool_args, DECISION_TOOLS, LEARNING_SIGNALS,
        _save_decision, _save_learning, runtime.session_decisions, runtime.session_learnings,
    )


def _post_session_end(session_summary: str = "", **_kwargs: Any) -> None:
    runtime = _sync_runtime_state()
    _core_post_session_end(
        session_summary, runtime.session_decisions, runtime.session_learnings, _update_current_state,
    )


def _on_session_finalize(session_id: str = "", platform: str = "", **_kwargs: Any) -> None:
    runtime = _sync_runtime_state()
    _core_on_session_finalize(
        session_id, platform, VAULT_DIR, runtime.session_decisions, runtime.session_learnings, _log,
    )


# ---------------------------------------------------------------------------
# Sync bidirecional: claude-mem → vault
# ---------------------------------------------------------------------------


def sync_claude_mem_to_vault() -> None:
    """Exporta observações recentes do claude-mem para o vault via API HTTP."""
    try:
        req = Request(f"{CLAUDE_MEM_URL}/api/search?query=&limit=10", method="GET")
        with urlopen(req, timeout=CLAUDE_MEM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            for item in data.get("items", []):
                obs_id = item.get("id", "unknown")
                content = item.get("content") or item.get("excerpt", "")
                if content:
                    _save_decision(title=f"claude-mem observation {obs_id}", content=content)
    except (URLError, OSError, json.JSONDecodeError, ValueError) as e:
        _log("error", "claude_mem_sync_failed", error=str(e))


# ---------------------------------------------------------------------------
# Health check — delega para core.memory.health passando globals atuais
# ---------------------------------------------------------------------------

from core.memory.health import health_check as _core_health_check


def health_check() -> Dict[str, Any]:
    """Retorna status completo de todos os backends e componentes."""
    return _core_health_check(
        NMEM_BIN, GRAPH_JSON, CLAUDE_MEM_URL, VAULT_DIR, len(_READ_BACKENDS),
    )


# ---------------------------------------------------------------------------
# Registro no Hermes
# ---------------------------------------------------------------------------


def register(ctx: Any) -> None:
    """Registra hooks de leitura e escrita no Hermes."""
    ctx.register_hook("pre_gateway_dispatch", _pre_prompt_build)
    ctx.register_hook("post_tool_call", _post_tool_use)
    ctx.register_hook("on_session_end", _post_session_end)
    ctx.register_hook("on_session_finalize", _on_session_finalize)


# ---------------------------------------------------------------------------
# Module exports for testability
# ---------------------------------------------------------------------------

__all__ = [
    "register_backend",
    "health_check",
    "sync_claude_mem_to_vault",
    "_pre_prompt_build",
    "_post_tool_use",
    "_on_session_finalize",
    "_post_session_end",
    "_query_vault_knowledge",
    "_backend_graphify",
    "_backend_claude_mem",
    "_backend_neural_memory",
    "_save_decision",
    "_save_learning",
    "_update_current_state",
    "_format_context",
    "_sanitize_slug",
    "_atomic_write",
    "_normalize",
    "_validate_graph_schema",
    "_validate_frontmatter_yaml",
    "_load_graph",
    "_log",
    "SINAPSE_HOME",
    "VAULT_DIR",
    "GRAPH_JSON",
    "DECISIONS_DIR",
    "MEMORY_FILE",
    "PATTERNS_FILE",
    "MAX_NODES",
    "MAX_OBSERVATIONS",
    "MAX_CONTEXT_CHARS",
    "NMEM_BIN",
    "NMEM_TIMEOUT",
]
