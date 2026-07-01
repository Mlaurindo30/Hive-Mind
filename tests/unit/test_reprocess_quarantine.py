"""F4.2 — Testes do reprocess_quarantine (K8 harden)."""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import scripts.health.reprocess_quarantine as rq


class ReprocessQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "test.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE observations (
                id TEXT PRIMARY KEY,
                content TEXT,
                archived INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

    def tearDown(self):
        self.conn.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _insert_obs(self, obs_id: str, age_days: int, *, archived: int = 2,
                    reason: str = "test", retry_count: int = 0) -> None:
        at = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
        meta = json.dumps({
            "quarantine": {
                "reason": reason,
                "retry_policy": "manual_fix_required",
                "at": at,
                "retries": retry_count,
            }
        })
        self.conn.execute(
            "INSERT INTO observations (id, content, archived, metadata) "
            "VALUES (?, ?, ?, ?)",
            (obs_id, "x", archived, meta),
        )
        self.conn.commit()

    def test_skips_recent_observations(self):
        # 3 dias, dentro do default 7
        self._insert_obs("obs-recent", age_days=3)
        rows = rq._quarantined_rows(self.conn)
        report = {"scanned": 0, "skipped_recent": 0, "retried": 0,
                  "recovered": 0, "terminal": 0, "errors": 0,
                  "by_reason": {}, "dry_run": True, "max_age_days": 7}
        # Replicate main loop logic minimally
        for row in rows:
            report["scanned"] += 1
            q_at = rq._parse_quarantine_at(row["metadata"])
            if q_at is not None:
                age = (datetime.now(timezone.utc) - q_at).days
                if age < 7:
                    report["skipped_recent"] += 1
        self.assertEqual(report["scanned"], 1)
        self.assertEqual(report["skipped_recent"], 1)

    def test_retries_old_observations(self):
        self._insert_obs("obs-old", age_days=14)
        rows = rq._quarantined_rows(self.conn)
        report = {"scanned": 0, "skipped_recent": 0, "retried": 0,
                  "recovered": 0, "terminal": 0, "errors": 0,
                  "by_reason": {}, "dry_run": True, "max_age_days": 7}
        for row in rows:
            report["scanned"] += 1
            q_at = rq._parse_quarantine_at(row["metadata"])
            if q_at is not None:
                age = (datetime.now(timezone.utc) - q_at).days
                if age < 7:
                    report["skipped_recent"] += 1
                else:
                    report["retried"] += 1
        self.assertEqual(report["retried"], 1)

    def test_terminal_after_exhausted_retries(self):
        # 35 dias, 3 retries esgotados, 30 dias é o terminal
        self._insert_obs("obs-doomed", age_days=35, retry_count=3)
        rows = rq._quarantined_rows(self.conn)
        for row in rows:
            obs_id = str(row["id"])
            q_at = rq._parse_quarantine_at(row["metadata"])
            retries = rq._retry_count(row["metadata"])
            if retries >= rq.MAX_RETRY_ATTEMPTS and q_at is not None and \
               (datetime.now(timezone.utc) - q_at).days >= rq.TERMINAL_AGE_DAYS:
                rq._mark_terminal(
                    self.conn, obs_id, "test terminal",
                )
        result = self.conn.execute(
            "SELECT archived FROM observations WHERE id = ?", ("obs-doomed",)
        ).fetchone()
        self.assertEqual(result["archived"], 3)
        meta = json.loads(
            self.conn.execute(
                "SELECT metadata FROM observations WHERE id = ?",
                ("obs-doomed",)
            ).fetchone()["metadata"]
        )
        self.assertIn("quarantine_terminal", meta)
        self.assertIn("reason", meta["quarantine_terminal"])
        self.assertEqual(meta["quarantine_terminal"]["reason"], "test terminal")

    def test_reset_reason_filter(self):
        self._insert_obs("obs-a", age_days=2, reason="fix1")
        self._insert_obs("obs-b", age_days=2, reason="fix2")
        # Force-specific retry_policy
        self.conn.execute(
            "UPDATE observations SET metadata = json_set(metadata, "
            "'$.quarantine.retry_policy', ?) WHERE id = ?",
            ("schema_fix_2026_07", "obs-a"),
        )
        self.conn.commit()
        rows = rq._quarantined_rows(self.conn, reset_reason="schema_fix_2026_07")
        ids = {str(r["id"]) for r in rows}
        self.assertEqual(ids, {"obs-a"})

    def test_corrupt_metadata_doesnt_crash(self):
        # Metadata com JSON inválido
        self.conn.execute(
            "INSERT INTO observations (id, content, archived, metadata) "
            "VALUES (?, ?, ?, ?)",
            ("obs-bad", "x", 2, "{not valid json"),
        )
        self.conn.commit()
        # _parse_quarantine_at deve retornar None em vez de explodir
        result = rq._parse_quarantine_at("{not valid json")
        self.assertIsNone(result)
        # _retry_count idem
        self.assertEqual(rq._retry_count("{not valid json"), 0)


if __name__ == "__main__":
    unittest.main()
