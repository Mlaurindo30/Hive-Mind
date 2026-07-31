from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from core.projects.audit import (
    AuditClassification,
    ProjectAuditRow,
    audit_projects,
    render_audit_table,
)
from hive_mind import cli


REGISTRY = Path(__file__).resolve().parents[2] / "config" / "project-aliases.yaml"


def _by_label(rows):
    return {row.legacy_label: row for row in rows}


def test_minimum_legacy_labels_have_auditable_classification(tmp_path):
    rows = _by_label(
        audit_projects(
            claude_mem_db=tmp_path / "missing-claude.db",
            hive_db=tmp_path / "missing-hive.db",
            vault_root=tmp_path / "missing-vault",
            registry_path=REGISTRY,
        )
    )

    assert rows["Hive-Mind"].classification is AuditClassification.CANONICAL
    assert rows["Hive-Mind"].proposed_project_id == "hive-mind"
    assert rows["hive-mind-windows-zero-install"].classification is AuditClassification.ALIAS
    assert rows["Hive-Mind/hive-mind-windows-zero-install"].classification is AuditClassification.ALIAS
    assert rows["miche"].classification is AuditClassification.PROFILE
    for label in ("Qwen", "hermes", "app", "Microsoft Visual Studio Code", "Microsoft VS Code"):
        assert rows[label].classification is AuditClassification.SURFACE
        assert rows[label].proposed_project_id.startswith("unclassified/")
    assert all(row.sessions == row.observations == row.vectors == row.markdown == 0 for row in rows.values())
    assert all(row.reason for row in rows.values())


def test_registry_backed_raju_trader_label_is_canonical(tmp_path):
    claude = tmp_path / "claude.db"
    with sqlite3.connect(claude) as connection:
        connection.execute("CREATE TABLE observations(id INTEGER, project TEXT)")
        connection.execute("INSERT INTO observations VALUES (1, 'Raju Trader')")

    rows = _by_label(
        audit_projects(
            claude_mem_db=claude,
            hive_db=tmp_path / "missing.db",
            vault_root=tmp_path / "vault",
            registry_path=REGISTRY,
            include_minimum_labels=False,
        )
    )

    assert rows["Raju Trader"].classification is AuditClassification.CANONICAL
    assert rows["Raju Trader"].proposed_project_id == "local/75a99723f2d2"


def test_shipped_hive_mind_registry_root_does_not_point_to_backup_worktrees():
    payload = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    hive_mind = next(
        project for project in payload["projects"] if project["project_id"] == "hive-mind"
    )

    assert hive_mind["roots"] == [r"D:\Hive-Mind"]


def test_validated_identity_evidence_links_surface_but_conflict_is_ambiguous(tmp_path):
    db = tmp_path / "claude.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE observations(id INTEGER, project TEXT, metadata TEXT)")
        connection.executemany(
            "INSERT INTO observations VALUES (?, ?, ?)",
            [
                (1, "hermes", json.dumps({"project_identity": {"project_id": "hive-mind"}})),
                (2, "Qwen", json.dumps({"project_identity": {"project_id": "project-a"}})),
                (3, "Qwen", json.dumps({"project_identity": {"project_id": "project-b"}})),
            ],
        )

    rows = _by_label(
        audit_projects(
            claude_mem_db=db,
            hive_db=tmp_path / "missing.db",
            vault_root=tmp_path / "vault",
            registry_path=REGISTRY,
            include_minimum_labels=False,
        )
    )

    assert rows["hermes"].classification is AuditClassification.ALIAS
    assert rows["hermes"].proposed_project_id == "hive-mind"
    assert rows["Qwen"].classification is AuditClassification.AMBIGUOUS
    assert rows["Qwen"].proposed_project_id is None
    assert "project-a" in rows["Qwen"].reason and "project-b" in rows["Qwen"].reason


def test_cli_projects_audit_json_uses_only_explicit_paths(tmp_path, capsys):
    claude = tmp_path / "claude.db"
    hive = tmp_path / "hive.db"
    with sqlite3.connect(claude) as connection:
        connection.execute("CREATE TABLE observations(id INTEGER, project TEXT)")
        connection.execute("INSERT INTO observations VALUES (1, 'Hive-Mind')")
    with sqlite3.connect(hive) as connection:
        connection.execute("CREATE TABLE observations(id TEXT, project TEXT)")
    vault = tmp_path / "vault"
    vault.mkdir()

    result = cli.main([
        "projects", "audit", "--json",
        "--claude-mem-db", str(claude),
        "--hive-db", str(hive),
        "--vault-root", str(vault),
        "--registry", str(REGISTRY),
    ])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    hive_mind = next(row for row in payload if row["legacy_label"] == "Hive-Mind")
    assert hive_mind["classification"] == "CANONICAL"
    assert hive_mind["observations"] == 1


def test_projects_audit_tolerates_unavailable_vec_module(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import core.projects.audit as audit_mod

    db = tmp_path / "claude.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE observations(id INTEGER, project TEXT)")
        connection.execute("INSERT INTO observations VALUES (1, 'Hive-Mind')")
        connection.execute("CREATE TABLE vec_observations(rowid INTEGER PRIMARY KEY, embedding BLOB)")
        connection.execute("INSERT INTO vec_observations VALUES (1, X'00')")

    original = audit_mod._columns

    def flaky_columns(connection, table):
        if table == "vec_observations":
            raise sqlite3.OperationalError("no such module: vec0")
        return original(connection, table)

    monkeypatch.setattr(audit_mod, "_columns", flaky_columns)

    rows = _by_label(
        audit_projects(
            claude_mem_db=db,
            hive_db=tmp_path / "missing.db",
            vault_root=tmp_path / "vault",
            registry_path=REGISTRY,
            include_minimum_labels=False,
        )
    )

    assert rows["Hive-Mind"].observations == 1
    assert rows["Hive-Mind"].vectors == 0

def test_classification_contract_has_exactly_six_values():
    assert {item.value for item in AuditClassification} == {
        "CANONICAL", "ALIAS", "SURFACE", "PROFILE", "UNCLASSIFIED", "AMBIGUOUS"
    }


def test_text_table_has_required_columns():
    rendered = render_audit_table(iter([
        ProjectAuditRow(
            legacy_label="app",
            proposed_project_id="unclassified/app",
            sessions=1,
            observations=2,
            vectors=3,
            markdown=4,
            confidence=0.95,
            classification=AuditClassification.SURFACE,
            reason="application surface",
        )
    ]))
    for heading in (
        "Label antiga", "project_id proposto", "Sessões", "Observações",
        "Vetores", "Markdown", "Confiança", "Classificação",
    ):
        assert heading in rendered
    assert "app" in rendered and "SURFACE" in rendered
    assert "Razões:" in rendered
    assert "application surface" in rendered
