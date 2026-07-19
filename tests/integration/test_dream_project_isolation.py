"""D002 — project A / project B isolation over a real SQLite database.

No mocks: a real on-disk SQLite file with the production `observations`
shape, exercised through the Dream Cycle's own selection and grouping code.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

AUDIT_A = "audit-project-a"
AUDIT_B = "audit-project-b"


@pytest.fixture(scope="module")
def dream():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(
        "dream_cycle_integration", ROOT / "scripts" / "dream" / "dream_cycle.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db(tmp_path):
    """Real SQLite file mirroring the production observations table."""
    path = tmp_path / "umc.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE observations (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            project TEXT,
            type TEXT,
            title TEXT,
            content TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            neuron_id TEXT,
            archived INTEGER DEFAULT 0,
            metadata JSON,
            workspace_id TEXT NOT NULL DEFAULT 'default'
        )
        """
    )
    conn.execute(
        "CREATE INDEX idx_observations_workspace ON observations(workspace_id)"
    )
    yield conn
    conn.close()


def _insert(conn, oid, project, workspace_id, created_at, title="t"):
    conn.execute(
        "INSERT INTO observations (id, project, workspace_id, created_at, type,"
        " title, content, archived) VALUES (?, ?, ?, ?, 'learning', ?, 'c', 0)",
        (oid, project, workspace_id, created_at, title),
    )
    conn.commit()


def _buckets(dream, rows):
    """Reproduce the cycle's grouping step."""
    buckets: dict[str, list] = {}
    identities: dict[str, object] = {}
    for row in rows:
        identity = dream.resolve_observation_project(row)
        identities.setdefault(identity.project_id, identity)
        buckets.setdefault(identity.project_id, []).append(row["id"])
    return buckets, identities


def test_two_projects_stay_in_separate_buckets(dream, db):
    _insert(db, "a1", "Audit Project A", AUDIT_A, "2026-01-01")
    _insert(db, "a2", "Audit Project A", AUDIT_A, "2026-01-02")
    _insert(db, "b1", "Audit Project B", AUDIT_B, "2026-01-03")

    rows = dream.fetch_balanced_observations(db, limit=10)
    buckets, _ = _buckets(dream, rows)

    assert set(buckets) == {AUDIT_A, AUDIT_B}
    assert buckets[AUDIT_A] == ["a1", "a2"]
    assert buckets[AUDIT_B] == ["b1"]
    assert not set(buckets[AUDIT_A]) & set(buckets[AUDIT_B])


def test_root_and_worktree_labels_collapse_into_one_bucket(dream, db):
    """The regression this delivery exists to fix."""
    _insert(db, "r1", "Hive-Mind", "hive-mind", "2026-01-01")
    _insert(db, "w1", "hive-mind-windows-zero-install", "hive-mind", "2026-01-02")
    _insert(db, "w2", "Hive-Mind/hive-mind-windows-zero-install", "hive-mind",
            "2026-01-03")

    rows = dream.fetch_balanced_observations(db, limit=10)
    buckets, identities = _buckets(dream, rows)

    assert list(buckets) == ["hive-mind"], "three labels must be one project"
    assert sorted(buckets["hive-mind"]) == ["r1", "w1", "w2"]
    assert identities["hive-mind"].canonical is True


def test_surfaces_do_not_create_projects(dream, db):
    """Qwen / VS Code / miche are surfaces, never a project_id (ADR-006)."""
    for i, surface in enumerate(["Qwen", "Microsoft VS Code", "miche", "hermes"]):
        _insert(db, f"s{i}", surface, "hive-mind", f"2026-02-0{i + 1}")

    rows = dream.fetch_balanced_observations(db, limit=10)
    buckets, _ = _buckets(dream, rows)

    assert list(buckets) == ["hive-mind"]


def test_legacy_rows_are_preserved_not_absorbed(dream, db):
    """Legacy rows keep their label grouping and are flagged non-canonical."""
    _insert(db, "leg1", "Hive-Mind", "default", "2026-01-01")
    _insert(db, "can1", "Hive-Mind", "hive-mind", "2026-01-02")

    rows = dream.fetch_balanced_observations(db, limit=10)
    buckets, identities = _buckets(dream, rows)

    assert set(buckets) == {"Hive-Mind", "hive-mind"}
    assert identities["Hive-Mind"].canonical is False
    assert identities["hive-mind"].canonical is True
    # Nothing was rewritten in the database (ADR-012).
    stored = dict(db.execute("SELECT id, workspace_id FROM observations").fetchall())
    assert stored == {"leg1": "default", "can1": "hive-mind"}


def test_balanced_window_round_robins_across_projects(dream, db):
    """One slot per project per rank — A must not starve B."""
    for i in range(5):
        _insert(db, f"a{i}", "Audit Project A", AUDIT_A, f"2026-01-0{i + 1}")
    _insert(db, "b1", "Audit Project B", AUDIT_B, "2026-03-01")

    rows = dream.fetch_balanced_observations(db, limit=2)
    picked = {r["id"] for r in rows}

    assert picked == {"a0", "b1"}, "B must appear despite being newest"


def test_cleanup_removes_only_synthetic_rows(dream, db):
    """Synthetic audit projects are removable without touching real data."""
    _insert(db, "a1", "Audit Project A", AUDIT_A, "2026-01-01")
    _insert(db, "b1", "Audit Project B", AUDIT_B, "2026-01-02")
    _insert(db, "real1", "Hive-Mind", "hive-mind", "2026-01-03")

    db.execute(
        "DELETE FROM observations WHERE workspace_id IN (?, ?)", (AUDIT_A, AUDIT_B)
    )
    db.commit()

    remaining = [r["id"] for r in db.execute("SELECT id FROM observations")]
    assert remaining == ["real1"]
