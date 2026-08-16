"""Testes do materializador de neurônios órfãos (P0, 2026-08-12)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.knowledge.materialize import (
    MATERIALIZABLE_TYPES,
    _derive_topic,
    materialize_neuron,
    materialize_orphan_neurons,
)


class MaterializeTests(unittest.TestCase):
    def _neuron(self, **overrides):
        base = {
            "id": "k3-fact-9f752da3e8065573",
            "label": "Um fato real",
            "type": "fact",
            "content": "Conteúdo do fato.",
            "hash": "9f752da3e8065573",
            "metadata": '{"candidate_metadata": {"concepts": ["parallel-processing"]}}',
            "workspace_id": "hive-mind",
            "topic": None,
        }
        base.update(overrides)
        return base

    def test_durable_types_are_materializable(self):
        for t in ("fact", "decision", "learning", "preference", "rationale",
                  "code_symbol", "document_chunk", "security_alert", "security_note", "sensitive"):
            self.assertIn(t, MATERIALIZABLE_TYPES)

    def test_ephemeral_types_are_not_materializable(self):
        for t in ("operational_fact", "project_status", "visual_observation",
                  "next_step", "summary", "observation"):
            self.assertNotIn(t, MATERIALIZABLE_TYPES)

    def test_derive_topic_from_concepts(self):
        # _derive_topic retorna o concept bruto; canonical_slug normaliza depois.
        self.assertEqual(
            _derive_topic('{"candidate_metadata": {"concepts": ["parallel-processing"]}}'),
            "parallel-processing",
        )
        self.assertEqual(_derive_topic(None), "general")
        self.assertEqual(_derive_topic('{}'), "general")

    def test_materialize_neuron_returns_none_for_ephemeral(self):
        neuron = self._neuron(type="operational_fact")
        self.assertIsNone(materialize_neuron(_fake_conn(), neuron))

    def test_materialize_writes_md_and_returns_source(self):
        tmp = Path(tempfile.mkdtemp())
        with mock.patch("core.knowledge.materialize.cp.TEMPORAL", tmp / "cerebro" / "cortex" / "temporal"), \
             mock.patch("core.knowledge.materialize.cp.SINAPSE_HOME", tmp):
            neuron = self._neuron()
            source = materialize_neuron(_fake_conn(), neuron)
            self.assertIsNotNone(source)
            # o arquivo foi escrito com o slug canônico (hífen)
            path = (tmp / "cerebro" / "cortex" / "temporal" / "hive-mind"
                    / "parallel-processing" / "neuronio-um-fato-real-9f752da3.md")
            self.assertTrue(path.exists(), path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("type: fact", text)
            self.assertIn("project_id: hive-mind", text)
            self.assertIn("Conteúdo do fato.", text)
            self.assertIn("## Sinapses", text)

    def test_orphan_materialization_counts(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE neurons (
                id TEXT PRIMARY KEY, label TEXT, type TEXT, content TEXT, hash TEXT,
                metadata TEXT, workspace_id TEXT, topic TEXT, source_file TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("""
            INSERT INTO neurons (id, label, type, content, hash, metadata, workspace_id, source_file)
            VALUES ('k3-fact-1', 'Fato A', 'fact', 'conteudo A', 'aaaaaaaaaaaaaaaa',
                    '{"candidate_metadata": {"concepts": ["topic-a"]}}', 'hive-mind', NULL)
        """)
        conn.execute("""
            INSERT INTO neurons (id, label, type, content, hash, metadata, workspace_id, source_file)
            VALUES ('k3-op-1', 'Estado X', 'operational_fact', 'estado', 'bbbbbbbbbbbbbbbb',
                    '{}', 'hive-mind', NULL)
        """)
        tmp = Path(tempfile.mkdtemp())
        with mock.patch("core.knowledge.materialize.cp.TEMPORAL", tmp / "cerebro" / "cortex" / "temporal"), \
             mock.patch("core.knowledge.materialize.cp.SINAPSE_HOME", tmp):
            report = materialize_orphan_neurons(conn)
        self.assertEqual(report["scanned"], 2)
        self.assertEqual(report["materialized"], 1)
        self.assertEqual(report["skipped"], 1)
        # o fact foi materializado (source_file preenchido)
        row = conn.execute("SELECT source_file FROM neurons WHERE id='k3-fact-1'").fetchone()
        self.assertIsNotNone(row["source_file"])
        # o efêmero segue sem source_file
        row2 = conn.execute("SELECT source_file FROM neurons WHERE id='k3-op-1'").fetchone()
        self.assertIsNone(row2["source_file"])


def _fake_conn():
    return sqlite3.connect(":memory:")


if __name__ == "__main__":
    unittest.main()
