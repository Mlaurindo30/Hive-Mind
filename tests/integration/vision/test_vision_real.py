"""PATCH 1 — Visão real.

Valida que o caminho de visão (image_path → OpenAI Vision content) entrega
imagem ao provedor e o JSON schema é respeitado.

Cenários:
  V1 — PRIMARY google-fake-404 → FALLBACK ollama-cloud/gemma3:4b
  V2 — PRIMARY ollama-cloud/gemma3:4b direto (caminho feliz)

Origem: /tmp/smoke_vision_real.py
"""
import time
import pytest
from pydantic import BaseModel

from core.auth import load_env
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


def _is_quota_error(exc: Exception) -> bool:
    """True se a falha foi rate limit / cota esgotada (429), não defeito de código."""
    blob = str(exc).lower()
    return "429" in blob or "usage limit" in blob or "rate limit" in blob or "quota" in blob


def _vision_call_or_skip(**kwargs) -> VisionResponse:
    """Executa a chamada de visão; pula o teste se o provedor estiver sem cota (429)."""
    try:
        return call_llm_with_fallback(**kwargs)
    except LLMChainFailure as exc:
        if _is_quota_error(exc):
            pytest.skip(f"ollama-cloud sem cota (429) — limite externo, não regressão: {exc}")
        raise


def test_v1_primary_breaks_fallback_ollama_cloud_vision(saved_env, requires_ollama_cloud, vision_png):
    """V1: PRIMARY google-fake-404 → FALLBACK ollama-cloud/gemma3:4b com imagem."""
    load_env()
    _set_vision(
        saved_env,
        prov="google-fake-404", mod="gemini-2.5-flash",
        fb_prov="ollama-cloud", fb_mod="gemma3:4b",
    )

    t0 = time.time()
    r = _vision_call_or_skip(
        role="vision", prompt=PROMPT, system_prompt=SYSTEM,
        response_model=VisionResponse, image_path=str(vision_png), max_retries=1,
    )
    dt = time.time() - t0
    assert r.description and r.dominant_color and 0.0 <= r.confidence <= 1.0
    assert _looks_red(r), f"semântica: esperava 'vermelho', recebi description={r.description!r}, color={r.dominant_color!r}"
    assert dt < 180, f"vision via fallback demorou {dt:.1f}s"


def test_v2_ollama_cloud_vision_direct(saved_env, requires_ollama_cloud, vision_png):
    """V2: PRIMARY ollama-cloud/gemma3:4b direto."""
    load_env()
    _set_vision(saved_env, prov="ollama-cloud", mod="gemma3:4b")

    t0 = time.time()
    r = _vision_call_or_skip(
        role="vision", prompt=PROMPT, system_prompt=SYSTEM,
        response_model=VisionResponse, image_path=str(vision_png), max_retries=1,
    )
    dt = time.time() - t0
    assert r.description and r.dominant_color and 0.0 <= r.confidence <= 1.0
    assert _looks_red(r)
    assert dt < 180


def test_v1_fallback_chain_failure_when_both_ollama_cloud_and_google_dead(saved_env, vision_png):
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
