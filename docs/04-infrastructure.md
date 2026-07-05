# 04 — Infrastructure and Configuration

> **Hive-Mind v3.0.0** — Requirements, services, ports, environment variables, and operations.
> Last review: 2026-06-30 · LightRAG (P4) integrated as `claude-mem/data/lightrag/` · **Born-Large (K0–K10):** VectorBackend with optional Milvus, RAGFlow headless adapter, optional LlamaIndex, negative vendoring contract via `components.lock.json`, `workspace_id` in all critical tables, session→annual cadence with dedicated roles. See [`01-architecture.md` §22–§31](01-architecture.md#22-arquitetura-de-conhecimento-born-large) and [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md).

---

## 1. Software Requirements

### 1.1 Runtime

| Dependency | Minimum version | Use |
|-------------|--------------|-----|
| Python | 3.10+ | Core — scripts, MCP server, REST API, Dream Cycle |
| SQLite | 3.44+ | UMC with `sqlite-vec` (required extension) |
| Node.js / Bun | 18+ / 1.0+ | claude-mem (TypeScript) |
| Rust / Cargo | 1.70+ | RTK (one-time compilation; optional prebuilt binary) |
| Syncthing | 1.27+ | P2P sync of Markdown files across machines |
| uv | 0.4+ | Python package manager |

### 1.2 Python Dependencies (requirements.txt)

| Package | Version | Use |
|--------|--------|-----|
| `fastapi` | ≥0.111 | REST API (sinapse-api.py) |
| `uvicorn` | ≥0.29 | ASGI server for FastAPI |
| `pydantic` | ≥2.7 | LLM output validation + schemas |
| `cryptography` | ≥42 | Fernet encryption (secret vault) |
| `fastembed` | ≥0.3 | Legacy/fallback dependency; canonical embeddings use Ollama 1024d |
| `watchdog` | ≥4.0 | Real-time file watcher |
| `pypdf` | ≥4.0 | PDF text extraction |
| `python-docx` | ≥1.1 | Word document reading |
| `PyMuPDF` | ≥1.24 | Image extraction from PDFs |
| `mss` | ≥9.0 | Screenshot capture |
| `pyyaml` | ≥6.0 | YAML frontmatter parsing |
| `httpx` | ≥0.27 | Async HTTP client (cloud mode) |
| `hnswlib` | ≥0.8.0 | Incremental HNSW index for vector search (HM-11) |
| `duckdb` | ≥0.10 | Read-only analytics over hive_mind.db (HM-11) |

---

## 2. Environment Variables

```
# .env at the project root (never committed)
```

### 2.1 System

| Variable | Description | Default |
|----------|-----------|--------|
| `SINAPSE_HOME` | Project root path | auto-detected |
| `SINAPSE_DRY_RUN` | `1` to run without side effects | `0` |
| `HIVE_MIND_API_KEY` | REST API Bearer token (required) | no default |
| `HIVE_MIND_API_PORT` | REST API port | `37702` |

### 2.2 LLM by role

Each role has optional primary and fallback; a role without a complete PROVIDER+MODEL pair inherits from Dreamer (rules: [`01-architecture.md`](01-architecture.md) §11.1 and ADR-009). The Born-Large Knowledge front adds **K5 cadence roles** and specialized K3/K4/K6/K7 roles (see [`02-ai-models.md` §2.1.0](02-ai-models.md#210-papéis-canônicos-constante-hive_llm_roles-em-coreauthpy)).

| Variable | Role | Description |
|----------|-------|-----------|
| `HIVE_DREAMER_PROVIDER` / `HIVE_DREAMER_MODEL` | Dreamer (inheritance base) | Dream Cycle LLM (Knowledge Intake K3 + Distiller/Validator/Router K4) |
| `HIVE_DREAMER_FALLBACK_PROVIDER` / `HIVE_DREAMER_FALLBACK_MODEL` | Dreamer | Opt-in fallback if primary fails |
| `HIVE_GRAPHIFY_PROVIDER` / `HIVE_GRAPHIFY_MODEL` | Graphify | Entity extraction during indexing |
| `HIVE_GRAPHIFY_FALLBACK_PROVIDER` / `HIVE_GRAPHIFY_FALLBACK_MODEL` | Graphify | Opt-in fallback |
| `HIVE_VISION_PROVIDER` / `HIVE_VISION_MODEL` | Vision | Screenshot description (multimodal) |
| `HIVE_VISION_FALLBACK_PROVIDER` / `HIVE_VISION_FALLBACK_MODEL` | Vision | Opt-in fallback |
| `HIVE_OCR_PROVIDER` / `HIVE_OCR_MODEL` | Optional OCR | Dedicated OCR; documented default `ollama/deepseek-ocr:latest`, opt-in in installer |
| `HIVE_SYNTHESIS_PROVIDER` / `HIVE_SYNTHESIS_MODEL` | P2P synthesis | Dialectical synthesis of conflicts |
| `HIVE_SYNTHESIS_FALLBACK_PROVIDER` / `HIVE_SYNTHESIS_FALLBACK_MODEL` | P2P synthesis | Opt-in fallback |
| `HIVE_CLAUDE_MEM_PROVIDER` / `HIVE_CLAUDE_MEM_MODEL` | claude_mem | `claude_mem_bridge.py` bridge (K4) — classifies `knowledge_type`; inherits from Dreamer if undefined |
| `HIVE_SESSION_SUMMARIZER_PROVIDER` / `HIVE_SESSION_SUMMARIZER_MODEL` | session_summarizer (K5) | Session summary (small/fast) |
| `HIVE_DAILY_WRITER_PROVIDER` / `HIVE_DAILY_WRITER_MODEL` | daily_writer (K5) | Daily synthesis (small/medium) |
| `HIVE_WEEKLY_SYNTHESIZER_PROVIDER` / `HIVE_WEEKLY_SYNTHESIZER_MODEL` | weekly_synthesizer (K5) | Weekly synthesis (medium/strong) |
| `HIVE_MONTHLY_SYNTHESIZER_PROVIDER` / `HIVE_MONTHLY_SYNTHESIZER_MODEL` | monthly_synthesizer (K5) | Monthly synthesis (strong) |
| `HIVE_YEARLY_SYNTHESIZER_PROVIDER` / `HIVE_YEARLY_SYNTHESIZER_MODEL` | yearly_synthesizer (K5) | Yearly synthesis (strong/batch) |
| `HIVE_LIGHTRAG_PROVIDER` / `HIVE_LIGHTRAG_MODEL` | lightrag (P4) | Local default `ollama/qwen2.5:3b` |
| `HIVE_RETRIEVAL_RERANKER` | reranker (K7, optional) | Local/fail-open lexical rerank via LlamaIndex; off by default in `local-min` ([`01-architecture.md` §31.1](01-architecture.md#311-reranker-reordenação-por-relevância)) |
| `HIVE_RERANKER_PROVIDER` / `HIVE_RERANKER_MODEL` | strong reranker (K7, optional) | Opt-in local cross-encoder; requires `uv sync --extra reranker`; off by default |
| `OLLAMA_LOCAL` | — | Ollama base URL (`http://localhost:11434`) |
| `OLLAMA_EMBED_MODEL` | Embeddings | Canonical default `snowflake-arctic-embed2:latest`, **1024d** (K1/K10) |
| `VECTOR_BACKEND` | Vectors | `sqlite` by default; `milvus` when integration is enabled (K1) |
| `HIVE_ALLOW_DEFERRED_MIGRATIONS` | Structural migrations (K10) | `0` (fail-closed); `1` for legacy DB diagnostics only |
| `HIVE_PROMOTION_BUDGET_*` | Promotion cost (K10) | Per-workspace cap; overflow remains `archived=0` (retry) |

Example values: provider `google`, `openai`, `anthropic`, `ollama`, `deepseek`; model `gemini-2.0-flash`, `gpt-4o`, `claude-haiku-4-5-20251001`, `qwen2.5-coder:3b`.
For local vision, the default is `HIVE_VISION_PROVIDER=ollama` with
`HIVE_VISION_MODEL=minicpm-v4.6:latest` and fallback `gemma3:4b`; the installer
uses `gemma3:4b` as primary only when the Ollama daemon does not yet support
the MiniCPM manifest. The legacy heavy model `llava:7b` is not part of the stack.

> The **embedding model is configurable**, but the canonical project default is
> `snowflake-arctic-embed2:latest` via local Ollama, **1024 dimensions**. The
> `search_vec` table and the 7 canonical collections (K1) — `memory_vectors`, `observation_vectors`,
> `document_vectors`, `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors` —
> expect 1024d. Switching to another model requires keeping the same dimension or running a
> **versioned migration** (K10, [`01-architecture.md` §30.4](01-architecture.md#30-escala-e-isolamento--workspace-e-federação)):
> online re-embed per workspace, dual-write until cutover, metric `vectors_model_mismatch` = 0
> within a collection.

### 2.2.1 Model Gateway (Priority 1, canonical)

The per-role `HIVE_*_PROVIDER/MODEL` table above is the **source of
truth** for which provider/model each role uses. The
`core/model_gateway.py` + `core/model_registry.py` layer is the
**canonical execution path** for every LLM call in the Hive-Mind
(specs/model-gateway-unification.md). `core/llm_client.call_llm_with_fallback`
is a thin wrapper that delegates to `ModelGateway.from_combined_config()`.
The registry composes `PROVIDERS_CONFIG` (base URL, env var, auth type)
with the `.env` `HIVE_*_PROVIDER/MODEL/FALLBACK*` and applies
`config/model-gateway.yaml` as an OPTIONAL override layer (never
requiring `provider`/`model` per role). Routing is by role **and**
required capability (structured output, tools, vision, embeddings,
rerank) across `native` (legacy bridge for vision + emergency bypass),
`openai_compatible`/`lmstudio`/`llamacpp`/`vllm`/`sglang` (one shared
HTTP adapter), and `litellm` (proxy mode). See
[`14-model-gateway.md`](14-model-gateway.md) for the full guide, backend
setup per provider, and known limitations.

| Variable | Description |
|----------|-------------|
| `MODEL_GATEWAY_MODE` | `auto` (default) / `on` / `off` — see `14-model-gateway.md` § Operating modes |
| `HIVE_FORCE_LEGACY_LLM` | Emergency bypass (`true`/`false`); never set by default |
| `MODEL_GATEWAY_ENABLED` | DEPRECATED shim for `MODEL_GATEWAY_MODE` |
| `MODEL_GATEWAY_CONFIG` | Path to the YAML override, default `config/model-gateway.yaml` |
| `LMSTUDIO_BASE_URL` / `LMSTUDIO_MODEL` | LM Studio local server (default `http://localhost:1234/v1`) |
| `LLAMACPP_BASE_URL` / `LLAMACPP_MODEL` | llama.cpp `server` (default `http://localhost:8080/v1`) |
| `VLLM_BASE_URL` / `VLLM_MODEL` | vLLM OpenAI-compatible server (default `http://localhost:8000/v1`) |
| `SGLANG_BASE_URL` / `SGLANG_MODEL` | SGLang OpenAI-compatible server (default `http://localhost:30000/v1`) |
| `LITELLM_BASE_URL` / `LITELLM_API_KEY` / `LITELLM_MODEL` | LiteLLM proxy, HTTP mode only (default `http://localhost:4000/v1`) |
| `OLLAMA_GATEWAY_BASE_URL` / `OLLAMA_GATEWAY_MODEL` | Ollama's own `/v1` API — enabled by default, no separate server (default `http://127.0.0.1:11434/v1`) |

O bloco de variáveis do Model Gateway fica em
`config/model-gateway.env.example` porque `.env.example` não pôde ser
alterado nesta sessão. O install/documentation deve apontar para esse
arquivo como fonte canônica do exemplo de ambiente do Model Gateway.

### 2.3 Vectors and Ingestion — Milvus (K1/K2) and RAGFlow (K6)

| Variable | Description | Default |
|----------|-----------|--------|
| `VECTOR_BACKEND` | Active vector backend: `sqlite_vec` (local-first) or `milvus` (production) | `sqlite_vec` |
| `MILVUS_URI` | Milvus container gRPC/HTTP endpoint | `http://localhost:19530` |
| `MILVUS_COLLECTION_PREFIX` | Prefix for the 7 canonical collections inside Milvus | `hm_` |
| `HIVE_KNOWLEDGE_HEALTH_MILVUS` | `1` so K8 `knowledge_health` measures real `milvus_sync_lag` instead of reporting `milvus_not_enabled` | `0` |
| `RAGFLOW_BASE` | Base URL for the headless RAGFlow container (K6, document ingestion) | `http://localhost:9380` |
| `RAGFLOW_API_KEY` | RAGFlow API key (generated at container first boot) | no default |

> Both services run as Docker containers (`docker compose` in
> `integrations/ragflow/docker-compose.yml` and equivalent for Milvus) and are
> **optional**: without `VECTOR_BACKEND=milvus`, the system uses local `sqlite_vec`
> and K8 `knowledge_health` reports `milvus_sync_lag.available=false` with
> `reason=milvus_not_enabled` (expected behavior, not a failure).
> `scripts/setup/components.py` refuses to clone `milvus`/`ragflow` as
> pinned components in `components.lock.json` (ADR-018) — both are only included
> as container/wrapper via `integrations/`.

### 2.4 API Keys by Provider

| Variable | Provider |
|----------|---------|
| `GOOGLE_API_KEY` | Google AI Studio (Gemini) |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth Device Flow |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth Device Flow (**⚠️ rotate if compromised**) |
| `OPENAI_API_KEY` | OpenAI / OpenRouter-compatible |
| `ANTHROPIC_API_KEY` | Anthropic |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `HF_TOKEN` | Hugging Face Inference |
| `DASHSCOPE_API_KEY` | Alibaba Qwen (DashScope) |
| `NVIDIA_API_KEY` | NVIDIA NIM |
| `OPENROUTER_API_KEY` | OpenRouter |

---

## 3. Services and Ports

| Service | Port | Protocol | Access | Process | Phase |
|---------|-------|-----------|--------|----------|------|
| REST API (FastAPI) | 37702 | HTTP REST | localhost (VPS: Bearer token) | `scripts/services/sinapse-api.py` | base + HM-12 |
| REST API — knowledge health | 37702 (`/api/v1/knowledge/health`) | HTTP REST | localhost (VPS: Bearer token) | `scripts/health/knowledge_health.py` | K8 |
| claude-mem Worker | 37700 | HTTP REST | localhost only | upstream worker with data in `~/.claude-mem` | base + K4 |
| Ollama | 11434 | HTTP REST | localhost | `ollama serve` | base |
| MCP Server (sinapse-mcp) | stdio | JSON-RPC | agent process | `scripts/services/sinapse-mcp.py` | base |
| Syncthing UI | 8384 | HTTP | localhost | `syncthing` | base |
| Milvus (K1, optional) | 19530 (gRPC) + 9091 (HTTP) | gRPC/HTTP | localhost or VPS | container pinned by digest | K1 |
| RAGFlow (K6, optional) | 9380 (HTTP) | HTTP | localhost or VPS | headless container + `ragflow-sdk` | K6 |
| FalkorDB (Graphiti) | 6379 | Redis | localhost | container | base + K10 |
| LightRAG/P4 | local (`claude-mem/data/lightrag/`) | files | local | `core/lightrag_index.py` | P4 |

No ports are externally exposed by default. For VPS deployment:

- The REST API (:37702) is exposed behind nginx/Caddy with TLS.
- **Milvus** (K1) and **RAGFlow** (K6) run as containers on an internal network; only `pymilvus` and `ragflow-sdk` go to external network (configurable). Details in [`01-architecture.md` §2.6](01-architecture.md#26-ferramentas-externas-como-órgãos-do-cérebro).
- Federated REST (`/api/v1/neurons/export`) is the only exposed cross-machine endpoint.

---

## 4. Background Services

### 4.1 Real-time Watcher

```bash
# Start watcher in background
./scripts/services/start-watcher.sh &

# Check if it is running
pgrep -f "start-watcher" && echo "OK"

# Stop
pkill -f "start-watcher"
```

The Watcher uses `watchdog` to monitor `cerebro/`. When it detects a `.md` change:
1. Queues the event (500ms debounce to avoid double reindex)
2. Calls Graphify to reindex the file
3. Updates `synapses` (structural graph); `WriteIndexer` is responsible for the UMC/FTS/vector path

### 3.1 Responsibility split (post-audit stabilization, R9.2)

The write path has three layers, each with a single owner. Silent
overlaps caused the original audit's "decision saved but not in UMC"
failure. The current contract is:

| Layer | Tool | Owns |
|---|---|---|
| Markdown on disk | `core/memory/writers.py` | creates the file |
| Structural graph | Graphify (`graphify watch`) | updates `synapses` and `graphify-out/graph.json` |
| UMC + FTS + vector | `core/indexing/WriteIndexer` (R2) | upserts `neurons`, `search_fts`, `search_vec`; called synchronously by `sinapse-write.py decision/learning` |
| Vector job queue | `core/indexing/vector_jobs_worker.py` (R3) | drains the `vector_jobs` table for `memory_vectors` and 6 other canonical collections |
| Async reindex fallback | `start-watcher.sh` + `graphify watch` | picks up edits the writer missed; **MUST NOT be the only path** that updates UMC/FTS/vector for synchronous writes |

### 3.2 RTK role (R1, R12.3)

**RTK is shell optimization only.** It rewrites terminal command args to
reduce token output. RTK MUST NOT be wired into `sinapse_query`,
`context_fusion`, `retrieval_router`, or any `read_backends` list.
RTK's Hermes plugin (`integrations/rtk/hooks/hermes/rtk-rewrite/`)
logs opt-in observations back to UMC, but those are append-only events,
not read paths.

### 3.3 Graphify version (R9.1)

`config/components.lock.json` pins Graphify's source clone
(`integrations/graphify`, built via `pip install -e`) at commit
`905e0a7` = **version 0.8.49**. `scripts/setup/components.py verify`
confirms the checkout matches this commit and the pinned patch is
applied.

**The project's actual runtime resolves to 0.8.49, matching the lock.**
Nothing in the codebase calls a bare `graphify` off `$PATH`: the
watcher (`scripts/services/start-watcher.sh`) invokes
`python -m graphify watch` through the project's own `.venv`, and
`install.sh` resolves `GRAPHIFY="$PROJECT_ROOT/.venv/bin/graphify"`
explicitly. `PATH="$PROJECT_ROOT/.venv/bin:...:$PATH" graphify --version`
reports `0.8.49` — the same version the lock pins.

A *separate*, host-level interactive CLI tool exists at
`~/.local/bin/graphify` (installed independently via `uv tool install
graphifyy`, one per developer machine, not part of this repo) and can
lag behind — e.g. it may still report `0.8.14` and print a
"skill is from graphify 0.8.49, package is 0.8.14" warning on some
machines. That warning is about the personal CLI tool a developer uses
for ad-hoc `/graphify` queries across *all* their projects; it is not
part of Hive-Mind's install or runtime and out of this repo's scope to
manage. To silence it on a given machine, run `uv tool upgrade
graphifyy` (or symlink `~/.local/bin/graphify` to that machine's
project `.venv/bin/graphify`) — a one-time, per-developer action, not
a stabilization blocker.

### 4.2 claude-mem (Temporal Tracking)

```bash
# The official runtime is global and multi-project.
systemctl --user restart sinapse-claude-mem.service
sqlite3 ~/.claude-mem/claude-mem.db 'PRAGMA quick_check;'
```

### 4.3 Syncthing P2P

```bash
syncthing &       # starts daemon
# UI at: http://localhost:8384
```

---

## 5. Cron Jobs

```cron
# Structural graph rebuild every 6h
0 */6 * * * cd $SINAPSE_HOME && ./scripts/graph/build-graph.sh >> logs/sync.log 2>&1

# P2P audit of temporal neurons + search_vec validation (hourly)
0 * * * * cd $SINAPSE_HOME && .venv/bin/python scripts/health/audit_memory.py --fix >> logs/audit.log 2>&1

# Consistent backup of critical SQLite databases (daily at 3am)
0 3 * * * cd $SINAPSE_HOME && .venv/bin/python scripts/health/backup_databases.py >> logs/backup.log 2>&1

# Dream Cycle and K5 cadence
0 2 * * * cd $SINAPSE_HOME && .venv/bin/python scripts/dream/dream_cycle.py --once --real >> logs/dream-cycle.log 2>&1
15 3 1 * * cd $SINAPSE_HOME && .venv/bin/python scripts/dream/monthly_synthesizer.py --real >> logs/monthly-synthesizer.log 2>&1
30 3 1 1 * cd $SINAPSE_HOME && .venv/bin/python scripts/dream/yearly_synthesizer.py --real >> logs/yearly-synthesizer.log 2>&1

# Sync summary_vectors to Milvus only when VECTOR_BACKEND=milvus
45 3 * * * cd $SINAPSE_HOME && if [ "${VECTOR_BACKEND:-sqlite}" = "milvus" ]; then .venv/bin/python scripts/maintenance/vector-sync.py --collection summary_vectors --json >> logs/vector-sync.log 2>&1; fi
```

`install.sh` installs this block idempotently when `crontab` is
available. In environments without cron, the same commands must be run by the
host orchestrator.

`audit_memory.py --fix` audits only real neurons from the temporal cortex.
Files generated with `type: moc` are navigation artifacts and remain out of the
neuron index; if an old version indexed them, the fix removes those legacy rows
and their vectors.

---

## 6. Directory Structure

```
  Hive-Mind/
  ├── cerebro/                                Obsidian vault (single source of truth)
  │   ├── atlas/                              Facts consolidated by Dream Cycle
  │   ├── brain/
  │   │   ├── Current State.md               Current state (updated in Stop hook)
  │   │   └── Patterns.md                     Accumulated learnings
  │   ├── work/
  │   │   └── active/                         Active decisions (YYYY-MM-DD-slug.md)
  │   ├── inbox/
  │   │   ├── visual/                         Captured screenshots
  │   │   └── documents/                      PDFs and DOCXs (parents of document_chunks K6)
  │   ├── conflicts/                          Resolved P2P conflicts (history)
  │   ├── graphify-out/                       Graphify output (graph.json, report)
  │   ├── .claude/
  │   │   └── settings.json                   Claude Code hooks (SessionStart, PostToolUse, Stop)
  │   └── .codex/
  │       └── hooks.json                      Codex CLI hooks
  ├── core/
  │   ├── umc_schema.sql                      Full database DDL
  │   ├── database.py                         Connection pool (WAL, busy_timeout=5000)
  │   ├── auth.py                             LLM provider auth (canonical roles)
  │   ├── llm_client.py                       call_llm_structured + classify_llm_error + retry/fallback
  │   ├── vector_backend.py                   Single contract (sqlite_vec / milvus) — K1
  │   ├── paths.py                            Canonical path constants (§2.7)
  │   ├── hnsw_index.py                       Incremental vector HNSW index — HM-11
  │   ├── signing.py                          Ed25519 neuron sign/verify — HM-12
  │   ├── redactor.py                         PII regex redaction, 8 categories — HM-12
  │   ├── retrieval/router.py                 RetrievalRouter (K7) — classifies intent, chooses route
  │   ├── knowledge/                          (K0–K10 front)
  │   │   ├── intake.py                       Knowledge Intake (K3)
  │   │   ├── promotion.py                    Promotion Layer (K4)
  │   │   ├── claude_mem_bridge.py            Read-only claude-mem SQL bridge (K4)
  │   │   ├── document_pipeline.py            DocumentPipeline (K6) — parent/chunk/citation
  │   │   ├── vector_sync.py                  Cadence and docs indexing (K1/K5/K6)
  │   │   ├── topic_consolidator.py           Topic consolidation in temporal lobe (K3)
  │   │   ├── alias_miner.py                  Alias mining (slugs)
  │   │   ├── sector_classifier.py            Cross-project sector (Diencephalon)
  │   │   ├── generate_mocs.py                MOC generation
  │   │   ├── ambiguities.py                  Dialectical synthesis (Insula)
  │   │   └── ...
  │   ├── search.py                           route_retrieval() — internal router adapter (K7)
  │   ├── lightrag_index.py                   P4 — entities + relations
  │   └── schemas/                            Pydantic models (Dream Cycle, cadence, K3/K4)
  ├── integrations/                           Born-Large vendors (K0–K10)
  │   ├── graphify/                           Clone (components.lock.json)
  │   ├── neural-memory/                      Clone (components.lock.json)
  │   ├── rtk/                                Clone (components.lock.json)
  │   ├── milvus/                             Wrapper (pymilvus + docker-compose, K1)
  │   ├── ragflow/                            Wrapper (ragflow-sdk headless, K6)
  │   └── graphiti/                           Wrapper (FalkorDB + docker-compose)
  ├── scripts/
  │   ├── dream/                              Offline consolidation
  │   │   ├── dream_cycle.py                  Main pipeline
  │   │   ├── session_consolidator.py         Session summary (K5)
  │   │   ├── daily_writer.py                 Daily (K5)
  │   │   ├── weekly_synthesizer.py           Weekly (K5)
  │   │   ├── monthly_synthesizer.py          Monthly (K5)
  │   │   ├── yearly_synthesizer.py           Yearly (K5)
  │   │   ├── pattern_distiller.py            Patterns (cerebelo/padroes/)
  │   │   └── semantic_diff.py                Conflict classification (vector + LLM)
  │   ├── knowledge/
  │   │   ├── document_ingest.py              PDF/DOCX ingestion via DocumentPipeline
  │   │   └── ...
  │   ├── services/                           sinapse-mcp, sinapse-api, sinapse-write, start-watcher
  │   ├── health/
  │   │   ├── audit_memory.py                 P2P audit (hash check + reindex)
  │   │   ├── health_dashboard.py             Insula health (operational)
  │   │   ├── alert_dispatcher.py             Insula alerts
  │   │   ├── review_writer.py                Review → saude/
  │   │   └── knowledge_health.py             K8 metrics (knowledge gate)
  │   ├── capture/visual_capture.py           Screenshots → visual_memories
  │   ├── analytics/planner.py                Goal decomposition — LLM + goals table
  │   ├── setup/setup-brain.py                Hive-Dreamer configuration UI
  │   ├── setup/setup-brain.sh                Shell wrapper
  │   ├── services/start-watcher.sh           Starts Watcher in background
  │   └── utils/recover.sh                    Disaster recovery (UMC rebuild)
  ├── plugins/
  │   └── hermes/
  │       └── sinapse-memory.py               Native plugin for Hermes Agent
  ├── tests/
  │   ├── smoke/                              Smoke tests
  │   ├── unit/                               Unit (mocks; no LLM)
  │   ├── integration/                        Integration (real backends)
  │   ├── e2e/                                E2E (full session)
  │   ├── test_synthesis.py                   Synthesis with real LLM
  │   ├── real/                               Real acceptance harness (K9) — service_registry
  │   ├── run_all.sh                          Full suite orchestrator
  │   └── README.md                           Suite conventions
  ├── docs/                                  This documentation
  ├── components.lock.json                    Negative vendoring contract (ADR-018)
  ├── hive_mind.db                           Unified Memory Core (SQLite + sqlite-vec) — v3: causal_edges, goals, visibility, workspace_id, source_id
  ├── claude-mem/data/lightrag/              LightRAG knowledge graph (P4) — entities/relationships/vdb
  │   ├── graph.npz                          NetworkX pickle (entities + edges)
  │   ├── vdb_chunks.json                    Text chunk embeddings (snowflake-arctic-embed2 1024d)
  │   ├── vdb_entities.json                  Extracted entity embeddings (snowflake-arctic-embed2 1024d)
  │   └── vdb_relationships.json             Extracted relationship embeddings (snowflake-arctic-embed2 1024d)
  ├── sinapse.yaml                           Central configuration
  ├── .env                                   Local secrets (gitignored)
  ├── .env.example                           Variable template (committed)
  ├── requirements.txt                       Python dependencies (includes pymilvus and opt-in llama-index)
  └── install.sh                             Installer (10 steps)
```

### 6.1 UMC Schema — Notable Tables and Columns (v3.0.0 + K0–K10)

| Table / Column | Type | Added | Description |
|----------------|------|-----------|-----------|
| `causal_edges` | table | HM-12 | Causal graph between neurons (source_id, target_id, weight, relation_type) |
| `goals` | table | HM-12 | Goals decomposed by Planner (id, description, status, parent_id) |
| `neurons.visibility` | column | HM-12 | Neuron visibility: `private`, `shared`, `public` |
| `neurons.workspace_id` | column | K10 | Isolation boundary; default `'default'` (K10) |
| `observations.workspace_id` | column | K10 | Same isolation; `claude_mem_bridge.py` preserves it |
| `observations.source_id` | column | K4 | `claude-mem:<table>:<id>` for source traceability |
| `observations.neuron_id` | column | K4 | FK to `neurons.id` when promoted |
| `observations.promoted` | column | K3/K4 | `0` pending / `1` consolidated / `2` structural quarantine |
| `synapses.workspace_id`, `goals.workspace_id`, `causal_edges.workspace_id` | column | K10 | Same boundary; `(workspace_id, ...)` on hot indexes |
| `document_memories` | table | K6 | Document parents (`document_id`, `source_uri`, `file_hash`, `project`, `workspace_id`) |
| `document_chunks` | table | K6 | Document atoms (`parent_id`, `parent_type=document`, `chunk_index`, offsets, hash, `workspace_id`) |
| `document_vectors` | collection | K1/K6 | Chunk vectors (1024d) with canonical metadata (K1) |
| `vector_metadata` | table | K1 | Canonical metadata (`parent_id`, `brain_lobe`, `knowledge_type`, `source_uri`, `valid_at`, `workspace_id`) for UMC collections |
| `summary_vectors` | collection | K1/K5 | Cadence vectors (session→annual) with canonical metadata |
| `knowledge_tombstones` | table | K8 | Auditable tombstones from `forget()` (reason, actor, target, `workspace_id`) |
| `query_route_log` | table | K7 | Query hash × route (`query_route_distribution` telemetry) |

> **Born-Large (K10):** every `RetrievalRouter` and promotion query filters by `workspace_id`. Milvus uses `partition_key=workspace_id` for partition-level isolation. Cross-workspace leakage is a security bug, not a ranking issue. Migrations that create this boundary are structural: migration failure is fail-closed by default. The only bypass is `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` (legacy DB diagnostics, with visible logging and without marking the installation as healthy).

---

## 7. Security

### 7.1 Principles

1. **Fail-closed**: REST API does not start without `HIVE_MIND_API_KEY`
2. **API keys in `.env`**: never committed (`.gitignore` covers `.env` and `*.db`)
3. **Constant-time tokens**: `hmac.compare_digest` comparison instead of `==`
4. **Secret vault**: secrets detected in content are encrypted with Fernet and replaced by `[SECRET:uuid]`
5. **Atomic writes**: `os.replace()` prevents file corruption on failures

### 7.2 Attack Surface

| Vector | Risk | Mitigation |
|-------|-------|-----------|
| REST API (:37702) | Forged token | `hmac.compare_digest` — timing-safe |
| claude-mem Worker (:37700) | Unauthorized local access | Bind to `127.0.0.1` only |
| Path traversal (vault write) | File outside `cerebro/` | `_sanitize_slug()` removes `/` and `..` |
| Secret injection (MCP input) | API key in query | Regex scan → Fernet → vault table |
| Google OAuth client_secret | Compromised if hardcoded | Only via `.env` (`_env("GOOGLE_OAUTH_CLIENT_SECRET")`) |

### 7.3 Sensitive Files

| File/Directory | Content | Protection |
|-------------------|----------|----------|
| `.env` | API keys, tokens, OAuth secrets | `.gitignore`, chmod 600 |
| `hive_mind.db` | Entire memory (includes vault table) | `.gitignore` |
| `~/.claude-mem/` | Global timestamped observations | local permissions + controlled backup |
| `claude-mem/data/lightrag/` | Knowledge graph + embeddings (P4) | `.gitignore` (regenerable via Dream Cycle) |
| `backups/` | UMC backups | `.gitignore` |

---

## 8. Deployment

### 8.1 Local (development)

```
  ┌─────────────────────────────────────────────┐
  │                 Local Machine                 │
  │                                               │
  │  ┌──────────────────────────────────────┐    │
  │  │          hive_mind.db (UMC)          │    │
  │  │   neurons / synapses / FTS5 / vec    │    │
  │  └──────────────────────────────────────┘    │
  │       ▲              ▲              ▲         │
  │  Watcher (~2s)   claude-mem    sinapse-api    │
  │  :watchdog       :37700        :37702         │
  │                                               │
  │  ┌──────────────────────────────────────┐    │
  │  │  claude-mem/data/lightrag/ (P4)      │    │
  │  │   graph + entities/rels/chunks vdb   │    │
  │  │   fed by Dream Cycle                 │    │
  │  └──────────────────────────────────────┘    │
  │       ▲                                       │
  │  Dream Cycle Stage 3.5 (best-effort)         │
  │                                               │
  │  ┌──────────────┐   ┌──────────────────────┐ │
  │  │  Obsidian    │   │  AI Agents            │ │
  │  │  (cerebro/)  │   │  MCP / Hooks / Plugin │ │
  │  └──────────────┘   └──────────────────────┘ │
  └─────────────────────────────────────────────┘
              │ Syncthing P2P
              ▼
        Other devices
```

### 8.2 VPS / Cloud

```
  ┌─────────────────────────────────────────────┐
  │                VPS (cloud)                    │
  │                                               │
  │  nginx/Caddy (TLS) → sinapse-api (:37702)    │
  │  systemd: watcher + claude-mem + api          │
  │  Ollama (:11434) — local models               │
  │  Syncthing — receives vault from other machines│
  └─────────────────────────────────────────────┘
              │
              │ HTTPS (Bearer token)
              ▼
  ┌──────────────────┐   ┌──────────────────┐
  │ Local machine 1  │   │ Local machine 2  │
  │ (cloud.enabled)  │   │ (cloud.enabled)  │
  └──────────────────┘   └──────────────────┘
```

### 8.3 What Hive-Mind DOES and DOES NOT DO

| DOES | DOES NOT DO |
|-----|---------|
| Indexes Obsidian vault into queryable UMC | Does not replace Obsidian as an editor |
| Automatically injects context into agents | Is not an AI agent |
| Consolidates memory offline via Dream Cycle | Does not train its own models |
| Syncs vault across machines via Syncthing | Is not a distributed database |
| Resolves P2P conflicts via Dialectical Synthesis | Does not search the internet |
| Processes images and documents (Phase 10) | Does not manage user authentication |
