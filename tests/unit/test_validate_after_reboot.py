from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "validate_after_reboot", ROOT / "scripts" / "validate_after_reboot.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


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

    # Pós-migração, o validator usa o DB GLOBAL (~/.claude-mem). Monta lá e
    # aponta Path.home() para o tmp_path. ROOT (local legado) não existe → usa global.
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
    monkeypatch.setattr(MODULE, "ROOT", tmp_path / "norepo")
    result = MODULE.claude_mem_database()
    assert result["path"] == str(db_path)
    assert result["integrity_check"] == "ok"
    assert result["observations"] == 1
    assert result["vectors"] == 1


def test_global_reference_scan_ignores_inaccessible_processes(monkeypatch, tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    inaccessible = proc_root / "123"
    inaccessible.mkdir()
    (inaccessible / "fd").mkdir()

    original_path = MODULE.Path

    class ProcPath(original_path):
        def iterdir(self):
            if str(self) == "/proc":
                return iter((inaccessible,))
            return super().iterdir()

    monkeypatch.setattr(MODULE, "Path", ProcPath)
    monkeypatch.setattr(
        MODULE.os,
        "readlink",
        lambda path: (_ for _ in ()).throw(PermissionError()),
    )
    assert MODULE.global_claude_mem_references() == []


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
    monkeypatch.setattr(MODULE, "global_claude_mem_references", lambda: [{"pid": 1, "references": ["ok"]}])

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
