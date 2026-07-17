"""F3/F4/F1 — Testes de validade temporal, disciplina epistêmica e fallback de intake.

Cobre: frontmatter review_date/next_review + confidence nos writers, fallback
para a área de intake quando a escrita direta no vault é negada, penalidade de
staleness/hypothesis no RetrievalRouter, check de staleness do audit e o
backfill idempotente.
"""
import hashlib
import os
import shutil
import sqlite3
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from core.memory.writers import (
    REVIEW_TTL_DAYS,
    intake_fallback_dir,
    save_decision,
    save_learning,
)
from core.retrieval.router import (
    _apply_governance_penalty,
    _governance_flags,
    _staleness_penalty_factor,
)


class WriterFrontmatterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.decisions_dir = os.path.join(
            self.tmpdir, "cerebro", "cortex", "frontal", "trabalho", "ativo"
        )
        os.makedirs(self.decisions_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_decision_without_evidence_is_hypothesis_with_review_dates(self):
        path = save_decision("Escolha do backend", "conteudo", self.decisions_dir)
        self.assertTrue(path)
        text = Path(path).read_text(encoding="utf-8")
        today = datetime.now().strftime("%Y-%m-%d")
        expected_review = (
            datetime.now() + timedelta(days=REVIEW_TTL_DAYS)
        ).strftime("%Y-%m-%d")
        self.assertIn("confidence: hypothesis", text)
        self.assertIn(f"review_date: {today}", text)
        self.assertIn(f"next_review: {expected_review}", text)
        self.assertNotIn("evidence:", text)

    def test_decision_with_evidence_is_verified(self):
        path = save_decision(
            "Escolha validada", "conteudo", self.decisions_dir,
            evidence="pytest tests/unit -x passou",
        )
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("confidence: verified", text)
        self.assertIn('evidence: "pytest tests/unit -x passou"', text)

    def test_decision_has_integrity_hash_of_content(self):
        content = "A decisão precisa ter integridade verificável."
        path = save_decision("Decisão íntegra", content, self.decisions_dir)
        text = Path(path).read_text(encoding="utf-8")
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        self.assertIn(f"integrity_hash: {expected}", text)

    def test_learning_entry_has_governance_line(self):
        patterns = os.path.join(self.tmpdir, "cerebro", "cerebelo", "Patterns.md")
        os.makedirs(os.path.dirname(patterns))
        save_learning("Padrao novo", "descricao", patterns)
        text = Path(patterns).read_text(encoding="utf-8")
        self.assertIn("> confidence: hypothesis · next_review:", text)

    def test_learning_with_evidence_is_verified(self):
        patterns = os.path.join(self.tmpdir, "cerebro", "cerebelo", "Patterns.md")
        os.makedirs(os.path.dirname(patterns))
        save_learning("Padrao validado", "descricao", patterns,
                      evidence="./tests/run_all.sh verde")
        text = Path(patterns).read_text(encoding="utf-8")
        self.assertIn("> confidence: verified", text)
        self.assertIn("evidence: ./tests/run_all.sh verde", text)


class IntakeFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmpdir, "cerebro")
        self.decisions_dir = os.path.join(
            self.vault, "cortex", "frontal", "trabalho", "ativo"
        )
        os.makedirs(self.decisions_dir)
        os.makedirs(os.path.join(self.vault, "90-intake"))

    def tearDown(self):
        for root, dirs, _files in os.walk(self.tmpdir):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_intake_dir_derived_from_vault_path(self):
        self.assertEqual(
            intake_fallback_dir(os.path.join(self.decisions_dir, "x.md")),
            os.path.join(self.vault, "90-intake"),
        )

    def test_intake_dir_env_override(self):
        with mock.patch.dict(os.environ, {"HIVE_INTAKE_DIR": "/custom/intake"}):
            self.assertEqual(intake_fallback_dir("/qualquer/coisa.md"), "/custom/intake")

    def test_intake_dir_none_outside_vault(self):
        self.assertIsNone(intake_fallback_dir("/tmp/fora/do/vault.md"))

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "chmod readonly POSIX-only")
    def test_decision_falls_back_to_intake_when_vault_readonly(self):
        os.chmod(self.decisions_dir, stat.S_IRUSR | stat.S_IXUSR)
        path = save_decision("Decisao bloqueada", "conteudo", self.decisions_dir)
        self.assertTrue(path)
        self.assertIn("90-intake", path)
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("promote_to:", text)
        self.assertIn("Decisao bloqueada", text)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "chmod readonly POSIX-only")
    def test_learning_falls_back_to_intake_when_patterns_readonly(self):
        padroes_dir = os.path.join(self.vault, "cerebelo", "padroes")
        os.makedirs(padroes_dir)
        patterns = os.path.join(padroes_dir, "Patterns.md")
        Path(patterns).write_text("# Patterns\n")
        os.chmod(padroes_dir, stat.S_IRUSR | stat.S_IXUSR)
        path = save_learning("Aprendizado bloqueado", "conteudo", patterns)
        self.assertTrue(path)
        self.assertIn("90-intake", path)
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("promote_to:", text)
        self.assertIn("Aprendizado bloqueado", text)


def _item(item_id: str, score: float | None, governance: dict | None) -> dict:
    item: dict = {"id": item_id, "score": score, "route": "memory"}
    if governance is not None:
        item["metadata"] = {"governance": governance}
    return item


class RouterPenaltyTests(unittest.TestCase):
    PAST = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    FUTURE = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    def test_neutral_items_untouched(self):
        context = [_item("a", 0.9, None), _item("b", 0.8, {"confidence": "verified", "ttl_review": self.FUTURE})]
        result = _apply_governance_penalty(list(context))
        self.assertEqual([i["id"] for i in result], ["a", "b"])
        self.assertEqual(result[0]["score"], 0.9)
        self.assertNotIn("governance_flags", result[0])

    def test_stale_item_demoted_and_penalized(self):
        context = [
            _item("stale", 0.95, {"confidence": "verified", "ttl_review": self.PAST}),
            _item("fresh", 0.5, {"confidence": "verified", "ttl_review": self.FUTURE}),
        ]
        result = _apply_governance_penalty(context)
        self.assertEqual([i["id"] for i in result], ["fresh", "stale"])
        stale = result[1]
        self.assertAlmostEqual(stale["score"], 0.95 * 0.85, places=4)
        self.assertTrue(stale["governance_flags"]["stale"])

    def test_hypothesis_item_penalized(self):
        context = [
            _item("hyp", 0.9, {"confidence": "hypothesis"}),
            _item("ver", 0.4, {"confidence": "verified"}),
        ]
        result = _apply_governance_penalty(context)
        self.assertEqual([i["id"] for i in result], ["ver", "hyp"])
        self.assertTrue(result[1]["governance_flags"]["hypothesis"])

    def test_factor_one_disables(self):
        with mock.patch.dict(os.environ, {"HIVE_STALENESS_PENALTY": "1.0"}):
            context = [_item("hyp", 0.9, {"confidence": "hypothesis"})]
            result = _apply_governance_penalty(list(context))
            self.assertEqual(result[0]["score"], 0.9)
            self.assertNotIn("governance_flags", result[0])

    def test_invalid_factor_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"HIVE_STALENESS_PENALTY": "banana"}):
            self.assertEqual(_staleness_penalty_factor(), 0.85)

    def test_next_review_key_also_recognized(self):
        stale, hypothesis = _governance_flags(
            _item("x", 0.5, {"confidence": "verified", "next_review": self.PAST})
        )
        self.assertTrue(stale)
        self.assertFalse(hypothesis)

    def test_invalid_deadline_ignored(self):
        stale, _ = _governance_flags(
            _item("x", 0.5, {"confidence": "verified", "ttl_review": "não-é-data"})
        )
        self.assertFalse(stale)

    def test_score_none_keeps_none(self):
        result = _apply_governance_penalty(
            [_item("hyp", None, {"confidence": "hypothesis"})]
        )
        self.assertIsNone(result[0]["score"])
        self.assertIn("governance_flags", result[0])


class AuditStalenessTests(unittest.TestCase):
    def test_audit_counts_stale_and_missing_review(self):
        import scripts.health.audit_memory as am

        tmpdir = tempfile.mkdtemp()
        try:
            home = Path(tmpdir)
            (home / "cerebro" / "cortex" / "temporal").mkdir(parents=True)
            frontal = home / "cerebro" / "cortex" / "frontal"
            frontal.mkdir(parents=True)
            (frontal / "vencida.md").write_text(
                "---\ntags: [decision]\nnext_review: 2020-01-01\n---\n# Velha\n"
            )
            (frontal / "fresca.md").write_text(
                "---\ntags: [decision]\nnext_review: 2099-01-01\n---\n# Nova\n"
            )
            (frontal / "sem-review.md").write_text(
                "---\ntags: [decision]\ncreated: 2026-01-01\n---\n# Sem review\n"
            )
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            with mock.patch.object(am, "SINAPSE_HOME", str(home)), \
                 mock.patch.object(am, "get_connection", lambda: conn):
                stats = am.run_audit(fix=False)
            self.assertEqual(stats["stale_notes"], 1)
            self.assertEqual(stats["missing_next_review"], 1)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class BackfillReviewDatesTests(unittest.TestCase):
    def test_backfill_adds_fields_idempotently(self):
        import scripts.maintenance.backfill_review_dates as bf

        tmpdir = tempfile.mkdtemp()
        try:
            root = Path(tmpdir)
            frontal = root / "cerebro" / "cortex" / "frontal"
            frontal.mkdir(parents=True)
            note = frontal / "nota.md"
            note.write_text("---\ntags: [decision]\ncreated: 2026-01-01\n---\n# Nota\n")
            plain = frontal / "sem-frontmatter.md"
            plain.write_text("# Sem frontmatter\n")
            with mock.patch.object(bf, "ROOT", root):
                first = bf.backfill(apply=True)
                second = bf.backfill(apply=True)
            self.assertEqual(first["updated"], 1)
            self.assertEqual(first["skipped_no_frontmatter"], 1)
            self.assertEqual(second["updated"], 0)
            self.assertEqual(second["skipped_has_review"], 1)
            text = note.read_text(encoding="utf-8")
            self.assertIn("review_date:", text)
            self.assertIn("next_review:", text)
            self.assertTrue(text.startswith("---"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
