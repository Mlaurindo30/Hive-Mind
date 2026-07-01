"""K10 — Workspace context para multi-tenancy / federacao.

Fornece um escopo de request (via contextvars) que propaga `workspace_id`
sem precisar passa-lo explicitamente em cada chamada. Usado por:

- `scripts/services/sinapse-api.py` (FastAPI): middleware que le o header
  `X-Workspace-Id` e injeta no contextvar.
- `scripts/services/sinapse-mcp.py` (MCP stdio): cada tool recebe
  `workspace_id` como argumento explicito OU pega do env
  `HIVE_DEFAULT_WORKSPACE`.
- `core/retrieval/`, `core/vector_backend.py`: leem via
  `current_workspace_id()` e adicionam como filtro nas queries.

ADR-019 (v3.7.9): workspace_id vira contrato de primeiro-class para
qualquer operacao que cria/le neurons/observations. Single-tenant
funciona com `default` implicito; multi-tenant exige que cada chamada
especifique um workspace.

Politica de validacao:
- workspace_id deve ser uma string ASCII alfanumerica + `-`/`_`, 1-64 chars
- `default` e o unico workspace reservado (single-tenant)
- workspace_id `__all__` e' reservado para operacoes cross-workspace
  (admin/diagnostico). Apenas `scripts/health/*` e o audit podem usa-lo.
"""
from __future__ import annotations

import contextvars
import os
import re
from contextlib import contextmanager
from typing import Iterator

# Regex: 1-64 chars, ^[a-zA-Z0-9][a-zA-Z0-9_-]*$, nao pode terminar em -/_.
# Rejeita: espacos, pontos, slashes, unicode, empty, leading -/_.
# 1-64 chars, ^[a-zA-Z0-9][a-zA-Z0-9_-]*$, nao pode terminar em -/_.
# (a verificacao de "nao terminar em -/_" e' feita em _is_valid_workspace)
_VALID_WORKSPACE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_RESERVED = frozenset({"default", "__all__"})

# Contextvar default = "default" (single-tenant).
# Cada request FastAPI seta o seu proprio via set_workspace().
_workspace_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "hive_workspace", default="default"
)


def current_workspace_id() -> str:
    """Retorna o workspace_id do contexto atual (default: 'default')."""
    return _workspace_var.get()


def set_workspace(workspace_id: str) -> contextvars.Token:
    """Define o workspace_id do contexto atual. Valida o formato.

    Raises ValueError se o nome for invalido. O Token retornado deve
    ser usado com `_workspace_var.reset(token)` em finally blocks.
    """
    if not _is_valid_workspace(workspace_id):
        raise ValueError(
            f"workspace_id invalido: {workspace_id!r}. "
            f"Use [a-zA-Z0-9][a-zA-Z0-9_-]{{0,63}}."
        )
    return _workspace_var.set(workspace_id)


def reset_workspace(token: contextvars.Token) -> None:
    _workspace_var.reset(token)


@contextmanager
def workspace_scope(workspace_id: str) -> Iterator[str]:
    """Context manager que seta workspace_id e restaura no finally.

    Uso:
        with workspace_scope("acme") as ws:
            neuron = add_observation(content="...", workspace_id=ws)
    """
    token = set_workspace(workspace_id)
    try:
        yield workspace_id
    finally:
        reset_workspace(token)


def _is_valid_workspace(workspace_id: str) -> bool:
    if not isinstance(workspace_id, str):
        return False
    if not _VALID_WORKSPACE.match(workspace_id):
        return False
    # Nao pode terminar em - ou _ (conflito com path-like formats)
    if workspace_id[-1] in ("-", "_"):
        return False
    return True


def is_reserved(workspace_id: str) -> bool:
    """True se o workspace_id e' reservado (`default` ou `__all__`)."""
    return workspace_id in _RESERVED


def default_workspace_from_env() -> str:
    """Le HIVE_DEFAULT_WORKSPACE do env, com fallback 'default'.

    Usado por servicos que nao recebem header (sinapse-mcp stdio):
    cada tool pega o valor daqui. Permite operator override sem
    mexer no codigo.
    """
    candidate = os.environ.get("HIVE_DEFAULT_WORKSPACE", "default").strip()
    if not _is_valid_workspace(candidate):
        return "default"
    return candidate


__all__ = [
    "current_workspace_id",
    "default_workspace_from_env",
    "is_reserved",
    "is_valid_workspace_id",
    "reset_workspace",
    "set_workspace",
    "workspace_scope",
]


def is_valid_workspace_id(workspace_id: str) -> bool:
    """Wrapper publico para validacao. Retorna True se o nome e' valido.

    Usado por middlewares (sinapse-api) que precisam validar sem
    levantar excecao. Internamente chama o helper privado.
    """
    return _is_valid_workspace(workspace_id)
