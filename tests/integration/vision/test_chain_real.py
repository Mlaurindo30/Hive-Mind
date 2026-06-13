"""Smoke C1-C4 (origem: /tmp/smoke_chain.py e /tmp/smoke_c3.py).

Cenários:
  C1 — primary=ollama local (qwen3:8b) sem fallback
  C2 — primary=google fake-404 → fallback=ollama local
  C3 — primary=ollama-cloud real (config do .env)
  C4 — primary=google fake + fallback=google fake → LLMChainFailure

Cobertura: PATCH 2 (load_env), PATCH 3 (LLMChainFailure preserva primary_exc +
fallback_exc), Bug 5 (ollama /v1 base_url).

Sem mocks. Pula se o provedor alvo não tem credencial ou Ollama local está off.
"""
import time
import pytest
from pydantic import BaseModel, Field

from core.auth import load_env, get_role_config
from core.llm_client import call_llm_with_fallback, LLMChainFailure


class SmokeOut(BaseModel):
    ok: bool
    n: int = Field(description="número de palavras do echo")


def _set_dreamer(env, prov=None, mod=None, fb_prov=None, fb_mod=None):
    for key, val in {
        "HIVE_DREAMER_PROVIDER": prov,
        "HIVE_DREAMER_MODEL": mod,
        "HIVE_DREAMER_FALLBACK_PROVIDER": fb_prov,
        "HIVE_DREAMER_FALLBACK_MODEL": fb_mod,
    }.items():
        if val is None:
            env.delenv(key, raising=False)
        else:
            env.setenv(key, val)


def _call(role, prompt, env, max_retries=1):
    return call_llm_with_fallback(
        role=role,
        system_prompt="Responda APENAS com JSON válido no schema exato. Nada além do JSON.",
        prompt=prompt,
        response_model=SmokeOut,
        max_retries=max_retries,
    )


# ============== C1 ==============

def test_c1_ollama_local_primary_no_fallback(saved_env, ollama_local_alive):
    """C1: caminho feliz ollama local sem fallback."""
    if not ollama_local_alive:
        pytest.skip("Ollama local :11434 offline")
    load_env()
    _set_dreamer(saved_env, prov="ollama", mod="qwen3:8b")
    cfg = get_role_config("dreamer")
    assert cfg["provider"] == "ollama"
    assert cfg["model"] == "qwen3:8b"

    t0 = time.time()
    out = _call("dreamer", "Diga OK. Conte palavras: 'casa carro livro'.", saved_env)
    dt = time.time() - t0
    assert out.ok is True
    assert out.n == 3
    assert dt < 180, f"ollama local demorou {dt:.1f}s"


# ============== C2 ==============

def test_c2_google_fake_404_falls_back_to_ollama_local(saved_env, ollama_local_alive):
    """C2: PRIMARY google/fake-404 → FALLBACK ollama local."""
    if not ollama_local_alive:
        pytest.skip("Ollama local :11434 offline (precisa pro fallback)")
    load_env()
    _set_dreamer(
        saved_env,
        prov="google", mod="gemini-2.5-flash-not-exist",
        fb_prov="ollama", fb_mod="qwen3:8b",
    )
    cfg = get_role_config("dreamer")
    assert cfg["provider"] == "google"
    assert cfg["fallback_provider"] == "ollama"

    out = _call("dreamer", "Diga OK. Conte palavras: 'casa carro'.", saved_env)
    assert out.ok is True
    assert out.n == 2


# ============== C3 ==============

def test_c3_ollama_cloud_real_primary(saved_env, requires_ollama_cloud):
    """C3: PRIMARY ollama-cloud (config real do .env) — caminho feliz.

    Valida o caminho feliz QUANDO o primário configurado é ollama-cloud.
    A config do dreamer é escolha do usuário (setup-brain); se ele apontou
    para outro provedor, este teste específico de ollama-cloud não se aplica
    e é pulado em vez de falhar por uma suposição de ambiente.
    """
    load_env()
    # não seta nada: usa o que load_env resolveu
    cfg = get_role_config("dreamer")
    if cfg["provider"] != "ollama-cloud":
        pytest.skip(
            f"dreamer primário é {cfg['provider']!r}, não ollama-cloud — "
            "teste específico de ollama-cloud não se aplica a esta config."
        )

    out = _call("dreamer", "Diga OK. Conte palavras: 'casa carro'.", saved_env)
    assert out.ok is True
    assert out.n == 2


# ============== C4 ==============

def test_c4_both_targets_dead_raises_chain_failure_with_both_exceptions(saved_env):
    """C4: PRIMARY google/fake + FALLBACK google/fake → LLMChainFailure com
    primary_exc E fallback_exc preservados (PATCH 3)."""
    load_env()
    _set_dreamer(
        saved_env,
        prov="google", mod="gemini-fake-1",
        fb_prov="google", fb_mod="gemini-fake-2",
    )
    with pytest.raises(LLMChainFailure) as exc_info:
        _call("dreamer", "Diga OK.", saved_env)
    e = exc_info.value
    assert e.primary_exc is not None, "LLMChainFailure.primary_exc deve preservar exceção do primário"
    assert e.fallback_exc is not None, "LLMChainFailure.fallback_exc deve preservar exceção do fallback"
    assert len(e.chain) == 2
