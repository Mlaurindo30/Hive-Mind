"""D002 — Dream Cycle groups by canonical project_id, not by free-text label.

The bridge writes the canonical identity into `observations.workspace_id`
(see core/knowledge/claude_mem_bridge.py). The Dream Cycle used to group by
`observations.project`, a free-text label, which fragmented the vault into
directories like `Hive-Mind/`, `hive-mind-windows-zero-install/`, `Qwen/`
and `miche/` for what is one project.

Legacy rows (written before the identity work, carrying the migration default
`workspace_id='default'`) must keep their current behaviour: they are NOT
rewritten and NOT relocated (ADR-012). They stay grouped by their label and
are marked non-canonical so the audit can find them.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load_dream_cycle():
    """Import dream_cycle.py by path (hyphenless module, not a package)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(
        "dream_cycle_under_test", ROOT / "scripts" / "dream" / "dream_cycle.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dream():
    return _load_dream_cycle()


def _row(**fields) -> sqlite3.Row:
    """Build a real sqlite3.Row so `.keys()` behaves like production."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cols = ", ".join(f"{k} TEXT" for k in fields)
    conn.execute(f"CREATE TABLE t ({cols})")
    placeholders = ", ".join("?" for _ in fields)
    conn.execute(f"INSERT INTO t VALUES ({placeholders})", tuple(fields.values()))
    return conn.execute("SELECT * FROM t").fetchone()


class TestResolveProjectIdentity:
    def test_canonical_workspace_id_wins_over_label(self, dream):
        row = _row(project="Hive-Mind", workspace_id="hive-mind")
        identity = dream.resolve_observation_project(row)
        assert identity.project_id == "hive-mind"
        assert identity.canonical is True

    def test_worktree_and_root_collapse_to_one_project(self, dream):
        """The whole point: two labels, one canonical id, one directory."""
        root = _row(project="Hive-Mind", workspace_id="hive-mind")
        worktree = _row(
            project="hive-mind-windows-zero-install", workspace_id="hive-mind"
        )
        assert (
            dream.resolve_observation_project(root).project_id
            == dream.resolve_observation_project(worktree).project_id
            == "hive-mind"
        )

    def test_project_name_prefers_label_for_display(self, dream):
        row = _row(project="Hive-Mind", workspace_id="hive-mind")
        assert dream.resolve_observation_project(row).project_name == "Hive-Mind"

    def test_project_name_falls_back_to_id_when_label_missing(self, dream):
        row = _row(project="", workspace_id="hive-mind")
        assert dream.resolve_observation_project(row).project_name == "hive-mind"

    @pytest.mark.parametrize("legacy_value", ["default", "", None])
    def test_legacy_rows_keep_label_grouping(self, dream, legacy_value):
        """Migration default / empty means: no canonical identity was recorded."""
        row = _row(project="Hive-Mind", workspace_id=legacy_value)
        identity = dream.resolve_observation_project(row)
        assert identity.project_id == "Hive-Mind"
        assert identity.canonical is False

    def test_legacy_row_without_label_uses_default_project(self, dream, monkeypatch):
        monkeypatch.delenv("HIVE_DEFAULT_PROJECT", raising=False)
        row = _row(project=None, workspace_id="default")
        identity = dream.resolve_observation_project(row)
        assert identity.project_id == dream.DEFAULT_PROJECT
        assert identity.canonical is False

    def test_row_without_workspace_column_is_legacy(self, dream):
        """Databases predating migrate_workspace_and_federation have no column."""
        row = _row(project="Hive-Mind")
        identity = dream.resolve_observation_project(row)
        assert identity.project_id == "Hive-Mind"
        assert identity.canonical is False

    def test_whitespace_is_not_a_project(self, dream):
        row = _row(project="Hive-Mind", workspace_id="   ")
        assert dream.resolve_observation_project(row).canonical is False

    def test_provider_and_surface_are_never_the_project_id(self, dream):
        """Guards ADR-006: an application name is a surface, not a project."""
        for surface in ("Qwen", "Microsoft VS Code", "miche", "app", "hermes"):
            row = _row(project=surface, workspace_id="hive-mind")
            assert dream.resolve_observation_project(row).project_id == "hive-mind"


class TestBalancedWindowPartitioning:
    """fetch_balanced_observations must round-robin over canonical projects."""

    def _seed(self, conn, rows):
        conn.execute(
            """
            CREATE TABLE observations (
                id TEXT PRIMARY KEY, project TEXT, workspace_id TEXT,
                created_at TEXT, archived INTEGER DEFAULT 0
            )
            """
        )
        conn.executemany(
            "INSERT INTO observations (id, project, workspace_id, created_at, archived)"
            " VALUES (?, ?, ?, ?, 0)",
            rows,
        )
        conn.commit()

    def test_root_and_worktree_share_one_partition(self, dream):
        """Two labels, one canonical project: must NOT get two round-robin slots."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self._seed(
            conn,
            [
                ("a1", "Hive-Mind", "hive-mind", "2026-01-01"),
                ("a2", "hive-mind-windows-zero-install", "hive-mind", "2026-01-02"),
                ("a3", "Hive-Mind", "hive-mind", "2026-01-03"),
                ("b1", "Other", "other-project", "2026-01-04"),
            ],
        )
        picked = [r["id"] for r in dream.fetch_balanced_observations(conn, limit=2)]
        # rank 1 of each canonical project: oldest hive-mind row + the other project
        assert set(picked) == {"a1", "b1"}

    def test_legacy_rows_partition_by_label(self, dream):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self._seed(
            conn,
            [
                ("l1", "ProjA", "default", "2026-01-01"),
                ("l2", "ProjA", "default", "2026-01-02"),
                ("l3", "ProjB", "default", "2026-01-03"),
            ],
        )
        picked = [r["id"] for r in dream.fetch_balanced_observations(conn, limit=2)]
        assert set(picked) == {"l1", "l3"}

    def test_archived_rows_are_excluded(self, dream):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self._seed(conn, [("x1", "ProjA", "hive-mind", "2026-01-01")])
        conn.execute("UPDATE observations SET archived = 1")
        conn.commit()
        assert dream.fetch_balanced_observations(conn, limit=10) == []

    def test_database_without_workspace_column_still_works(self, dream):
        """Legacy DB predating migrate_workspace_and_federation must not crash."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE observations (id TEXT PRIMARY KEY, project TEXT,"
            " created_at TEXT, archived INTEGER DEFAULT 0)"
        )
        conn.executemany(
            "INSERT INTO observations (id, project, created_at, archived)"
            " VALUES (?, ?, ?, 0)",
            [("o1", "ProjA", "2026-01-01"), ("o2", "ProjB", "2026-01-02")],
        )
        conn.commit()
        picked = [r["id"] for r in dream.fetch_balanced_observations(conn, limit=2)]
        assert set(picked) == {"o1", "o2"}


class TestCanonicalFrontmatter:
    """Markdown carries project_id so retrieval can filter by project."""

    def _fields(self, dream, identity):
        """Render the frontmatter block the way _route_and_persist_project does."""
        source = (ROOT / "scripts" / "dream" / "dream_cycle.py").read_text(
            encoding="utf-8"
        )
        assert "project_id: {identity.project_id}" in source
        assert "project_name: {identity.project_name}" in source
        assert "identity_source: {'canonical' if identity.canonical else" in source
        return source

    def test_frontmatter_declares_project_id(self, dream):
        self._fields(dream, None)

    def test_note_path_uses_project_id_not_label(self, dream):
        """cortex/temporal/<project_dir>/<topic>/ — one dir per project.

        FASE 0 (2026-08-12): o diretório é resolvido por vault_project_dir(proj)
        (nome canônico sem prefixo de source-type), não pelo project_id cru nem
        pelo label. A intenção do teste original se mantém: o path deriva do
        project_id canônico, não do rótulo humano.
        """
        source = (ROOT / "scripts" / "dream" / "dream_cycle.py").read_text(
            encoding="utf-8"
        )
        assert "note_file = cp.TEMPORAL / project_dir / safe_topic" in source, (
            "note path must derive from the canonical project dir (vault_project_dir)"
        )
        assert "project_dir = vault_project_dir(proj)" in source, (
            "project dir must come from the canonical vault layer, not the raw project_id"
        )

    def test_legacy_identity_is_marked_in_frontmatter(self, dream):
        identity = dream.ObservationProject("Hive-Mind", "Hive-Mind", False)
        assert identity.canonical is False
        assert identity.project_id == "Hive-Mind"

    def test_route_and_persist_accepts_identity(self, dream):
        import inspect

        params = inspect.signature(dream._route_and_persist_project).parameters
        assert "identity" in params, (
            "_route_and_persist_project must receive the resolved identity"
        )
        assert params["identity"].default is None, "identity stays optional"
