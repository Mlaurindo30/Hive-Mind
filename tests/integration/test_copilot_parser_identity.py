from __future__ import annotations

import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path

from hive_mind.capture.session_events import attach_project_identity
from hive_mind.projects.identity import ProjectAliasRegistry, ProjectIdentityResolver


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "capture"
PARSER_PATH = CAPTURE / "parsers" / "copilot.py"
if str(CAPTURE) not in sys.path:
    sys.path.insert(0, str(CAPTURE))


def _parser():
    spec = importlib.util.spec_from_file_location("copilot_parser_identity", PARSER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=10
    )


def test_copilot_sqlite_workspace_evidence_resolves_a_local_git_project(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "copilot-workspace"
    workspace.mkdir()
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "copilot-tests@example.invalid")
    _git(workspace, "config", "user.name", "Copilot Tests")
    (workspace / "README.md").write_text("identity\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-m", "initial")
    foreign_root = tmp_path / "foreign-project"
    foreign_root.mkdir()
    monkeypatch.setenv("HIVE_PROJECT_ROOT", str(foreign_root))
    monkeypatch.setenv("HIVE_PROJECT_ID", "forced/environment")

    database = tmp_path / "session-store.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE sessions (id TEXT, cwd TEXT, repository TEXT, branch TEXT, host_type TEXT);
            CREATE TABLE turns (
                session_id TEXT, turn_index INTEGER, user_message TEXT, assistant_response TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
            ("copilot-1", str(workspace), str(workspace), "main", "vscode"),
        )
        connection.execute(
            "INSERT INTO turns VALUES (?, ?, ?, ?)",
            ("copilot-1", 1, "prompt", "answer"),
        )

    session = _parser().parse(database)[0]
    monkeypatch.delenv("HIVE_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("HIVE_PROJECT_ID", raising=False)
    normalized = attach_project_identity(
        "copilot",
        session,
        resolver=ProjectIdentityResolver(registry=ProjectAliasRegistry.empty()),
    )

    assert normalized["project_id"].startswith("local/")
    assert normalized["project_id"] != "unclassified/copilot"
    assert normalized["workspace_root"] == str(workspace.resolve())
    assert normalized["repository_root"] == str(workspace.resolve())
    assert normalized["resolution_method"] == "official_workspace"
