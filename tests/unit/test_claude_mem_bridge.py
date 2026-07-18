"""Ponte claude-mem → hive_mind (doc 08) — preserva project, idempotente, quarentena.

Testa contra SQLite REAL (R1/R5): fonte (claude-mem) e destino (hive_mind) em arquivos
temporários, com get_connection/open_claude_mem monkeypatchados p/ abrir conexões frescas
(fiel ao runtime, onde cada chamada abre/fecha sua conexão)."""
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts.services import claude_mem_bridge as br

_HM_DDL = """
CREATE TABLE observations (
    id TEXT PRIMARY KEY, session_id TEXT, project TEXT, type TEXT, title TEXT,
    content TEXT, created_at DATETIME, neuron_id TEXT, metadata JSON,
    archived INTEGER DEFAULT 0
);
CREATE TABLE neurons (id TEXT PRIMARY KEY, label TEXT, type TEXT);
"""
_CM_DDL = """
CREATE TABLE observations (
    id INTEGER PRIMARY KEY, project TEXT, text TEXT, narrative TEXT, title TEXT,
    type TEXT, created_at TEXT, created_at_epoch INTEGER, content_hash TEXT
);
"""


def _connect(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    return c


@pytest.fixture()
def hm_path(tmp_path, monkeypatch):
    p = tmp_path / "hive_mind.db"
    c = _connect(p); c.executescript(_HM_DDL); c.commit(); c.close()
    monkeypatch.setattr(br, "get_connection", lambda: _connect(p))
    monkeypatch.setattr(br, "ensure_migrations", lambda c: None)
    return p


@pytest.fixture()
def cm_path(tmp_path, monkeypatch):
    p = tmp_path / "claude-mem.db"
    c = _connect(p); c.executescript(_CM_DDL)
    c.executemany(
        "INSERT INTO observations (id,project,text,narrative,title,type,created_at,created_at_epoch,content_hash)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        [(1, "ComfyUI", "node novo", None, "Node", "decision", "2026-06-10", 1000, "h-comfy"),
         (2, "Thoth", "rota auth", None, "Auth", "learning", "2026-06-11", 1001, "h-thoth"),
         (3, "Hive-Mind", "tweak dream", None, "Dream", "decision", "2026-06-12", 1002, "h-hive"),
         (4, None, "sem projeto", None, "Sem", "event", "2026-06-13", 1003, "h-null")])
    c.commit(); c.close()
    monkeypatch.setattr(br, "open_claude_mem", lambda db_path=None: _connect(p))
    return p


def _count(path, where="1=1"):
    c = _connect(path)
    try:
        return c.execute(f"SELECT COUNT(*) FROM observations WHERE {where}").fetchone()[0]
    finally:
        c.close()


def test_bridge_preserva_project(hm_path, cm_path):
    stats = br.bridge(cm_db=cm_path)
    assert stats["inserted"] == 4
    c = _connect(hm_path)
    projs = dict(c.execute("SELECT project, COUNT(*) FROM observations GROUP BY project").fetchall())
    c.close()
    assert projs.get("ComfyUI") == 1 and projs.get("Thoth") == 1
    assert _count(hm_path, "project IS NULL") == 0   # null vira default, não fica NULL


def test_default_claude_mem_db_aponta_para_global(monkeypatch):
    monkeypatch.delenv("CLAUDE_MEM_DB", raising=False)
    assert br.CLAUDE_MEM_DB == br.Path.home() / ".claude-mem" / "claude-mem.db"


def test_bridge_idempotente(hm_path, cm_path):
    br.bridge(cm_db=cm_path)
    stats2 = br.bridge(cm_db=cm_path)
    assert stats2["inserted"] == 0 and stats2["skipped"] == 4
    assert _count(hm_path) == 4   # não duplica


def test_bridge_id_deterministico(hm_path, cm_path):
    br.bridge(cm_db=cm_path)
    c = _connect(hm_path)
    ids = [r[0] for r in c.execute("SELECT id FROM observations")]
    c.close()
    assert all(i.startswith("cm-") for i in ids)
    assert "cm-h-comfy" in ids


def test_dry_run_nao_escreve(hm_path, cm_path):
    stats = br.bridge(cm_db=cm_path, dry_run=True)
    assert stats["inserted"] == 4
    assert _count(hm_path) == 0


def test_quarantine_legacy(hm_path, cm_path):
    c = _connect(hm_path)
    c.execute("INSERT INTO observations (id, project, archived) VALUES ('junk1', NULL, 0)")
    c.execute("INSERT INTO observations (id, project, archived) VALUES ('junk2', NULL, 0)")
    c.commit(); c.close()
    n = br.quarantine_legacy()
    assert n == 2
    assert _count(hm_path, "archived=2") == 2
    # bridged (cm-*) nunca é quarentenado
    br.bridge(cm_db=cm_path)
    assert _count(hm_path, "id LIKE 'cm-%' AND archived=2") == 0


def _identity_envelope(**overrides):
    envelope = {
        "project_id": "root/canonical-2fbe6cbe9d3a",
        "project_name": "Canonical Project",
        "workspace_root": r"D:\\Canonical",
        "repository_root": r"D:\\Canonical",
        "repository_remote": "github.com/example/canonical-project",
        "git_common_dir": r"D:\\Canonical\\.git",
        "worktree_name": "canonical-worktree",
        "branch": "feature/identity",
        "provider": "copilot",
        "surface": "ide-extension",
        "resolution_method": "git_remote",
        "resolution_confidence": 1.0,
        "referenced_projects": [],
        "schema_version": 1,
        "future_optional_field": "preserved",
    }
    envelope.update(overrides)
    return envelope


def test_bridge_uses_versioned_identity_envelope_for_project_and_workspace(hm_path, cm_path):
    import json

    hm = _connect(hm_path)
    hm.execute("ALTER TABLE observations ADD COLUMN workspace_id TEXT")
    hm.commit()
    hm.close()

    cm = _connect(cm_path)
    cm.execute("ALTER TABLE observations ADD COLUMN metadata TEXT")
    cm.execute("ALTER TABLE observations ADD COLUMN memory_session_id TEXT")
    cm.execute(
        "UPDATE observations SET project=?, memory_session_id=?, metadata=? WHERE id=1",
        (
            "provider-free-form-label",
            "source-session-1",
            json.dumps({"project_identity": _identity_envelope()}),
        ),
    )
    cm.commit()
    cm.close()

    stats = br.bridge(cm_db=cm_path, source_ids=["claude-mem:observations:1"])

    hm = _connect(hm_path)
    row = hm.execute(
        "SELECT project, workspace_id, metadata FROM observations WHERE id='cm-h-comfy'"
    ).fetchone()
    hm.close()
    metadata = json.loads(row["metadata"])
    assert row["workspace_id"] == "root/canonical-2fbe6cbe9d3a"
    assert row["project"] == "Canonical Project"
    assert metadata["project_id"] == "root/canonical-2fbe6cbe9d3a"
    assert metadata["project_name"] == "Canonical Project"
    assert metadata["provider"] == "copilot"
    assert metadata["surface"] == "ide-extension"
    assert metadata["branch"] == "feature/identity"
    assert metadata["worktree_name"] == "canonical-worktree"
    assert metadata["source_session"] == "source-session-1"
    assert metadata["identity_status"] == "canonical"
    assert metadata["project_identity"]["future_optional_field"] == "preserved"
    assert stats["by_identity"] == {"canonical": 1}


def test_bridge_marks_legacy_identity_unclassified_without_inference(hm_path, cm_path):
    import json

    hm = _connect(hm_path)
    hm.execute("ALTER TABLE observations ADD COLUMN workspace_id TEXT")
    hm.commit()
    hm.close()

    stats = br.bridge(cm_db=cm_path, source_ids=["claude-mem:observations:2"])

    hm = _connect(hm_path)
    row = hm.execute(
        "SELECT project, workspace_id, metadata FROM observations WHERE id='cm-h-thoth'"
    ).fetchone()
    hm.close()
    metadata = json.loads(row["metadata"])
    assert row["project"] == "Thoth"
    assert row["workspace_id"] == "unclassified/legacy"
    assert metadata["project_id"] == "unclassified/legacy"
    assert metadata["identity_status"] == "legacy"
    assert metadata["legacy_identity"] is True
    assert metadata["project_id"] not in {"thoth", "provider", "surface"}
    assert stats["by_identity"] == {"legacy": 1}
