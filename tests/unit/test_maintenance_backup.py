"""D008-R1B — verified backup engine, synthetic data only.

Never touches a real database. Covers the guarantees the legacy engine
lacked, above all: retention must not run when the new backup failed.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from hive_mind.maintenance.backup import (
    BackupTarget,
    Coverage,
    MANIFEST_PREFIX,
    RestoreRefused,
    latest_manifest,
    restore,
    run,
    sha256_file,
    sqlite_is_intact,
    status,
    verify,
)
from hive_mind.maintenance.lock import MaintenanceLock, MaintenanceLockError


def _db(path: Path, rows: int = 5, wal: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t (v) VALUES (?)", [(f"row-{i}",) for i in range(rows)])
    conn.commit()
    conn.close()
    return path


def _target(tmp_path: Path, name="db", rows=5, keep=3, wal=False) -> BackupTarget:
    return BackupTarget(
        name=name,
        src=_db(tmp_path / "live" / f"{name}.db", rows=rows, wal=wal),
        dest_dir=tmp_path / "backups",
        keep_last=keep,
    )


class TestBackupRun:
    def test_creates_a_verified_artifact(self, tmp_path):
        target = _target(tmp_path)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        assert report.healthy
        result = report.results[0]
        assert result.status == "OK"
        assert result.artifact is not None
        assert Path(result.artifact.path).is_file()
        assert result.artifact.sha256 == sha256_file(Path(result.artifact.path))

    def test_backup_of_a_wal_database_is_intact(self, tmp_path):
        target = _target(tmp_path, wal=True, rows=20)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        artifact = report.results[0].artifact
        intact, reason = sqlite_is_intact(Path(artifact.path))
        assert intact, reason

    def test_backup_of_an_open_database_succeeds(self, tmp_path):
        target = _target(tmp_path)
        holder = sqlite3.connect(target.src)  # keep it open during the copy
        holder.execute("INSERT INTO t (v) VALUES ('while-open')")
        holder.commit()
        try:
            report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        finally:
            holder.close()
        assert report.healthy

    def test_missing_source_is_skipped_not_failed(self, tmp_path):
        target = BackupTarget("ghost", tmp_path / "nope.db", tmp_path / "backups")
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        assert report.results[0].status == "SKIP"
        assert report.healthy

    def test_dry_run_writes_nothing(self, tmp_path):
        target = _target(tmp_path)
        report = run([target], dry_run=True, lock_dir=tmp_path, stamp="2026-01-01")
        assert report.healthy
        assert not target.dest_dir.exists() or not list(target.dest_dir.glob("*.db"))
        assert report.manifest_path is None

    def test_rerun_same_day_is_idempotent(self, tmp_path):
        target = _target(tmp_path)
        run([target], lock_dir=tmp_path, stamp="2026-01-01")
        second = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        assert second.healthy
        assert "already present" in second.results[0].detail

    def test_no_partial_file_survives(self, tmp_path):
        target = _target(tmp_path)
        run([target], lock_dir=tmp_path, stamp="2026-01-01")
        assert list(target.dest_dir.glob("*.partial")) == []

    def test_unicode_and_spaces_in_paths(self, tmp_path):
        base = tmp_path / "caminho com espaço" / "acentuação"
        target = BackupTarget("báse", _db(base / "báse.db"), base / "backups")
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        assert report.healthy


class TestRetentionSafety:
    def test_prunes_after_a_successful_run(self, tmp_path):
        target = _target(tmp_path, keep=2)
        for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
            run([target], lock_dir=tmp_path, stamp=day)
        kept = sorted(p.name for p in target.dest_dir.glob("db.20*.db"))
        assert len(kept) == 2
        assert kept[-1] == "db.2026-01-03.db"

    def test_a_failed_run_never_prunes(self, tmp_path):
        """The legacy engine pruned right after copying; a bad new backup
        could therefore evict a good old one."""
        target = _target(tmp_path, keep=1)
        run([target], lock_dir=tmp_path, stamp="2026-01-01")
        run([target], lock_dir=tmp_path, stamp="2026-01-02")
        before = {p.name for p in target.dest_dir.glob("db.20*.db")}

        broken = BackupTarget("db", tmp_path / "live" / "gone.db", target.dest_dir, keep_last=1)
        failing = BackupTarget("other", tmp_path / "live" / "missing.db", target.dest_dir)
        target.src.unlink()  # force the copy to fail
        report = run([target, broken, failing], lock_dir=tmp_path, stamp="2026-01-03")

        after = {p.name for p in target.dest_dir.glob("db.20*.db")}
        assert after == before, "a failed run must not evict existing backups"
        assert report.results[0].pruned == []


class TestLock:
    def test_second_run_is_refused_while_locked(self, tmp_path):
        lock = MaintenanceLock(tmp_path / "backup.lock")
        lock.acquire()
        try:
            with pytest.raises(MaintenanceLockError):
                run([_target(tmp_path)], lock_dir=tmp_path, stamp="2026-01-01")
        finally:
            lock.release()

    def test_lock_is_released_after_a_run(self, tmp_path):
        target = _target(tmp_path)
        run([target], lock_dir=tmp_path, stamp="2026-01-01")
        assert not (tmp_path / "backup.lock").exists()

    def test_lock_is_released_even_when_a_target_fails(self, tmp_path):
        failing = BackupTarget("x", tmp_path / "absent.db", tmp_path / "backups")
        run([failing], lock_dir=tmp_path, stamp="2026-01-01")
        assert not (tmp_path / "backup.lock").exists()


class TestManifestAndVerify:
    def test_manifest_records_every_artifact(self, tmp_path):
        target = _target(tmp_path)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        payload = json.loads(Path(report.manifest_path).read_text(encoding="utf-8"))
        assert payload["manifest_version"] == 1
        assert payload["artifacts"][0]["name"] == "db"
        assert payload["coverage"]["milvus"] == Coverage.REQUIRES_SERVICE_SNAPSHOT

    def test_verify_passes_on_a_fresh_backup(self, tmp_path):
        target = _target(tmp_path)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        assert verify(report.manifest_path)["ok"] is True

    def test_verify_detects_a_tampered_artifact(self, tmp_path):
        target = _target(tmp_path)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        artifact = Path(report.results[0].artifact.path)
        artifact.write_bytes(artifact.read_bytes() + b"tampered")
        result = verify(report.manifest_path)
        assert result["ok"] is False
        assert result["checks"][0]["reason"] == "sha256 mismatch"

    def test_verify_detects_a_truncated_artifact(self, tmp_path):
        target = _target(tmp_path)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        artifact = Path(report.results[0].artifact.path)
        artifact.write_bytes(artifact.read_bytes()[:100])
        assert verify(report.manifest_path)["ok"] is False

    def test_verify_detects_a_missing_artifact(self, tmp_path):
        target = _target(tmp_path)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        Path(report.results[0].artifact.path).unlink()
        result = verify(report.manifest_path)
        assert result["checks"][0]["reason"] == "missing"

    def test_latest_manifest_is_found(self, tmp_path):
        target = _target(tmp_path)
        run([target], lock_dir=tmp_path, stamp="2026-01-01")
        run([target], lock_dir=tmp_path, stamp="2026-01-02")
        newest = latest_manifest(target.dest_dir)
        assert newest is not None and "2026-01-02" in newest.name


class TestRestore:
    def test_restores_into_an_alternate_directory(self, tmp_path):
        target = _target(tmp_path, rows=7)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        out = tmp_path / "restored"
        result = restore(report.manifest_path, out)
        assert result["ok"]
        restored = Path(result["restored"][0]["path"])
        conn = sqlite3.connect(restored)
        try:
            assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 7
        finally:
            conn.close()

    def test_restored_data_matches_the_source(self, tmp_path):
        target = _target(tmp_path, rows=11)
        original = sqlite3.connect(target.src).execute("SELECT id, v FROM t").fetchall()
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        result = restore(report.manifest_path, tmp_path / "restored")
        conn = sqlite3.connect(result["restored"][0]["path"])
        try:
            assert conn.execute("SELECT id, v FROM t").fetchall() == original
        finally:
            conn.close()

    def test_restore_refuses_to_overwrite_by_default(self, tmp_path):
        target = _target(tmp_path)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        out = tmp_path / "restored"
        restore(report.manifest_path, out)
        with pytest.raises(RestoreRefused):
            restore(report.manifest_path, out)

    def test_restore_overwrites_only_when_asked(self, tmp_path):
        target = _target(tmp_path)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        out = tmp_path / "restored"
        restore(report.manifest_path, out)
        assert restore(report.manifest_path, out, allow_overwrite_live=True)["ok"]

    def test_restore_rejects_a_tampered_artifact(self, tmp_path):
        target = _target(tmp_path)
        report = run([target], lock_dir=tmp_path, stamp="2026-01-01")
        artifact = Path(report.results[0].artifact.path)
        artifact.write_bytes(artifact.read_bytes() + b"x")
        with pytest.raises(ValueError):
            restore(report.manifest_path, tmp_path / "restored")


class TestStatus:
    def test_status_reports_counts_and_coverage(self, tmp_path):
        target = _target(tmp_path)
        run([target], lock_dir=tmp_path, stamp="2026-01-01")
        data = status([target])
        entry = data["targets"][0]
        assert entry["backups"] == 1
        assert entry["source_present"] is True
        assert data["coverage"]["cerebro-markdown"] == Coverage.NOT_SUPPORTED


class TestSqliteIsIntact:
    def test_foreign_key_violations_are_non_fatal(self, tmp_path):
        # P1-H (2026-08-12): claude-mem roda com foreign_keys=OFF e acumula
        # órfãos. O backup deve aceitar (warning), não falhar o snapshot.
        path = tmp_path / "orphaned.db"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, "
            "parent_id INTEGER REFERENCES parent(id))"
        )
        conn.execute("INSERT INTO child (id, parent_id) VALUES (1, 999)")
        conn.commit()
        conn.close()

        intact, reason = sqlite_is_intact(path)
        assert intact, reason
        assert "non-fatal" in reason

    def test_integrity_corruption_still_fails(self, tmp_path):
        path = _db(tmp_path / "live" / "corrupt.db", rows=5)
        # corrompe uma página: integrity_check deve continuar sendo FAIL.
        raw = bytearray(path.read_bytes())
        # sobrescreve o cabeçalho SQLite (primeiros 16 bytes são o magic string)
        raw[0:16] = b"\x00" * 16
        path.write_bytes(bytes(raw))
        intact, reason = sqlite_is_intact(path)
        # Cabeçalho corrompido: integrity_check falha, e NÃO é um warning de FK.
        assert not intact
        assert "foreign_key_check" not in reason
