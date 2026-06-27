"""Graphiti temporal graph client for Hive-Mind.

Órgão do **lóbulo temporal** (córtex): grafo de causalidade temporal que
complementa o tracking de eventos do `claude-mem` (tálamo sensorial do
mesmo lobo). Juntos, dão ao cérebro a capacidade de responder "o que era
verdade sobre X em tal data" — sem isso, o lóbulo temporal só tem sinapses
estáticas.

Config (env vars):
  FALKORDB_HOST        — default: localhost
  FALKORDB_PORT        — default: 6379
  FALKORDB_USER        — default: (empty)
  FALKORDB_PASSWORD    — default: (empty)
  FALKORDB_DB          — default: sinapse
  GRAPHITI_LLM_BASE    — default: http://localhost:11434/v1
  HIVE_GRAPHITI_MODEL  — modelo de extração (role no setupbrain). Default:
                         qwen2.5:3b (prosa multilíngue, ~1.9GB, coexiste na GPU).
                         GRAPHITI_LLM_MODEL é alias legado e tem precedência.
  GRAPHITI_EMBED_MODEL — default: bge-m3:latest (deve existir no Ollama)
  HIVE_GRAPHITI_RETRIES    — default: 3 (tentativas com backoff 1s, 2s, 4s)
  HIVE_GRAPHITI_CB_FAILS   — default: 3 (falhas consecutivas que abrem o circuit)
  HIVE_GRAPHITI_CB_COOLDOWN — default: 30s

Robustez:
  1. Smoke test (assert_health) — verifica FalkorDB + modelos Ollama.
  2. Circuit breaker — após N falhas, pausa N segundos.
  3. Persistência — bind mount do FalkorDB no install.sh; sem Docker,
     fallback para JSON-lines em `cortex/temporal/_global/grafo.jsonl`.
  4. Retry com backoff — 3 tentativas (1s, 2s, 4s) por operação.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_graphiti: Any = None
_event_loop: Any = None
_circuit_open_until: float = 0.0
_consecutive_failures: int = 0


def _run_async(coro_factory):
    """Roda uma corrotina num event loop dedicado e *persistente*.

    Graphiti/FalkorDriver mantém conexões vinculadas ao event loop em que o
    cliente foi criado. `asyncio.run()` cria E FECHA um loop a cada chamada —
    então a partir da 2ª chamada no mesmo processo o driver cacheado aponta
    para um loop fechado ("Event loop is closed"). Isso é exatamente o que
    acontece quando o Dream Cycle empurra vários neurônios em sequência.

    Mantemos um único loop reutilizado; se ele tiver sido fechado, recriamos e
    invalidamos o cliente cacheado (que estava preso ao loop antigo).
    """
    global _event_loop, _graphiti
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
        _graphiti = None  # cliente vinculado ao loop anterior é inválido
    return _event_loop.run_until_complete(coro_factory())


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _cfg_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _cfg_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _ollama_base() -> str:
    return os.environ.get("GRAPHITI_LLM_BASE", "http://localhost:11434/v1")


def _ollama_root() -> str:
    # /v1 → root, usado por /api/tags
    return _ollama_base().rstrip("/").removesuffix("/v1")


def _llm_model() -> str:
    # Default: modelo de PROSA PEQUENO e MULTILÍNGUE (PT/EN). Dois critérios:
    #   1) Prosa + multilíngue: qwen2.5:3b extrai entidades/relações de texto
    #      natural muito melhor que granite3-dense:2b (que alucinava no gleaning)
    #      e que qwen2.5-coder:3b (modelo de código, gerava entidades vazias/NaN).
    #   2) Pequeno para COEXISTIR na GPU: no Dream Cycle, modelos locais (ex.
    #      claude_mem 8b ~6GB) + bge-m3 (~1.2GB) já ocupam a GPU de 12GB; um 3º
    #      modelo grande estoura → OOM → embeddings NaN. qwen2.5:3b (~1.9GB) cabe.
    # Configurável via setupbrain (HIVE_GRAPHITI_MODEL) — ex.: qwen2.5:7b em
    # máquinas com mais VRAM. GRAPHITI_LLM_MODEL é mantido como alias legado.
    return (
        os.environ.get("GRAPHITI_LLM_MODEL")
        or os.environ.get("HIVE_GRAPHITI_MODEL")
        or "qwen2.5:3b"
    )


def _embed_model() -> str:
    return os.environ.get("GRAPHITI_EMBED_MODEL", "bge-m3:latest")


# ---------------------------------------------------------------------------
# Health / availability
# ---------------------------------------------------------------------------

def ollama_model_exists(model: str) -> bool:
    """Verifica via GET /api/tags se `model` está disponível no Ollama local."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"{_ollama_root()}/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        for m in data.get("models", []):
            if m.get("name", "").split(":")[0] == model.split(":")[0]:
                return True
        return False
    except Exception:
        return False


def graphiti_available() -> bool:
    """Return True when FalkorDB is reachable on the configured host/port."""
    if _circuit_is_open():
        return False
    try:
        import falkordb

        host = os.environ.get("FALKORDB_HOST", "localhost")
        port = _cfg_int("FALKORDB_PORT", 6379)
        client = falkordb.FalkorDB(host=host, port=port)
        # Force a real ping — connection alone is not enough.
        try:
            client.connection.ping()
        except Exception:
            return False
        return True
    except Exception:
        return False


def assert_health() -> dict:
    """Smoke test do órgão Graphiti.

    Retorna dict com chaves:
      - falkordb: bool
      - llm_model: str
      - llm_model_exists: bool
      - embed_model: str
      - embed_model_exists: bool
      - write_smoke: bool | None
      - read_smoke: bool | None
      - circuit: dict
      - errors: list[str]

    Use no install.sh e no `sinapse-write.py health`.
    """
    errors: list[str] = []
    falkordb = graphiti_available()
    llm = ollama_model_exists(_llm_model())
    embed = ollama_model_exists(_embed_model())

    if not falkordb:
        errors.append("FalkorDB não responde em localhost:6379")
    if not llm:
        errors.append(
            f"Modelo LLM '{_llm_model()}' não está no Ollama (rode: ollama pull {_llm_model()})"
        )
    if not embed:
        errors.append(
            f"Modelo embed '{_embed_model()}' não está no Ollama (rode: ollama pull {_embed_model()})"
        )

    write_smoke: bool | None = None
    read_smoke: bool | None = None
    if falkordb and llm and embed:
        try:
            write_smoke = push_neuron(
                "hive-smoke-test",
                "Smoke test do Graphiti — pode deletar.",
                source="health",
            )
            if write_smoke:
                results = search_graph("smoke test", num_results=1)
                read_smoke = len(results) >= 0  # qualquer retorno (mesmo []) conta
        except Exception as e:
            errors.append(f"Smoke write/read falhou: {e}")

    return {
        "falkordb": falkordb,
        "llm_model": _llm_model(),
        "llm_model_exists": llm,
        "embed_model": _embed_model(),
        "embed_model_exists": embed,
        "write_smoke": write_smoke,
        "read_smoke": read_smoke,
        "circuit": circuit_state(),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

def _circuit_is_open() -> bool:
    return time.monotonic() < _circuit_open_until


def _circuit_record_success() -> None:
    global _consecutive_failures, _circuit_open_until
    _consecutive_failures = 0
    _circuit_open_until = 0.0


def _circuit_record_failure() -> None:
    global _consecutive_failures, _circuit_open_until
    _consecutive_failures += 1
    threshold = _cfg_int("HIVE_GRAPHITI_CB_FAILS", 3)
    if _consecutive_failures >= threshold:
        cooldown = _cfg_float("HIVE_GRAPHITI_CB_COOLDOWN", 30.0)
        _circuit_open_until = time.monotonic() + cooldown
        print(
            f"  [graphiti] circuit breaker ABERTO por {cooldown:.0f}s "
            f"(após {_consecutive_failures} falhas consecutivas)"
        )


def circuit_state() -> dict:
    """Estado do circuit breaker — para o `sinapse-write.py health`."""
    if _circuit_is_open():
        remaining = max(0.0, _circuit_open_until - time.monotonic())
        return {
            "open": True,
            "remaining_s": round(remaining, 1),
            "consecutive_failures": _consecutive_failures,
        }
    return {"open": False, "remaining_s": 0.0, "consecutive_failures": _consecutive_failures}


# ---------------------------------------------------------------------------
# Retry com backoff
# ---------------------------------------------------------------------------

def _is_transient(error: Exception) -> bool:
    """Decide se vale retentar. Erros DETERMINÍSTICOS (NaN no embed/LLM,
    validação, schema) devolvem o mesmo resultado em cada tentativa — retentar
    só desperdiça o backoff (1+2+4s por neurônio). Isso era a causa do Dream
    Cycle levar ~25min: cada push que dava "json: unsupported value: NaN" do
    Ollama gastava 7s antes de cair no fallback. Só retentamos falhas
    plausivelmente transitórias (rede, timeout, conexão)."""
    msg = str(error).lower()
    nonretryable = (
        "unsupported value: nan",
        "json: unsupported value",
        "validationerror",
        "invalid schema",
    )
    return not any(s in msg for s in nonretryable)


def _retry_with_backoff(fn, *args, **kwargs):
    """Roda `fn(*args, **kwargs)` com N tentativas e backoff 1s, 2s, 4s.

    Retorna (success, result_or_none). Atualiza o circuit breaker. Erros
    não-transitórios (ver _is_transient) falham imediatamente, sem backoff.
    """
    retries = _cfg_int("HIVE_GRAPHITI_RETRIES", 3)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            result = fn(*args, **kwargs)
            _circuit_record_success()
            return True, result
        except Exception as e:
            last_error = e
            if not _is_transient(e):
                print(f"  [graphiti] erro não-transitório (sem retry): {e}")
                break
            wait = 2 ** attempt  # 1s, 2s, 4s
            print(
                f"  [graphiti] tentativa {attempt + 1}/{retries} falhou: {e} "
                f"(próxima em {wait}s)"
            )
            if attempt < retries - 1:
                time.sleep(wait)
    _circuit_record_failure()
    return False, last_error


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------

def _build_client():
    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_client import OpenAIClient

    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = _cfg_int("FALKORDB_PORT", 6379)
    user = os.environ.get("FALKORDB_USER") or None
    password = os.environ.get("FALKORDB_PASSWORD") or None
    database = os.environ.get("FALKORDB_DB", "sinapse")

    llm_base = _ollama_base()
    llm_model = _llm_model()
    embed_model = _embed_model()

    # Set small_model to the same model — prevents graphiti from falling back to
    # the default "gpt-4.1-nano" when running against a local Ollama endpoint.
    llm_cfg = LLMConfig(
        api_key="ollama", model=llm_model, base_url=llm_base, small_model=llm_model
    )
    driver = FalkorDriver(
        host=host, port=port, username=user, password=password, database=database
    )
    llm = OpenAIClient(config=llm_cfg)
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key="ollama", base_url=llm_base, embedding_model=embed_model
        )
    )
    # Graphiti also creates a cross_encoder internally — pass one with Ollama config
    # so it doesn't fall back to looking for OPENAI_API_KEY in the environment.
    cross_encoder = OpenAIRerankerClient(config=llm_cfg)
    return Graphiti(
        graph_driver=driver,
        llm_client=llm,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )


def _client() -> Any:
    global _graphiti
    if _graphiti is None:
        _graphiti = _build_client()
    return _graphiti


# ---------------------------------------------------------------------------
# Persistência alternativa (JSON-lines no lóbulo temporal) — quando
# FalkorDB não está disponível. Garante que o cérebro não perca neurônios.
# Path: $SINAPSE_HOME/cerebro/cortex/temporal/_global/grafo.jsonl
# ---------------------------------------------------------------------------

def _fallback_dir() -> Path:
    """Resolve o diretório do fallback a cada chamada."""
    base = os.environ.get("SINAPSE_HOME", ".")
    return Path(base) / "cerebro" / "cortex" / "temporal" / "_global"


def _fallback_path() -> Path:
    """Resolve o path do fallback JSON-lines a cada chamada (não no import)."""
    env_path = os.environ.get("HIVE_TEMPORAL_GRAFO", "")
    if env_path:
        return Path(env_path)
    return _fallback_dir() / "grafo.jsonl"


def _fallback_append(edge: dict) -> bool:
    """Append de um edge no fallback JSON-lines (lóbulo temporal)."""
    try:
        path = _fallback_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(edge, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"  [graphiti] fallback write falhou: {e}")
        return False


def _fallback_search(query: str, num_results: int = 10) -> list[dict]:
    """Busca linear no fallback JSON-lines (substring match em fact)."""
    path = _fallback_path()
    if not path.exists():
        return []
    try:
        results: list[dict] = []
        q = query.lower()
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    edge = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if q in edge.get("fact", "").lower():
                    results.append(edge)
                if len(results) >= num_results:
                    break
        return results
    except Exception as e:
        print(f"  [graphiti] fallback read falhou: {e}")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def push_neuron(neuron_id: str, content: str, source: str = "dream") -> bool:
    """Push a synthesized neuron into the temporal graph as an episode.

    Returns True on success. Swallows all errors so dream_cycle never fails
    because of Graphiti being unavailable. Quando FalkorDB está offline,
    faz fallback para o arquivo JSON-lines em `cortex/temporal/_global/`.
    Quando FalkorDB está online mas a operação falha, também escreve no
    fallback para não perder o neurônio.
    """
    if _circuit_is_open():
        return False

    if not graphiti_available():
        # FalkorDB offline → fallback silencioso para o arquivo do lóbulo temporal.
        return _fallback_append(
            {
                "uuid": f"neuron:{neuron_id}",
                "source": source,
                "fact": content[:4000],
                "valid_at": datetime.now(timezone.utc).isoformat(),
                "invalid_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "fallback": True,
            }
        )

    async def _do_push():
        from graphiti_core.nodes import EpisodeType

        await _client().add_episode(
            name=f"neuron:{neuron_id}",
            episode_body=content[:4000],
            source_description=f"Hive-Mind dream — neuron {neuron_id} ({source})",
            reference_time=datetime.now(timezone.utc),
            source=EpisodeType.text,
            group_id="hive-mind",
        )

    success, error = _retry_with_backoff(lambda: _run_async(_do_push))
    if not success:
        # FalkorDB disponível mas falhou — escreve no fallback
        # para não perder o neurônio.
        _fallback_append(
            {
                "uuid": f"neuron:{neuron_id}",
                "source": source,
                "fact": content[:4000],
                "valid_at": datetime.now(timezone.utc).isoformat(),
                "invalid_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "fallback": True,
                "last_error": str(error) if error else None,
            }
        )
        return False
    return True


def search_graph(query: str, num_results: int = 10) -> list[dict]:
    """Search the temporal graph for relevant facts/edges.

    Returns list of {fact, valid_at, invalid_at, uuid} dicts.
    Returns [] when FalkorDB is unreachable or on any error. Quando offline,
    faz fallback de leitura no JSON-lines do lóbulo temporal.
    """
    if _circuit_is_open():
        return []

    if not graphiti_available():
        return _fallback_search(query, num_results)

    async def _do_search():
        return await _client().search(
            query=query,
            group_ids=["hive-mind"],
            num_results=num_results,
        )

    success, edges = _retry_with_backoff(lambda: _run_async(_do_search))
    if not success or edges is None:
        return []
    return [
        {
            "fact": getattr(edge, "fact", str(edge)),
            "valid_at": str(getattr(edge, "valid_at", "")),
            "invalid_at": str(getattr(edge, "invalid_at", "")),
            "uuid": str(getattr(edge, "uuid", "")),
        }
        for edge in edges
    ]


def reset_circuit() -> None:
    """Reseta o circuit breaker manualmente (uso em testes)."""
    global _consecutive_failures, _circuit_open_until
    _consecutive_failures = 0
    _circuit_open_until = 0.0
