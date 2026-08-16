"""Testes do decision_promoter v2 com LLM fallback (F2.1)."""
import unittest
from unittest import mock

from scripts.knowledge.decision_promoter import _fill_via_llm, _record_body


class DecisionLLMTests(unittest.TestCase):
    def test_fill_via_llm_uses_fallback_not_call_llm_role(self):
        # FIX (2026-08-13): _fill_via_llm deve usar call_llm_with_fallback (gateway
        # com fallback para ollama), NÃO call_llm_role do dream_cycle (que falha
        # quando o gemini-cli não está instalado).
        fake_out = mock.Mock(contexto="ctx", rationale="rat",
                             alternativas="alt", consequencias="cons")
        with mock.patch("core.auth.load_env"), \
             mock.patch("core.llm_client.call_llm_with_fallback",
                        return_value=fake_out):
            r = _fill_via_llm("decisão", "título")
            self.assertEqual(r, {
                "contexto": "ctx", "rationale": "rat",
                "alternativas": "alt", "consequencias": "cons",
            })

    def test_fill_via_llm_empty_on_none(self):
        with mock.patch("core.auth.load_env"), \
             mock.patch("core.llm_client.call_llm_with_fallback",
                        return_value=None):
            self.assertEqual(_fill_via_llm("d", "t"), {})

    def test_record_body_with_llm_fills_missing(self):
        item = {
            "path": mock.Mock(stem="neuronio-x-abcdef12"),
            "data": {"integrity_hash": "abcdef12"},
            "project": "Hive-Mind",
            "body": "# Uma decisão\n\nO corpo da decisão.\n",
        }
        with mock.patch("scripts.knowledge.decision_promoter._fill_via_llm", return_value={
            "contexto": "C", "rationale": "R",
            "alternativas": "A", "consequencias": "K",
        }):
            body = _record_body(item, with_llm=True)
        self.assertNotIn("_(a preencher)_", body)
        self.assertIn("C", body)
        self.assertIn("## Sinapses", body)


if __name__ == "__main__":
    unittest.main()
