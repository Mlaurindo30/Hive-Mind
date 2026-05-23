import os
import pytest
import sinapse_memory as sm


class TestEdgeCases:
    """E5: Casos de borda e robustez."""

    def test_decision_with_emoji_title(self, temp_vault, monkeypatch):
        """Decisão com emoji no título gera arquivo válido."""
        monkeypatch.setattr(sm, "DECISIONS_DIR", f"{temp_vault}/work/active")
        path = sm._save_decision("🚀 Lançamento do produto", "Conteúdo")
        assert path is not None
        assert os.path.isfile(path)
        with open(path) as f:
            content = f.read()
        assert "lançamento" in content.lower() or "Lancamento" in content or "Lançamento" in content

    def test_very_long_title_truncated(self, temp_vault, monkeypatch):
        """Título muito longo é truncado no slug."""
        monkeypatch.setattr(sm, "DECISIONS_DIR", f"{temp_vault}/work/active")
        long_title = "A" * 200 + "B"
        path = sm._save_decision(long_title, "Content")
        assert path is not None
        fname = os.path.basename(path)
        assert len(fname) <= 80  # date prefix + slug

    def test_decision_with_special_filename_chars(self, temp_vault, monkeypatch):
        r"""Caracteres especiais (/, \, :) são sanitizados."""
        monkeypatch.setattr(sm, "DECISIONS_DIR", f"{temp_vault}/work/active")
        path = sm._save_decision("A / B : C \\ D", "Content")
        assert path is not None
        fname = os.path.basename(path)
        assert "/" not in fname
        assert ":" not in fname
        assert "\\" not in fname

    def test_newline_in_content_preserved(self, temp_vault, monkeypatch):
        """Quebras de linha no conteúdo são preservadas."""
        monkeypatch.setattr(sm, "DECISIONS_DIR", f"{temp_vault}/work/active")
        path = sm._save_decision("Test", "Linha 1\nLinha 2\n\nLinha 4")
        assert path is not None
        with open(path) as f:
            content = f.read()
        assert "Linha 1\nLinha 2" in content

    def test_learning_never_duplicated(self, temp_vault, monkeypatch):
        """Aprendizado exato nunca é duplicado."""
        patterns_file = f"{temp_vault}/brain/Patterns.md"
        monkeypatch.setattr(sm, "PATTERNS_FILE", patterns_file)

        paths = []
        for _ in range(5):
            p = sm._save_learning("Same Pattern", "Same content")
            if p:
                paths.append(p)

        # Only first write should succeed
        assert len(paths) == 1

    def test_current_state_handles_no_decisions(self, temp_vault, monkeypatch):
        """Current State lida com lista vazia de decisões."""
        monkeypatch.setattr(sm, "MEMORY_FILE", f"{temp_vault}/brain/Current State.md")
        sm._update_current_state([], [], "Resumo vazio")
        with open(f"{temp_vault}/brain/Current State.md") as f:
            content = f.read()
        assert "Last Update:" in content
        assert "Nenhuma decisão" in content

    def test_schema_validation_edge_cases(self):
        """Validação de schema lida com edge cases."""
        assert sm._validate_graph_schema({}) == False
        assert sm._validate_graph_schema(None) == False
        assert sm._validate_graph_schema("string") == False
        assert sm._validate_graph_schema({"nodes": [], "links": []}) == True
