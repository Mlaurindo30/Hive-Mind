import os
import pytest
import sinapse_memory as sm


class TestFullSession:
    """E1: Ciclo completo de sessão."""

    def test_full_read_write_cycle(self, temp_vault, monkeypatch):
        """Simula sessão completa: pre_prompt → post_tool → post_session."""
        # Redireciona paths para vault temporário
        monkeypatch.setattr(sm, "VAULT_DIR", temp_vault)
        monkeypatch.setattr(sm, "DECISIONS_DIR", f"{temp_vault}/work/active")
        monkeypatch.setattr(sm, "MEMORY_FILE", f"{temp_vault}/brain/Current State.md")
        monkeypatch.setattr(sm, "PATTERNS_FILE", f"{temp_vault}/brain/Patterns.md")

        # Passo 1: Leitura (simplificado — sem backends reais)
        result = sm._pre_prompt_build(user_message="projeto thoth")
        assert isinstance(result, dict)

        # Passo 2: Escrita de decisão
        sm._post_tool_use(
            tool_name="memory_add",
            tool_args={
                "title": "Migrar servidor para Hetzner",
                "content": "Decisão: migrar VPS para Hetzner. Insight: padrão de economizar em cloud.",
            },
        )

        # Verifica decisão salva
        decisions = os.listdir(f"{temp_vault}/work/active")
        assert any("migrar-servidor" in d or "Migrar-servidor" in d for d in decisions)

        # Passo 3: Fim de sessão
        sm._post_session_end(
            session_summary="Sessão produtiva com decisões importantes"
        )

        # Verifica Current State
        with open(f"{temp_vault}/brain/Current State.md") as f:
            state = f.read()
        assert "Last Update:" in state

        # Verifica aprendizado (Patterns.md) — deve ter sido detectado
        with open(f"{temp_vault}/brain/Patterns.md") as f:
            patterns = f.read()
        assert "Migrar servidor" in patterns

    def test_session_with_no_decisions(self, temp_vault, monkeypatch):
        """E1.2: Sessão sem decisões não quebra."""
        monkeypatch.setattr(sm, "VAULT_DIR", temp_vault)
        monkeypatch.setattr(sm, "DECISIONS_DIR", f"{temp_vault}/work/active")
        monkeypatch.setattr(sm, "MEMORY_FILE", f"{temp_vault}/brain/Current State.md")
        monkeypatch.setattr(sm, "PATTERNS_FILE", f"{temp_vault}/brain/Patterns.md")

        # Post session end com buffer vazio
        sm._post_session_end(session_summary="Nada aconteceu nesta sessão")

        # Não deve crashar e Last Update deve existir
        with open(f"{temp_vault}/brain/Current State.md") as f:
            state = f.read()
        assert "Last Update:" in state
        assert "Nenhuma decisão" in state

    def test_session_multiple_decisions(self, temp_vault, monkeypatch):
        """E1.3: Múltiplas decisões na mesma sessão."""
        monkeypatch.setattr(sm, "VAULT_DIR", temp_vault)
        monkeypatch.setattr(sm, "DECISIONS_DIR", f"{temp_vault}/work/active")
        monkeypatch.setattr(sm, "MEMORY_FILE", f"{temp_vault}/brain/Current State.md")
        monkeypatch.setattr(sm, "PATTERNS_FILE", f"{temp_vault}/brain/Patterns.md")

        for i in range(3):
            sm._post_tool_use(
                tool_name="memory_add",
                tool_args={
                    "title": f"Decisão {i}",
                    "content": f"Conteúdo da decisão {i}",
                },
            )

        decisions = os.listdir(f"{temp_vault}/work/active")
        assert len(decisions) == 3

    def test_dry_run_no_files_written(self, temp_vault, monkeypatch):
        """E1.4: Dry-run não escreve arquivos reais."""
        monkeypatch.setattr(sm, "DRY_RUN", True)
        monkeypatch.setattr(sm, "VAULT_DIR", temp_vault)
        monkeypatch.setattr(sm, "DECISIONS_DIR", f"{temp_vault}/work/active")
        monkeypatch.setattr(sm, "MEMORY_FILE", f"{temp_vault}/brain/Current State.md")
        monkeypatch.setattr(sm, "PATTERNS_FILE", f"{temp_vault}/brain/Patterns.md")

        path = sm._save_decision("Teste Dry", "Conteúdo")
        assert path == "/dev/null/dry-run"

        # Nenhum arquivo real deve ser criado
        decision_files = os.listdir(f"{temp_vault}/work/active")
        assert len(decision_files) == 0

    def test_nmem_backend_not_crashing(self, monkeypatch):
        """E1.5: Backend nmem ausente não crasha."""
        monkeypatch.setattr(sm, "NMEM_BIN", "/nonexistent/nmem")
        result = sm._backend_neural_memory("test")
        assert result is None
