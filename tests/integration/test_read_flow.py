import os
import pytest
from sinapse_memory import _pre_prompt_build, _query_vault_knowledge, health_check


class TestReadFlow:
    """I1: Fluxo de leitura"""

    def test_pre_prompt_build_no_crash(self):
        """I1.1: pre_prompt_build não crasha com query simples."""
        result = _pre_prompt_build(user_message="projeto thoth")
        assert isinstance(result, dict)

    def test_pre_prompt_build_empty_message(self):
        """I1.2: Query vazia retorna dict vazio."""
        result = _pre_prompt_build(user_message="")
        assert result == {}

    def test_query_vault_knowledge_real(self, ensure_backends):
        """I1.3: query_vault_knowledge com backends reais."""
        result = _query_vault_knowledge("test")
        assert result is None or isinstance(result, dict)

    def test_health_check_returns_dict(self):
        """I1.4: health_check retorna dict com keys esperadas."""
        status = health_check()
        assert isinstance(status, dict)
        assert "backends" in status
        assert "vault" in status
        assert "plugin" in status

    def test_health_check_has_healthy_key(self):
        """I1.5: health_check tem key 'healthy'."""
        status = health_check()
        assert "healthy" in status
