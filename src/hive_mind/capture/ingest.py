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


_identity_store_singleton = None


def default_identity_store():
    """One store per process, opened lazily.

    Returns None rather than raising if the store cannot be opened: capture
    that cannot record its decision must not deliver (see `ingest`), but a
    caller who passes `identity_store=` explicitly — every test does — should
    not pay for a default it never uses.
    """
    global _identity_store_singleton
    if _identity_store_singleton is None:
        try:
            from hive_mind.capture.identity_store import IdentityStore

            _identity_store_singleton = IdentityStore()
        except Exception:
            return None
    return _identity_store_singleton


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
    identity_store=None,
    on_refused: Optional[Callable[[IdentityRefused], None]] = None,
    on_degraded: Optional[Callable[[CaptureIdentity], None]] = None,
    on_conflict: Optional[Callable[[Exception], None]] = None,
) -> int:
    """Deliver one session. Returns how many records were emitted.

    The order below is the contract, not an implementation detail: the
    identity decision is **written before the post**. The worker generates
    observations itself and drops our metadata (M14-A), so the only way the
    bridge can recover a project id later is from a decision recorded against
    the session id — and a decision recorded *after* delivery would be missing
    for exactly the events that crashed in between.

    `on_refused`, `on_degraded` and `on_conflict` let an entrypoint log
    without deciding: the decision has already been made here, and the
    callback only observes it. An entrypoint that ignores them loses
    visibility, not correctness.
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

    normalized = apply_identity(session, identity)
    registry = identity_store if identity_store is not None else default_identity_store()
    content_session_id = str(session.get("sid") or "").strip()

    if registry is not None and content_session_id:
        from hive_mind.capture.identity_store import IdentityStoreError

        try:
            registry.record_pending(
                content_session_id=content_session_id,
                provider=identity.provider,
                surface=identity.surface,
                project_id=identity.project_id,
                project_name=identity.project_name,
                identity=identity.envelope,
                raw_project_label=identity.raw_label,
            )
        except IdentityStoreError as problem:
            # Nothing is delivered without a recoverable decision. A conflict
            # here means the same session already decided differently, which
            # is a defect upstream — posting anyway would put an event in the
            # store that the bridge could never attribute.
            if on_conflict is not None:
                on_conflict(problem)
            return 0

    try:
        emitted = engine.emit(provider, normalized, store)
    except Exception as failure:
        if registry is not None and content_session_id:
            registry.mark_failed(content_session_id, str(failure))
        raise

    if registry is not None and content_session_id and emitted:
        registry.mark_posted(content_session_id)
    return emitted


def ingest_many(provider: str, sessions, store, **kwargs) -> int:
    total = 0
    for session in sessions or ():
        if isinstance(session, dict):
            total += ingest(provider, session, store, **kwargs)
    return total


__all__ = ["ingest", "ingest_many", "SeenStore", "default_resolver"]
