"""Controlled migration of legacy UMC observations.

This module never guesses project IDs from free text. It only upgrades rows
when a preserved Claude Mem session still points to a project label that the
canonical registry recognizes. Everything else stays preserved as legacy.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.database import with_sqlite_retry
from hive_mind.maintenance.lock import MaintenanceLock
from hive_mind.projects.identity import DEFAULT_REGISTRY_PATH, ProjectAliasRegistry


@dataclass(frozen=True)
class LegacyMigrationReport:
    hive_db: str
    claude_mem_db: str
    registry_path: str
    source_workspace: str
    apply: bool
    target_project_id: str | None
    scanned: int = 0
    candidates: int = 0
    updated: int = 0
    skipped_missing_source_session: int = 0
    skipped_missing_sdk_session: int = 0
    skipped_missing_project_label: int = 0
    skipped_target_filter: int = 0
    candidate_rows_by_project: tuple[tuple[str, int], ...] = ()
    unmapped_rows_by_label: tuple[tuple[str, int], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _open_rw(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 60000;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass
    return conn


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


def _load_registry(path: Path | None) -> tuple[ProjectAliasRegistry, Path]:
    registry_path = Path(path) if path else Path(DEFAULT_REGISTRY_PATH)
    return ProjectAliasRegistry.load(registry_path), registry_path


def _load_metadata(raw: object) -> dict[str, object]:
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


_UNCLASSIFIED_LABEL_RE = re.compile(r"^\s*Unclassified\s*\((?P<provider>[^()]+)\)\s*$", re.IGNORECASE)


def _unclassified_provider_entry(project_label: str) -> tuple[str, str] | None:
    match = _UNCLASSIFIED_LABEL_RE.match(str(project_label or ""))
    if match is None:
        return None
    provider = re.sub(r"[^a-z0-9._-]+", "-", match.group("provider").strip().lower())
    provider = provider.strip("-._")
    if not provider:
        return None
    return (f"unclassified/{provider}", f"Unclassified ({provider})")


def _sdk_project_lookup(
    claude_mem: sqlite3.Connection,
    sid: str,
    *,
    session_query: str | None,
) -> str | None:
    if not session_query:
        return None
    derived_sid = _derived_content_session_id(sid)
    if "content_session_id" in session_query:
        row = claude_mem.execute(session_query, (sid, derived_sid or sid)).fetchone()
    else:
        row = claude_mem.execute(session_query, (sid,)).fetchone()
    if row is None:
        return None
    project = str(row[0] or "").strip()
    return project or None


def _session_query(claude_mem: sqlite3.Connection) -> str | None:
    tables = {r[0] for r in claude_mem.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if "sdk_sessions" not in tables:
        return None
    columns = _table_columns(claude_mem, "sdk_sessions")
    if "memory_session_id" in columns and "content_session_id" in columns:
        return (
            "SELECT project FROM sdk_sessions "
            "WHERE memory_session_id=? OR content_session_id=? LIMIT 1"
        )
    if "memory_session_id" in columns:
        return "SELECT project FROM sdk_sessions WHERE memory_session_id=? LIMIT 1"
    return None


def _updated_metadata(
    metadata: dict[str, object],
    *,
    project_id: str,
    project_name: str,
    source_workspace: str,
    source_label: str,
) -> str:
    patched = dict(metadata)
    patched.update({
        "project": project_name,
        "project_id": project_id,
        "project_name": project_name,
        "identity_status": "canonical",
        "legacy_identity": False,
    })
    reconciliation = patched.get("legacy_reconciliation")
    if not isinstance(reconciliation, dict):
        reconciliation = {}
    reconciliation.update({
        "at": datetime.now(timezone.utc).isoformat(),
        "method": "sdk_session_alias_registry",
        "source_workspace": source_workspace,
        "source_project_label": source_label,
    })
    patched["legacy_reconciliation"] = reconciliation
    return json.dumps(patched, ensure_ascii=False, sort_keys=True)


def migrate_legacy_observations(
    *,
    hive_db: str | Path,
    claude_mem_db: str | Path,
    registry_path: str | Path | None = None,
    source_workspace: str = "unclassified/legacy",
    target_project_id: str | None = None,
    apply: bool = False,
) -> LegacyMigrationReport:
    hive_path = Path(hive_db)
    claude_mem_path = Path(claude_mem_db)
    registry, resolved_registry_path = _load_registry(
        Path(registry_path) if registry_path else None
    )

    if not hive_path.is_file():
        raise FileNotFoundError(hive_path)
    if not claude_mem_path.is_file():
        raise FileNotFoundError(claude_mem_path)

    ro_hive = _open_ro(hive_path)
    ro_claude = _open_ro(claude_mem_path)
    try:
        query = _session_query(ro_claude)
        rows = ro_hive.execute(
            "SELECT id, project, metadata FROM observations "
            "WHERE workspace_id = ? AND archived = 0",
            (source_workspace,),
        ).fetchall()

        candidate_rows_by_project: Counter[str] = Counter()
        unmapped_rows_by_label: Counter[str] = Counter()
        updates: list[tuple[str, str, str, str, str]] = []
        skipped_missing_source_session = 0
        skipped_missing_sdk_session = 0
        skipped_missing_project_label = 0
        skipped_target_filter = 0
        candidates = 0

        for row in rows:
            metadata = _load_metadata(row["metadata"])
            sid = str(
                metadata.get("source_session") or metadata.get("memory_session_id") or ""
            ).strip()
            if not sid:
                skipped_missing_source_session += 1
                continue
            project_label = _sdk_project_lookup(ro_claude, sid, session_query=query)
            if project_label is None:
                skipped_missing_sdk_session += 1
                continue
            if not project_label.strip():
                skipped_missing_project_label += 1
                continue
            entry = registry.by_alias(project_label)
            if entry is not None:
                candidate_project_id = entry.project_id
                candidate_project_name = entry.project_name
            else:
                fallback = _unclassified_provider_entry(project_label)
                if fallback is None:
                    unmapped_rows_by_label[project_label] += 1
                    continue
                candidate_project_id, candidate_project_name = fallback
            if target_project_id and candidate_project_id != target_project_id:
                skipped_target_filter += 1
                continue
            candidates += 1
            candidate_rows_by_project[candidate_project_id] += 1
            updates.append((
                candidate_project_id,
                candidate_project_name,
                _updated_metadata(
                    metadata,
                    project_id=candidate_project_id,
                    project_name=candidate_project_name,
                    source_workspace=source_workspace,
                    source_label=project_label,
                ),
                str(row["id"]),
                source_workspace,
            ))
    finally:
        ro_claude.close()
        ro_hive.close()

    updated = 0
    if apply and updates:
        lock_path = hive_path.with_suffix(hive_path.suffix + ".legacy-migration.lock")
        with MaintenanceLock(lock_path):
            rw_hive = _open_rw(hive_path)
            try:
                def _write() -> None:
                    nonlocal updated
                    rw_hive.execute("BEGIN IMMEDIATE")
                    rw_hive.executemany(
                        "UPDATE observations "
                        "SET workspace_id = ?, project = ?, metadata = ? "
                        "WHERE id = ? AND workspace_id = ? AND archived = 0",
                        updates,
                    )
                    updated = sum(1 for _ in updates)
                    rw_hive.commit()

                with_sqlite_retry(_write, op_label="legacy_migration_apply")
            except Exception:
                rw_hive.rollback()
                raise
            finally:
                rw_hive.close()

    return LegacyMigrationReport(
        hive_db=str(hive_path),
        claude_mem_db=str(claude_mem_path),
        registry_path=str(resolved_registry_path),
        source_workspace=source_workspace,
        apply=apply,
        target_project_id=target_project_id,
        scanned=len(rows),
        candidates=candidates,
        updated=updated,
        skipped_missing_source_session=skipped_missing_source_session,
        skipped_missing_sdk_session=skipped_missing_sdk_session,
        skipped_missing_project_label=skipped_missing_project_label,
        skipped_target_filter=skipped_target_filter,
        candidate_rows_by_project=tuple(
            sorted(candidate_rows_by_project.items(), key=lambda item: (-item[1], item[0]))
        ),
        unmapped_rows_by_label=tuple(
            sorted(unmapped_rows_by_label.items(), key=lambda item: (-item[1], item[0]))
        ),
    )
