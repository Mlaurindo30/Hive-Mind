"""The canonical capture entrypoint (D004-R2).

Every entrypoint calls this. None of them resolves identity itself — that is
the whole point. `capture-realtime.py` used to call `attach_project_identity`
and `capture-tailer.py` did not, which is how a free-text label reached the
field Claude Mem groups by.

    provider source → parser → ingest() → Claude Mem

`ingest` enforces identity, then hands the normalised session to the transport
engine. A session whose identity cannot be established is refused *before*
anything is written, so there is no half-delivered state to reconcile.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from hive_mind.capture import engine
from hive_mind.capture.identity import apply_identity, resolve_identity
from hive_mind.capture.models import CaptureIdentity, IdentityRefused, IdentityStatus

SeenStore = engine.SeenStore

_resolver_singleton = None


def default_resolver():
    """One resolver per process. Building it walks git; doing that per session
    would make the tailer's cost scale with the number of files it scans."""
    global _resolver_singleton
    if _resolver_singleton is None:
        from hive_mind.projects.identity import ProjectIdentityResolver

        _resolver_singleton = ProjectIdentityResolver()
    return _resolver_singleton


def ingest(
    provider: str,
    session: dict,
    store: "engine.SeenStore",
    *,
    resolver=None,
    default_surface: Optional[str] = None,
    on_refused: Optional[Callable[[IdentityRefused], None]] = None,
    on_degraded: Optional[Callable[[CaptureIdentity], None]] = None,
) -> int:
    """Deliver one session. Returns how many records were emitted.

    `on_refused` and `on_degraded` let an entrypoint log without deciding:
    the decision has already been made here, and the callback only observes
    it. An entrypoint that ignores them loses visibility, not correctness.
    """
    try:
        identity = resolve_identity(
            provider, session,
            resolver=resolver or default_resolver(),
            default_surface=default_surface,
        )
    except IdentityRefused as refused:
        if on_refused is not None:
            on_refused(refused)
        return 0

    if identity.status is IdentityStatus.UNCLASSIFIED and on_degraded is not None:
        on_degraded(identity)

    return engine.emit(provider, apply_identity(session, identity), store)


def ingest_many(provider: str, sessions, store, **kwargs) -> int:
    total = 0
    for session in sessions or ():
        if isinstance(session, dict):
            total += ingest(provider, session, store, **kwargs)
    return total


__all__ = ["ingest", "ingest_many", "SeenStore", "default_resolver"]
