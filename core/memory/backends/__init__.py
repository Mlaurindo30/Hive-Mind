"""
Backends de busca para Sinapse Memory.

Cada função recebe todos os parâmetros que precisa (sem acessar globals
de outros módulos). O chamador — plugins/hermes/sinapse-memory.py — passa
suas próprias variáveis de módulo como argumentos. Isso garante que
monkeypatch.setattr("sinapse_memory.X", ...) afete os valores usados aqui.
"""

from core.memory.backends.filesystem import backend_filesystem, fs_cache_put
from core.memory.backends.graphify import (
    backend_graphify,
    load_graph,
    validate_graph_schema,
)
from core.memory.backends.neural_memory import backend_neural_memory
from core.memory.backends.http import backend_claude_mem, backend_sqlite_vec
from core.memory.backends.umc import backend_umc

__all__ = [
    "backend_filesystem",
    "fs_cache_put",
    "backend_graphify",
    "load_graph",
    "validate_graph_schema",
    "backend_neural_memory",
    "backend_claude_mem",
    "backend_sqlite_vec",
    "backend_umc",
]
