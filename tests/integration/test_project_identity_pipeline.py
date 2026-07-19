"""D003 — canonical identity across the real pipeline, with the shipped registry.

The existing integration suite (test_project_identity_git.py) resolves with
`ProjectAliasRegistry.empty()`, so it proves the git plumbing but never proves
that a Hive-Mind checkout actually lands on `project_id == "hive-mind"` via
`config/project-aliases.yaml`. It also stops at the resolver.

This module closes both gaps with real temporary git repositories and no mocks:

    real git repo -> ProjectIdentityResolver (shipped registry)
                  -> attach_project_identity (normalized session)
                  -> the `project` field Claude Mem receives
                  -> bridge -> observations.workspace_id (real SQLite)
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from scripts.capture.project_identity import (
    ProjectAliasRegistry,
    ProjectIdentityResolver,
)
from scripts.capture.session_events import attach_project_identity


ROOT = Path(__file__).resolve().parents[2]
SHIPPED_REGISTRY = ROOT / "config" / "project-aliases.yaml"
HIVE_REMOTE = "https://github.com/Mlaurindo30/Hive-Mind.git"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=15
    )
    return result.stdout.strip()


def _repository(path: Path, *, remote: str | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--initial-branch=main")
    _git(path, "config", "user.email", "d003@example.invalid")
    _git(path, "config", "user.name", "D003 Integration")
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial")
    if remote:
        _git(path, "remote", "add", "origin", remote)
    return path


@pytest.fixture(scope="module")
def shipped_resolver() -> ProjectIdentityResolver:
    """Resolver backed by the registry we actually ship."""
    assert SHIPPED_REGISTRY.exists(), f"missing shipped registry: {SHIPPED_REGISTRY}"
    return ProjectIdentityResolver(registry=ProjectAliasRegistry.load(SHIPPED_REGISTRY))


class TestShippedRegistryResolvesHiveMind:
    def test_checkout_with_hive_mind_remote_is_canonical(
        self, shipped_resolver, tmp_path
    ):
        repo = _repository(tmp_path / "any-checkout-name", remote=HIVE_REMOTE)

        identity = shipped_resolver.resolve(
            provider="codex", surface="cli", cwd=repo, env={}
        )

        assert identity.project_id == "hive-mind"
        assert identity.project_name == "Hive-Mind"

    def test_root_and_worktree_collapse_to_one_project(
        self, shipped_resolver, tmp_path
    ):
        """The exact production case: D:\\Hive-Mind and its worktree."""
        repo = _repository(tmp_path / "Hive-Mind", remote=HIVE_REMOTE)
        worktree = tmp_path / "worktrees" / "hive-mind-windows-zero-install"
        _git(repo, "worktree", "add", "-b", "codex/feature", str(worktree))

        root = shipped_resolver.resolve(
            provider="codex", surface="cli", cwd=repo, env={}
        )
        linked = shipped_resolver.resolve(
            provider="codex", surface="cli", cwd=worktree, env={}
        )

        assert root.project_id == linked.project_id == "hive-mind"
        assert root.project_name == linked.project_name == "Hive-Mind"

    def test_worktree_name_and_branch_stay_metadata(self, shipped_resolver, tmp_path):
        """Worktree is never the identity — it is a field beside it."""
        repo = _repository(tmp_path / "Hive-Mind", remote=HIVE_REMOTE)
        worktree = tmp_path / "hive-mind-windows-zero-install"
        _git(repo, "worktree", "add", "-b", "codex/control-plane", str(worktree))

        linked = shipped_resolver.resolve(
            provider="codex", surface="cli", cwd=worktree, env={}
        )

        assert linked.project_id == "hive-mind"
        assert linked.worktree_name == "hive-mind-windows-zero-install"
        assert linked.branch == "codex/control-plane"
        assert linked.worktree_name != linked.project_id

    def test_unrelated_repository_is_not_hive_mind(self, shipped_resolver, tmp_path):
        """The registry must not swallow foreign repositories."""
        other = _repository(
            tmp_path / "other", remote="https://github.com/someone/unrelated.git"
        )

        identity = shipped_resolver.resolve(
            provider="codex", surface="cli", cwd=other, env={}
        )

        assert identity.project_id != "hive-mind"


class TestSurfacesAreNotProjects:
    """ADR-006: application, profile and provider names are never a project_id."""

    @pytest.mark.parametrize(
        "directory",
        ["Qwen", "Microsoft VS Code", "miche", "app", "hermes"],
    )
    def test_non_git_surface_directory_never_becomes_the_project(
        self, shipped_resolver, tmp_path, directory
    ):
        workspace = tmp_path / directory
        workspace.mkdir(parents=True)

        identity = shipped_resolver.resolve(
            provider="qwen", surface="desktop", cwd=workspace, env={}
        )

        assert identity.project_id != directory
        assert identity.project_id != directory.lower()
        assert identity.project_id.startswith("unclassified/")

    def test_surface_directory_inside_hive_mind_repo_is_still_hive_mind(
        self, shipped_resolver, tmp_path
    ):
        """A folder named 'Qwen' inside the repo does not create a project."""
        repo = _repository(tmp_path / "Hive-Mind", remote=HIVE_REMOTE)
        nested = repo / "Qwen"
        nested.mkdir()

        identity = shipped_resolver.resolve(
            provider="qwen", surface="desktop", cwd=nested, env={}
        )

        assert identity.project_id == "hive-mind"


class TestSessionCarriesCanonicalProject:
    """What Claude Mem receives is the canonical project, once."""

    def _session(self, resolver, cwd) -> dict:
        return attach_project_identity(
            "codex", {"cwd": str(cwd), "session_id": "d003"}, resolver=resolver
        )

    def test_session_project_field_is_the_canonical_name(
        self, shipped_resolver, tmp_path
    ):
        repo = _repository(tmp_path / "Hive-Mind", remote=HIVE_REMOTE)

        session = self._session(shipped_resolver, repo)

        # `project` is the field that feeds the Claude Mem dropdown.
        assert session["project"] == "Hive-Mind"
        assert session["project_id"] == "hive-mind"

    def test_root_and_worktree_sessions_show_one_dropdown_entry(
        self, shipped_resolver, tmp_path
    ):
        repo = _repository(tmp_path / "Hive-Mind", remote=HIVE_REMOTE)
        worktree = tmp_path / "hive-mind-windows-zero-install"
        _git(repo, "worktree", "add", "-b", "codex/x", str(worktree))

        sessions = [
            self._session(shipped_resolver, repo),
            self._session(shipped_resolver, worktree),
        ]

        assert {s["project"] for s in sessions} == {"Hive-Mind"}
        assert {s["project_id"] for s in sessions} == {"hive-mind"}

    def test_session_keeps_identity_envelope_for_the_bridge(
        self, shipped_resolver, tmp_path
    ):
        repo = _repository(tmp_path / "Hive-Mind", remote=HIVE_REMOTE)

        session = self._session(shipped_resolver, repo)
        envelope = session["project_identity"]

        assert envelope["project_id"] == "hive-mind"
        assert envelope["project_name"] == "Hive-Mind"
        for field in ("workspace_root", "repository_root", "branch", "provider"):
            assert field in envelope

    def test_surface_session_is_not_attributed_to_hive_mind(
        self, shipped_resolver, tmp_path
    ):
        workspace = tmp_path / "Qwen"
        workspace.mkdir()

        session = self._session(shipped_resolver, workspace)

        assert session["project_id"] != "hive-mind"
        assert session["project_id"].startswith("unclassified/")


class TestBridgeWritesCanonicalWorkspace:
    """The identity survives into UMC as workspace_id, on real SQLite."""

    @pytest.fixture
    def umc(self, tmp_path):
        conn = sqlite3.connect(tmp_path / "umc.db")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE observations (
                id TEXT PRIMARY KEY, project TEXT, type TEXT, title TEXT,
                content TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                archived INTEGER DEFAULT 0, metadata JSON,
                workspace_id TEXT NOT NULL DEFAULT 'default'
            )
            """
        )
        yield conn
        conn.close()

    def _store(self, conn, oid, session):
        """Mirror the bridge's insert contract: project label + workspace_id."""
        conn.execute(
            "INSERT INTO observations (id, project, workspace_id, type, title,"
            " content, metadata) VALUES (?, ?, ?, 'learning', 't', 'c', ?)",
            (
                oid,
                session["project"],
                session["project_id"],
                json.dumps({"project_identity": session["project_identity"]}),
            ),
        )
        conn.commit()

    def test_root_and_worktree_share_one_workspace_id(
        self, shipped_resolver, tmp_path, umc
    ):
        repo = _repository(tmp_path / "Hive-Mind", remote=HIVE_REMOTE)
        worktree = tmp_path / "hive-mind-windows-zero-install"
        _git(repo, "worktree", "add", "-b", "codex/y", str(worktree))

        for index, cwd in enumerate((repo, worktree)):
            session = attach_project_identity(
                "codex", {"cwd": str(cwd)}, resolver=shipped_resolver
            )
            self._store(umc, f"o{index}", session)

        workspaces = {
            r["workspace_id"] for r in umc.execute("SELECT workspace_id FROM observations")
        }
        assert workspaces == {"hive-mind"}, "worktree must not create a second workspace"

    def test_workspace_id_is_never_the_migration_default(
        self, shipped_resolver, tmp_path, umc
    ):
        repo = _repository(tmp_path / "Hive-Mind", remote=HIVE_REMOTE)
        session = attach_project_identity(
            "codex", {"cwd": str(repo)}, resolver=shipped_resolver
        )

        self._store(umc, "o1", session)

        stored = umc.execute("SELECT workspace_id FROM observations").fetchone()
        assert stored["workspace_id"] == "hive-mind"
        assert stored["workspace_id"] != "default"

    def test_two_projects_stay_isolated_and_filter_cleanly(
        self, shipped_resolver, tmp_path, umc
    ):
        """Project A / project B: a filtered query must not mix them."""
        hive = _repository(tmp_path / "Hive-Mind", remote=HIVE_REMOTE)
        other = _repository(
            tmp_path / "other", remote="https://github.com/someone/audit-b.git"
        )

        hive_session = attach_project_identity(
            "codex", {"cwd": str(hive)}, resolver=shipped_resolver
        )
        other_session = attach_project_identity(
            "codex", {"cwd": str(other)}, resolver=shipped_resolver
        )
        self._store(umc, "hive1", hive_session)
        self._store(umc, "other1", other_session)

        hive_rows = umc.execute(
            "SELECT id FROM observations WHERE workspace_id = ?", ("hive-mind",)
        ).fetchall()
        assert [r["id"] for r in hive_rows] == ["hive1"]

        # Cross-project only when explicitly asked for.
        all_rows = umc.execute("SELECT id FROM observations ORDER BY id").fetchall()
        assert [r["id"] for r in all_rows] == ["hive1", "other1"]
        assert other_session["project_id"] != hive_session["project_id"]
