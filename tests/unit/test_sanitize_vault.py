"""Testes do sanitize_vault (decisões A-D do arquiteto squad 04)."""
import tempfile
import unittest
from pathlib import Path

from scripts.knowledge.sanitize_vault import _is_mojibake, _fix_mojibake, _MOJIBAKE_MAP


class MojibakeTests(unittest.TestCase):
    def test_detects_double_encoded(self):
        self.assertTrue(_is_mojibake("canÃ´nico"))
        self.assertTrue(_is_mojibake("instÃ¢ncia"))
        self.assertFalse(_is_mojibake("canónico"))

    def test_fix_selective_preserves_correct_utf8(self):
        tmp = Path(tempfile.mkdtemp()) / "n.md"
        # mistura: mojibake + utf-8 correto no mesmo arquivo
        tmp.write_text("título canÃ´nico e correto é assim", encoding="utf-8")
        self.assertTrue(_fix_mojibake(tmp, apply=True))
        fixed = tmp.read_text(encoding="utf-8")
        self.assertIn("canónico", fixed)
        self.assertIn("correto é assim", fixed)  # UTF-8 correto preservado
        self.assertNotIn("Ã´", fixed)

    def test_fix_no_mojibake_returns_false(self):
        tmp = Path(tempfile.mkdtemp()) / "ok.md"
        tmp.write_text("tudo certo, sem mojibake", encoding="utf-8")
        self.assertFalse(_fix_mojibake(tmp, apply=True))


if __name__ == "__main__":
    unittest.main()
