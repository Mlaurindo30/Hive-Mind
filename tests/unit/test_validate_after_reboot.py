from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.health import validate_after_reboot as MODULE


def test_listening_ports_extracts_loopback(monkeypatch):
    output = "\n".join(
        [
            "LISTEN 0 512 127.0.0.1:37700 0.0.0.0:*",
            "LISTEN 0 5 127.0.0.1:37701 0.0.0.0:*",
            "LISTEN 0 2048 127.0.0.1:37702 0.0.0.0:*",
        ]
    )

    class Result:
        stdout = output

    monkeypatch.setattr(MODULE, "run", lambda *args, **kwargs: Result())
    assert MODULE.listening_ports() == {
        "37700": "127.0.0.1:37700",
        "37701": "127.0.0.1:37701",
        "37702": "127.0.0.1:37702",
    }


def test_prepare_records_current_boot(monkeypatch, tmp_path):
    marker = tmp_path / "pre-reboot.json"
    monkeypatch.setattr(MODULE, "LOG_DIR", tmp_path)
    monkeypatch.setattr(MODULE, "MARKER", marker)
    monkeypatch.setattr(MODULE, "REPORT", tmp_path / "post-reboot.json")
    monkeypatch.setattr(MODULE, "boot_id", lambda: "boot-before")
    assert MODULE.prepare() == 0
    assert '"boot_id": "boot-before"' in marker.read_text()


def test_claude_mem_database_loads_sqlite_vec(monkeypatch, tmp_path):
    import sqlite_vec

    home = tmp_path / "home"
    db_dir = home / ".claude-mem"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "claude-mem.db"
    connection = MODULE.sqlite3.connect(db_path)
    connection.execute("CREATE TABLE observations(id INTEGER PRIMARY KEY)")
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    connection.execute("CREATE VIRTUAL TABLE vec_observations USING vec0(embedding float[2])")
    connection.execute("INSERT INTO observations DEFAULT VALUES")
    connection.execute(
        "INSERT INTO vec_observations(rowid, embedding) VALUES (1, ?)",
        (b"\x00" * 8,),
    )
    connection.commit()
    connection.close()

    monkeypatch.setattr(MODULE.Path, "home", classmethod(lambda cls: home))
    result = MODULE.claude_mem_database()
    assert result["path"] == str(db_path)
    assert result["integrity_check"] == "ok"
    assert result["observations"] == 1
    assert result["vectors"] == 1



def _build_claude_mem_like(db_path):
    """Cria um claude-mem.db mínimo com as 3 FKs reais para sdk_sessions."""
    conn = MODULE.sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE sdk_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_session_id TEXT UNIQUE NOT NULL,
            memory_session_id TEXT UNIQUE,
            project TEXT NOT NULL,
            platform_source TEXT NOT NULL DEFAULT 'claude',
            started_at TEXT NOT NULL,
            started_at_epoch INTEGER NOT NULL,
            status TEXT CHECK(status IN ('active','completed','failed')) NOT NULL DEFAULT 'active'
        );
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT NOT NULL,
            FOREIGN KEY(memory_session_id) REFERENCES sdk_sessions(memory_session_id)
                ON DELETE CASCADE ON UPDATE CASCADE
        );
        CREATE TABLE session_summaries (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT NOT NULL,
            FOREIGN KEY(memory_session_id) REFERENCES sdk_sessions(memory_session_id)
                ON DELETE CASCADE ON UPDATE CASCADE
        );
        CREATE TABLE user_prompts (
            id INTEGER PRIMARY KEY,
            content_session_id TEXT NOT NULL,
            FOREIGN KEY(content_session_id) REFERENCES sdk_sessions(content_session_id)
                ON DELETE CASCADE
        );
        CREATE TABLE pending_messages (
            id INTEGER PRIMARY KEY,
            session_db_id INTEGER NOT NULL,
            FOREIGN KEY(session_db_id) REFERENCES sdk_sessions(id) ON DELETE CASCADE
        );
        """
    )
    # Órfãos nos 3 caminhos de FK (sem nenhuma sdk_session existente):
    conn.execute("INSERT INTO observations(id, memory_session_id) VALUES (1,'msid-orphan')")
    conn.execute("INSERT INTO session_summaries(id, memory_session_id) VALUES (1,'msid-orphan')")  # mesma chave
    conn.execute("INSERT INTO session_summaries(id, memory_session_id) VALUES (2,'msid-other')")
    conn.execute("INSERT INTO user_prompts(id, content_session_id) VALUES (1,'csid-orphan')")
    conn.execute("INSERT INTO pending_messages(id, session_db_id) VALUES (1, 999)")
    # Um órfão com chave vazia (não reparável — deve ser pulado sem quebrar):
    conn.execute("INSERT INTO observations(id, memory_session_id) VALUES (2,'')")
    conn.commit()
    return conn


def test_repair_fk_orphans_covers_all_three_fk_paths(tmp_path):
    db_path = tmp_path / "claude-mem.db"
    conn = _build_claude_mem_like(db_path)
    before = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    assert before > 0

    repaired = MODULE._repair_fk_orphans(conn)
    # 3 chaves materializáveis (msid-orphan, msid-other, csid-orphan) + id=999.
    # A chave vazia '' é pulada de propósito → continua órfã (1 violação restante).
    assert repaired == 4

    remaining = conn.execute("PRAGMA foreign_key_check").fetchall()
    # Só a observação de chave vazia segue órfã; os 3 caminhos reais foram sanados.
    assert all(row[0] == "observations" for row in remaining)
    assert len(remaining) == 1

    # Idempotência: nada novo na 2ª passada.
    assert MODULE._repair_fk_orphans(conn) == 0
    conn.close()


def test_validate_fails_without_real_reboot(monkeypatch, tmp_path):
    marker = tmp_path / "pre-reboot.json"
    marker.write_text('{"boot_id": "same-boot", "require_api": false}')
    monkeypatch.setattr(MODULE, "MARKER", marker)
    monkeypatch.setattr(MODULE, "REPORT", tmp_path / "report.json")
    monkeypatch.setattr(MODULE, "boot_id", lambda: "same-boot")

    try:
        MODULE.validate()
        raise AssertionError("validate() should have raised RuntimeError")
    except RuntimeError as exc:
        assert "boot_id did not change" in str(exc)


def test_validate_marks_fail_when_ports_not_loopback(monkeypatch, tmp_path):
    marker = tmp_path / "pre-reboot.json"
    marker.write_text('{"boot_id": "old-boot", "require_api": true}')
    report = tmp_path / "post-reboot-validation.json"

    monkeypatch.setattr(MODULE, "MARKER", marker)
    monkeypatch.setattr(MODULE, "REPORT", report)
    monkeypatch.setattr(MODULE, "LOG_DIR", tmp_path)
    monkeypatch.setattr(MODULE, "boot_id", lambda: "new-boot")
    monkeypatch.setattr(MODULE, "wait_for_runtime", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        MODULE,
        "service_state",
        lambda _service: {
            "ActiveState": "active",
            "SubState": "running",
            "NRestarts": 0,
            "MainPID": 123,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "listening_ports",
        lambda _ports: {
            "37700": "0.0.0.0:37700",
            "37701": "127.0.0.1:37701",
            "37702": "127.0.0.1:37702",
        },
    )
    monkeypatch.setattr(
        MODULE,
        "verify_database",
        lambda _path: {
            "integrity_check": "ok",
            "quick_check": "ok",
            "foreign_key_violations": 0,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "claude_mem_database",
        lambda: {
            "integrity_check": "ok",
            "foreign_key_violations": 0,
            "observations": 200,
            "vectors": 200,
        },
    )
    class SmokeResult:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(MODULE, "run", lambda *args, **kwargs: SmokeResult())

    exit_code = MODULE.validate()
    assert exit_code == 1
    payload = report.read_text()
    assert '"status": "fail"' in payload
    assert '"ports_loopback_only": false' in payload
