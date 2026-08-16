"""Testes do bridge session_summaries → cerebelo/sessoes (F2.2a)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.knowledge.bridge_session_summaries import _session_body, _session_date, _slug


class BridgeSessionTests(unittest.TestCase):
    def test_slug_normalizes(self):
        self.assertEqual(_slug("Verification of missing files"), "verification-of-missing-files")

    def test_session_date_parses_iso(self):
        dt = _session_date("2026-08-12T21:44:02.938Z")
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 12)

    def test_session_body_has_frontmatter_and_sinapses(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE session_summaries (
                id INTEGER, memory_session_id TEXT, project TEXT, request TEXT,
                investigated TEXT, learned TEXT, completed TEXT, next_steps TEXT,
                files_read TEXT, files_edited TEXT, notes TEXT, created_at TEXT,
                created_at_epoch INTEGER
            )
        """)
        conn.execute("""
            INSERT INTO session_summaries (id, memory_session_id, project, request,
                investigated, learned, completed, next_steps, created_at)
            VALUES (1, 'ses-abc123', 'Hive-Mind', 'Auditar o projeto',
                    'A arquitetura do cerebro', 'O temporal e a fonte', 'Auditoria feita',
                    'Corrigir o preenchimento', '2026-08-12T21:44:02.938Z')
        """)
        row = conn.execute("SELECT * FROM session_summaries").fetchone()
        body = _session_body(row)
        self.assertIn("type: session-log", body)
        self.assertIn("project: Hive-Mind", body)
        self.assertIn("# Auditar o projeto", body)
        self.assertIn("## Sinapses", body)
        self.assertIn("lobo:: [[cerebelo]]", body)
        conn.close()


if __name__ == "__main__":
    unittest.main()
