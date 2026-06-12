"""Bug 7 — Ollama local /v1 retorna content="" e coloca resposta no campo
``reasoning`` para modelos que pensam (gemma4, qwen3.5).

Sem o fix, o parser Pydantic aceita ``description: str`` como string vazia e
o resultado fica silenciosamente errado.

Estes testes exigem:
  - Ollama local em :11434
  - gemma4:26b E/OU qwen3.5:9b instalados (`ollama pull ...`)

Origem: /tmp/smoke_bug7.py
"""
import pytest
from pydantic import BaseModel

from core.auth import load_env
from core.llm_client import call_llm_with_fallback


class VisionResponse(BaseModel):
    description: str
    dominant_color: str
    confidence: float


def _set_vision(env, prov, mod):
    env.delenv("HIVE_VISION_FALLBACK_PROVIDER", raising=False)
    env.delenv("HIVE_VISION_FALLBACK_MODEL", raising=False)
    env.setenv("HIVE_VISION_PROVIDER", prov)
    env.setenv("HIVE_VISION_MODEL", mod)


SYSTEM = (
    "Você é um classificador visual. Pense passo a passo em português, depois "
    "responda APENAS com JSON válido no schema exato. Nada além do JSON."
)
PROMPT = (
    "Olhe para a imagem anexa. Primeiro pense: que cor vejo? É uniforme? Há detalhes?\n"
    "Depois responda APENAS com JSON válido no schema exato. NÃO escreva nada além do JSON.\n\n"
    'Schema: {"description": str, "dominant_color": str, "confidence": float entre 0 e 1}'
)


def _looks_red(r: VisionResponse) -> bool:
    blob = (r.description + " " + r.dominant_color).lower()
    return ("vermelho" in blob) or ("red" in blob)


def _needs_bug7():
    return True  # gating via env: HIVE_RUN_BUG7=1


def test_bug7_gemma4_local_reasoning_fallback(saved_env, ollama_local_alive, ollama_model_available, vision_png):
    """Bug 7 fix: gemma4:26b via /v1 — content vazio + reasoning cheio → não pode dar description vazia."""
    if not ollama_local_alive:
        pytest.skip("Ollama local :11434 offline")
    if not _needs_bug7():
        pytest.skip("Bug 7 subset desabilitado (HIVE_RUN_BUG7=1)")
    if not ollama_model_available("gemma4:26b"):
        pytest.skip("gemma4:26b não está instalado localmente")

    load_env()
    _set_vision(saved_env, "ollama", "gemma4:26b")

    r = call_llm_with_fallback(
        role="vision", prompt=PROMPT, system_prompt=SYSTEM,
        response_model=VisionResponse, image_path=str(vision_png), max_retries=1,
    )
    assert r.description and r.description.strip(), \
        f"Bug 7 NÃO corrigido: description veio vazia ({r.description!r})"
    assert r.dominant_color, "dominant_color veio vazia"
    assert 0.0 <= r.confidence <= 1.0
    assert _looks_red(r), f"semântica: esperava 'vermelho', recebi {r.description!r}"


def test_bug7_qwen35_local_reasoning_fallback(saved_env, ollama_local_alive, ollama_model_available, vision_png):
    """Bug 7 fix: qwen3.5:9b via /v1 — mesmo padrão."""
    if not ollama_local_alive:
        pytest.skip("Ollama local :11434 offline")
    if not _needs_bug7():
        pytest.skip("Bug 7 subset desabilitado (HIVE_RUN_BUG7=1)")
    if not ollama_model_available("qwen3.5:9b"):
        pytest.skip("qwen3.5:9b não está instalado localmente")

    load_env()
    _set_vision(saved_env, "ollama", "qwen3.5:9b")

    r = call_llm_with_fallback(
        role="vision", prompt=PROMPT, system_prompt=SYSTEM,
        response_model=VisionResponse, image_path=str(vision_png), max_retries=1,
    )
    assert r.description and r.description.strip()
    assert r.dominant_color
    assert 0.0 <= r.confidence <= 1.0
    assert _looks_red(r)
