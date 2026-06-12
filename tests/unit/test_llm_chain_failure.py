"""
Testes para PATCH 3 do LLM Council — ``core.llm_client.LLMChainFailure``
preserva o contexto da cadeia (primary + fallback) em vez de engolir
a causa raiz quando primário e fallback falham.

Cobre:
- LLMChainFailure herda de RuntimeError (compatibilidade com except genérico).
- LLMChainFailure preserva o chain (lista de tuplas (provider, model)).
- LLMChainFailure preserva primary_exc e fallback_exc como atributos.
- A mensagem inclui o provider/model do primário e do fallback.
- call_llm_with_fallback levanta LLMChainFailure quando a cadeia cai inteira
  (transient no primário + transient no fallback, sem retries disponíveis).
- call_llm_with_fallback NÃO levanta LLMChainFailure quando a validação
  falha — propagação direta da LLMValidationError original.
- call_llm_with_fallback NÃO levanta LLMChainFailure em auth: o fallback
  direto (sem retry no primário) pode dar certo e a função retorna o
  resultado do fallback.

Sem chamadas reais: requests.post é mockado para sempre levantar
exception transitória (Timeout).
"""
import unittest.mock as mock

import pytest

from core import llm_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def primary_only_role(monkeypatch):
    """Papel com apenas alvo primário (sem fallback) — para testar LLMChainFailure de 1 alvo."""
    cfg = {
        "provider": "openai",
        "model": "gpt-4o",
        "fallback_provider": None,
        "fallback_model": None,
    }
    monkeypatch.setattr(llm_client, "get_role_config", lambda role: cfg)
    return cfg


@pytest.fixture()
def two_target_role(monkeypatch):
    """Papel com primário + fallback — para testar LLMChainFailure de 2 alvos."""
    cfg = {
        "provider": "openai",
        "model": "gpt-4o",
        "fallback_provider": "anthropic",
        "fallback_model": "claude-3-5-sonnet",
    }
    monkeypatch.setattr(llm_client, "get_role_config", lambda role: cfg)
    return cfg


@pytest.fixture()
def always_transient(monkeypatch):
    """Mocka requests.post para sempre levantar Timeout (transient)."""
    import requests
    monkeypatch.setattr(
        llm_client.requests, "post",
        mock.Mock(side_effect=requests.exceptions.Timeout("simulated network timeout")),
    )


@pytest.fixture()
def fake_get_credentials(monkeypatch):
    """Mocka get_credentials para devolver credenciais fake por provedor."""
    creds = {
        "openai": {"key": "sk-fake-openai", "url": "https://api.openai.com/v1", "type": "api_key"},
        "anthropic": {"key": "sk-fake-anthropic", "url": "https://api.anthropic.com/v1", "type": "api_key"},
    }
    monkeypatch.setattr(llm_client, "get_credentials", lambda provider: creds.get(provider))


# ---------------------------------------------------------------------------
# Tests: estrutura do LLMChainFailure
# ---------------------------------------------------------------------------

class TestLLMChainFailureStructure:
    """A exceção precisa preservar a estrutura para diagnóstico."""

    def test_llm_chain_failure_inherits_runtime_error(self):
        """LLMChainFailure é uma RuntimeError (compat com except Exception)."""
        from core.llm_client import LLMChainFailure
        assert issubclass(LLMChainFailure, RuntimeError)

    def test_llm_chain_failure_preserves_chain_attribute(self):
        """O atributo .chain contém a lista de tuplas tentadas."""
        from core.llm_client import LLMChainFailure
        chain = [("openai", "gpt-4o"), ("anthropic", "claude-3-5-sonnet")]
        exc = LLMChainFailure(chain=chain, primary_exc=RuntimeError("p"), fallback_exc=RuntimeError("f"))
        assert exc.chain == chain
        assert exc.chain[0] == ("openai", "gpt-4o")
        assert exc.chain[1] == ("anthropic", "claude-3-5-sonnet")

    def test_llm_chain_failure_preserves_exceptions(self):
        """primary_exc e fallback_exc ficam acessíveis para diagnóstico."""
        from core.llm_client import LLMChainFailure
        p = ValueError("primary died")
        f = ConnectionError("fallback also died")
        exc = LLMChainFailure(
            chain=[("a", "1"), ("b", "2")],
            primary_exc=p,
            fallback_exc=f,
        )
        assert exc.primary_exc is p
        assert exc.fallback_exc is f

    def test_llm_chain_failure_message_mentions_providers(self):
        """A mensagem legível inclui provider/model para triagem rápida."""
        from core.llm_client import LLMChainFailure
        exc = LLMChainFailure(
            chain=[("openai", "gpt-4o"), ("anthropic", "claude-3-5-sonnet")],
            primary_exc=RuntimeError("p"),
            fallback_exc=RuntimeError("f"),
        )
        msg = str(exc)
        assert "openai" in msg
        assert "gpt-4o" in msg
        assert "anthropic" in msg
        assert "claude-3-5-sonnet" in msg

    def test_llm_chain_failure_handles_single_target_chain(self):
        """Cadeia de 1 só (sem fallback configurado) não quebra a mensagem."""
        from core.llm_client import LLMChainFailure
        exc = LLMChainFailure(
            chain=[("openai", "gpt-4o")],
            primary_exc=RuntimeError("p"),
            fallback_exc=None,
        )
        # Mensagem inclui o primário mas não quebra ao formatar fallback ausente
        assert "openai" in str(exc)


# ---------------------------------------------------------------------------
# Tests: call_llm_with_fallback levanta LLMChainFailure corretamente
# ---------------------------------------------------------------------------

class TestCallLlmWithFallbackRaisesChainFailure:
    """Integração: call_llm_with_fallback precisa levantar LLMChainFailure."""

    def test_primary_only_raises_chain_failure_after_exhausting_retries(
        self, primary_only_role, always_transient, fake_get_credentials, monkeypatch
    ):
        """Cadeia de 1 alvo: após max_retries, levanta LLMChainFailure."""
        # Limpa max_retries para acelerar: 1 retry só
        with mock.patch.object(llm_client, "call_llm_structured",
                               side_effect=__import__("requests").exceptions.Timeout("nope")):
            with pytest.raises(llm_client.LLMChainFailure) as excinfo:
                llm_client.call_llm_with_fallback(
                    role="graphify",
                    prompt="x", system_prompt="y",
                    response_model=None,  # não chegamos lá
                    max_retries=1,
                )
        assert excinfo.value.chain == [("openai", "gpt-4o")]
        assert isinstance(excinfo.value.primary_exc, __import__("requests").exceptions.Timeout)

    def test_primary_and_fallback_both_fail_raises_chain_failure(
        self, two_target_role, monkeypatch
    ):
        """Cadeia de 2 alvos: ambos falham (transient) → LLMChainFailure com ambos os excs."""
        import requests
        # call_llm_structured simulado levanta Timeout no primário e no fallback
        # (precisamos distinguir entre os dois alvos; a forma mais simples
        # é contar quantas vezes foi chamado e levantar o mesmo tipo)
        side_effects = [
            requests.exceptions.Timeout("primary 1"),
            requests.exceptions.Timeout("primary 2"),  # 1 retry do primário
            requests.exceptions.Timeout("fallback 1"),
            requests.exceptions.Timeout("fallback 2"),  # 1 retry do fallback
        ]
        with mock.patch.object(llm_client, "call_llm_structured",
                               side_effect=side_effects):
            with pytest.raises(llm_client.LLMChainFailure) as excinfo:
                llm_client.call_llm_with_fallback(
                    role="graphify",
                    prompt="x", system_prompt="y",
                    response_model=None,
                    max_retries=1,  # 1 retry por alvo = total de 4 chamadas
                )
        exc = excinfo.value
        assert exc.chain == [("openai", "gpt-4o"), ("anthropic", "claude-3-5-sonnet")]
        assert exc.fallback_exc is not None
        # primary_exc é a primeira exceção vista (Timeout do primário)
        assert isinstance(exc.primary_exc, requests.exceptions.Timeout)


# ---------------------------------------------------------------------------
# Tests: call_llm_with_fallback NÃO levanta LLMChainFailure para
# validação ou auth (a semântica original é preservada).
# ---------------------------------------------------------------------------

class TestCallLlmWithFallbackDoesNotChainFailureOnOtherErrors:
    """PATCH 3 só mexe no caminho de exaustão total. Validação e auth
    continuam propagando suas exceções originais."""

    def test_validation_error_propagates_directly(self, primary_only_role, monkeypatch):
        """LLMValidationError não vira LLMChainFailure — passa direto."""
        with mock.patch.object(
            llm_client, "call_llm_structured",
            side_effect=llm_client.LLMValidationError("pydantic boom"),
        ):
            with pytest.raises(llm_client.LLMValidationError):
                llm_client.call_llm_with_fallback(
                    role="graphify",
                    prompt="x", system_prompt="y",
                    response_model=None,
                    max_retries=2,
                )

    def test_auth_error_on_primary_falls_back_and_succeeds(
        self, two_target_role, monkeypatch
    ):
        """Auth no primário → vai direto pro fallback (sem retry no mesmo
        modelo) → fallback retorna sucesso. Sem LLMChainFailure."""

        class _FakeResult:
            ok = True

        # Primário: auth (sem retry). Fallback: sucesso.
        # Para isso, call_llm_structured precisa de side_effects:
        # 1ª chamada (primário) → levanta auth
        # 2ª chamada (fallback) → "retorna com sucesso" (na verdade nosso
        # teste falha antes de tentar serializar, mas o ponto é: NÃO
        # levanta LLMChainFailure)
        from core.llm_client import LLMValidationError  # só para garantir import
        auth_err = Exception("API Error (401): unauthorized")
        with mock.patch.object(
            llm_client, "call_llm_structured",
            side_effect=[auth_err, "fake-success-from-fallback"],
        ):
            result = llm_client.call_llm_with_fallback(
                role="graphify",
                prompt="x", system_prompt="y",
                response_model=None,
                max_retries=2,
            )
        assert result == "fake-success-from-fallback"
