import json
import sqlite3

from hive_mind.maintenance.legacy_migration import migrate_legacy_observations


def _make_registry(tmp_path):
    path = tmp_path / "project-aliases.yaml"
    path.write_text(
        """
schema_version: 1
projects:
  - project_id: hive-mind
    project_name: Hive-Mind
    aliases:
      - Hive-Mind
""".strip(),
        encoding="utf-8",
    )
    return path


def test_migrate_legacy_dry_run_accepts_unclassified_provider_fallback(monkeypatch, tmp_path):
    registry = _make_registry(tmp_path)
    umc = tmp_path / "hive.db"
    conn = sqlite3.connect(umc)
    conn.execute(
        "CREATE TABLE observations (id TEXT PRIMARY KEY, workspace_id TEXT, project TEXT,"
        " metadata TEXT, archived INTEGER)"
    )
    conn.execute(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
        ("a", "unclassified/legacy", "legacy", json.dumps({"source_session": "sid-1"}), 0),
    )
    conn.commit()
    conn.close()

    cmem = tmp_path / "claude-mem.db"
    conn = sqlite3.connect(cmem)
    conn.execute("CREATE TABLE sdk_sessions (memory_session_id TEXT PRIMARY KEY, project TEXT)")
    conn.execute(
        "INSERT INTO sdk_sessions VALUES (?, ?)",
        ("sid-1", "Unclassified (antigravity)"),
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("CLAUDE_MEM_DB", str(cmem))

    report = migrate_legacy_observations(
        hive_db=umc,
        claude_mem_db=cmem,
        registry_path=registry,
        apply=False,
    )

    assert report.scanned == 1
    assert report.candidates == 1
    assert report.updated == 0
    assert dict(report.candidate_rows_by_project) == {"unclassified/antigravity": 1}
    assert dict(report.unmapped_rows_by_label) == {}


def test_migrate_legacy_apply_rewrites_to_unclassified_provider_fallback(monkeypatch, tmp_path):
    registry = _make_registry(tmp_path)
    umc = tmp_path / "hive.db"
    conn = sqlite3.connect(umc)
    conn.execute(
        "CREATE TABLE observations (id TEXT PRIMARY KEY, workspace_id TEXT, project TEXT,"
        " metadata TEXT, archived INTEGER)"
    )
    conn.execute(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
        ("a", "unclassified/legacy", "legacy", json.dumps({"source_session": "sid-1"}), 0),
    )
    conn.commit()
    conn.close()

    cmem = tmp_path / "claude-mem.db"
    conn = sqlite3.connect(cmem)
    conn.execute("CREATE TABLE sdk_sessions (memory_session_id TEXT PRIMARY KEY, project TEXT)")
    conn.execute(
        "INSERT INTO sdk_sessions VALUES (?, ?)",
        ("sid-1", "Unclassified (antigravity)"),
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("CLAUDE_MEM_DB", str(cmem))

    report = migrate_legacy_observations(
        hive_db=umc,
        claude_mem_db=cmem,
        registry_path=registry,
        apply=True,
    )

    assert report.candidates == 1
    assert report.updated == 1

    conn = sqlite3.connect(umc)
    conn.row_factory = sqlite3.Row
    migrated = conn.execute(
        "SELECT workspace_id, project, metadata FROM observations WHERE id='a'"
    ).fetchone()
    conn.close()

    payload = json.loads(migrated["metadata"])
    assert migrated["workspace_id"] == "unclassified/antigravity"
    assert migrated["project"] == "Unclassified (antigravity)"
    assert payload["project_id"] == "unclassified/antigravity"
    assert payload["project_name"] == "Unclassified (antigravity)"
    assert payload["identity_status"] == "canonical"


def test_migrate_legacy_dry_run_only_counts_recoverable_rows(monkeypatch, tmp_path):
    registry = _make_registry(tmp_path)
    umc = tmp_path / "hive.db"
    conn = sqlite3.connect(umc)
    conn.execute(
        "CREATE TABLE observations (id TEXT PRIMARY KEY, workspace_id TEXT, project TEXT,"
        " metadata TEXT, archived INTEGER)"
    )
    conn.executemany(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
        [
            ("a", "unclassified/legacy", "Hive-Mind", json.dumps({"source_session": "sid-1"}), 0),
            ("b", "unclassified/legacy", "Raju Trader", json.dumps({"source_session": "sid-2"}), 0),
            ("c", "unclassified/legacy", "Missing", json.dumps({}), 0),
        ],
    )
    conn.commit()
    conn.close()

    cmem = tmp_path / "claude-mem.db"
    conn = sqlite3.connect(cmem)
    conn.execute("CREATE TABLE sdk_sessions (memory_session_id TEXT PRIMARY KEY, project TEXT)")
    conn.executemany(
        "INSERT INTO sdk_sessions VALUES (?, ?)",
        [("sid-1", "Hive-Mind"), ("sid-2", "Raju Trader")],
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("CLAUDE_MEM_DB", str(cmem))

    report = migrate_legacy_observations(
        hive_db=umc,
        claude_mem_db=cmem,
        registry_path=registry,
        apply=False,
    )
    assert report.scanned == 3
    assert report.candidates == 1
    assert report.updated == 0
    assert report.skipped_missing_source_session == 1
    assert dict(report.unmapped_rows_by_label) == {"Raju Trader": 1}
    assert dict(report.candidate_rows_by_project) == {"hive-mind": 1}

    conn = sqlite3.connect(umc)
    row = conn.execute("SELECT workspace_id FROM observations WHERE id='a'").fetchone()
    conn.close()
    assert row[0] == "unclassified/legacy"


def test_migrate_legacy_apply_rewrites_only_recoverable_rows(monkeypatch, tmp_path):
    registry = _make_registry(tmp_path)
    umc = tmp_path / "hive.db"
    conn = sqlite3.connect(umc)
    conn.execute(
        "CREATE TABLE observations (id TEXT PRIMARY KEY, workspace_id TEXT, project TEXT,"
        " metadata TEXT, archived INTEGER)"
    )
    conn.executemany(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
        [
            ("a", "unclassified/legacy", "Legacy Label", json.dumps({"source_session": "sid-1"}), 0),
            ("b", "unclassified/legacy", "Raju Trader", json.dumps({"source_session": "sid-2"}), 0),
        ],
    )
    conn.commit()
    conn.close()

    cmem = tmp_path / "claude-mem.db"
    conn = sqlite3.connect(cmem)
    conn.execute("CREATE TABLE sdk_sessions (memory_session_id TEXT PRIMARY KEY, project TEXT)")
    conn.executemany(
        "INSERT INTO sdk_sessions VALUES (?, ?)",
        [("sid-1", "Hive-Mind"), ("sid-2", "Raju Trader")],
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("CLAUDE_MEM_DB", str(cmem))

    report = migrate_legacy_observations(
        hive_db=umc,
        claude_mem_db=cmem,
        registry_path=registry,
        apply=True,
    )
    assert report.candidates == 1
    assert report.updated == 1

    conn = sqlite3.connect(umc)
    conn.row_factory = sqlite3.Row
    migrated = conn.execute(
        "SELECT workspace_id, project, metadata FROM observations WHERE id='a'"
    ).fetchone()
    untouched = conn.execute(
        "SELECT workspace_id, project FROM observations WHERE id='b'"
    ).fetchone()
    conn.close()

    payload = json.loads(migrated["metadata"])
    assert migrated["workspace_id"] == "hive-mind"
    assert migrated["project"] == "Hive-Mind"
    assert payload["identity_status"] == "canonical"
    assert payload["legacy_identity"] is False
    assert payload["legacy_reconciliation"]["source_workspace"] == "unclassified/legacy"
    assert untouched["workspace_id"] == "unclassified/legacy"
    assert untouched["project"] == "Raju Trader"
