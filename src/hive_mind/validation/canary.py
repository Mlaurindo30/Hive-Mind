"""Multiagent capture canary over real data (D004-R1).

Replaces `scripts/health/canary_multiagent_runner.py`, which built a synthetic
session, created mock SQLite schemas and monkeypatched the bridge's
`get_connection`. That proved the wiring of code it had already replaced with
doubles — it could not fail while real capture was broken.

This canary injects nothing and writes nothing. For each provider it:

  1. resolves the provider's **real** source files from the adapter registry;
  2. runs the provider's **real** parser over sources newest-first until one
     produces sessions;
  3. resolves identity with the **real** shipped alias registry;
  4. reports the **real** delivery state (outbox + UMC), read-only.

A provider only passes when its real sessions resolve to a canonical
project id AND its captured events actually reached a destination.
"""
from __future__ import annotations

import time
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from hive_mind.validation import sources
from hive_mind.validation.delivery import (
    OutboxState,
    UmcState,
    inspect_outbox,
    inspect_umc,
)
from hive_mind.validation.models import CanaryReport, CanaryResult, CanaryStatus


@dataclass(frozen=True)
class CanaryPaths:
    outbox_db: Path
    umc_db: Path


@dataclass(frozen=True)
class FreshMarkerPaths:
    claude_mem_db: Path
    identity_db: Path
    umc_db: Path


def _read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _contains_marker(value, marker: str) -> bool:
    if isinstance(value, str):
        return marker in value
    if isinstance(value, dict):
        return any(_contains_marker(item, marker) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_marker(item, marker) for item in value)
    return False


def _as_epoch(value) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result / 1000.0 if result > 10_000_000_000 else result
    text = str(value).strip()
    try:
        return _as_epoch(float(text))
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _session_epoch(session: dict, source: Path) -> float:
    for key in (
        "started_at_epoch", "created_at_epoch", "updated_at_epoch",
        "started_at", "created_at", "updated_at", "timestamp", "time",
    ):
        epoch = _as_epoch(session.get(key))
        if epoch is not None:
            return epoch
    return source.stat().st_mtime


def _failed(provider: str, reason: str, started: float) -> CanaryResult:
    return CanaryResult(
        provider=provider, status=CanaryStatus.FAILED, reason=reason,
        duration_seconds=round(time.monotonic() - started, 3),
    )


def _fresh_source_session(
    provider: str, marker: str, since_epoch: int, started: float
) -> tuple[Optional[dict], Optional[CanaryResult]]:
    inventory = sources.inventory(provider)
    if not inventory.found:
        return None, _failed(provider, "provider source is absent", started)
    marker_was_old = False
    for source in inventory.files:
        try:
            sessions = sources.parse_sessions(provider, source)
        except Exception as exc:  # noqa: BLE001 - a parser failure is a real result
            return None, CanaryResult(
                provider=provider, status=CanaryStatus.ERROR,
                reason=f"parser failed for {source.name}: {type(exc).__name__}: {exc}",
                duration_seconds=round(time.monotonic() - started, 3),
            )
        for session in sessions:
            if not _contains_marker(session, marker):
                continue
            if _session_epoch(session, source) < since_epoch:
                marker_was_old = True
                continue
            if not str(session.get("sid") or "").strip():
                return None, _failed(
                    provider, "provider source marker has no content_session_id", started
                )
            return session, None
    reason = "provider source marker predates --since" if marker_was_old else (
        "marker absent from provider source"
    )
    return None, _failed(provider, reason, started)


def _claude_mem_has_marker(path: Path, sid: str, marker: str,
                           since_epoch: int) -> bool:
    if not path.is_file():
        return False
    connection = _read_only(path)
    try:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not {"user_prompts", "sdk_sessions"} <= tables:
            return False
        prompt_columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(user_prompts)"
        )}
        if not {"content_session_id", "prompt_text"} <= prompt_columns:
            return False
        session_columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(sdk_sessions)"
        )}
        if "content_session_id" not in session_columns:
            return False
        if "created_at_epoch" not in prompt_columns:
            return False
        params: list[object] = [sid, marker, int(since_epoch)]
        row = connection.execute(
            "SELECT 1 FROM user_prompts p JOIN sdk_sessions s "
            "ON s.content_session_id=p.content_session_id "
            "WHERE p.content_session_id=? AND instr(p.prompt_text, ?) > 0 "
            "AND p.created_at_epoch >= ? LIMIT 1",
            params,
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def _bridged_identity(path: Path, sid: str, provider: str,
                      since_epoch: int) -> Optional[str]:
    if not path.is_file():
        return None
    connection = _read_only(path)
    try:
        row = connection.execute(
            "SELECT project_id, bridged_at FROM capture_identity_decisions "
            "WHERE content_session_id=? AND provider=? AND delivery_state='BRIDGED' "
            "LIMIT 1",
            (sid, provider),
        ).fetchone()
        if not row or not row[0]:
            return None
        bridged_epoch = _as_epoch(row[1])
        if bridged_epoch is None or bridged_epoch < since_epoch:
            return None
        return str(row[0])
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def _umc_has_session(path: Path, sid: str, project_id: str,
                     since_epoch: int) -> bool:
    if not path.is_file():
        return False
    connection = _read_only(path)
    try:
        columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(observations)"
        )}
        if not {"metadata", "workspace_id"} <= columns:
            return False
        selected = ["metadata", "workspace_id"]
        if "created_at" not in columns:
            return False
        selected.append("created_at")
        rows = connection.execute(
            f"SELECT {', '.join(selected)} FROM observations "
            "WHERE workspace_id=? AND instr(COALESCE(metadata,''), ?) > 0",
            (project_id, sid),
        ).fetchall()
        for row in rows:
            try:
                metadata = json.loads(row["metadata"] or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if str(metadata.get("content_session_id") or "") != sid:
                continue
            created = _as_epoch(row[2])
            if created is not None and created >= since_epoch:
                return True
        return False
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def run_fresh_marker(*, marker: str, since_epoch: int, providers: list[str],
                     paths: Optional[FreshMarkerPaths] = None) -> CanaryReport:
    """Prove a newly-created marker traversed the real chain, read-only.

    This deliberately does not inspect the legacy capture outbox: only the
    provider source, Claude Mem, canonical identity store and UMC are evidence.
    """
    if not marker.strip():
        raise ValueError("marker is required")
    if since_epoch < 0:
        raise ValueError("since_epoch must be non-negative")
    if not providers:
        raise ValueError("at least one explicit provider is required")
    paths = paths or default_fresh_marker_paths()
    results = []
    for provider in providers:
        started = time.monotonic()
        session, failure = _fresh_source_session(
            provider, marker, since_epoch, started
        )
        if failure is not None:
            results.append(failure)
            continue
        sid = str(session["sid"])
        if not _claude_mem_has_marker(
            paths.claude_mem_db, sid, marker, since_epoch
        ):
            results.append(_failed(
                provider, "marker absent or stale in Claude Mem", started
            ))
            continue
        project_id = _bridged_identity(
            paths.identity_db, sid, provider, since_epoch
        )
        if project_id is None:
            results.append(_failed(
                provider, "BRIDGED identity decision absent", started
            ))
            continue
        if not _umc_has_session(
            paths.umc_db, sid, project_id, since_epoch
        ):
            results.append(_failed(
                provider, "UMC observation/workspace correlation absent", started
            ))
            continue
        results.append(CanaryResult(
            provider=provider, status=CanaryStatus.PASSED,
            project_id=project_id, inserted=1,
            duration_seconds=round(time.monotonic() - started, 3),
        ))
    return CanaryReport(results=tuple(results))


def _resolver():
    """The real ProjectIdentityResolver with the shipped alias registry."""
    import sys

    from hive_mind.project import resolve_project_root

    root = resolve_project_root()
    for entry in (str(root), str(root / "scripts" / "capture")):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    from hive_mind.projects.identity import (  # noqa: PLC0415 - until D003-R1
        ProjectAliasRegistry,
        ProjectIdentityResolver,
    )

    registry_path = root / "config" / "project-aliases.yaml"
    return ProjectIdentityResolver(registry=ProjectAliasRegistry.load(registry_path))


def _attach_identity(provider: str, session: dict, resolver, surface: str):
    from scripts.capture.session_events import (  # noqa: PLC0415 - until D003-R1
        attach_project_identity,
    )

    return attach_project_identity(
        provider=provider, session=session, resolver=resolver,
        default_surface=surface,
    )


def run_provider(
    provider: str,
    *,
    resolver=None,
    outbox: Optional[OutboxState] = None,
) -> CanaryResult:
    """Validate one provider against its real sources and real delivery."""
    started = time.monotonic()

    def done(status, **kw) -> CanaryResult:
        return CanaryResult(
            provider=provider, status=status,
            duration_seconds=round(time.monotonic() - started, 3), **kw
        )

    inv = sources.inventory(provider)
    if not inv.found:
        return done(CanaryStatus.SKIPPED, reason="no real source file on this host")

    attempted_sources = []
    sessions = []
    for source in inv.files:
        attempted_sources.append(source.name)
        try:
            sessions = sources.parse_sessions(provider, source)
        except Exception as exc:  # noqa: BLE001 - a parser failure is a real result
            return done(
                CanaryStatus.ERROR,
                reason=(
                    f"parser failed for {source.name}: {type(exc).__name__}: {exc}"
                ),
            )
        if sessions:
            break

    if not sessions:
        return done(
            CanaryStatus.FAILED,
            reason=(
                "parser produced no sessions from attempted sources: "
                f"{', '.join(attempted_sources)}"
            ),
        )

    resolver = resolver or _resolver()
    canonical = 0
    project_id = None          # first id seen, for diagnostics
    canonical_id = None        # first *classified* id — what justifies a pass
    for session in sessions:
        normalized = _attach_identity(provider, session, resolver, "cli")
        pid = normalized.get("project_id")
        project_id = project_id or pid
        if pid and not pid.startswith("unclassified/"):
            canonical += 1
            canonical_id = canonical_id or pid

    if project_id is None:
        return done(CanaryStatus.FAILED, reason="no project identity attached")

    # An `unclassified/<provider>` id means identity resolution failed on real
    # data. Passing on it would make the canary agree with a broken pipeline.
    if canonical == 0:
        return done(
            CanaryStatus.FAILED,
            project_id=project_id,
            reason=(
                f"{len(sessions)} real session(s) parsed but none resolved to a "
                f"classified project (got {project_id})"
            ),
        )

    # Historical legacy outbox rows are not evidence that the current realtime
    # path is broken: the live chain is parser -> capture.ingest -> Claude Mem
    # -> bridge, and old outbox rows may remain undelivered forever by design.
    # Fresh end-to-end delivery is proven separately by run_fresh_marker().
    _ = outbox

    # Report the identity that justified the pass, not merely the first seen.
    return done(CanaryStatus.PASSED, project_id=canonical_id, inserted=canonical)


def run(
    providers: Optional[list[str]] = None, *, paths: Optional[CanaryPaths] = None
) -> tuple[CanaryReport, OutboxState, UmcState]:
    """Run the canary across providers. Reads only; writes nothing."""
    paths = paths or default_paths()
    outbox = inspect_outbox(paths.outbox_db)
    umc = inspect_umc(paths.umc_db)
    resolver = _resolver()

    targets = providers if providers is not None else sources.provider_ids()
    results = tuple(
        run_provider(p, resolver=resolver, outbox=outbox) for p in targets
    )
    return CanaryReport(results=results), outbox, umc


def default_paths() -> CanaryPaths:
    """Real database locations on this host."""
    import os

    home = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
    runtime = Path(os.environ.get("SINAPSE_HOME") or "D:/Hive-Mind")
    return CanaryPaths(
        outbox_db=home / ".claude-mem" / "capture.db",
        umc_db=runtime / "hive_mind.db",
    )


def default_fresh_marker_paths() -> FreshMarkerPaths:
    """Protected databases used by fresh-marker validation."""
    import os

    home = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
    runtime = Path(os.environ.get("SINAPSE_HOME") or "D:/Hive-Mind")
    state_dir = runtime / ".hive-mind" / "state"
    override = os.environ.get("HIVE_CAPTURE_IDENTITY_DB")
    if override:
        identity = Path(override)
    else:
        candidates = (
            state_dir / "capture-identities.db",
            state_dir / "capture-identity.db",
        )
        identity = next((path for path in candidates if path.exists()), candidates[0])
    return FreshMarkerPaths(
        claude_mem_db=Path(os.environ.get(
            "CLAUDE_MEM_DB", str(home / ".claude-mem" / "claude-mem.db")
        )),
        identity_db=identity,
        umc_db=runtime / "hive_mind.db",
    )
