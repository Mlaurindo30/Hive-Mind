# Roadmap de Implementação — Hive-Mind Integrações
**Data:** 2026-06-21 | **Baseado em:** docs/09-integration-study.md

> Documento de engenharia. Cada task tem: arquivo exato, linha, o que muda, o que conecta.
> Ordem por ROI decrescente. Nenhuma fase depende da próxima — podem rodar em paralelo.

---

## Índice de Fases

| Fase | Nome | Esforço | Impacto | Pré-requisito |
|------|------|---------|---------|---------------|
| [P0](#fase-p0--embeddings-100-local-ollama-bge-m3--concluído) | Embeddings 100% Local | ✅ DONE | Alto | — |
| [P1](#fase-p1--screenpipe-substitui-deep-portal--concluído) | Screenpipe → Deep Portal | ✅ DONE | Alto | Screenpipe instalado* |
| [P2](#fase-p2--graphiti--falkordb-semântica-temporal) | Graphiti + FalkorDB | Semanas | Alto | FalkorDB Docker |
| [P3](#fase-p3--langfuse-self-hosted--observabilidade) | Langfuse Observabilidade | Dias | Alto | Docker |
| [P4](#fase-p4--lightrag-no-dream-cycle) | LightRAG no Dream Cycle | Dias | Alto | Phase P0 |
| [P5](#fase-p5--cr-sqlite--sync-multi-dispositivo) | CR-SQLite Multi-Device | Dias | Alto | nenhum |
| [P6](#fase-p6--a-mem-link-evolution-no-grafo) | A-MEM Link Evolution | Dias | Médio | Phase P2 |
| [P7](#fase-p7--mcp-streamable-http-spec-2025-03-26) | MCP Streamable HTTP | Semanas | Médio | Nenhum |

---

## Estado Atual do Código

```
core/
  database.py       ← EMBED_BACKEND=ollama, bge-m3:latest 1024d via OllamaEmbedder ✅P0
  indexing.py       ← index_neuron_ids() usa get_embedder() (agnóstico ao backend) ✅P0
  hnsw_index.py     ← HNSW_DIM=1024 (env-var configurável) ✅P0
  umc_schema.sql    ← search_vec FLOAT[1024] ✅P0

scripts/
  dream/
    dream_cycle.py  ← ETL 806 linhas: Distiller→Validator→Router→Síntese
  services/
    sinapse-mcp.py  ← MCP stdio, 450 linhas, _capture_screen() chama visual_capture.py
  capture/
    capture_core.py ← SeenStore SQLite WAL ✅ (migrado 2026-06-21)
    parsers/        ← 11 parsers: antigravity, codex, copilot, hermes, kilo...
  setup/
    migrate_embed_dim.py ← script one-shot para re-indexação ✅P0

plugins/
  sqlite-vec-worker/worker.py ← EMBED_BACKEND=ollama, DIMENSIONS=1024 ✅P0

integrations/
  neural-memory/    ← graphiti_adapter.py já existe aqui (parcialmente implementado)

requirements.txt    ← fastembed (legado, fallback), sqlite-vec, duckdb, mss
```

---

## Fase P0 — Embeddings 100% Local (Ollama bge-m3) ✅ CONCLUÍDO

**Objetivo:** eliminar `fastembed + all-MiniLM-L6-v2 (384d)` e migrar para modelo multilingual PT+EN de maior qualidade rodando 100% local via Ollama.
**Status:** IMPLEMENTADO | **Commits:** `93db445`, `f087279` | **Data:** 2026-06-21

### Bloqueio resolvido

`sqlite-lembed` (plano original) é incompatível com Python 3.12+ — a API `sqlite3_result_subtype()` foi restringida e gera `OperationalError: misuse of sqlite3_result_subtype()`. Não é limitação do Python 3.14 especificamente; afeta 3.12 em diante. Solução adotada: Ollama HTTP API, que já estava rodando localmente.

### Modelo selecionado: `bge-m3:latest`

| Modelo avaliado | Dim | Warm latency | PT support | Decisão |
|---|---|---|---|---|
| all-MiniLM-L6-v2 (fastembed) | 384 | 49ms | Fraca | Descartado |
| nomic-embed-text v1.5 | 768 | 28ms | Moderada | Descartado |
| nomic-embed-text-v2-moe | 768 | 625ms | Boa | Descartado (lento) |
| **bge-m3:latest** | **1024** | **91ms** | **Excelente** | **✅ Adotado** |

`bge-m3` (BAAI/bge-m3): MTEB multilingual #1 2024, treinado em 100+ idiomas incluindo PT-BR.

### O que foi implementado

#### Task P0.1 — Backend configurável (`core/database.py`)

```python
# Env vars para controle:
EMBED_BACKEND = os.environ.get("EMBED_BACKEND", "ollama")       # "ollama" | "fastembed"
OLLAMA_BASE   = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3:latest")

class OllamaEmbedder:
    """HTTP client Ollama /api/embeddings — interface compatível com fastembed."""
    def embed(self, texts):  # yields list[float] para cada texto

def get_embedder():  # retorna OllamaEmbedder ou TextEmbedding conforme EMBED_BACKEND
def embed_text(text: str) -> list:  # retorna list() — funciona com ambos os backends
```

#### Task P0.2 — Dimensão 384 → 1024 (5 arquivos)

| Arquivo | Mudança |
|---|---|
| `core/hnsw_index.py:25` | `HNSW_DIM` default `384` → `1024` |
| `core/umc_schema.sql:92` | `FLOAT[384]` → `FLOAT[1024]` em `search_vec` |
| `scripts/setup/setup_umc.py:62,66` | test vector e probe table `384` → `1024` |
| `scripts/setup/migrate_to_uuid.py:172` | `FLOAT[384]` → `FLOAT[1024]` |
| `plugins/sqlite-vec-worker/worker.py:45` | `VEC_EMBED_DIM` default `384` → `1024` |

#### Task P0.3 — Worker atualizado (`plugins/sqlite-vec-worker/worker.py`)

```python
EMBED_BACKEND = os.environ.get("EMBED_BACKEND", "ollama")         # ollama | fastembed
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3:latest")
DIMENSIONS = int(os.environ.get("VEC_EMBED_DIM", "1024"))
# fastembed e numpy agora opcionais (try/except)
```

#### Task P0.4 — Migração do banco (`scripts/setup/migrate_embed_dim.py`)

Script one-shot reutilizável:
1. Drop + recreate `search_vec` com nova dimensão
2. Re-indexa todos os neurônios via Ollama (incremental — pula já indexados)
3. Reseta HNSW index em disco

Resultado: 3639/3642 neurônios re-indexados em 407s (8.9/s). 3 falhas por HTTP 500 do Ollama em conteúdo problemático (0.1%).

```bash
# Para re-executar migração (ex: após novos neurônios ou mudança de modelo):
python scripts/setup/migrate_embed_dim.py
```

#### Task P0.5 — Testes (`tests/unit/test_p0_embedding.py`)

10 testes cobrindo:
- `embed_text()` retorna lista de floats com dim consistente
- Determinismo (mesmo texto → mesmo vetor)
- Seleção de backend via `EMBED_BACKEND` env var
- `OllamaEmbedder` live (skip se Ollama não estiver rodando)
- Testes bge-m3 live: dim=1024 confirmado

```bash
pytest tests/unit/test_p0_embedding.py -v  # 10/10 passando
pytest tests/unit/ -q                       # 434/434 passando
```

### Rollback (se necessário)

```bash
export EMBED_BACKEND=fastembed
export HNSW_DIM=384
# Re-executar migrate_embed_dim.py com modelo fastembed carregado
```

### Notas para sqlite-lembed (futuro)

Quando `sqlite-lembed` resolver o Python 3.12+ bug (`misuse of sqlite3_result_subtype()`), a migração de volta é simples: `EMBED_BACKEND=lembed` + adicionar `_init_lembed()` em `get_connection()`. A interface `embed_text()` já é agnóstica ao backend.

---

## Fase P1 — Screenpipe Substitui Deep Portal ✅ CONCLUÍDO

**Objetivo:** deprecar `mss + LLM Vision` e consumir Screenpipe via REST API local.
**Status:** IMPLEMENTADO | **Commit:** `9597ef5` | **Data:** 2026-06-21
**Ativação:** instalar Screenpipe em screenpipe.dev — código já está integrado.

### O que foi implementado

| Arquivo | Mudança |
|---|---|
| `scripts/capture/parsers/screenpipe.py` (novo) | Cliente REST completo: `screenpipe_alive()`, `fetch_recent_ocr()`, `fetch_recent_audio()`, `capture_screenshot()` |
| `scripts/capture/capture_adapters.py` | `_parse_screenpipe()` adapter + entrada `"screenpipe"` em ADAPTERS |
| `scripts/services/sinapse-mcp.py` | `_capture_screen()` tenta Screenpipe REST primeiro, fallback para `visual_capture.py` |
| `tests/unit/test_screenpipe_parser.py` | 10 testes offline + 3 live (skip automático quando Screenpipe não está rodando) |

### Para ativar

```bash
# Instalar Screenpipe (binário Rust, ~50MB)
curl -sSL https://get.screenpi.pe | sh
# ou: cargo install screenpipe

# Iniciar
screenpipe &

# Verificar
curl http://localhost:3030/health  # → {"status": "ok", ...}

# Os 3 testes live vão passar automaticamente
pytest tests/unit/test_screenpipe_parser.py -v
```

Variáveis de ambiente:
- `SCREENPIPE_BASE` (default: `http://localhost:3030`)
- `SCREENPIPE_TIMEOUT` (default: `5` segundos)

---

## Fase P1 — Screenpipe (plano original — substituído pela implementação acima)

**Objetivo:** deprecar `mss + LLM Vision` e consumir Screenpipe via REST API local.
**Esforço:** 1-2 dias | **Risco:** Baixo (additive, fallback mantido) | **Pré-req:** Screenpipe instalado

### Por que

Hoje `sinapse-mcp.py:253-269` chama `scripts/visual_capture.py` via subprocess. Screenpipe já roda localmente em `localhost:3030`, já tem SQLite+FTS5, e seu schema pode ser lido via `ATTACH DATABASE`. Ganho: compressão 6x, Whisper local, event-driven (sem polling).

### Task P1.1 — Instalar Screenpipe

```bash
# Screenpipe (Rust binary — instalar via script oficial)
curl -sSL https://raw.githubusercontent.com/screenpipe/screenpipe/main/install.sh | bash

# Ou via cargo:
cargo install screenpipe

# Verificar que roda:
screenpipe &
curl http://localhost:3030/health
```

### Task P1.2 — Criar `scripts/capture/parsers/screenpipe.py`

**Arquivo NOVO:** `scripts/capture/parsers/screenpipe.py`

```python
"""Parser Screenpipe — lê OCR/áudio via REST API localhost:3030."""
from __future__ import annotations
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

SCREENPIPE_BASE = "http://localhost:3030"


def _api(path: str, params: dict = None) -> dict:
    url = f"{SCREENPIPE_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}


def screenpipe_alive() -> bool:
    return bool(_api("/health").get("status") == "ok")


def fetch_recent_ocr(since_minutes: int = 60, limit: int = 50) -> list[dict]:
    """Retorna chunks OCR recentes do Screenpipe como sessões para o pipeline."""
    start_time = (datetime.utcnow() - timedelta(minutes=since_minutes)).isoformat() + "Z"
    data = _api("/search", {
        "content_type": "ocr",
        "start_time": start_time,
        "limit": limit,
    })
    sessions = []
    for item in data.get("data", []):
        content = item.get("content", {})
        text = content.get("text", "").strip()
        if not text:
            continue
        frame_id = str(item.get("content_id", item.get("id", "")))
        app = content.get("app_name", "unknown")
        sessions.append({
            "sid": f"screenpipe:{frame_id}",
            "prompt": f"[{app}] {text[:120]}",
            "turns": [{
                "tool_name": "ScreenCapture",
                "tool_input": {"app": app, "text": text[:500]},
                "tool_response": text,
            }],
            "last": text[:200],
        })
    return sessions


def fetch_recent_audio(since_minutes: int = 60, limit: int = 20) -> list[dict]:
    """Retorna transcrições Whisper recentes do Screenpipe."""
    start_time = (datetime.utcnow() - timedelta(minutes=since_minutes)).isoformat() + "Z"
    data = _api("/search", {
        "content_type": "audio",
        "start_time": start_time,
        "limit": limit,
    })
    sessions = []
    for item in data.get("data", []):
        content = item.get("content", {})
        text = content.get("transcription", "").strip()
        if not text:
            continue
        chunk_id = str(item.get("content_id", item.get("id", "")))
        sessions.append({
            "sid": f"screenpipe:audio:{chunk_id}",
            "prompt": f"[áudio] {text[:120]}",
            "turns": [{
                "tool_name": "AudioTranscription",
                "tool_input": {"transcription": text[:500]},
                "tool_response": text,
            }],
            "last": text[:200],
        })
    return sessions
```

### Task P1.3 — Atualizar `sinapse-mcp.py` — `_capture_screen()`

**Arquivo:** `scripts/services/sinapse-mcp.py`
**Função:** `_capture_screen()` — **linhas 253-269**

```python
# ANTES:
def _capture_screen(description=""):
    """Captura a tela chamando o script visual_capture.py via subprocesso."""
    import subprocess
    import os
    ...
    capture_script = os.path.join(scripts_dir, "visual_capture.py")
    ...
```

```python
# DEPOIS:
def _capture_screen(description=""):
    """Captura tela via Screenpipe (REST) com fallback para visual_capture.py."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from scripts.capture.parsers.screenpipe import screenpipe_alive, _api
        if screenpipe_alive():
            # Solicitar screenshot via Screenpipe
            import json
            import urllib.request
            req = urllib.request.Request(
                "http://localhost:3030/screenshot",
                data=json.dumps({"description": description}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode())
                    path = data.get("path", "")
                    if path:
                        return {"path": path, "description": description, "source": "screenpipe"}
            except Exception:
                pass
    except ImportError:
        pass
    # Fallback: visual_capture.py legado
    import subprocess
    import os
    scripts_dir = os.path.join(os.environ.get("SINAPSE_HOME", ""), "scripts")
    capture_script = os.path.join(scripts_dir, "visual_capture.py")
    if not os.path.exists(capture_script):
        return {"error": "visual_capture.py não encontrado e Screenpipe indisponível"}
    result = subprocess.run(
        [sys.executable, capture_script, "--description", description],
        capture_output=True, text=True, timeout=30
    )
    path = result.stdout.strip()
    return {"path": path, "description": description, "source": "visual_capture"}
```

### Task P1.4 — Adicionar adapter Screenpipe ao pipeline de captura

**Arquivo:** `scripts/capture/capture_adapters.py`
**Onde:** no dict `ADAPTERS`, adicionar entrada:

```python
"screenpipe": {
    "owner": "timer",           # roda via capture-tailer periodicamente
    "mode": "reparse",
    "parser": _parse_screenpipe,
    "sources": [],              # sem arquivo local — usa REST
    "watch": [],
},
```

**Adicionar função no mesmo arquivo:**
```python
def _parse_screenpipe(_source=None):
    """Adapter que lê Screenpipe via REST em vez de arquivo."""
    try:
        from scripts.capture.parsers.screenpipe import fetch_recent_ocr, fetch_recent_audio
        return fetch_recent_ocr(since_minutes=60) + fetch_recent_audio(since_minutes=60)
    except Exception:
        return []
```

### Task P1.5 — Verificação

```bash
# Testar parser manualmente
python3 -c "
from scripts.capture.parsers.screenpipe import screenpipe_alive, fetch_recent_ocr
print('Screenpipe alive:', screenpipe_alive())
sessions = fetch_recent_ocr(since_minutes=5)
print(f'{len(sessions)} sessões OCR recentes')
"
```

---

## Fase P2 — Graphiti + FalkorDB: Semântica Temporal

**Objetivo:** adicionar janelas de validade de fatos ao grafo neurônios/sinapses.
**Esforço:** 1-2 semanas | **Risco:** Médio | **Pré-req:** FalkorDB Docker

> **Nota:** `integrations/neural-memory/` já tem `graphiti_adapter.py` parcialmente implementado. Esta fase conecta aquele adapter ao Dream Cycle e ao MCP server.

### Task P2.1 — FalkorDB local

```bash
# FalkorDB (open-source, local, compatível Bolt protocol)
docker run -p 6379:6379 -p 7474:7474 -it --rm falkordb/falkordb:latest

# Testar conexão:
python3 -c "import falkordb; db = falkordb.FalkorDB(); print('FalkorDB OK')"
```

**`requirements.txt`** — adicionar:
```
graphiti-core>=0.3.0
falkordb>=1.0.0
```

### Task P2.2 — Criar `core/graphiti_client.py`

**Arquivo NOVO:** `core/graphiti_client.py`

```python
"""Cliente singleton para Graphiti temporal knowledge graph."""
from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime

_graphiti = None


def get_graphiti():
    """Retorna instância singleton do cliente Graphiti (lazy init)."""
    global _graphiti
    if _graphiti is not None:
        return _graphiti
    try:
        from graphiti_core import Graphiti
    except ImportError:
        return None
    uri = os.environ.get("GRAPHITI_URI", "bolt://localhost:7474")
    user = os.environ.get("GRAPHITI_USER", "")
    password = os.environ.get("GRAPHITI_PASSWORD", "")
    try:
        _graphiti = Graphiti(uri, user, password)
        return _graphiti
    except Exception as e:
        print(f"  ⚠ Graphiti indisponível: {e}")
        return None


async def add_episode(session_id: str, content: str, source: str = "dream_cycle") -> bool:
    """Insere um episódio consolidado no grafo temporal."""
    from graphiti_core.nodes import EpisodeType
    g = get_graphiti()
    if g is None:
        return False
    try:
        await g.add_episode(
            name=f"{source}:{session_id}",
            episode_body=content,
            source=EpisodeType.text,
            reference_time=datetime.now(),
        )
        return True
    except Exception as e:
        print(f"  ⚠ Graphiti add_episode falhou: {e}")
        return False


async def temporal_search(query: str, num_results: int = 10) -> list[dict]:
    """Busca no grafo com semântica temporal."""
    g = get_graphiti()
    if g is None:
        return []
    try:
        results = await g.search(query, num_results=num_results)
        return [
            {
                "fact": r.fact,
                "valid_from": str(r.valid_at) if hasattr(r, "valid_at") else None,
                "invalid_from": str(r.invalid_at) if hasattr(r, "invalid_at") else None,
                "score": getattr(r, "score", 0),
            }
            for r in results
        ]
    except Exception as e:
        print(f"  ⚠ Graphiti search falhou: {e}")
        return []
```

### Task P2.3 — Conectar ao Dream Cycle

**Arquivo:** `scripts/dream/dream_cycle.py`
**Onde:** após a função de síntese (após Router aprovar) — adicionar chamada async:

```python
# Adicionar no topo do arquivo (imports):
import asyncio

# Adicionar função helper perto do fim do arquivo (antes de main()):
def _push_to_graphiti(session_id: str, synthesis_text: str) -> None:
    """Envia memória consolidada ao Graphiti de forma não-bloqueante."""
    try:
        from core.graphiti_client import add_episode
        asyncio.get_event_loop().run_until_complete(
            add_episode(session_id, synthesis_text, source="dream_cycle")
        )
    except Exception as e:
        print(f"  ⚠ Graphiti push ignorado: {e}")
```

**Onde chamar:** na função que finaliza cada ciclo de síntese (procurar por `archived = 1` ou `UPDATE observations SET archived`):

```python
# Logo após o UPDATE que arquiva a observação processada:
_push_to_graphiti(str(obs_id), synthesis_result)
```

### Task P2.4 — Adicionar ferramenta MCP `sinapse_temporal_graph_search`

**Arquivo:** `scripts/services/sinapse-mcp.py`
**Onde:** na lista `TOOLS` (array de dicts de ferramentas) — adicionar entrada:

```python
{
    "name": "sinapse_temporal_graph_search",
    "description": "Busca no grafo temporal Graphiti — retorna fatos com janela de validade (valid_from/invalid_from). Use para perguntas como 'o que era verdade sobre X em tal data'.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Query de busca semântica"},
            "num_results": {"type": "integer", "default": 10}
        },
        "required": ["query"]
    }
},
```

**No dispatcher** (`handle_request` ou equivalente) — adicionar:
```python
"sinapse_temporal_graph_search": lambda args: _temporal_graph_search(
    args["query"], args.get("num_results", 10)
),
```

**Adicionar função:**
```python
def _temporal_graph_search(query: str, num_results: int = 10) -> dict:
    import asyncio
    try:
        from core.graphiti_client import temporal_search
        results = asyncio.get_event_loop().run_until_complete(
            temporal_search(query, num_results)
        )
        return {"results": results, "count": len(results)}
    except Exception as e:
        return {"error": str(e), "results": []}
```

### Task P2.5 — Variáveis de ambiente

**Arquivo:** `.env` (gitignored) — adicionar:
```bash
GRAPHITI_URI=bolt://localhost:7474
GRAPHITI_USER=
GRAPHITI_PASSWORD=
```

---

## Fase P3 — Langfuse Self-Hosted: Observabilidade

**Objetivo:** tracing OpenTelemetry do Dream Cycle e do pipeline de captura.
**Esforço:** 1-2 dias | **Risco:** Baixo (opt-in via env var)

### Task P3.1 — Deploy Langfuse

```bash
# docker-compose.langfuse.yml na raiz do projeto
cat > docker-compose.langfuse.yml << 'EOF'
version: "3"
services:
  langfuse:
    image: langfuse/langfuse:latest
    ports:
      - "3100:3000"
    environment:
      DATABASE_URL: "file:/data/langfuse.db"
      NEXTAUTH_SECRET: "local-secret-change-me"
      NEXTAUTH_URL: "http://localhost:3100"
      SALT: "local-salt"
    volumes:
      - ./claude-mem/data/langfuse:/data
EOF

docker-compose -f docker-compose.langfuse.yml up -d
# Acesso: http://localhost:3100
```

**`requirements.txt`** — adicionar:
```
opentelemetry-sdk>=1.20
opentelemetry-exporter-otlp-proto-http>=1.20
```

### Task P3.2 — Criar `core/telemetry.py`

**Arquivo NOVO:** `core/telemetry.py`

```python
"""Telemetria opcional via OpenTelemetry → Langfuse self-hosted."""
from __future__ import annotations
import os
import base64
from contextlib import contextmanager

_tracer = None
_enabled = False


def _langfuse_headers() -> dict:
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
    if not pk or not sk:
        return {}
    token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def init_telemetry() -> bool:
    """Inicializa OTEL se LANGFUSE_PUBLIC_KEY estiver definido. Idempotente."""
    global _tracer, _enabled
    if _tracer is not None:
        return _enabled
    headers = _langfuse_headers()
    if not headers:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = os.environ.get("LANGFUSE_HOST", "http://localhost:3100")
        exporter = OTLPSpanExporter(
            endpoint=f"{endpoint}/api/public/otel/v1/traces",
            headers=headers,
        )
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("hive-mind")
        _enabled = True
        return True
    except ImportError:
        return False


@contextmanager
def span(name: str, attributes: dict = None):
    """Context manager para criar um span OTEL. No-op se telemetria desabilitada."""
    if not _enabled or _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, str(v))
        yield s
```

### Task P3.3 — Instrumentar Dream Cycle

**Arquivo:** `scripts/dream/dream_cycle.py`
**Onde:** no início de `main()` ou da função de ciclo principal:

```python
# Adicionar import no topo:
from core.telemetry import init_telemetry, span

# No início de cada ciclo:
init_telemetry()

# Envolver etapas principais com spans:
with span("dream.distiller", {"obs_count": len(observations)}):
    distiller_result = run_distiller(observations)

with span("dream.validator", {"distiller_output": str(distiller_result)[:200]}):
    validator_result = run_validator(distiller_result)

with span("dream.synthesis", {"session_id": session_id}):
    synthesis = run_synthesis(validator_result)
```

### Task P3.4 — Instrumentar capture_core

**Arquivo:** `scripts/capture/capture_core.py`
**Função:** `ingest()` — envolver emissão com span:

```python
# Adicionar no topo de ingest():
from core.telemetry import span  # lazy import para não quebrar se core/ não no path

# Envolver o loop de turns:
with span("capture.ingest", {"platform": platform, "sid": sid}):
    # ... código existente do loop de turns ...
    pass
```

### Task P3.5 — Variáveis de ambiente

**Arquivo:** `.env`:
```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...      # gerado no dashboard http://localhost:3100
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3100
```

---

## Fase P4 — LightRAG no Dream Cycle

**Objetivo:** indexação automática de entidades/relações no corpus consolidado.
**Esforço:** 2-3 dias | **Pré-req:** Phase P0 recomendado

### Task P4.1 — Instalar LightRAG

```bash
pip install lightrag-hku
```

**`requirements.txt`** — adicionar:
```
lightrag-hku>=1.0.0
```

### Task P4.2 — Criar `core/lightrag_index.py`

**Arquivo NOVO:** `core/lightrag_index.py`

```python
"""LightRAG: indexação de entidades/relações pós Dream Cycle."""
from __future__ import annotations
import os
from pathlib import Path

_rag = None
_WORKING_DIR = str(Path(os.environ.get("SINAPSE_HOME", ".")) / "claude-mem" / "data" / "lightrag")


def get_rag():
    global _rag
    if _rag is not None:
        return _rag
    try:
        from lightrag import LightRAG, QueryParam
        from lightrag.llm.openai import openai_complete_if_cache, openai_embed
        import asyncio

        async def _llm_func(prompt, **kwargs):
            from core.llm_client import call_llm
            return await asyncio.get_event_loop().run_in_executor(
                None, call_llm, prompt
            )

        Path(_WORKING_DIR).mkdir(parents=True, exist_ok=True)
        _rag = LightRAG(
            working_dir=_WORKING_DIR,
            llm_model_func=_llm_func,
        )
        return _rag
    except ImportError:
        return None


async def index_memory(text: str, metadata: dict = None) -> bool:
    """Indexa texto consolidado no grafo LightRAG."""
    rag = get_rag()
    if rag is None:
        return False
    try:
        await rag.ainsert(text)
        return True
    except Exception as e:
        print(f"  ⚠ LightRAG index falhou: {e}")
        return False


async def query_rag(question: str, mode: str = "hybrid") -> str:
    """Consulta o grafo LightRAG com modo hybrid (grafo + vetor)."""
    from lightrag import QueryParam
    rag = get_rag()
    if rag is None:
        return ""
    try:
        return await rag.aquery(question, param=QueryParam(mode=mode))
    except Exception as e:
        print(f"  ⚠ LightRAG query falhou: {e}")
        return ""
```

### Task P4.3 — Conectar ao Dream Cycle

**Arquivo:** `scripts/dream/dream_cycle.py`
**Onde:** mesma área onde chama `_push_to_graphiti()` — adicionar em paralelo:

```python
# Adicionar helper (junto com _push_to_graphiti):
def _index_in_lightrag(synthesis_text: str) -> None:
    """Indexa memória consolidada no LightRAG de forma não-bloqueante."""
    try:
        from core.lightrag_index import index_memory
        asyncio.get_event_loop().run_until_complete(index_memory(synthesis_text))
    except Exception as e:
        print(f"  ⚠ LightRAG push ignorado: {e}")

# Chamar após arquivar observação:
_push_to_graphiti(str(obs_id), synthesis_result)   # Graphiti (fase P2)
_index_in_lightrag(synthesis_result)               # LightRAG (fase P4)
```

### Task P4.4 — Adicionar ferramenta MCP `sinapse_rag_query`

**Arquivo:** `scripts/services/sinapse-mcp.py`

```python
# Na lista de TOOLS:
{
    "name": "sinapse_rag_query",
    "description": "Consulta o índice LightRAG (grafo + vetor) sobre memórias consolidadas. Melhor para perguntas multi-hop que FTS5 não resolve.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "mode": {"type": "string", "enum": ["naive", "local", "global", "hybrid"], "default": "hybrid"}
        },
        "required": ["question"]
    }
},

# No dispatcher:
"sinapse_rag_query": lambda args: _rag_query(args["question"], args.get("mode", "hybrid")),
```

```python
def _rag_query(question: str, mode: str = "hybrid") -> dict:
    import asyncio
    try:
        from core.lightrag_index import query_rag
        result = asyncio.get_event_loop().run_until_complete(query_rag(question, mode))
        return {"answer": result, "mode": mode}
    except Exception as e:
        return {"error": str(e)}
```

---

## Fase P5 — CR-SQLite: Sync Multi-Dispositivo

**Objetivo:** `hive_mind.db` replicável entre dispositivos sem conflitos.
**Esforço:** 2-3 dias | **Risco:** Médio (schema change) | **Pré-req:** backup antes

### Task P5.1 — Instalar CR-SQLite

```bash
pip install crsqlite
# Verificar extensão:
python3 -c "import crsqlite; print('CR-SQLite:', crsqlite.__version__)"
```

**`requirements.txt`**:
```
crsqlite>=0.16.0
```

### Task P5.2 — Criar `core/crdt_sync.py`

**Arquivo NOVO:** `core/crdt_sync.py`

```python
"""CR-SQLite: sincronização CRDT para hive_mind.db."""
from __future__ import annotations
import sqlite3
import os
from pathlib import Path

# Tabelas que participam da sincronização CRDT.
# NÃO incluir capture-state.db — ele é local-only.
CRDT_TABLES = ["neurons", "synapses", "observations", "visual_memories"]

_crdt_initialized = False


def enable_crdt(conn: sqlite3.Connection) -> bool:
    """Habilita CR-SQLite na conexão e converte tabelas para CRR."""
    global _crdt_initialized
    if _crdt_initialized:
        return True
    try:
        import crsqlite
        conn.enable_load_extension(True)
        crsqlite.load(conn)
        for table in CRDT_TABLES:
            try:
                conn.execute(f"SELECT crsql_as_crr('{table}')")
            except sqlite3.OperationalError:
                pass  # tabela já é CRR ou não existe ainda
        conn.commit()
        _crdt_initialized = True
        return True
    except ImportError:
        return False


def get_changes_since(conn: sqlite3.Connection, db_version: int = 0) -> list[tuple]:
    """Retorna mudanças desde a versão `db_version` para transmissão."""
    return conn.execute(
        "SELECT * FROM crsql_changes WHERE db_version > ?", (db_version,)
    ).fetchall()


def apply_changes(conn: sqlite3.Connection, changes: list[tuple]) -> int:
    """Aplica mudanças recebidas de outra instância."""
    applied = 0
    for change in changes:
        try:
            conn.execute(
                "INSERT INTO crsql_changes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                change
            )
            applied += 1
        except sqlite3.Error:
            pass
    conn.execute("SELECT crsql_commit_alter('neurons')")  # notifica merge
    conn.commit()
    return applied


def current_db_version(conn: sqlite3.Connection) -> int:
    """Retorna a versão atual do DB para uso em sincronização incremental."""
    row = conn.execute("SELECT crsql_db_version()").fetchone()
    return row[0] if row else 0
```

### Task P5.3 — Integrar em `core/database.py`

**Arquivo:** `core/database.py`
**Função:** `get_connection()` — adicionar ao final (antes do `return conn`):

```python
    # CR-SQLite: habilitar se disponível (no-op se já inicializado)
    if os.environ.get("HIVE_CRDT_SYNC", "").lower() == "true":
        from core.crdt_sync import enable_crdt
        enable_crdt(conn)
    return conn
```

### Task P5.4 — Criar `scripts/services/sinapse-sync.py`

**Arquivo NOVO:** `scripts/services/sinapse-sync.py`

```python
#!/usr/bin/env python3
"""Sincronização CRDT entre instâncias Hive-Mind.

Uso:
  sinapse-sync.py --export > changes.bin          # exportar mudanças
  sinapse-sync.py --import changes.bin            # importar mudanças
  sinapse-sync.py --push http://remote:37702      # push direto via REST
  sinapse-sync.py --pull http://remote:37702      # pull direto via REST
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

SINAPSE_HOME = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SINAPSE_HOME))

from core.database import get_connection, DB_PATH
from core.crdt_sync import get_changes_since, apply_changes, current_db_version


def cmd_export(since_version: int = 0):
    conn = get_connection()
    changes = get_changes_since(conn, since_version)
    data = {"version": current_db_version(conn), "changes": [list(c) for c in changes]}
    print(json.dumps(data))


def cmd_import(path: str):
    data = json.loads(Path(path).read_text())
    conn = get_connection()
    applied = apply_changes(conn, [tuple(c) for c in data["changes"]])
    print(f"Aplicadas {applied} mudanças (versão remota: {data['version']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--import", dest="import_file")
    ap.add_argument("--since", type=int, default=0)
    args = ap.parse_args()
    if args.export:
        cmd_export(args.since)
    elif args.import_file:
        cmd_import(args.import_file)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
```

### Task P5.5 — Variáveis de ambiente

**`.env`**:
```bash
HIVE_CRDT_SYNC=true        # habilita CR-SQLite em get_connection()
```

---

## Fase P6 — A-MEM Link Evolution no Grafo

**Objetivo:** links entre neurônios evoluem automaticamente quando nova memória é inserida.
**Esforço:** 2 dias | **Pré-req:** Phase P2 (Graphiti) recomendado

### Task P6.1 — Instalar A-MEM

```bash
pip install amem
# ou diretamente do repo:
pip install git+https://github.com/agiresearch/A-mem.git
```

### Task P6.2 — Criar `core/amem_linker.py`

**Arquivo NOVO:** `core/amem_linker.py`

```python
"""A-MEM: evolução automática de links entre neurônios."""
from __future__ import annotations
import os

_memory_system = None


def get_amem():
    global _memory_system
    if _memory_system is not None:
        return _memory_system
    try:
        from amem import AgenticMemory
        _memory_system = AgenticMemory(
            llm_backend=os.environ.get("HIVE_DREAMER_PROVIDER", "openai"),
            model=os.environ.get("HIVE_DREAMER_MODEL", "gpt-4o-mini"),
        )
        return _memory_system
    except ImportError:
        return None


def add_and_evolve(neuron_id: str, content: str, conn) -> list[dict]:
    """Adiciona memória ao A-MEM e retorna links sugeridos para o grafo Hive-Mind."""
    mem = get_amem()
    if mem is None:
        return []
    try:
        # A-MEM analisa o corpus e gera links com memórias relacionadas
        result = mem.add(content, metadata={"neuron_id": neuron_id})
        links = []
        for link in result.get("related_memories", []):
            related_id = link.get("id")
            score = link.get("score", 0.0)
            if related_id and related_id != neuron_id and score > 0.7:
                links.append({"from": neuron_id, "to": related_id, "weight": score})
        return links
    except Exception as e:
        print(f"  ⚠ A-MEM link evolution falhou: {e}")
        return []


def _write_links_to_hive(links: list[dict], conn) -> int:
    """Persiste links A-MEM como sinapses no grafo do Hive-Mind."""
    written = 0
    for link in links:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO synapses(from_id, to_id, weight, kind)
                   VALUES (?, ?, ?, 'amem')""",
                (link["from"], link["to"], link["weight"]),
            )
            written += 1
        except Exception:
            pass
    if written:
        conn.commit()
    return written
```

### Task P6.3 — Chamar no Dream Cycle

**Arquivo:** `scripts/dream/dream_cycle.py`
**Onde:** após `_push_to_graphiti()` e `_index_in_lightrag()`:

```python
def _evolve_links(neuron_id: str, synthesis_text: str, conn) -> None:
    """A-MEM: evolui links após nova memória consolidada."""
    try:
        from core.amem_linker import add_and_evolve, _write_links_to_hive
        links = add_and_evolve(neuron_id, synthesis_text, conn)
        written = _write_links_to_hive(links, conn)
        if written:
            print(f"  🔗 A-MEM: {written} novos links criados")
    except Exception as e:
        print(f"  ⚠ A-MEM ignorado: {e}")

# Chamar após arquivar observação:
_push_to_graphiti(str(obs_id), synthesis_result)
_index_in_lightrag(synthesis_result)
_evolve_links(str(neuron_id), synthesis_result, conn)
```

---

## Fase P7 — MCP Streamable HTTP (spec 2025-03-26)

**Objetivo:** migrar MCP server de stdio para Streamable HTTP — múltiplos clientes simultâneos.
**Esforço:** 1-2 semanas | **Risco:** Médio (mudança de protocolo)

### Task P7.1 — Criar `scripts/services/sinapse-mcp-http.py`

**Arquivo NOVO:** `scripts/services/sinapse-mcp-http.py`

```python
#!/usr/bin/env python3
"""MCP server via Streamable HTTP (spec 2025-03-26).

Roda em paralelo ao stdio server existente (sinapse-mcp.py).
Permite múltiplos agentes conectados simultaneamente.

Uso: python sinapse-mcp-http.py --port 37703
"""
from __future__ import annotations
import json
import sys
import asyncio
from pathlib import Path
from aiohttp import web

SINAPSE_HOME = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SINAPSE_HOME))

# Importa lógica de handle_request do servidor stdio existente
from scripts.services.sinapse_mcp import handle_request, TOOLS  # noqa


async def handle_mcp(request: web.Request) -> web.Response:
    """Endpoint SSE para MCP Streamable HTTP."""
    body = await request.json()
    result = handle_request(body)
    return web.json_response(result or {"jsonrpc": "2.0", "result": None, "id": body.get("id")})


async def handle_tools_list(request: web.Request) -> web.Response:
    return web.json_response({"tools": TOOLS})


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=37703)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    app = web.Application()
    app.router.add_post("/mcp", handle_mcp)
    app.router.add_get("/mcp/tools", handle_tools_list)
    app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))

    print(f"MCP HTTP server em http://{args.host}:{args.port}/mcp")
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

**`requirements.txt`**:
```
aiohttp>=3.9
```

### Task P7.2 — Adicionar serviço systemd

**Arquivo:** `scripts/setup/install_services.py`
**Onde:** no dict `unit_definitions` — adicionar:

```python
"sinapse-mcp-http.service": """[Unit]
Description=Hive-Mind MCP HTTP Server (Streamable HTTP spec 2025-03-26)
After=network.target

[Service]
Type=simple
ExecStart={venv}/python {project}/scripts/services/sinapse-mcp-http.py --port 37703
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
""",
```

---

## Resumo: Mapa de Arquivos por Fase

| Fase | Arquivo | Ação |
|------|---------|------|
| P0 | `core/database.py` | Substituir bloco `fastembed` por `sqlite-lembed` + fallback |
| P0 | `core/indexing.py` | Usar `embed_text(t, conn=conn)` em vez de `embedder.embed()` |
| P0 | `requirements.txt` | `+sqlite-lembed` |
| P1 | `scripts/capture/parsers/screenpipe.py` | **NOVO** — adapter REST |
| P1 | `scripts/capture/capture_adapters.py` | `+screenpipe` no dict ADAPTERS |
| P1 | `scripts/services/sinapse-mcp.py` | `_capture_screen()` com fallback Screenpipe |
| P2 | `core/graphiti_client.py` | **NOVO** — wrapper async |
| P2 | `scripts/dream/dream_cycle.py` | `+_push_to_graphiti()` pós síntese |
| P2 | `scripts/services/sinapse-mcp.py` | `+sinapse_temporal_graph_search` tool |
| P2 | `requirements.txt` | `+graphiti-core, falkordb` |
| P3 | `core/telemetry.py` | **NOVO** — OTEL wrapper |
| P3 | `scripts/dream/dream_cycle.py` | `+span()` nas etapas do pipeline |
| P3 | `scripts/capture/capture_core.py` | `+span()` em `ingest()` |
| P3 | `requirements.txt` | `+opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http` |
| P4 | `core/lightrag_index.py` | **NOVO** — wrapper LightRAG |
| P4 | `scripts/dream/dream_cycle.py` | `+_index_in_lightrag()` pós síntese |
| P4 | `scripts/services/sinapse-mcp.py` | `+sinapse_rag_query` tool |
| P4 | `requirements.txt` | `+lightrag-hku` |
| P5 | `core/crdt_sync.py` | **NOVO** — CR-SQLite helpers |
| P5 | `core/database.py` | `+enable_crdt()` em `get_connection()` |
| P5 | `scripts/services/sinapse-sync.py` | **NOVO** — CLI de sync |
| P5 | `requirements.txt` | `+crsqlite` |
| P6 | `core/amem_linker.py` | **NOVO** — A-MEM wrapper |
| P6 | `scripts/dream/dream_cycle.py` | `+_evolve_links()` pós síntese |
| P7 | `scripts/services/sinapse-mcp-http.py` | **NOVO** — HTTP server |
| P7 | `scripts/setup/install_services.py` | `+sinapse-mcp-http.service` |

---

## Checklist por Sprint

### Sprint 1 — P0 + P3 (Embeddings + Observabilidade)
- [ ] `pip install sqlite-lembed`
- [ ] Baixar GGUF `all-MiniLM-L6-v2.Q8_0.gguf`
- [ ] Reescrever bloco embedder em `core/database.py`
- [ ] Atualizar `core/indexing.py`
- [ ] Deploy Langfuse Docker
- [ ] Criar `core/telemetry.py`
- [ ] Instrumentar Dream Cycle com spans
- [ ] `pytest tests/unit/ -q` → tudo verde

### Sprint 2 — P1 (Screenpipe)
- [ ] Instalar Screenpipe
- [ ] Criar `scripts/capture/parsers/screenpipe.py`
- [ ] Atualizar `capture_adapters.py`
- [ ] Atualizar `_capture_screen()` no MCP server
- [ ] Testar captura via `sinapse_capture_screen`

### Sprint 3 — P4 (LightRAG)
- [ ] `pip install lightrag-hku`
- [ ] Criar `core/lightrag_index.py`
- [ ] Conectar Dream Cycle
- [ ] Adicionar tool `sinapse_rag_query` no MCP
- [ ] Testar com corpus existente

### Sprint 4 — P2 (Graphiti)
- [ ] Docker FalkorDB
- [ ] `pip install graphiti-core falkordb`
- [ ] Criar `core/graphiti_client.py`
- [ ] Conectar Dream Cycle
- [ ] Adicionar tool `sinapse_temporal_graph_search`
- [ ] Testar busca temporal

### Sprint 5 — P5 (CR-SQLite)
- [ ] Backup de `hive_mind.db` antes de qualquer mudança
- [ ] `pip install crsqlite`
- [ ] Criar `core/crdt_sync.py`
- [ ] Integrar em `get_connection()`
- [ ] Criar `sinapse-sync.py`
- [ ] Testar sync entre duas instâncias locais (dois diretórios)
