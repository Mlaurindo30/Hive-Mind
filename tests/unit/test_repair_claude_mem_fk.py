import sqlite3
from pathlib import Path

from scripts.setup.repair_claude_mem_fk import DEFAULT_DB, ROOT, backup_database, repair


def test_default_db_e_project_local():
    assert DEFAULT_DB == ROOT / "claude-mem" / "data" / "claude-mem.db"
    assert Path.home() / ".claude-mem" not in DEFAULT_DB.parents


def test_repair_creates_session_without_deleting_children(tmp_path):
    db = tmp_path / "claude-mem.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE sdk_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_session_id TEXT UNIQUE NOT NULL,
            memory_session_id TEXT UNIQUE,
            project TEXT NOT NULL,
            platform_source TEXT NOT NULL,
            started_at TEXT NOT NULL,
            started_at_epoch INTEGER NOT NULL,
            completed_at TEXT,
            completed_at_epoch INTEGER,
            status TEXT NOT NULL,
            prompt_counter INTEGER DEFAULT 0,
            custom_title TEXT
        );
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT REFERENCES sdk_sessions(memory_session_id),
            project TEXT,
            created_at TEXT,
            created_at_epoch INTEGER,
            prompt_number INTEGER
        );
        CREATE TABLE session_summaries (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT REFERENCES sdk_sessions(memory_session_id),
            project TEXT,
            created_at TEXT,
            created_at_epoch INTEGER,
            prompt_number INTEGER
        );
        """
    )
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute(
        "INSERT INTO observations VALUES (1,'gemini-orphan','Hive','2026-06-10T00:00:00Z',10,2)"
    )
    conn.commit()
    conn.close()

    repaired, backup = repair(db)

    conn = sqlite3.connect(db)
    assert repaired == 1
    assert backup and backup.exists()
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sdk_sessions").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_backup_database_prunes_old_files(tmp_path):
    db = tmp_path / "claude-mem.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY)")
    conn.commit()

    backup_dir = tmp_path / "backups" / "fk-repair"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stale = backup_dir / "claude-mem.before-fk-repair.20200101T000000Z.db"
    stale.write_bytes(b"stale")

    backup_path = backup_database(conn, db, keep_last=1)
    conn.close()

    backups = sorted(backup_dir.glob("claude-mem.before-fk-repair.*.db"))
    assert len(backups) == 1
    assert backups[0] == backup_path
    assert not stale.exists()
