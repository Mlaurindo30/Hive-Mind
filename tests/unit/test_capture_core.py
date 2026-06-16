"""Testes do motor de transporte capture_core (idempotência por content-hash).

Garante que a Causa A (duplo-emit do 1º prompt) e a re-emissão sob reparse/
reescrita/multi-processo estão eliminadas — sem depender de um worker real
(monkeypatch em _post).
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("capture_core", SCRIPTS / "capture_core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


@pytest.fixture
def capture_posts(monkeypatch):
    """Captura todas as chamadas a _post sem rede; finge worker OK."""
    calls = []

    def fake_post(path, payload):
        calls.append((path, payload))
        return {"stored": True}

    monkeypatch.setattr(core, "_post", fake_post)
    return calls


def _counts(calls):
    inits = [c for c in calls if c[0] == "/api/sessions/init"]
    obs = [c for c in calls if c[0] == "/api/sessions/observations"]
    return len(inits), len(obs)


def _session():
    return {
        "sid": "ses_test_1",
        "prompt": "pergunta inicial do usuário",
        "turns": [
            # 1º turn carrega o MESMO prompt inicial (origem da Causa A)
            {"tool_name": "Message",
             "tool_input": {"prompt": "pergunta inicial do usuário"},
             "tool_response": "resposta 1"},
            {"tool_name": "Message",
             "tool_input": {"prompt": "segunda pergunta"},
             "tool_response": "resposta 2"},
        ],
        "last": "resposta 2",
    }


def test_content_hash_estavel():
    assert core.content_hash("s", "p", "oi") == core.content_hash("s", "p", "oi")
    assert core.content_hash("s", "p", "oi") != core.content_hash("s", "p", "tchau")


def test_primeiro_prompt_nao_duplica(capture_posts):
    """Causa A: o prompt inicial NÃO pode ser emitido 2× (init de sessão + 1º turn)."""
    state = {}
    core.ingest("teste", _session(), state)
    inits, obs = _counts(capture_posts)
    # 2 prompts distintos (inicial + segunda pergunta), nunca 3
    assert inits == 2, f"esperado 2 inits, veio {inits} (1º prompt duplicado?)"
    assert obs == 2


def test_reingest_idempotente(capture_posts):
    """Reparsear a mesma sessão N vezes → só a 1ª emite; as demais 0."""
    state = {}
    sent1 = core.ingest("teste", _session(), state)
    n_after_first = len(capture_posts)
    sent2 = core.ingest("teste", _session(), state)
    sent3 = core.ingest("teste", _session(), state)
    assert sent1 == 2
    assert sent2 == 0 and sent3 == 0, "reingest emitiu conteúdo já visto"
    assert len(capture_posts) == n_after_first, "nenhum POST novo no reingest"


def test_turno_novo_emite_so_o_novo(capture_posts):
    """Fonte cresce (1 turn novo) → só o turn novo emite, não a sessão toda."""
    state = {}
    core.ingest("teste", _session(), state)
    base = len(capture_posts)
    grown = _session()
    grown["turns"].append({"tool_name": "Message",
                           "tool_input": {"prompt": "terceira"},
                           "tool_response": "resposta 3"})
    sent = core.ingest("teste", grown, state)
    assert sent == 1, "deveria emitir só a observação nova"
    # +1 init (prompt 'terceira') +1 observation +1 summarize
    novos = len(capture_posts) - base
    assert novos == 3, f"esperado 3 POSTs (init+obs+summary), veio {novos}"
