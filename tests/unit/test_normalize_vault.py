"""Testes do normalizador de vault (FASE 1, 2026-08-12)."""
import unittest

from scripts.knowledge.normalize_vault import (
    _SOURCE_TYPE_BUCKETS,
    _classify_project_name,
    _looks_like_vaulted_prompt,
)


class NormalizeVaultTests(unittest.TestCase):
    def test_repo_name_is_not_vaulted_prompt(self):
        # Nomes longos de repositório são legítimos.
        self.assertFalse(_looks_like_vaulted_prompt("dados-ia-agente-politicas-corporativas-340c9b8fbc41"))
        self.assertFalse(_looks_like_vaulted_prompt("moneyprinterturbo-83ef01772a6d"))

    def test_prompt_markers_are_detected(self):
        self.assertTrue(_looks_like_vaulted_prompt("preciso-que-verifique-o-por-que-3-fea062a54bfb"))
        self.assertTrue(_looks_like_vaulted_prompt("referenced-chatgpt-conversation-this-is-untrusted-45dfd61711b9"))
        self.assertTrue(_looks_like_vaulted_prompt("scratch-23172f0cae71"))

    def test_classify_normal_repo_keeps_name(self):
        self.assertEqual(
            _classify_project_name("git", "moneyprinterturbo-83ef01772a6d"),
            "moneyprinterturbo-83ef01772a6d",
        )

    def test_classify_vaulted_prompt_reclassifies(self):
        self.assertEqual(
            _classify_project_name("root", "preciso-que-verifique-o-por-que-bf972cf60ee5"),
            "unclassified",
        )

    def test_source_type_buckets_known(self):
        self.assertEqual(set(_SOURCE_TYPE_BUCKETS), {"git", "root", "local", "unclassified"})


if __name__ == "__main__":
    unittest.main()
