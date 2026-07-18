from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from core.projects.audit import audit_projects


REGISTRY = Path(__file__).resolve().parents[2] / "config" / "project-aliases.yaml"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path, table: str) -> int:
    with sqlite3.connect(path) as connection:
        return connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def test_audit_inventory_is_schema_tolerant_and_does_not_change_sources(tmp_path):
    claude = tmp_path / "claude-mem.db"
    with sqlite3.connect(claude) as connection:
        connection.executescript("""
            CREATE TABLE sessions(id TEXT PRIMARY KEY, project TEXT, metadata TEXT);
            CREATE TABLE observations(id INTEGER PRIMARY KEY, project TEXT, metadata TEXT);
            CREATE TABLE vec_observations(rowid INTEGER PRIMARY KEY, embedding BLOB);
        """)
        connection.executemany(
            "INSERT INTO sessions VALUES (?, ?, ?)",
            [
                ("s1", "Hive-Mind", json.dumps({"project_identity": {"project_id": "hive-mind"}})),
                ("s2", "hermes", None),
            ],
        )
        connection.executemany(
            "INSERT INTO observations VALUES (?, ?, ?)",
            [
                (1, "Hive-Mind", json.dumps({"project_identity": {"project_id": "hive-mind"}})),
                (2, "hermes", None),
            ],
        )
        connection.execute("INSERT INTO vec_observations VALUES (1, X'0000')")

    hive = tmp_path / "hive_mind.db"
    with sqlite3.connect(hive) as connection:
        connection.executescript("""
            CREATE TABLE observations(id TEXT PRIMARY KEY, project TEXT, metadata JSON);
            CREATE TABLE vector_metadata(collection TEXT, id TEXT, project TEXT);
        """)
        connection.execute("INSERT INTO observations VALUES ('o1', 'Hive-Mind', NULL)")
        connection.execute("INSERT INTO vector_metadata VALUES ('document_vectors', 'v1', 'Hive-Mind')")

    vault = tmp_path / "cerebro"
    note = vault / "cortex" / "temporal" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text("---\nproject: Hive-Mind\n---\n# note\n", encoding="utf-8")

    files = (claude, hive, note)
    before = {path: (_digest(path), path.stat().st_mtime_ns) for path in files}
    before_rows = {
        (claude, "sessions"): _rows(claude, "sessions"),
        (claude, "observations"): _rows(claude, "observations"),
        (claude, "vec_observations"): _rows(claude, "vec_observations"),
        (hive, "observations"): _rows(hive, "observations"),
        (hive, "vector_metadata"): _rows(hive, "vector_metadata"),
    }

    rows = {row.legacy_label: row for row in audit_projects(
        claude_mem_db=claude,
        hive_db=hive,
        vault_root=vault,
        registry_path=REGISTRY,
        include_minimum_labels=False,
    )}

    assert rows["Hive-Mind"].sessions == 1
    assert rows["Hive-Mind"].observations == 2
    assert rows["Hive-Mind"].vectors == 2
    assert rows["Hive-Mind"].markdown == 1
    assert rows["hermes"].sessions == 1
    assert rows["hermes"].observations == 1
    assert rows["hermes"].vectors == 0

    after = {path: (_digest(path), path.stat().st_mtime_ns) for path in files}
    after_rows = {(path, table): _rows(path, table) for path, table in before_rows}
    assert after == before
    assert after_rows == before_rows


def test_audit_ignores_absent_tables_and_unknown_markdown_schema(tmp_path):
    db = tmp_path / "minimal.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('leave-me')")
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "plain.md").write_text("# no frontmatter\n", encoding="utf-8")

    assert audit_projects(
        claude_mem_db=db,
        hive_db=db,
        vault_root=vault,
        registry_path=REGISTRY,
        include_minimum_labels=False,
    ) == []
    assert _rows(db, "unrelated") == 1

def test_implicit_rowid_observation_vectors_are_attributed(tmp_path):
    db = tmp_path / "implicit-rowid.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE observations(id INTEGER PRIMARY KEY, project TEXT)")
        connection.execute("CREATE TABLE vec_observations(embedding BLOB)")
        connection.execute("INSERT INTO observations VALUES (1, 'Hive-Mind')")
        connection.execute("INSERT INTO vec_observations(rowid, embedding) VALUES (1, X'00')")

    rows = {row.legacy_label: row for row in audit_projects(
        claude_mem_db=db,
        hive_db=tmp_path / "absent.db",
        vault_root=tmp_path / "vault",
        registry_path=REGISTRY,
        include_minimum_labels=False,
    )}

    assert rows["Hive-Mind"].vectors == 1