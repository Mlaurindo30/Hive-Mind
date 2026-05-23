import os
import pytest
from sinapse_memory import _save_decision, _save_learning, _sanitize_slug


class TestWriteReadCycle:
    """I2: Ciclo de escrita e leitura"""

    def test_save_and_read_decision(self, temp_vault, monkeypatch):
        """I2.1: Decisão salva pode ser lida de volta."""
        monkeypatch.setattr("sinapse_memory.DECISIONS_DIR", f"{temp_vault}/work/active")
        path = _save_decision("Teste de integração", "Conteúdo do teste")
        assert path is not None
        assert os.path.isfile(path)
        with open(path) as f:
            content = f.read()
        assert "Teste de integração" in content

    def test_save_learning_dedup_across_calls(self, temp_vault, monkeypatch):
        """I2.2: Deduplicação funciona em chamadas repetidas."""
        patterns_file = f"{temp_vault}/brain/Patterns.md"
        monkeypatch.setattr("sinapse_memory.PATTERNS_FILE", patterns_file)
        r1 = _save_learning("Pattern X", "First write")
        r2 = _save_learning("Pattern X", "Duplicate write")
        assert r1 is not None
        assert r2 is None  # dedup skipped
        with open(patterns_file) as f:
            content = f.read()
            assert content.count("Pattern X") == 1

    def test_decision_slug_preserves_readability(self):
        """I2.3: Slug preserva legibilidade."""
        slug = _sanitize_slug("Migrar servidor para Hetzner Cloud")
        assert "Migrar" in slug
        assert "servidor" in slug
        assert "Hetzner" in slug
        assert len(slug) <= 60

    def test_multiple_decisions_saved(self, temp_vault, monkeypatch):
        """I2.4: Múltiplas decisões salvas sem conflito."""
        monkeypatch.setattr("sinapse_memory.DECISIONS_DIR", f"{temp_vault}/work/active")
        paths = []
        for i in range(3):
            path = _save_decision(f"Decisão {i}", f"Conteúdo {i}")
            if path:
                paths.append(path)
        assert len(paths) == 3
        # Check all files exist
        for p in paths:
            assert os.path.isfile(p)
