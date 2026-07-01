"""F4.3 — Testes unitarios para SLO gates em evaluate_fail_closed (K8 harden).

Cobre os gates S4 (observations_linked_pct >= 80%) e S5 (discoveries_pending <= 500)
adicionados em v3.7.8. S1, S2, S3 ja sao cobertos em tests/real.
"""
import unittest

from scripts.health.knowledge_health import evaluate_fail_closed


def _metrics(
    *,
    orphan: int = 0,
    obs_total: int = 0,
    obs_pct: float | None = 100.0,
    discoveries: int | None = 0,
    neurons_total: int = 100,
    neurons_pct: float | None = 100.0,
    doc_total: int = 0,
    doc_pct: float | None = None,
) -> dict:
    return {
        "orphan_vectors": orphan,
        "observations_total": obs_total,
        "observations_linked_pct": obs_pct,
        "discoveries_pending": discoveries,
        "neurons_total": neurons_total,
        "neurons_vectorized_pct": neurons_pct,
        "collections": {
            "document_vectors": {
                "source_total": doc_total,
                "vectorized_pct": doc_pct,
            }
        },
    }


class EvaluateFailClosedTests(unittest.TestCase):
    def test_all_gates_pass_when_healthy(self):
        metrics = _metrics(obs_total=200, obs_pct=95.0, discoveries=10)
        self.assertEqual(evaluate_fail_closed(metrics), [])

    def test_s4_fails_when_linked_pct_below_threshold(self):
        # 100 obs total (>=100), 50% linked (<80%) - must fail
        metrics = _metrics(obs_total=100, obs_pct=50.0)
        failures = evaluate_fail_closed(metrics)
        self.assertTrue(
            any("observations_linked_pct" in f for f in failures),
            f"expected S4 gate, got: {failures}",
        )

    def test_s4_skipped_when_few_observations(self):
        # 50 obs total (<100), 50% linked - should NOT fail (insufficient sample)
        metrics = _metrics(obs_total=50, obs_pct=50.0)
        failures = evaluate_fail_closed(metrics)
        self.assertFalse(
            any("observations_linked_pct" in f for f in failures),
            f"should skip S4 below 100 obs, got: {failures}",
        )

    def test_s4_skipped_when_pct_is_none(self):
        # obs_total=200 mas pct=None (queries falharam) - nao falha
        metrics = _metrics(obs_total=200, obs_pct=None)
        failures = evaluate_fail_closed(metrics)
        self.assertFalse(
            any("observations_linked_pct" in f for f in failures),
            f"pct=None should not crash, got: {failures}",
        )

    def test_s4_at_exact_threshold_passes(self):
        # 80.0 == threshold, deve passar
        metrics = _metrics(obs_total=100, obs_pct=80.0)
        self.assertEqual(evaluate_fail_closed(metrics), [])

    def test_s5_fails_when_discoveries_above_500(self):
        metrics = _metrics(discoveries=600)
        failures = evaluate_fail_closed(metrics)
        self.assertTrue(
            any("discoveries_pending" in f for f in failures),
            f"expected S5 gate, got: {failures}",
        )

    def test_s5_at_exact_500_passes(self):
        metrics = _metrics(discoveries=500)
        # Apenas S5, sem outras falhas
        self.assertEqual(evaluate_fail_closed(metrics), [])

    def test_s5_skipped_when_none(self):
        # discoveries=None significa "nao foi medido" - nao falha
        metrics = _metrics(discoveries=None)
        self.assertEqual(evaluate_fail_closed(metrics), [])

    def test_s1_still_fails_on_orphan_vectors(self):
        metrics = _metrics(orphan=3)
        failures = evaluate_fail_closed(metrics)
        self.assertTrue(any("orphan_vectors" in f for f in failures))

    def test_s2_still_fails_on_unknown_neurons_pct(self):
        metrics = _metrics(neurons_total=50, neurons_pct=None)
        failures = evaluate_fail_closed(metrics)
        self.assertTrue(any("neurons_vectorized_pct" in f for f in failures))

    def test_s3_still_fails_on_unknown_doc_pct(self):
        metrics = _metrics(doc_total=10, doc_pct=None)
        failures = evaluate_fail_closed(metrics)
        self.assertTrue(any("document_vectors_vectorized_pct" in f for f in failures))

    def test_multiple_gates_can_fail_simultaneously(self):
        metrics = _metrics(
            orphan=2,
            obs_total=200,
            obs_pct=40.0,
            discoveries=800,
        )
        failures = evaluate_fail_closed(metrics)
        # S1, S4, S5 todos devem falhar
        self.assertEqual(len(failures), 3)


if __name__ == "__main__":
    unittest.main()
