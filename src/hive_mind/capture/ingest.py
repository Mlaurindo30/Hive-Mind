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

import os
import sqlite3
import threading
import time
from typing import Any, Callable, Optional
from pathlib import Path

from hive_mind.capture import engine
from hive_mind.capture.identity import apply_identity, resolve_identity
from hive_mind.capture.models import CaptureIdentity, IdentityRefused, IdentityStatus

SeenStore = engine.SeenStore

_resolver_singleton = None


_identity_store_singleton = None
_bridge_retry_lock = threading.Lock()
_bridge_retry_sessions: set[tuple[str, str]] = set()


# O DB do claude-mem vive em {ROOT}/claude-mem/data (projeto, gitignored), não
# em ~/.claude-mem. O fallback usa o ROOT do projeto quando CLAUDE_MEM_DB não é
# definido pelo ambiente (o supervisor/launcher o define explicitamente).
CLAUDE_MEM_DB = Path(
    os.environ.get(
        "CLAUDE_MEM_DB",
        str(Path(__file__).resolve().parents[3] / "claude-mem" / "data" / "claude-mem.db"),
    )
)


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


def _sync_sdk_session_project(*, content_session_id: str, provider: str,
                              project_name: str) -> None:
    """Keep Claude Mem's session grouping aligned with the canonical identity.

    The worker can reuse an existing `sdk_sessions` row for the same
    `content_session_id`. When that row was first created from degraded
    evidence, some Claude Mem builds keep the old `project` label even after a
    later replay arrives with a canonical workspace-backed identity. Updating
    the row here makes the grouping deterministic from the side that already
    knows the canonical answer.
    """
    if not content_session_id or not project_name or not CLAUDE_MEM_DB.exists():
        return
    conn = sqlite3.connect(CLAUDE_MEM_DB, timeout=5)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute(
            """
            UPDATE sdk_sessions
               SET project = ?
             WHERE content_session_id = ?
               AND COALESCE(NULLIF(platform_source, ''), 'claude') = ?
               AND (project IS NULL OR project = '' OR project LIKE 'Unclassified (%)')
            """,
            (project_name, content_session_id, provider),
        )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
    finally:
        conn.close()


def _collect_bridge_source_ids(*, content_session_id: str, provider: str,
                               deadline_seconds: float) -> list[str]:
    source_ids: list[str] = []
    deadline = time.monotonic() + max(0.0, deadline_seconds)
    while True:
        conn = sqlite3.connect(CLAUDE_MEM_DB, timeout=5)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=5000")
            rows = conn.execute(
                """
                SELECT DISTINCT memory_session_id
                  FROM sdk_sessions
                 WHERE content_session_id = ?
                   AND COALESCE(NULLIF(platform_source, ''), 'claude') = ?
                   AND COALESCE(memory_session_id, '') <> ''
                """,
                (content_session_id, provider),
            ).fetchall()
            memory_session_ids = [str(row["memory_session_id"]).strip()
                                  for row in rows if row["memory_session_id"]]
            if memory_session_ids:
                placeholders = ",".join("?" for _ in memory_session_ids)
                for table in ("observations", "discoveries", "session_summaries"):
                    table_exists = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,),
                    ).fetchone()
                    if table_exists is None:
                        continue
                    columns = {
                        row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                    }
                    if "memory_session_id" not in columns:
                        continue
                    for row in conn.execute(
                        f"SELECT id FROM {table} WHERE memory_session_id IN ({placeholders})",
                        tuple(memory_session_ids),
                    ).fetchall():
                        source_ids.append(f"claude-mem:{table}:{row['id']}")
        except sqlite3.Error:
            return []
        finally:
            conn.close()

        if source_ids or time.monotonic() >= deadline:
            break
        time.sleep(0.25)
    return list(dict.fromkeys(source_ids))


def _bridge_recent_session_into_umc(*, content_session_id: str, provider: str,
                                    identity_store=None,
                                    deadline_seconds: float = 5.0) -> bool:
    """Promote the just-posted session into the UMC without waiting for cron.

    The runtime scheduler is passive on this host and the Windows bridge task
    is periodic, so newly captured summaries can remain absent from the UMC
    until the next scheduled run. This bridges only the rows already tied to
    the current `content_session_id`, keeping the hot path narrow and
    idempotent.
    """
    if not content_session_id or not CLAUDE_MEM_DB.exists():
        return False
    source_ids = _collect_bridge_source_ids(
        content_session_id=content_session_id,
        provider=provider,
        deadline_seconds=deadline_seconds,
    )
    if not source_ids:
        return False

    try:
        from core.knowledge.claude_mem_bridge import bridge as bridge_claude_mem

        stats = bridge_claude_mem(
            cm_db=CLAUDE_MEM_DB,
            limit=len(source_ids),
            source_ids=source_ids,
            identity_store=identity_store,
        )
        if identity_store is not None and (stats.get("inserted") or stats.get("skipped")):
            try:
                identity_store.mark_observed(content_session_id)
                identity_store.mark_bridged(content_session_id)
            except Exception:
                pass
            return True
    except Exception:
        return False
    return False


def _schedule_bridge_retry(*, content_session_id: str, provider: str,
                           identity_store=None, delay_seconds: float = 1.0,
                           deadline_seconds: float = 90.0) -> None:
    if not content_session_id:
        return
    key = (provider, content_session_id)
    with _bridge_retry_lock:
        if key in _bridge_retry_sessions:
            return
        _bridge_retry_sessions.add(key)

    def _worker() -> None:
        try:
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            _bridge_recent_session_into_umc(
                content_session_id=content_session_id,
                provider=provider,
                identity_store=identity_store,
                deadline_seconds=deadline_seconds,
            )
        finally:
            with _bridge_retry_lock:
                _bridge_retry_sessions.discard(key)

    threading.Thread(
        target=_worker,
        name=f"hive-bridge-{provider}-{content_session_id[:8]}",
        daemon=True,
    ).start()


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

    if registry is not None and content_session_id:
        # Not gated on the count. `emit` returns how much content was *new*,
        # which is a different question from whether the session was
        # delivered: a session whose records were already seen emits zero and
        # is still posted. Gating on it left such sessions PENDING forever, so
        # the bridge could never advance them — found by a real Codex session
        # in D004-M, where the observation arrived and the state did not move.
        registry.mark_posted(content_session_id)
    if content_session_id:
        _sync_sdk_session_project(
            content_session_id=content_session_id,
            provider=identity.provider,
            project_name=identity.project_name,
        )
        bridged = _bridge_recent_session_into_umc(
            content_session_id=content_session_id,
            provider=identity.provider,
            identity_store=registry,
        )
        if not bridged:
            _schedule_bridge_retry(
                content_session_id=content_session_id,
                provider=identity.provider,
                identity_store=registry,
            )
    return emitted


def ingest_many(provider: str, sessions, store, **kwargs) -> int:
    total = 0
    for session in sessions or ():
        if isinstance(session, dict):
            total += ingest(provider, session, store, **kwargs)
    return total


__all__ = ["ingest", "ingest_many", "SeenStore", "default_resolver"]
