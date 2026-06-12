"""
Testes para PATCH 2 do LLM Council — ``core.auth.load_env()`` precisa
de fato injetar variáveis em ``os.environ`` (antes era um no-op que
apenas retornava um dict ignorado).

Cobre:
- load_env() popula os.environ com chaves lidas do .env.
- load_env() NÃO sobrescreve variáveis já exportadas no shell
  (contrato de operador: setdefault).
- load_env() lida com valores que contêm '=' (URLs, JSON, etc.).
- load_env() remove aspas opcionais em volta do valor.
- load_env() ignora linhas de comentário.
- load_env() retorna {} quando ENV_FILE não existe.

Sem acesso ao .env real do projeto: apontamos ``ENV_FILE`` para um
arquivo temporário via monkeypatch.
"""
import os

import pytest

from core import auth


@pytest.fixture()
def tmp_env_file(tmp_path, monkeypatch):
    """Cria um .env temporário e redireciona auth.ENV_FILE para ele."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        # Comentários e linhas em branco
        "# Header comment\n"
        "\n"
        # Variáveis de papel Hive-Mind
        "HIVE_DREAMER_PROVIDER=anthropic\n"
        "HIVE_DREAMER_MODEL=claude-3-5-sonnet\n"
        # Valor com '=' no meio (URL com query string)
        "GOOGLE_API_KEY=AIzaSyD-abc123=https://example.com?x=1\n"
        # Valor com aspas
        'ANTHROPIC_API_KEY="sk-ant-fake-quoted"\n'
        # Aspas simples também
        "OPENAI_API_KEY='sk-openai-single'\n"
        # Comentário no meio do arquivo
        "# outro comentário\n"
        # Linha inválida (sem '=') — ignorada silenciosamente
        "NOT_A_VALID_LINE\n"
    )
    monkeypatch.setattr(auth, "ENV_FILE", env_file)
    return env_file


@pytest.fixture()
def clean_hive_env(monkeypatch):
    """Remove todas as HIVE_* e chaves usadas no teste de os.environ."""
    keys_to_clear = [
        "HIVE_DREAMER_PROVIDER", "HIVE_DREAMER_MODEL",
        "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "EXTRA_SHELL_VAR", "HIVE_VISION_PROVIDER",
    ]
    for k in keys_to_clear:
        monkeypatch.delenv(k, raising=False)
    return keys_to_clear


class TestLoadEnvInjectsIntoOsEnviron:
    """load_env() deve popular os.environ (não apenas devolver um dict)."""

    def test_load_env_injects_hive_dreamer_vars(self, tmp_env_file, clean_hive_env):
        """A correção do PATCH 2: load_env() popula os.environ com as chaves do .env."""
        result = auth.load_env()

        assert result["HIVE_DREAMER_PROVIDER"] == "anthropic"
        assert result["HIVE_DREAMER_MODEL"] == "claude-3-5-sonnet"
        # E o efeito no ambiente (a parte que estava quebrada):
        assert os.environ.get("HIVE_DREAMER_PROVIDER") == "anthropic", (
            "load_env() precisa injetar em os.environ (PATCH 2). "
            "Antes era no-op, agora deve popular o ambiente."
        )
        assert os.environ.get("HIVE_DREAMER_MODEL") == "claude-3-5-sonnet"

    def test_load_env_preserves_existing_shell_vars(self, tmp_env_file, clean_hive_env, monkeypatch):
        """setdefault: variáveis já exportadas no shell NÃO são sobrescritas."""
        monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "google-shell-wins")
        monkeypatch.setenv("HIVE_DREAMER_MODEL", "gemini-shell-wins")

        auth.load_env()

        assert os.environ["HIVE_DREAMER_PROVIDER"] == "google-shell-wins", (
            "Variável do shell deve ter precedência sobre o .env (contrato de operador)."
        )
        assert os.environ["HIVE_DREAMER_MODEL"] == "gemini-shell-wins"

    def test_load_env_handles_values_with_equals(self, tmp_env_file, clean_hive_env):
        """Valores contendo '=' (URLs com query string) devem ser preservados inteiros."""
        auth.load_env()

        # partition('=') é tolerante: o valor inteiro (incluindo '=') é preservado
        assert os.environ["GOOGLE_API_KEY"] == "AIzaSyD-abc123=https://example.com?x=1"

    def test_load_env_strips_double_quotes(self, tmp_env_file, clean_hive_env):
        """Aspas duplas em volta do valor devem ser removidas."""
        auth.load_env()

        assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-fake-quoted", (
            f"Aspas duplas deveriam ter sido removidas; "
            f"obtido: {os.environ.get('ANTHROPIC_API_KEY')!r}"
        )

    def test_load_env_strips_single_quotes(self, tmp_env_file, clean_hive_env):
        """Aspas simples em volta do valor devem ser removidas."""
        auth.load_env()

        assert os.environ["OPENAI_API_KEY"] == "sk-openai-single", (
            f"Aspas simples deveriam ter sido removidas; "
            f"obtido: {os.environ.get('OPENAI_API_KEY')!r}"
        )

    def test_load_env_ignores_comment_and_blank_lines(self, tmp_env_file, clean_hive_env):
        """Linhas iniciadas com '#' e linhas em branco são ignoradas."""
        # Nenhuma chave de comentário vaza para o ambiente
        auth.load_env()

        for k in os.environ:
            assert not k.startswith("#"), f"Comentário vazou como chave: {k}"

    def test_load_env_returns_empty_dict_when_no_env_file(self, tmp_path, monkeypatch):
        """Se ENV_FILE não existe, load_env() retorna {} sem efeito colateral."""
        monkeypatch.setattr(auth, "ENV_FILE", tmp_path / "no_such_file.env")
        # Não toca em os.environ
        sentinel = "x" + "y" * 20
        monkeypatch.setenv("HIVE_DREAMER_PROVIDER", sentinel)

        result = auth.load_env()

        assert result == {}
        assert os.environ["HIVE_DREAMER_PROVIDER"] == sentinel

    def test_load_env_get_role_config_resolves_after_load(
        self, tmp_env_file, clean_hive_env, monkeypatch
    ):
        """Integração ponta-a-ponta: load_env() → get_role_config() resolve o papel.

        Este é o cenário de uso real: numa shell fresca, o operador
        chama load_env() uma vez e get_role_config() passa a retornar
        o provider/model do Dreamer em vez de None.
        """
        # Garante que o .env do projeto real não está influenciando
        for k in clean_hive_env:
            monkeypatch.delenv(k, raising=False)
        # Aponta o ENV_FILE para o .env temporário
        monkeypatch.setattr(auth, "ENV_FILE", tmp_env_file)

        # Antes: get_role_config retorna None
        assert auth.get_role_config("graphify") is None

        # load_env() injeta as vars
        auth.load_env()

        # Depois: get_role_config consegue resolver
        cfg = auth.get_role_config("graphify")
        assert cfg is not None
        assert cfg["provider"] == "anthropic"
        assert cfg["model"] == "claude-3-5-sonnet"
