"""Read-only inspection of the real delivery state.

Opens the historical databases with SQLite's ``mode=ro`` URI so they cannot
be written, drained, migrated or locked. Reports what is actually there:
how many captured events are still sitting in the outbox undelivered, and
whether UMC observations carry a canonical ``workspace_id``.

These databases are protected (ADR-011/ADR-012): never write here.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
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


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


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
        newest = conn.execute(
            "SELECT occurred_at FROM capture_outbox WHERE delivered_at IS NULL "
            "ORDER BY occurred_at DESC LIMIT 1"
        ).fetchone()
        return OutboxState(
            path=str(path), exists=True, total=total, delivered=delivered,
            undelivered=total - delivered, dead_letter=dead,
            by_provider=by_provider,
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
