"""PATCH 1 — Visão real.

Valida que o caminho de visão (image_path → OpenAI Vision content) entrega
imagem ao provedor e o JSON schema é respeitado.

Cenários:
  V1 — PRIMARY google-fake-404 → FALLBACK configurado em HIVE_VISION_*
  V2 — PRIMARY configurado em HIVE_VISION_* direto (caminho feliz)

Origem: /tmp/smoke_vision_real.py
"""
import time
import pytest
from pydantic import BaseModel

from core.auth import get_credentials, get_role_config, load_env
from core.llm_client import call_llm_with_fallback, LLMChainFailure


class VisionResponse(BaseModel):
    description: str
    dominant_color: str
    confidence: float


def _set_vision(env, prov=None, mod=None, fb_prov=None, fb_mod=None):
    for key, val in {
        "HIVE_VISION_PROVIDER": prov,
        "HIVE_VISION_MODEL": mod,
        "HIVE_VISION_FALLBACK_PROVIDER": fb_prov,
        "HIVE_VISION_FALLBACK_MODEL": fb_mod,
    }.items():
        if val is None:
            env.delenv(key, raising=False)
        else:
            env.setenv(key, val)


SYSTEM = "Você é um classificador visual. Responda APENAS com JSON válido no schema. Nada além do JSON."
PROMPT = (
    "Olhe para a imagem anexa. Responda APENAS com JSON válido no schema exato.\n"
    "NÃO escreva nada além do JSON.\n\n"
    "Schema: {\"description\": str, \"dominant_color\": str, \"confidence\": float entre 0 e 1}\n\n"
    'Exemplo: {"description": "Fundo vermelho sólido", "dominant_color": "vermelho", "confidence": 0.95}'
)


def _looks_red(r: VisionResponse) -> bool:
    blob = (r.description + " " + r.dominant_color).lower()
    return ("vermelho" in blob) or ("red" in blob) or ("rgb" in blob and "220" in blob)


def _is_external_provider_unavailable(exc: Exception) -> bool:
    """True se um provedor remoto real está indisponível por limite/auth/cobrança."""
    blob = str(exc).lower()
    return any(
        marker in blob
        for marker in (
            "429",
            "401",
            "402",
            "403",
            "usage limit",
            "rate limit",
            "quota",
            "payment is past due",
            "subscription payment is past due",
            "billing",
            "unauthorized",
            "forbidden",
        )
    )


def _ollama_models() -> set[str]:
    import subprocess

    try:
        out = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("`ollama` CLI não disponível")
    return {line.split()[0] for line in out.splitlines() if line.strip() and not line.startswith("NAME")}


def _active_vision_target_or_skip(ollama_local_alive) -> tuple[str, str]:
    load_env()
    cfg = get_role_config("vision")
    if not cfg:
        pytest.skip("Papel vision não configurado no setup-brain/.env")

    provider = cfg["provider"]
    model = cfg["model"]
    if provider == "ollama":
        if not ollama_local_alive:
            pytest.skip("Ollama local :11434 offline")
        if model not in _ollama_models():
            pytest.skip(f"Modelo vision local {model!r} não está instalado")
    elif not get_credentials(provider):
        pytest.skip(f"Credencial do provider vision {provider!r} ausente")
    return provider, model


def _vision_call_or_skip(provider: str, **kwargs) -> VisionResponse:
    """Executa visão; só pula indisponibilidade externa para providers remotos."""
    try:
        return call_llm_with_fallback(**kwargs)
    except LLMChainFailure as exc:
        if provider != "ollama" and _is_external_provider_unavailable(exc):
            pytest.skip(f"provider vision remoto indisponível externamente; não é regressão de código: {exc}")
        raise


def test_v1_primary_breaks_fallback_to_configured_vision(saved_env, ollama_local_alive, vision_png):
    """V1: PRIMARY google-fake-404 → FALLBACK configurado no setup-brain."""
    provider, model = _active_vision_target_or_skip(ollama_local_alive)
    _set_vision(
        saved_env,
        prov="google-fake-404", mod="gemini-2.5-flash",
        fb_prov=provider, fb_mod=model,
    )

    t0 = time.time()
    r = _vision_call_or_skip(
        provider=provider,
        role="vision", prompt=PROMPT, system_prompt=SYSTEM,
        response_model=VisionResponse, image_path=str(vision_png), max_retries=1,
    )
    dt = time.time() - t0
    assert r.description and r.dominant_color and 0.0 <= r.confidence <= 1.0
    assert _looks_red(r), f"semântica: esperava 'vermelho', recebi description={r.description!r}, color={r.dominant_color!r}"
    assert dt < 180, f"vision via fallback configurado demorou {dt:.1f}s"


def test_v2_configured_vision_direct(saved_env, ollama_local_alive, vision_png):
    """V2: PRIMARY configurado no setup-brain direto."""
    provider, model = _active_vision_target_or_skip(ollama_local_alive)
    _set_vision(saved_env, prov=provider, mod=model)

    t0 = time.time()
    r = _vision_call_or_skip(
        provider=provider,
        role="vision", prompt=PROMPT, system_prompt=SYSTEM,
        response_model=VisionResponse, image_path=str(vision_png), max_retries=1,
    )
    dt = time.time() - t0
    assert r.description and r.dominant_color and 0.0 <= r.confidence <= 1.0
    assert _looks_red(r)
    assert dt < 180


def test_v1_fallback_chain_failure_when_both_targets_dead(saved_env, vision_png):
    """V1 negativo: PRIMARY e FALLBACK ambos fake → LLMChainFailure preserva ambos exc."""
    load_env()
    _set_vision(
        saved_env,
        prov="google-fake-404", mod="gemini-2.5-flash",
        fb_prov="google-fake-503", fb_mod="gemini-2.5-flash",
    )
    with pytest.raises(LLMChainFailure) as exc_info:
        call_llm_with_fallback(
            role="vision", prompt=PROMPT, system_prompt=SYSTEM,
            response_model=VisionResponse, image_path=str(vision_png), max_retries=1,
        )
    e = exc_info.value
    assert e.primary_exc is not None
    assert e.fallback_exc is not None
    assert len(e.chain) == 2
