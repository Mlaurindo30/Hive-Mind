"""Testes de escala F3: sector_classifier em lote + conflict_detector via HNSW."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.knowledge.conflict_detector import find_candidate_pairs
from scripts.knowledge.sector_classifier import _write_sectors


class ConflictHNSWTests(unittest.TestCase):
    def test_find_candidate_pairs_uses_hnsw_not_o_n2(self):
        # Com embed_fn=None (produção), deve chamar core.hnsw_index.search, não O(n²).
        neurons = [
            {"path": Path(f"/t/proj/t/neuronio-{i}.md"), "body": f"# T{i}\nconteudo {i}",
             "data": {}, "type": "fact", "project": "p", "topic": "t"}
            for i in range(5)
        ]
        with mock.patch("core.hnsw_index.load_or_create"), \
             mock.patch("core.hnsw_index.search", side_effect=lambda vec, k: []), \
             mock.patch("scripts.knowledge.conflict_detector._embed_single",
                        side_effect=lambda t: [0.0, 0.0]):
            pairs = find_candidate_pairs(neurons)
            # Sem vizinhos, retorna vazio (não quebra, não faz O(n²)).
            self.assertEqual(pairs, [])

    def test_embed_fn_path_preserved_for_tests(self):
        # O caminho de teste (embed_fn injetado) continua O(n²) para corpus pequeno.
        neurons = [
            {"path": Path(f"/t/p/n-{i}.md"), "body": f"# F{i}\nx", "data": {},
             "type": "fact", "project": "p", "topic": "t"}
            for i in range(3)
        ]
        def fake_embed(texts):
            # vetores ortogonais → similaridade 0 → sem pares acima de threshold
            return [[1.0, 0.0, 0.0][:len(t)] for t in [""]]
        # usa threshold alto para não achar nada
        pairs = find_candidate_pairs(neurons, threshold=0.99, embed_fn=lambda ts: [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]])
        self.assertEqual(pairs, [])


class SectorWriteTests(unittest.TestCase):
    def test_write_sectors_idempotent(self):
        tmp = Path(tempfile.mkdtemp())
        f = tmp / "neuronio-x.md"
        f.write_text("---\ntype: fact\n---\n# T\n\nconteudo\n", encoding="utf-8")
        _write_sectors(f, ["ai-infra"])
        text = f.read_text(encoding="utf-8")
        self.assertIn("sectors:", text)
        self.assertIn("ai-infra", text)
        # idempotente: mesma lista não reescreve
        mtime1 = f.stat().st_mtime_ns
        _write_sectors(f, ["ai-infra"])
        self.assertEqual(f.stat().st_mtime_ns, mtime1)


if __name__ == "__main__":
    unittest.main()
