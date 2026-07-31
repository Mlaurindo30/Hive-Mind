"""Read-only inspection of the real delivery state.

Opens the historical databases with SQLite's ``mode=ro`` URI so they cannot
be written, drained, migrated or locked. Reports what is actually there:
how many captured events are still sitting in the outbox undelivered, and
whether UMC observations carry a canonical ``workspace_id``.

These databases are protected (ADR-011/ADR-012): never write here.
"""
from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional

LEGACY_WORKSPACE_IDS = frozenset({"", "default"})


@dataclass(frozen=True)
class OutboxState:
    path: str
    exists: bool
    total: int = 0
    delivered: int = 0
    undelivered: int = 0
    dead_letter: int = 0
    by_provider: tuple[tuple[str, int], ...] = ()
    oldest_undelivered: Optional[str] = None
    newest_undelivered: Optional[str] = None

    @property
    def stalled(self) -> bool:
        """Events were captured but none reached their destination."""
        return self.total > 0 and self.delivered == 0


@dataclass(frozen=True)
class UmcState:
    path: str
    exists: bool
    observations: int = 0
    canonical: int = 0
    legacy: int = 0
    by_workspace: tuple[tuple[str, int], ...] = ()

    @property
    def canonical_pct(self) -> float:
        return (self.canonical / self.observations * 100) if self.observations else 0.0


@dataclass(frozen=True)
class UmcLegacyState:
    path: str
    exists: bool
    default_workspace: int = 0
    empty_workspace: int = 0
    unclassified_legacy: int = 0
    archived_quarantine: int = 0
    default_active_by_project: tuple[tuple[str, int], ...] = ()
    unclassified_active_by_project: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class LegacyRecoveryState:
    path: str
    exists: bool
    source_workspaces: tuple[str, ...] = ()
    legacy_source_sessions: int = 0
    decisions_found: int = 0
    bridged_recoverable: int = 0
    bridged_by_project: tuple[tuple[str, int], ...] = ()
    claude_mem_path: str = ""
    claude_mem_exists: bool = False
    session_rows_found: int = 0
    session_project_signals: int = 0
    canonical_alias_matches: int = 0
    canonical_signal_by_project: tuple[tuple[str, int], ...] = ()
    unmapped_session_projects: tuple[tuple[str, int], ...] = ()


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _derived_content_session_id(memory_session_id: str) -> str | None:
    raw = str(memory_session_id or "").strip()
    if not raw:
        return None
    parts = raw.split("-")
    if len(parts) < 3 or not parts[-1].isdigit():
        return None
    candidate = "-".join(parts[1:-1]).strip()
    return candidate or None


def inspect_outbox(path: Path) -> OutboxState:
    """Count captured-but-undelivered events, per provider. Read-only."""
    if not path.is_file():
        return OutboxState(str(path), False)
    conn = _read_only(path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "capture_outbox" not in tables:
            return OutboxState(str(path), True)
        total = conn.execute("SELECT COUNT(*) FROM capture_outbox").fetchone()[0]
        delivered = conn.execute(
            "SELECT COUNT(*) FROM capture_outbox WHERE delivered_at IS NOT NULL"
        ).fetchone()[0]
        dead = conn.execute(
            "SELECT COUNT(*) FROM capture_outbox WHERE dead_letter_at IS NOT NULL"
        ).fetchone()[0]
        by_provider = tuple(
            conn.execute(
                "SELECT provider, COUNT(*) FROM capture_outbox "
                "WHERE delivered_at IS NULL GROUP BY provider ORDER BY 2 DESC"
            ).fetchall()
        )
        oldest = conn.execute(
            "SELECT occurred_at FROM capture_outbox WHERE delivered_at IS NULL "
            "ORDER BY occurred_at ASC LIMIT 1"
        ).fetchone()
        newest = conn.execute(
            "SELECT occurred_at FROM capture_outbox WHERE delivered_at IS NULL "
            "ORDER BY occurred_at DESC LIMIT 1"
        ).fetchone()
        return OutboxState(
            path=str(path), exists=True, total=total, delivered=delivered,
            undelivered=total - delivered, dead_letter=dead,
            by_provider=by_provider,
            oldest_undelivered=oldest[0] if oldest else None,
            newest_undelivered=newest[0] if newest else None,
        )
    finally:
        conn.close()


def inspect_umc(path: Path) -> UmcState:
    """Report how many observations carry a canonical workspace. Read-only."""
    if not path.is_file():
        return UmcState(str(path), False)
    conn = _read_only(path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "observations" not in tables:
            return UmcState(str(path), True)
        rows = conn.execute(
            "SELECT COALESCE(workspace_id, ''), COUNT(*) FROM observations "
            "GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        total = sum(n for _, n in rows)
        legacy = sum(n for w, n in rows if (w or "").strip() in LEGACY_WORKSPACE_IDS)
        return UmcState(
            path=str(path), exists=True, observations=total,
            canonical=total - legacy, legacy=legacy, by_workspace=tuple(rows),
        )
    finally:
        conn.close()


def inspect_umc_legacy(path: Path) -> UmcLegacyState:
    """Break legacy-like UMC rows into safe operational buckets. Read-only."""
    if not path.is_file():
        return UmcLegacyState(str(path), False)
    conn = _read_only(path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "observations" not in tables:
            return UmcLegacyState(str(path), True)
        columns = _table_columns(conn, "observations")
        archived_filter = " AND archived = 0" if "archived" in columns else ""
        archived_expr = (
            "SUM(CASE WHEN archived = 2 THEN 1 ELSE 0 END)"
            if "archived" in columns else "0"
        )
        project_expr = 'COALESCE(project, "<null>")' if "project" in columns else '"<missing>"'
        default_workspace = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE workspace_id = 'default'"
        ).fetchone()[0]
        empty_workspace = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE COALESCE(workspace_id, '') = ''"
        ).fetchone()[0]
        unclassified_legacy = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE workspace_id = 'unclassified/legacy'"
        ).fetchone()[0]
        archived_quarantine = conn.execute(
            f"SELECT {archived_expr} FROM observations"
        ).fetchone()[0]
        default_active_by_project = tuple(conn.execute(
            f"SELECT {project_expr}, COUNT(*) FROM observations "
            "WHERE workspace_id = 'default'"
            f"{archived_filter} GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall())
        unclassified_active_by_project = tuple(conn.execute(
            f"SELECT {project_expr}, COUNT(*) FROM observations "
            "WHERE workspace_id = 'unclassified/legacy'"
            f"{archived_filter} GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall())
        return UmcLegacyState(
            path=str(path),
            exists=True,
            default_workspace=int(default_workspace),
            empty_workspace=int(empty_workspace),
            unclassified_legacy=int(unclassified_legacy),
            archived_quarantine=int(archived_quarantine or 0),
            default_active_by_project=default_active_by_project,
            unclassified_active_by_project=unclassified_active_by_project,
        )
    finally:
        conn.close()


def inspect_legacy_recovery(
    path: Path,
    *,
    identity_db: Path | None = None,
    source_workspaces: tuple[str, ...] = ("unclassified/legacy", "default"),
) -> LegacyRecoveryState:
    """Measure whether active legacy rows are recoverable via IdentityStore."""
    if not path.is_file():
        return LegacyRecoveryState(str(path), False)
    if identity_db is None:
        try:
            from hive_mind.capture.identity_store import default_path

            identity_db = default_path()
        except Exception:
            identity_db = Path.cwd() / ".hive-mind" / "state" / "capture-identities.db"
    if not identity_db.is_file():
        return LegacyRecoveryState(str(identity_db), False)

    try:
        from hive_mind.projects.identity import DEFAULT_REGISTRY_PATH, ProjectAliasRegistry

        registry = ProjectAliasRegistry.load(DEFAULT_REGISTRY_PATH)
    except Exception:
        registry = None
    claude_mem_db = Path(
        os.environ.get("CLAUDE_MEM_DB", str(Path.home() / ".claude-mem" / "claude-mem.db"))
    )

    umc = _read_only(path)
    ids = _read_only(identity_db)
    cmem = _read_only(claude_mem_db) if claude_mem_db.is_file() else None
    try:
        tables = {r[0] for r in umc.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "observations" not in tables:
            return LegacyRecoveryState(str(identity_db), True)
        columns = _table_columns(umc, "observations")
        if "metadata" not in columns:
            return LegacyRecoveryState(str(identity_db), True)
        workspaces = tuple(
            str(value).strip() for value in source_workspaces if str(value).strip()
        )
        if not workspaces:
            return LegacyRecoveryState(str(identity_db), True, source_workspaces=())
        placeholders = ", ".join("?" for _ in workspaces)
        rows = umc.execute(
            "SELECT metadata FROM observations "
            f"WHERE workspace_id IN ({placeholders}) AND archived=0",
            workspaces,
        ).fetchall()
        source_sessions: list[str] = []
        for row in rows:
            try:
                metadata = json.loads(row[0] or "{}") if isinstance(row[0], str) else {}
            except Exception:
                metadata = {}
            sid = str(
                metadata.get("source_session")
                or metadata.get("memory_session_id")
                or ""
            ).strip()
            if sid:
                source_sessions.append(sid)
        unique_sessions = list(dict.fromkeys(source_sessions))
        decisions_found = 0
        bridged_recoverable = 0
        bridged_by_project: dict[str, int] = {}
        session_rows_found = 0
        session_project_signals = 0
        canonical_alias_matches = 0
        canonical_signal_by_project: dict[str, int] = {}
        unmapped_session_projects: dict[str, int] = {}
        session_query = None
        if cmem is not None:
            cmem_tables = {
                r[0] for r in cmem.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "sdk_sessions" in cmem_tables:
                cmem_columns = _table_columns(cmem, "sdk_sessions")
                if "memory_session_id" in cmem_columns and "content_session_id" in cmem_columns:
                    session_query = (
                        "SELECT project FROM sdk_sessions "
                        "WHERE memory_session_id=? OR content_session_id=? LIMIT 1"
                    )
                elif "memory_session_id" in cmem_columns:
                    session_query = (
                        "SELECT project FROM sdk_sessions WHERE memory_session_id=? LIMIT 1"
                    )
        for sid in unique_sessions:
            row = ids.execute(
                "SELECT project_id, delivery_state FROM capture_identity_decisions "
                "WHERE content_session_id=?",
                (sid,),
            ).fetchone()
            if row is not None:
                decisions_found += 1
                project_id = str(row[0] or "").strip()
                delivery_state = str(row[1] or "").strip()
                if (
                    delivery_state == "BRIDGED"
                    and project_id
                    and project_id != "unclassified/legacy"
                    and not project_id.startswith("unclassified/")
                ):
                    bridged_recoverable += 1
                    bridged_by_project[project_id] = bridged_by_project.get(project_id, 0) + 1
            if cmem is None or session_query is None:
                continue
            derived_sid = _derived_content_session_id(sid)
            if "content_session_id" in session_query:
                session = cmem.execute(session_query, (sid, derived_sid or sid)).fetchone()
            else:
                session = cmem.execute(session_query, (sid,)).fetchone()
            if session is None:
                continue
            session_rows_found += 1
            project_label = str(session[0] or "").strip()
            if not project_label:
                continue
            session_project_signals += 1
            if registry is None:
                unmapped_session_projects[project_label] = (
                    unmapped_session_projects.get(project_label, 0) + 1
                )
                continue
            entry = registry.by_alias(project_label)
            if entry is None:
                unmapped_session_projects[project_label] = (
                    unmapped_session_projects.get(project_label, 0) + 1
                )
                continue
            canonical_alias_matches += 1
            canonical_signal_by_project[entry.project_id] = (
                canonical_signal_by_project.get(entry.project_id, 0) + 1
            )
        return LegacyRecoveryState(
            path=str(identity_db),
            exists=True,
            source_workspaces=workspaces,
            legacy_source_sessions=len(unique_sessions),
            decisions_found=decisions_found,
            bridged_recoverable=bridged_recoverable,
            bridged_by_project=tuple(
                sorted(bridged_by_project.items(), key=lambda item: (-item[1], item[0]))
            ),
            claude_mem_path=str(claude_mem_db),
            claude_mem_exists=claude_mem_db.is_file(),
            session_rows_found=session_rows_found,
            session_project_signals=session_project_signals,
            canonical_alias_matches=canonical_alias_matches,
            canonical_signal_by_project=tuple(
                sorted(canonical_signal_by_project.items(), key=lambda item: (-item[1], item[0]))
            ),
            unmapped_session_projects=tuple(
                sorted(unmapped_session_projects.items(), key=lambda item: (-item[1], item[0]))
            ),
        )
    finally:
        if cmem is not None:
            cmem.close()
        ids.close()
        umc.close()
