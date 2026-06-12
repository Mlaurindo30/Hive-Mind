"""
Testes unitários para get_role_config() — configuração de LLM por papel.

Cobre os seguintes comportamentos:
- Papel com variáveis próprias usa as próprias vars
- Papel sem vars próprias herda de HIVE_DREAMER_*
- Fallback: papel com primário próprio usa seu próprio fallback; papel que herda
  o primário do Dreamer herda também o fallback do Dreamer
- Papel sem nada e sem Dreamer configurado → None ou RuntimeError

Sem chamadas a LLM real; sem acesso a disco; usa apenas monkeypatch de os.environ.
"""
import importlib
import os
import sys
import types
import pytest


# ---------------------------------------------------------------------------
# Helpers de importação
# ---------------------------------------------------------------------------

def _reload_dream_cycle(env: dict):
    """
    Carrega scripts/dream_cycle.py com o ambiente *env* isolado.

    Retorna o módulo carregado com as variáveis de módulo corretas.
    O truque de usar importlib.util + exec_module garante que variáveis
    de nível-de-módulo (como LLM_PROVIDER) sejam lidas do env fornecido
    e não de importações anteriores que ficaram cacheadas.
    """
    from pathlib import Path
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "dream_cycle.py"

    # Isola o ambiente
    orig_env = os.environ.copy()
    os.environ.clear()
    os.environ.update(env)

    try:
        spec = importlib.util.spec_from_file_location("_dream_cycle_test", module_path)
        mod = importlib.util.module_from_spec(spec)

        # Stub para que load_yaml não precise abrir arquivos reais
        # e para que get_connection não abra o banco de disco
        import unittest.mock as mock

        with (
            mock.patch("builtins.open", mock.mock_open(read_data="")),
            mock.patch("yaml.safe_load", return_value={
                "dream_cycle": {"validation": {"max_retries": 2}},
                "system_prompt": "stub de prompt para testes",
            }),
            mock.patch("core.database.get_connection", return_value=mock.MagicMock()),
            mock.patch("core.database.ensure_migrations"),
        ):
            # Não queremos que o módulo falhe ao tentar carregar YAMLs;
            # mock de yaml.safe_load já cobre isso acima, mas precisamos
            # garantir que as chamadas de topo de módulo não explodam.
            # Usamos um loader mínimo:
            try:
                spec.loader.exec_module(mod)
            except Exception:
                pass  # pode falhar em partes não relevantes
        return mod
    finally:
        os.environ.clear()
        os.environ.update(orig_env)


def _import_get_role_config():
    """
    Importa get_role_config de scripts/dream_cycle.py via importlib direto.
    Retorna a função ou None se ainda não implementada.
    """
    from pathlib import Path
    import importlib.util

    module_path = Path(__file__).resolve().parents[2] / "scripts" / "dream_cycle.py"
    spec = importlib.util.spec_from_file_location("_dc_for_role_config", module_path)
    mod = importlib.util.module_from_spec(spec)
    return mod, module_path


# ---------------------------------------------------------------------------
# Fixture principal
# ---------------------------------------------------------------------------

@pytest.fixture()
def get_role_config_fn():
    """
    Retorna a função get_role_config importada de scripts/dream_cycle.py,
    ou pula o teste se a função ainda não existir (feature não implementada).
    """
    from pathlib import Path
    import importlib.util
    import unittest.mock as mock

    module_path = Path(__file__).resolve().parents[2] / "scripts" / "dream_cycle.py"
    spec = importlib.util.spec_from_file_location("_dc_role_cfg", module_path)
    mod = importlib.util.module_from_spec(spec)

    with (
        mock.patch("yaml.safe_load", return_value={
            "dream_cycle": {"validation": {"max_retries": 2}},
            "system_prompt": "stub de prompt para testes",
        }),
        mock.patch("builtins.open", mock.mock_open(read_data="")),
        mock.patch("core.database.get_connection", return_value=mock.MagicMock()),
        mock.patch("core.database.ensure_migrations"),
    ):
        try:
            spec.loader.exec_module(mod)
        except Exception:
            pass

    if not hasattr(mod, "get_role_config"):
        pytest.skip("get_role_config() ainda não implementada — coder pendente")

    return mod.get_role_config


# ---------------------------------------------------------------------------
# Classe de testes
# ---------------------------------------------------------------------------

class TestGetRoleConfig:
    """
    Testes para get_role_config(role: str) -> dict | None.

    Convenção de env vars esperada pelo coder:
      Primário:  HIVE_{ROLE_UPPER}_PROVIDER   / HIVE_{ROLE_UPPER}_MODEL
      Fallback:  HIVE_{ROLE_UPPER}_FALLBACK_PROVIDER / HIVE_{ROLE_UPPER}_FALLBACK_MODEL
      Default:   HIVE_DREAMER_PROVIDER         / HIVE_DREAMER_MODEL
      Fallback d: HIVE_DREAMER_FALLBACK_PROVIDER / HIVE_DREAMER_FALLBACK_MODEL
    """

    def test_should_return_own_provider_when_role_has_own_vars(
        self, get_role_config_fn, monkeypatch
    ):
        """
        should return own provider/model when role has its own env vars set.
        """
        monkeypatch.setenv("HIVE_GRAPHIFY_PROVIDER", "anthropic")
        monkeypatch.setenv("HIVE_GRAPHIFY_MODEL", "claude-haiku-4")
        monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "google")
        monkeypatch.setenv("HIVE_DREAMER_MODEL", "gemini-2.0-flash")

        cfg = get_role_config_fn("graphify")

        assert cfg is not None
        assert cfg["provider"] == "anthropic"
        assert cfg["model"] == "claude-haiku-4"

    def test_should_inherit_dreamer_provider_when_role_has_no_own_vars(
        self, get_role_config_fn, monkeypatch
    ):
        """
        should inherit HIVE_DREAMER_PROVIDER and MODEL when role has no own vars.
        """
        # Apaga vars do papel
        monkeypatch.delenv("HIVE_VISION_PROVIDER", raising=False)
        monkeypatch.delenv("HIVE_VISION_MODEL", raising=False)
        monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "deepseek")
        monkeypatch.setenv("HIVE_DREAMER_MODEL", "deepseek-v3")

        cfg = get_role_config_fn("vision")

        assert cfg is not None
        assert cfg["provider"] == "deepseek"
        assert cfg["model"] == "deepseek-v3"

    def test_should_use_own_fallback_when_role_has_own_primary(
        self, get_role_config_fn, monkeypatch
    ):
        """
        should use role's own fallback when role defines its own primary vars.

        Regra: papel com primário próprio → usa somente o seu próprio fallback,
        NÃO herda o fallback do Dreamer.
        """
        monkeypatch.setenv("HIVE_SYNTHESIS_PROVIDER", "openai")
        monkeypatch.setenv("HIVE_SYNTHESIS_MODEL", "gpt-4o")
        monkeypatch.setenv("HIVE_SYNTHESIS_FALLBACK_PROVIDER", "ollama")
        monkeypatch.setenv("HIVE_SYNTHESIS_FALLBACK_MODEL", "llama3.2")
        # Dreamer com fallback diferente — deve ser ignorado para este papel
        monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "google")
        monkeypatch.setenv("HIVE_DREAMER_MODEL", "gemini-2.0-flash")
        monkeypatch.setenv("HIVE_DREAMER_FALLBACK_PROVIDER", "anthropic")
        monkeypatch.setenv("HIVE_DREAMER_FALLBACK_MODEL", "claude-haiku")

        cfg = get_role_config_fn("synthesis")

        assert cfg is not None
        assert cfg.get("fallback_provider") == "ollama"
        assert cfg.get("fallback_model") == "llama3.2"

    def test_should_inherit_dreamer_fallback_when_role_inherits_primary(
        self, get_role_config_fn, monkeypatch
    ):
        """
        should inherit HIVE_DREAMER fallback when role has no own primary vars.

        Regra: papel que herda o primário do Dreamer herda também o fallback
        do Dreamer (não tem fallback independente para ele mesmo).
        """
        monkeypatch.delenv("HIVE_GRAPHIFY_PROVIDER", raising=False)
        monkeypatch.delenv("HIVE_GRAPHIFY_MODEL", raising=False)
        monkeypatch.delenv("HIVE_GRAPHIFY_FALLBACK_PROVIDER", raising=False)
        monkeypatch.delenv("HIVE_GRAPHIFY_FALLBACK_MODEL", raising=False)
        monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "openai")
        monkeypatch.setenv("HIVE_DREAMER_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("HIVE_DREAMER_FALLBACK_PROVIDER", "ollama")
        monkeypatch.setenv("HIVE_DREAMER_FALLBACK_MODEL", "qwen2.5-coder:3b")

        cfg = get_role_config_fn("graphify")

        assert cfg is not None
        assert cfg.get("fallback_provider") == "ollama"
        assert cfg.get("fallback_model") == "qwen2.5-coder:3b"

    def test_should_not_expose_dreamer_fallback_when_role_has_own_primary_but_no_own_fallback(
        self, get_role_config_fn, monkeypatch
    ):
        """
        should NOT inherit Dreamer fallback when role has its own primary but no own fallback.

        Regra: papel com primário próprio mas sem fallback próprio definido →
        fallback é None (ou ausente), nunca o fallback do Dreamer.
        """
        monkeypatch.setenv("HIVE_VISION_PROVIDER", "google")
        monkeypatch.setenv("HIVE_VISION_MODEL", "gemini-2.0-flash")
        monkeypatch.delenv("HIVE_VISION_FALLBACK_PROVIDER", raising=False)
        monkeypatch.delenv("HIVE_VISION_FALLBACK_MODEL", raising=False)
        monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "openai")
        monkeypatch.setenv("HIVE_DREAMER_MODEL", "gpt-4o")
        monkeypatch.setenv("HIVE_DREAMER_FALLBACK_PROVIDER", "anthropic")
        monkeypatch.setenv("HIVE_DREAMER_FALLBACK_MODEL", "claude-haiku")

        cfg = get_role_config_fn("vision")

        assert cfg is not None
        # Quando papel tem primário próprio sem fallback próprio, não deve herdar
        # o fallback do Dreamer
        fallback_provider = cfg.get("fallback_provider")
        assert fallback_provider != "anthropic", (
            "Papel com primário próprio não deve herdar o fallback do Dreamer"
        )

    def test_should_return_none_or_raise_when_nothing_configured(
        self, get_role_config_fn, monkeypatch
    ):
        """
        should return None or raise RuntimeError when neither role vars nor
        HIVE_DREAMER_* are configured.

        Comportamento definido pelo coder: None ou RuntimeError explícito.
        Qualquer dos dois é aceitável, desde que não retorne um dict vazio
        que passe silenciosamente para call_llm_structured com valores None.
        """
        monkeypatch.delenv("HIVE_GRAPHIFY_PROVIDER", raising=False)
        monkeypatch.delenv("HIVE_GRAPHIFY_MODEL", raising=False)
        monkeypatch.delenv("HIVE_DREAMER_PROVIDER", raising=False)
        monkeypatch.delenv("HIVE_DREAMER_MODEL", raising=False)

        try:
            result = get_role_config_fn("graphify")
        except (RuntimeError, ValueError, KeyError, Exception) as exc:
            # Qualquer exceção explícita é aceitável: falha clara
            assert str(exc) != "", "Exceção deve ter mensagem descritiva"
            return

        # Se não levantou exceção, deve retornar None ou um dict sem provider/model válidos
        assert result is None or (
            result.get("provider") is None and result.get("model") is None
        ), (
            "Quando nada está configurado, get_role_config deve retornar None "
            "ou levantar uma exceção clara — não um dict com valores preenchidos."
        )

    def test_should_be_case_insensitive_for_role_name(
        self, get_role_config_fn, monkeypatch
    ):
        """
        should resolve env vars correctly regardless of role name casing.
        """
        monkeypatch.setenv("HIVE_GRAPHIFY_PROVIDER", "anthropic")
        monkeypatch.setenv("HIVE_GRAPHIFY_MODEL", "claude-haiku-4")

        cfg_lower = get_role_config_fn("graphify")
        cfg_upper = get_role_config_fn("GRAPHIFY")

        assert cfg_lower is not None
        assert cfg_upper is not None
        assert cfg_lower["provider"] == cfg_upper["provider"]
        assert cfg_lower["model"] == cfg_upper["model"]

    def test_should_support_all_pipeline_roles(
        self, get_role_config_fn, monkeypatch
    ):
        """
        should accept all four pipeline roles without raising TypeError.
        """
        monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "google")
        monkeypatch.setenv("HIVE_DREAMER_MODEL", "gemini-2.0-flash")

        for role in ("dreamer", "graphify", "vision", "synthesis"):
            cfg = get_role_config_fn(role)
            assert cfg is not None, f"Role '{role}' retornou None com Dreamer configurado"
