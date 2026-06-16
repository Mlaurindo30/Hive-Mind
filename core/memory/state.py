"""Runtime state models for the Sinapse memory orchestrator.

This module centralizes mutable orchestrator state so runtime behavior can be
observed and reasoned about explicitly, while still allowing legacy globals in
`plugins/hermes/sinapse-memory.py` for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class RuntimeState:
    """Explicit mutable runtime state for plugin orchestration."""

    backend_state: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    graph_cache: Dict[str, Any] = field(default_factory=dict)
    graph_cache_time: float = 0.0
    fs_cache: Dict[str, Any] = field(default_factory=dict)
    fs_cache_time: float = 0.0
    read_backends: List[Callable[..., Any]] = field(default_factory=list)
    session_decisions: List[str] = field(default_factory=list)
    session_learnings: List[str] = field(default_factory=list)
    api_server_mode: bool = False


def build_runtime_state(
    backend_state: Dict[str, Dict[str, Any]],
    graph_cache: Dict[str, Any],
    graph_cache_time: float,
    fs_cache: Dict[str, Any],
    fs_cache_time: float,
    read_backends: List[Callable[..., Any]],
    session_decisions: List[str],
    session_learnings: List[str],
    api_server_mode: bool,
) -> RuntimeState:
    """Create a RuntimeState snapshot from legacy mutable globals."""

    return RuntimeState(
        backend_state=backend_state,
        graph_cache=graph_cache,
        graph_cache_time=graph_cache_time,
        fs_cache=fs_cache,
        fs_cache_time=fs_cache_time,
        read_backends=read_backends,
        session_decisions=session_decisions,
        session_learnings=session_learnings,
        api_server_mode=api_server_mode,
    )
