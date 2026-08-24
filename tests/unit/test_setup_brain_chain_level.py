"""Aceitação do sync do Setup Brain por nível da cadeia claude_mem.

Contrato: editar fallback (nível 1) ou fallback2 (nível 2) no papel
claude_mem deve refletir imediatamente na CLAUDE_MEM_PROVIDER_CHAIN viva —
a verificação confere a entrada correspondente da cadeia, não o primário.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_setup_brain():
    """Importa scripts/setup/setup-brain.py sem executar o menu interativo."""
    path = PROJECT_ROOT / "scripts" / "setup" / "setup-brain.py"
    spec = importlib.util.spec_from_file_location("setup_brain_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("setup_brain_mod", mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sb():
    return _load_setup_brain()


CHAIN = [
    {"slot": "openrouter", "provider": "omniroute", "model": "agy/gemini-3.6-flash-low"},
    {"slot": "openrouter", "provider": "ollama", "model": "granite4.1:8b"},
]


def _settings(chain):
    return {"CLAUDE_MEM_PROVIDER_CHAIN": __import__("json").dumps(chain)}


def test_primary_level_matches(sb):
    ok, msg = sb._chain_level_matches(_settings(CHAIN), 0, "omniroute", "agy/gemini-3.6-flash-low")
    assert ok and "nível 0" in msg


def test_fallback_level_matches_case_insensitive_provider(sb):
    ok, msg = sb._chain_level_matches(_settings(CHAIN), 1, "Ollama", "granite4.1:8b")
    assert ok and "nível 1" in msg


def test_fallback_level_mismatch_reports_live_entry(sb):
    ok, msg = sb._chain_level_matches(_settings(CHAIN), 1, "omniroute", "other-model")
    assert not ok and "granite4.1:8b" in msg and "other-model" in msg


def test_missing_level_fails(sb):
    ok, msg = sb._chain_level_matches(_settings(CHAIN), 2, "ollama", "x")
    assert not ok and "ausente" in msg


def test_invalid_chain_json_fails(sb):
    ok, msg = sb._chain_level_matches({"CLAUDE_MEM_PROVIDER_CHAIN": "[{bad"}, 1, "ollama", "x")
    assert not ok and "inválida" in msg


def test_empty_settings_fail(sb):
    ok, _ = sb._chain_level_matches({}, 0, "omniroute", "agy/gemini-3.6-flash-low")
    assert not ok
