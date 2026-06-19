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

from scripts import claude_mem_bridge as br

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
