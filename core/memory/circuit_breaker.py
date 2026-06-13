"""
Circuit breaker para backends de busca do Sinapse Memory.

Design: completamente stateless — o estado é passado como parâmetro (dict)
e retornado modificado. Isso evita qualquer dependência de globals do módulo
pai e permite que os testes façam monkeypatch livremente.
"""

import time
from typing import Any, Callable, Dict, Optional


def is_backend_healthy(
    name: str,
    backend_state: Dict[str, Dict[str, Any]],
    log_fn: Optional[Callable] = None,
) -> bool:
    """
    Verifica se o backend está saudável (circuit breaker simples).
    Pula backends com >= 3 falhas nos últimos `cooldown` segundos.
    """
    state = backend_state.get(name, {})
    failures = state.get("failures", 0)
    last_failure = state.get("last_failure", 0)
    cooldown = state.get("cooldown", 30)

    if failures >= 3 and (time.time() - last_failure) < cooldown:
        if log_fn:
            log_fn("warn", "circuit_breaker_open", backend=name, failures=failures)
        return False
    return True


def record_backend_result(
    name: str,
    success: bool,
    backend_state: Dict[str, Dict[str, Any]],
) -> None:
    """
    Registra resultado de um backend no estado do circuit breaker.
    Modifica `backend_state` in-place.
    """
    state = backend_state.setdefault(
        name, {"failures": 0, "last_failure": 0, "cooldown": 30}
    )
    if success:
        state["failures"] = 0
    else:
        state["failures"] += 1
        state["last_failure"] = time.time()
