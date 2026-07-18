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

spec = importlib.util.spec_from_file_location("capture_core", SCRIPTS / "capture" / "capture_core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def test_data_dir_default_e_project_local():
    expected = SCRIPTS.parent / "claude-mem" / "data"
    assert core.DATA_DIR == expected


@pytest.fixture
def capture_posts(monkeypatch):
    """Captura todas as chamadas a _post sem rede; finge worker OK."""
    calls = []

    def fake_post(path, payload):
        calls.append((path, payload))
        return {"stored": True}

    monkeypatch.setattr(core, "_post", fake_post)
    return calls


@pytest.fixture
def store(tmp_path):
    """SeenStore isolado em diretório temporário para cada teste."""
    s = core.SeenStore(db_path=tmp_path / "test-state.db")
    yield s
    s.close()


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


def test_primeiro_prompt_nao_duplica(capture_posts, store):
    """Causa A: o prompt inicial NÃO pode ser emitido 2× (init de sessão + 1º turn)."""
    core.ingest("teste", _session(), store)
    inits, obs = _counts(capture_posts)
    # 2 prompts distintos (inicial + segunda pergunta), nunca 3
    assert inits == 2, f"esperado 2 inits, veio {inits} (1º prompt duplicado?)"
    assert obs == 2


def test_reingest_idempotente(capture_posts, store):
    """Reparsear a mesma sessão N vezes → só a 1ª emite; as demais 0."""
    sent1 = core.ingest("teste", _session(), store)
    n_after_first = len(capture_posts)
    sent2 = core.ingest("teste", _session(), store)
    sent3 = core.ingest("teste", _session(), store)
    assert sent1 == 2
    assert sent2 == 0 and sent3 == 0, "reingest emitiu conteúdo já visto"
    assert len(capture_posts) == n_after_first, "nenhum POST novo no reingest"


def test_turno_novo_emite_so_o_novo(capture_posts, store):
    """Fonte cresce (1 turn novo) → só o turn novo emite, não a sessão toda."""
    core.ingest("teste", _session(), store)
    base = len(capture_posts)
    grown = _session()
    grown["turns"].append({"tool_name": "Message",
                           "tool_input": {"prompt": "terceira"},
                           "tool_response": "resposta 3"})
    sent = core.ingest("teste", grown, store)
    assert sent == 1, "deveria emitir só a observação nova"
    # +1 init (prompt 'terceira') +1 observation +1 summarize
    novos = len(capture_posts) - base
    assert novos == 3, f"esperado 3 POSTs (init+obs+summary), veio {novos}"


def test_prompt_novo_sem_turno_emite_init(capture_posts, store):
    """Sessão Codex viva pode receber novo role=user antes de qualquer tool call."""
    core.ingest("teste", {"sid": "ses", "prompt": "primeiro", "prompts": ["primeiro"]}, store)
    base = len(capture_posts)

    sent = core.ingest(
        "teste",
        {"sid": "ses", "prompt": "primeiro", "prompts": ["primeiro", "segundo"]},
        store,
    )

    assert sent == 0
    novos = capture_posts[base:]
    assert len(novos) == 1
    assert novos[0][0] == "/api/sessions/init"
    assert novos[0][1]["prompt"] == "segundo"



@pytest.mark.parametrize("failed_response", [{"error": "worker offline"}, {"stored": False}])
def test_init_falha_nao_confirma_prompt_e_reenvia_quando_worker_volta(store, monkeypatch, failed_response):
    """Falha no init não pode tornar o prompt inicial permanentemente perdido."""
    calls = []
    online = False

    def fake_post(path, payload):
        calls.append((path, payload))
        if path == "/api/sessions/init" and not online:
            return failed_response
        return {"stored": True}

    monkeypatch.setattr(core, "_post", fake_post)
    core.ingest("teste", _session(), store)

    sid = "ses_test_1"
    initial = core.content_hash(sid, "p", core._norm("pergunta inicial do usuário"))
    additional = core.content_hash(sid, "p", core._norm("segunda pergunta"))
    observation = core.content_hash(sid, "o", "Message", core._norm("resposta 1"))
    assert not store.is_inited("teste", sid)
    assert not store.contains("teste", sid, initial)
    assert not store.contains("teste", sid, additional)
    assert store.contains("teste", sid, observation), "observações entregues continuam confirmadas"

    online = True
    before_retry = len(calls)
    assert core.ingest("teste", _session(), store) == 0

    retried_inits = [payload for path, payload in calls[before_retry:] if path == "/api/sessions/init"]
    assert [payload["prompt"] for payload in retried_inits] == [
        "pergunta inicial do usuário",
        "segunda pergunta",
    ]
    assert store.is_inited("teste", sid)
    assert store.contains("teste", sid, initial)
    assert store.contains("teste", sid, additional)


@pytest.mark.parametrize("failed_response", [{"error": "worker offline"}, {"stored": False}])
def test_emit_prompt_falho_e_retentado_sem_perder_prompt_adicional(store, monkeypatch, failed_response):
    """emit_prompt só grava seu hash depois de o init adicional ser aceito."""
    calls = []
    online = True

    def fake_post(path, payload):
        calls.append((path, payload))
        if path == "/api/sessions/init" and payload["prompt"] == "segundo" and not online:
            return failed_response
        return {"stored": True}

    monkeypatch.setattr(core, "_post", fake_post)
    session = {"sid": "ses_extra", "prompt": "primeiro", "prompts": ["primeiro", "segundo"]}

    online = False
    core.ingest("teste", session, store)

    second_hash = core.content_hash("ses_extra", "p", core._norm("segundo"))
    assert store.is_inited("teste", "ses_extra")
    assert not store.contains("teste", "ses_extra", second_hash)

    online = True
    before_retry = len(calls)
    assert core.ingest("teste", session, store) == 0

    retried_inits = [payload for path, payload in calls[before_retry:] if path == "/api/sessions/init"]
    assert [payload["prompt"] for payload in retried_inits] == ["segundo"]
    assert store.contains("teste", "ses_extra", second_hash)
def test_dois_processos_nao_duplicam(capture_posts, tmp_path):
    """Dois SeenStore no mesmo DB (concorrência) → sem duplicatas."""
    db = tmp_path / "shared.db"
    store_a = core.SeenStore(db_path=db)
    store_b = core.SeenStore(db_path=db)

    sent_a = core.ingest("teste", _session(), store_a)
    sent_b = core.ingest("teste", _session(), store_b)  # mesmo conteúdo, store diferente

    assert sent_a == 2
    assert sent_b == 0, "store_b duplicou conteúdo já emitido por store_a"

    store_a.close()
    store_b.close()


def test_seen_store_sobrevive_restart(capture_posts, tmp_path):
    """SeenStore carregado do mesmo arquivo não re-emite hashes anteriores."""
    db = tmp_path / "persist.db"

    store1 = core.SeenStore(db_path=db)
    core.ingest("teste", _session(), store1)
    n_first = len(capture_posts)
    store1.close()

    # Simula reinício: novo SeenStore abrindo o mesmo DB
    store2 = core.SeenStore(db_path=db)
    core.ingest("teste", _session(), store2)
    store2.close()

    assert len(capture_posts) == n_first, "reinício re-emitiu conteúdo já visto"


def test_seen_store_prune(tmp_path):
    """prune() remove hashes antigos sem afetar os recentes."""
    import time
    db = tmp_path / "prune.db"
    store = core.SeenStore(db_path=db)

    old_ts = int(time.time()) - 100
    store._con.execute(
        "INSERT OR IGNORE INTO seen_hashes(platform,sid,hash,ts) VALUES(?,?,?,?)",
        ("p", "s", "oldhash", old_ts),
    )
    store._con.execute(
        "INSERT OR IGNORE INTO seen_hashes(platform,sid,hash,ts) VALUES(?,?,?,?)",
        ("p", "s", "newhash", int(time.time())),
    )
    store._con.commit()

    removed = store.prune(int(time.time()) - 50)
    assert removed >= 1
    assert not store.contains("p", "s", "oldhash")
    assert store.contains("p", "s", "newhash")
    store.close()


def test_delivery_log_is_cp1252_safe_on_windows(capture_posts, store, monkeypatch):
    """A entrega não pode falhar ao escrever o status no console CP1252 do Windows."""
    class Cp1252Stream:
        def write(self, value):
            value.encode("cp1252", errors="strict")
            return len(value)

        def flush(self):
            return None

    monkeypatch.setattr(sys, "stdout", Cp1252Stream())
    assert core.ingest("copilot", _session(), store) == 2

def test_ordered_messages_retry_after_worker_returns_and_replay_is_idempotent(
    store, monkeypatch
):
    session = {
        "sid": "hermes-ordered-retry",
        "prompt": "prompt one",
        "prompts": ["prompt one", "prompt two"],
        "turns": [
            {
                "tool_name": "Message",
                "tool_input": {"prompt": "prompt one"},
                "tool_response": "answer one",
            },
            {
                "tool_name": "Message",
                "tool_input": {"prompt": "prompt two"},
                "tool_response": "answer two",
            },
        ],
        "messages": [
            {"role": "user", "content": "prompt one", "timestamp": 101.0},
            {"role": "assistant", "content": "answer one", "timestamp": 102.0},
            {"role": "tool", "content": "tool output", "timestamp": 103.0},
            {"role": "user", "content": "prompt two", "timestamp": 104.0},
            {"role": "assistant", "content": "answer two", "timestamp": 105.0},
        ],
        "last": "answer two",
    }
    calls = []
    online = False

    def fake_post(path, payload):
        calls.append((path, payload))
        return {"stored": True} if online else {"error": "worker offline"}

    monkeypatch.setattr(core, "_post", fake_post)

    assert core.ingest("hermes", session, store) == 0
    assert not store.is_inited("hermes", session["sid"])
    assert not store.contains(
        "hermes",
        session["sid"],
        core.content_hash(session["sid"], "p", core._norm("prompt one")),
    )
    assert not store.contains(
        "hermes",
        session["sid"],
        core.content_hash(session["sid"], "o", "Tool", core._norm("tool output")),
    )

    online = True
    calls.clear()
    assert core.ingest("hermes", session, store) == 3
    assert [path for path, _ in calls] == [
        "/api/sessions/init",
        "/api/sessions/observations",
        "/api/sessions/observations",
        "/api/sessions/init",
        "/api/sessions/observations",
        "/api/sessions/summarize",
    ]

    delivered_call_count = len(calls)
    assert core.ingest("hermes", session, store) == 0
    assert len(calls) == delivered_call_count
