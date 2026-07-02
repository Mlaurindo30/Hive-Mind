"""F2 governança — Testes da classificação confidence×risk e da política de promoção.

Cobre o classificador determinístico do intake, a política proporcional ao
risco na promoção (verified+low imediato, hypothesis drenado, high-risk só com
aprovação explícita), a drenagem da fila held, o kill-switch e a migração
idempotente do schema.
"""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from core.knowledge.intake import (
    KnowledgeCandidate,
    build_candidate,
    classify_governance,
    normalize_observation,
)
from core.knowledge.promotion import (
    ensure_knowledge_schema,
    governance_enabled,
    held_review_queue,
    promote_held_candidates,
    promote_pending_observations,
    store_candidates,
)


class ClassifyGovernanceTests(unittest.TestCase):
    def test_verified_via_files_evidence(self):
        confidence, risk = classify_governance(
            title="Fato", content="conteudo qualquer",
            evidence={"files": ["a.py"]}, metadata={},
        )
        self.assertEqual(confidence, "verified")
        self.assertEqual(risk, "low")

    def test_verified_via_commands_evidence(self):
        confidence, _ = classify_governance(
            title="Fato", content="x",
            evidence={"commands": ["./tests/run_all.sh"]}, metadata={},
        )
        self.assertEqual(confidence, "verified")

    def test_verified_via_source_uri(self):
        confidence, _ = classify_governance(
            title="Doc", content="x",
            evidence={"source_uri": "/vault/nota.md"}, metadata={},
        )
        self.assertEqual(confidence, "verified")

    def test_hypothesis_without_artifacts(self):
        confidence, _ = classify_governance(
            title="Inferencia", content="acho que o sistema faz X",
            evidence={"source_observation_id": "obs-1", "source_title": "t"},
            metadata={},
        )
        self.assertEqual(confidence, "hypothesis")

    def test_high_risk_on_secret_marker(self):
        _, risk = classify_governance(
            title="Config", content="a api key do provider ficou exposta",
            evidence={"files": ["x"]}, metadata={},
        )
        self.assertEqual(risk, "high")

    def test_high_risk_on_destructive_marker(self):
        _, risk = classify_governance(
            title="Limpeza", content="rodou rm -rf no diretorio de build",
            evidence={}, metadata={},
        )
        self.assertEqual(risk, "high")

    def test_llm_token_vocabulary_stays_low_risk(self):
        _, risk = classify_governance(
            title="Custo", content="a sessao consumiu 1224k tokens de trabalho",
            evidence={}, metadata={},
        )
        self.assertEqual(risk, "low")

    def test_explicit_governance_override(self):
        confidence, risk = classify_governance(
            title="t", content="c", evidence={"files": ["a"]},
            metadata={"governance": {"confidence": "hypothesis", "risk": "high"}},
        )
        self.assertEqual(confidence, "hypothesis")
        self.assertEqual(risk, "high")

    def test_invalid_override_falls_back_to_heuristic(self):
        confidence, risk = classify_governance(
            title="t", content="c", evidence={"files": ["a"]},
            metadata={"governance": {"confidence": "certeza", "risk": "medio"}},
        )
        self.assertEqual(confidence, "verified")
        self.assertEqual(risk, "low")

    def test_dataclass_rejects_invalid_axes(self):
        with self.assertRaises(ValueError):
            KnowledgeCandidate(
                id="kc-x", source_type="t", source_id="s",
                knowledge_type="fact", title="t", content="c",
                confidence="certeza",
            )
        with self.assertRaises(ValueError):
            KnowledgeCandidate(
                id="kc-x", source_type="t", source_id="s",
                knowledge_type="fact", title="t", content="c",
                risk="medio",
            )

    def test_build_candidate_classifies(self):
        candidate = build_candidate(
            source_type="promoter", source_id="s1", knowledge_type="fact",
            title="t", content="c", evidence={"files": ["a.py"]},
        )
        self.assertEqual(candidate.confidence, "verified")
        self.assertEqual(candidate.risk, "low")


def _make_db(tmpdir: str) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(tmpdir) / "test.db")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE observations (
            id TEXT PRIMARY KEY,
            project TEXT,
            workspace_id TEXT DEFAULT 'default',
            type TEXT,
            title TEXT,
            content TEXT,
            archived INTEGER DEFAULT 0,
            neuron_id TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE neurons (
            id TEXT PRIMARY KEY,
            label TEXT, type TEXT, content TEXT, hash TEXT, metadata TEXT,
            created_at TEXT, updated_at TEXT,
            workspace_id TEXT, embedding_model TEXT, embedding_dim INTEGER
        );
        CREATE TABLE goals (
            id TEXT PRIMARY KEY,
            description TEXT, steps_json TEXT, status TEXT,
            created_at TEXT, workspace_id TEXT
        );
    """)
    return conn


def _insert_obs(conn, obs_id: str, *, obs_type: str = "discovery",
                content: str = "conteudo da observacao",
                payload: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO observations (id, project, type, title, content, metadata) "
        "VALUES (?, 'Hive-Mind', ?, ?, ?, ?)",
        (obs_id, obs_type, f"titulo {obs_id}", content,
         json.dumps(payload or {}, ensure_ascii=False)),
    )
    conn.commit()


class PromotionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = _make_db(self.tmpdir)

    def tearDown(self):
        self.conn.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_verified_low_promotes_with_ttl(self):
        _insert_obs(self.conn, "obs-v", payload={
            "facts": ["fato verificado"],
            "evidence": {"files": ["a.py"], "commands": ["pytest"]},
        })
        report = promote_pending_observations(self.conn, apply=True)
        self.assertEqual(report["promoted"], 1)
        self.assertEqual(report["held_hypothesis"], 0)
        self.assertEqual(report["held_high_risk"], 0)
        row = self.conn.execute(
            "SELECT status, ttl_review, confidence, risk FROM knowledge_candidates"
        ).fetchone()
        self.assertEqual(row["status"], "promoted")
        self.assertEqual(row["confidence"], "verified")
        self.assertEqual(row["risk"], "low")
        self.assertTrue(row["ttl_review"])
        neuron = self.conn.execute("SELECT metadata FROM neurons").fetchone()
        governance = json.loads(neuron["metadata"])["governance"]
        self.assertEqual(governance["confidence"], "verified")
        self.assertTrue(governance["ttl_review"])

    def test_hypothesis_is_held_and_raw_preserved(self):
        _insert_obs(self.conn, "obs-h", payload={"facts": ["inferencia sem artefato"]})
        report = promote_pending_observations(self.conn, apply=True)
        self.assertEqual(report["promoted"], 0)
        self.assertEqual(report["held_hypothesis"], 1)
        row = self.conn.execute(
            "SELECT status, retry_policy FROM knowledge_candidates"
        ).fetchone()
        self.assertEqual(row["status"], "held")
        self.assertEqual(row["retry_policy"], "governance_review")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM neurons").fetchone()[0], 0)
        obs = self.conn.execute(
            "SELECT archived, content FROM observations WHERE id='obs-h'"
        ).fetchone()
        self.assertEqual(obs["archived"], 1)
        self.assertEqual(obs["content"], "conteudo da observacao")

    def test_high_risk_is_held_even_with_evidence(self):
        _insert_obs(self.conn, "obs-r", payload={
            "facts": ["a senha do banco vazou no log"],
            "evidence": {"files": ["log.txt"]},
        })
        report = promote_pending_observations(self.conn, apply=True)
        self.assertEqual(report["promoted"], 0)
        self.assertEqual(report["held_high_risk"], 1)
        row = self.conn.execute("SELECT status, risk FROM knowledge_candidates").fetchone()
        self.assertEqual(row["status"], "held")
        self.assertEqual(row["risk"], "high")

    def test_kill_switch_restores_promote_all(self):
        _insert_obs(self.conn, "obs-k", payload={"facts": ["inferencia sem artefato"]})
        with mock.patch.dict(os.environ, {"HIVE_GOVERNANCE_RISK": "0"}):
            self.assertFalse(governance_enabled())
            report = promote_pending_observations(self.conn, apply=True)
        self.assertEqual(report["promoted"], 1)
        self.assertEqual(report["held_hypothesis"], 0)

    def test_mixed_observation_splits_per_candidate(self):
        _insert_obs(self.conn, "obs-m", payload={
            "facts": ["fato com artefato"],
            "decisions": ["decisao com artefato"],
            "narrative": "narrativa investigativa",
            "evidence": {"files": ["a.py"]},
        })
        report = promote_pending_observations(self.conn, apply=True)
        # evidence compartilhada torna todos verified; nenhum marker high-risk
        self.assertEqual(report["promoted"], 3)
        self.assertEqual(report["held_hypothesis"], 0)


class HeldDrainTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = _make_db(self.tmpdir)
        ensure_knowledge_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _hold(self, kc_id_suffix: str, *, risk: str = "low",
              confidence: str = "hypothesis", age_days: int = 0) -> None:
        created = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
        candidate = build_candidate(
            source_type="test", source_id=f"src-{kc_id_suffix}",
            knowledge_type="fact", title=f"t-{kc_id_suffix}",
            content=f"c-{kc_id_suffix}", created_at=created,
            metadata={"governance": {"confidence": confidence, "risk": risk}},
        )
        store_candidates(self.conn, [candidate])
        self.conn.execute(
            "UPDATE knowledge_candidates SET status='held', created_at=? WHERE id=?",
            (created, candidate.id),
        )
        self.conn.commit()

    def test_recent_hypothesis_is_skipped(self):
        self._hold("recent", age_days=2)
        report = promote_held_candidates(self.conn, min_age_days=7)
        self.assertEqual(report["skipped_recent"], 1)
        self.assertEqual(report["promoted"], 0)

    def test_aged_hypothesis_promotes(self):
        self._hold("aged", age_days=10)
        report = promote_held_candidates(self.conn, min_age_days=7)
        self.assertEqual(report["promoted"], 1)
        row = self.conn.execute(
            "SELECT status, ttl_review FROM knowledge_candidates"
        ).fetchone()
        self.assertEqual(row["status"], "promoted")
        self.assertTrue(row["ttl_review"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM neurons").fetchone()[0], 1)

    def test_high_risk_needs_explicit_flag(self):
        self._hold("high", risk="high", age_days=60)
        report = promote_held_candidates(self.conn, min_age_days=7)
        self.assertEqual(report["skipped_high_risk"], 1)
        self.assertEqual(report["promoted"], 0)
        report = promote_held_candidates(
            self.conn, min_age_days=7, include_high_risk=True
        )
        self.assertEqual(report["promoted"], 1)

    def test_dry_run_does_not_write(self):
        self._hold("dry", age_days=10)
        report = promote_held_candidates(self.conn, min_age_days=7, apply=False)
        self.assertEqual(report["promoted"], 1)
        self.assertTrue(report["dry_run"])
        row = self.conn.execute("SELECT status FROM knowledge_candidates").fetchone()
        self.assertEqual(row["status"], "held")

    def test_held_review_queue_counts(self):
        self._hold("q1", risk="high", age_days=1)
        self._hold("q2", age_days=1)
        self._hold("q3", age_days=1)
        counts = held_review_queue(self.conn)
        self.assertEqual(counts["held_total"], 3)
        self.assertEqual(counts["held_high_risk"], 1)
        self.assertEqual(counts["held_hypothesis"], 2)


class SchemaMigrationTests(unittest.TestCase):
    def test_legacy_table_gains_columns_idempotently(self):
        tmpdir = tempfile.mkdtemp()
        conn = sqlite3.connect(Path(tmpdir) / "legacy.db")
        conn.row_factory = sqlite3.Row
        # Schema anterior à governança (sem confidence/risk/ttl_review)
        conn.execute("""
            CREATE TABLE knowledge_candidates (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                knowledge_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                project TEXT NOT NULL DEFAULT 'default',
                workspace_id TEXT NOT NULL DEFAULT 'default',
                evidence_json TEXT NOT NULL,
                metadata_json TEXT,
                hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'candidate',
                neuron_id TEXT,
                error TEXT,
                retry_policy TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                promoted_at TEXT,
                UNIQUE(source_id, knowledge_type, hash, workspace_id)
            )
        """)
        conn.execute(
            "INSERT INTO knowledge_candidates (id, source_type, source_id, "
            "knowledge_type, title, content, evidence_json, hash) "
            "VALUES ('kc-old', 't', 's', 'fact', 'ti', 'co', '{}', 'h')"
        )
        ensure_knowledge_schema(conn)
        ensure_knowledge_schema(conn)  # idempotente
        row = conn.execute(
            "SELECT confidence, risk, ttl_review FROM knowledge_candidates WHERE id='kc-old'"
        ).fetchone()
        # Linhas legadas são tratadas como verified+low (não retro-segurar)
        self.assertEqual(row["confidence"], "verified")
        self.assertEqual(row["risk"], "low")
        self.assertIsNone(row["ttl_review"])
        conn.close()
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


class NormalizeGovernancePropagationTests(unittest.TestCase):
    def test_payload_governance_reaches_candidates(self):
        row = {
            "id": "obs-gov",
            "project": "Hive-Mind",
            "type": "discovery",
            "title": "t",
            "content": json.dumps({
                "facts": ["fato qualquer"],
                "governance": {"confidence": "verified", "risk": "high"},
            }),
            "metadata": "{}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        candidates = normalize_observation(row)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].confidence, "verified")
        self.assertEqual(candidates[0].risk, "high")


if __name__ == "__main__":
    unittest.main()
