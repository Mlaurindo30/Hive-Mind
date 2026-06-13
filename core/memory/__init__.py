"""
core.memory — Pacote de lógica de memória do Sinapse Agent.

Este pacote contém a lógica pura (sem globals de módulo).
O módulo plugins/hermes/sinapse-memory.py é o orquestrador: mantém todos os
globals mutáveis e delega a lógica para cá, passando os valores correntes
como parâmetros. Isso preserva 100% de compatibilidade com monkeypatch de testes.

Submodules:
  config          — constantes default e helper de log
  circuit_breaker — is_backend_healthy / record_backend_result
  context_fusion  — query_vault_knowledge / _fuse_contexts
  writers         — save_decision / save_learning / update_current_state
  hooks           — pre_prompt_build / post_tool_use / post_session_end
  health          — health_check
  backends/       — implementações dos backends de busca
"""

from core.memory.config import log, load_yaml_config
from core.memory.circuit_breaker import is_backend_healthy, record_backend_result
from core.memory.context_fusion import query_vault_knowledge, _fuse_contexts
from core.memory.writers import (
    sanitize_slug,
    atomic_write,
    validate_frontmatter_yaml,
    save_decision,
    save_learning,
    update_current_state,
)
from core.memory.hooks import (
    classify_message,
    generate_plan,
    format_context,
    pre_prompt_build,
    post_tool_use,
    post_session_end,
    on_session_finalize,
)
from core.memory.health import health_check
from core.memory.backends.umc import backend_umc
from core.memory.backends.neural_memory import backend_neural_memory
from core.memory.backends.http import backend_claude_mem, backend_sqlite_vec
from core.memory.backends.graphify import backend_graphify, load_graph, validate_graph_schema
from core.memory.backends.filesystem import backend_filesystem, fs_cache_put

__all__ = [
    # config
    "log",
    "load_yaml_config",
    # circuit_breaker
    "is_backend_healthy",
    "record_backend_result",
    # context_fusion
    "query_vault_knowledge",
    "_fuse_contexts",
    # writers
    "sanitize_slug",
    "atomic_write",
    "validate_frontmatter_yaml",
    "save_decision",
    "save_learning",
    "update_current_state",
    # hooks
    "classify_message",
    "generate_plan",
    "format_context",
    "pre_prompt_build",
    "post_tool_use",
    "post_session_end",
    "on_session_finalize",
    # health
    "health_check",
    # backends
    "backend_umc",
    "backend_neural_memory",
    "backend_claude_mem",
    "backend_sqlite_vec",
    "backend_graphify",
    "load_graph",
    "validate_graph_schema",
    "backend_filesystem",
    "fs_cache_put",
]
