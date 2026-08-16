"""Testes do consolidate_loop (orquestrador contínuo do cerebro)."""
import unittest
from unittest import mock


class ConsolidateLoopTests(unittest.TestCase):
    def test_fast_layer_calls_pipeline_in_order(self):
        import sys
        sys.path.insert(0, 'D:/Hive-Mind')
        from scripts.knowledge.consolidate_loop import _fast_layer

        with mock.patch("scripts.knowledge.consolidate_loop.bridge", return_value={"inserted": 3}) as m_bridge, \
             mock.patch("scripts.knowledge.consolidate_loop.promote_pending_observations", return_value={"promoted": 2}) as m_promote, \
             mock.patch("scripts.knowledge.consolidate_loop.materialize_orphan_neurons", return_value={"materialized": 1}):
            report = _fast_layer(conn=object())
            self.assertEqual(report["bridge"], 3)
            self.assertEqual(report["promoted"], 2)
            self.assertEqual(report["materialized"], 1)
            m_bridge.assert_called_once()
            m_promote.assert_called_once()

    def test_medium_layer_isolates_failures(self):
        import sys
        sys.path.insert(0, 'D:/Hive-Mind')
        from scripts.knowledge.consolidate_loop import _medium_layer

        def boom(*a, **k):
            raise RuntimeError("fail")

        with mock.patch("scripts.knowledge.consolidate_loop.subprocess.run", side_effect=boom):
            report = _medium_layer()
            # nenhuma falha derruba a camada; todos marcados 0
            self.assertEqual(report, {"decision": 0, "work": 0, "projects": 0, "health": 0, "daily": 0})


if __name__ == "__main__":
    unittest.main()
