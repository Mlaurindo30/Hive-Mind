import json
import sqlite3
from pathlib import Path

from hive_mind.maintenance.legacy_migration import migrate_legacy_observations


def _write_registry(path: Path) -> None:
    path.write_text(
        "\n".join([
            "schema_version: 1",
            "projects:",
            "  - project_id: hive-mind",
            "    project_name: Hive-Mind",
            "    aliases:",
            "      - Hive-Mind",
            "      - hive-mind-windows-zero-install",
        ]),
        encoding="utf-8",
    )


def _init_hive(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE observations ("
        "id TEXT PRIMARY KEY, workspace_id TEXT, project TEXT, metadata TEXT, archived INTEGER)"
    )
    conn.executemany(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
        [
            (
                "obs-hive",
                "unclassified/legacy",
                "Hive-Mind",
                json.dumps({"source_session": "openrouter-11111111-1111-1111-1111-111111111111-1785172305849"}),
                0,
            ),
            (
                "obs-raju",
                "unclassified/legacy",
                "Raju Trader",
                json.dumps({"source_session": "openrouter-22222222-2222-2222-2222-222222222222-1785126932184"}),
                0,
            ),
        ],
    )
    conn.commit()
    conn.close()


def _init_claude_mem(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE sdk_sessions ("
        "memory_session_id TEXT PRIMARY KEY, content_session_id TEXT, project TEXT)"
    )
    conn.executemany(
        "INSERT INTO sdk_sessions VALUES (?, ?, ?)",
        [
            (
                "openrouter-x-1785000000000",
                "11111111-1111-1111-1111-111111111111",
                "Hive-Mind",
            ),
            (
                "openrouter-22222222-2222-2222-2222-222222222222-1785126932184",
                "22222222-2222-2222-2222-222222222222",
                "Raju Trader",
            ),
        ],
    )
    conn.commit()
    conn.close()


def test_dry_run_reports_only_registry_backed_candidates(tmp_path):
    hive = tmp_path / "hive.db"
    claude_mem = tmp_path / "claude-mem.db"
    registry = tmp_path / "project-aliases.yaml"
    _init_hive(hive)
    _init_claude_mem(claude_mem)
    _write_registry(registry)

    report = migrate_legacy_observations(
        hive_db=hive,
        claude_mem_db=claude_mem,
        registry_path=registry,
        apply=False,
    )

    assert report.apply is False
    assert report.scanned == 2
    assert report.candidates == 1
    assert report.updated == 0
    assert dict(report.candidate_rows_by_project) == {"hive-mind": 1}
    assert dict(report.unmapped_rows_by_label) == {"Raju Trader": 1}


def test_apply_updates_only_safe_candidates(tmp_path):
    hive = tmp_path / "hive.db"
    claude_mem = tmp_path / "claude-mem.db"
    registry = tmp_path / "project-aliases.yaml"
    _init_hive(hive)
    _init_claude_mem(claude_mem)
    _write_registry(registry)

    report = migrate_legacy_observations(
        hive_db=hive,
        claude_mem_db=claude_mem,
        registry_path=registry,
        target_project_id="hive-mind",
        apply=True,
    )

    assert report.updated == 1

    conn = sqlite3.connect(hive)
    conn.row_factory = sqlite3.Row
    migrated = conn.execute(
        "SELECT workspace_id, project, metadata FROM observations WHERE id='obs-hive'"
    ).fetchone()
    preserved = conn.execute(
        "SELECT workspace_id, project, metadata FROM observations WHERE id='obs-raju'"
    ).fetchone()
    conn.close()

    migrated_meta = json.loads(migrated["metadata"])
    assert migrated["workspace_id"] == "hive-mind"
    assert migrated["project"] == "Hive-Mind"
    assert migrated_meta["project_id"] == "hive-mind"
    assert migrated_meta["project_name"] == "Hive-Mind"
    assert migrated_meta["identity_status"] == "canonical"
    assert migrated_meta["legacy_identity"] is False
    assert migrated_meta["legacy_reconciliation"]["method"] == "sdk_session_alias_registry"

    assert preserved["workspace_id"] == "unclassified/legacy"
    assert preserved["project"] == "Raju Trader"


def test_default_ins_without_registry_alias_stays_preserved(tmp_path):
    hive = tmp_path / "hive.db"
    claude_mem = tmp_path / "claude-mem.db"
    registry = tmp_path / "project-aliases.yaml"
    _write_registry(registry)

    conn = sqlite3.connect(hive)
    conn.execute(
        "CREATE TABLE observations ("
        "id TEXT PRIMARY KEY, workspace_id TEXT, project TEXT, metadata TEXT, archived INTEGER)"
    )
    conn.execute(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
        (
            "obs-ins",
            "default",
            "ins",
            json.dumps(
                {
                    "source_session": "openrouter-019f6b7a-98a8-7e22-85b8-661bbcee3d91-1784228743493",
                    "project": "ins",
                }
            ),
            0,
        ),
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(claude_mem)
    conn.execute(
        "CREATE TABLE sdk_sessions ("
        "memory_session_id TEXT PRIMARY KEY, content_session_id TEXT, project TEXT)"
    )
    conn.execute(
        "INSERT INTO sdk_sessions VALUES (?, ?, ?)",
        (
            "openrouter-019f6b7a-98a8-7e22-85b8-661bbcee3d91-1784228743493",
            "019f6b7a-98a8-7e22-85b8-661bbcee3d91",
            "ins",
        ),
    )
    conn.commit()
    conn.close()

    report = migrate_legacy_observations(
        hive_db=hive,
        claude_mem_db=claude_mem,
        registry_path=registry,
        source_workspace="default",
        apply=False,
    )

    assert report.scanned == 1
    assert report.candidates == 0
    assert report.updated == 0
    assert dict(report.unmapped_rows_by_label) == {"ins": 1}
