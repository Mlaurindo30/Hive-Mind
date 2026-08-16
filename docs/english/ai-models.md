# AI Models

> **Hive-Mind v3.10.1** — LLM roles, models in use, Model Gateway, structured output for reasoning models, fallback chain and embeddings.
> Revision 2026-08-15. Consolidates [`02-ai-models.md`](02-ai-models.md) and [`ai-models.md`](ai-models.md).

---

## 1. Overview

Hive-Mind **does not train proprietary models**. It uses third-party models in distinct contexts, all configurable per role via `HIVE_{ROLE}_*`:

1. **Graphify** — structural indexing of the vault (entity and relationship extraction).
2. **Hive-Dreamer** — offline semantic consolidation (Dream Cycle, K3 Knowledge Intake + K4 Promotion Layer).
3. **Cadence** — cadence writers (K5: `session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer`, `yearly_synthesizer`), each with its own model or inheritance from the Dreamer.

In all cases, the model choice is **configurable by the user** via environment variables and through `setup-brain.sh`/`setup-brain.py`. No model is hardcoded.

### Models in use (v3.10.1)

| Model | Role | Type | Where it runs |
|--------|-------|------|-----------|
| `granite4.1:8b` | Distiller / Router (Dream Cycle), local instruct extraction | local instruct | Ollama |
| `qwen3.5:397b` | Validator (Dream Cycle) and reasoning | reasoning | cloud |
| `gpt-oss-120b` | reasoning (synthesis/validation) | reasoning | cloud (`gpt-oss-120b-maas` via antigravity) |
| `snowflake-arctic-embed2:latest` | embeddings (1024d) | embedding | local Ollama |

> The v3.10.1 role split: **Distiller/Router** route via role config (`granite4.1:8b` local instruct); **Validator** keeps reasoning (`qwen3.5:397b`). The model registry marks `reasoning=True` per role (`dreamer`/`validator`/`synthesis`).

---

## 2. Canonical LLM roles

Constant `HIVE_LLM_ROLES` in `core/auth.py`. Roles are case-insensitive (`-` becomes `_`); empty or non-string names raise `ValueError`. Resolution is centralized in `get_role_config()` (`core/auth.py`).

| Role | Used by | Call profile | reasoning=True |
|-------|-----------|-------------------|----------------|
| `dreamer` | Knowledge Intake + Distiller, Validator, Router (legacy) | Reasoning — quality matters | ✅ |
| `graphify` | Entity/relationship extraction during indexing | Volume — cost matters | — |
| `vision` | Screenshot description (Phase 10) | Requires a multimodal model | — |
| `synthesis` | P2P Dialectic Synthesis | Critical reasoning — decides truth | ✅ |
| `planner` | Goal decomposition (`sinapse_plan_goal`, `scripts/planner.py`) | Structural reasoning; inherits from `HIVE_DREAMER_*` | — |
| `claude_mem` | `claude_mem_bridge.py` bridge (K4) — classifies `knowledge_type` | Cheap and fast; inherits from the Dreamer if undefined | — |
| `session_summarizer` (K5) | `session_consolidator.py` — session summary | Small/fast; compresses local logs | — |
| `daily_writer` (K5) | `daily_writer.py` — daily synthesis | Small or medium; aggregates the day's sessions | — |
| `weekly_synthesizer` (K5) | `weekly_synthesizer.py` — weekly synthesis | Medium/strong; crosses days, detects patterns | — |
| `monthly_synthesizer` (K5) | `monthly_synthesizer.py` — monthly synthesis | Strong; produces goals, drift, risks | — |
| `yearly_synthesizer` (K5) | `yearly_synthesizer.py` — yearly synthesis | Strong/offline batch; historical memory, principles | — |
| `alias_miner` | Alias (slug) mining | Cheap | — |
| `topic_router` | Routing facts to the temporal lobe | Cheap | — |
| `sector_classifier` | Cross-project sector (Diencephalon) | Cheap | — |
| `drift_detector` | Drift detection (>90d → cold archive) | Cheap | — |
| `decision_promoter` | Decision promotion to the Frontal Cortex | Short reasoning | — |
| `project_synthesizer` | Project synthesis | Medium/strong | — |
| `pattern_distiller` | Pattern distillation to `cerebelo/padroes/` | Medium reasoning | — |
| `conflict_detector` | Conflict detection in the Insula | Cheap | — |
| `graphiti` | Graphiti/FalkorDB causal extraction | Cheap | — |
| `lightrag` | LightRAG extraction (entities + relationships) | local `qwen2.5:3b` | — |
| `reranker` (optional, §31.1) | Local lexical rerank via `HIVE_RETRIEVAL_RERANKER=1`; strong local cross-encoder via `HIVE_RERANKER_PROVIDER/MODEL` + extra `reranker` | Small local; off by default in `local-min` | — |

**Cadence rule (K5):** session and daily may use small models (local compression); weekly uses medium/strong models; monthly and yearly **must not** be silently downgraded without warning. **Fail-closed:** a role without its own model and without Dreamer inheritance registers an auditable failure and does not fabricate synthesis.

### Configuration per role

```bash
# In .env — minimal case: only the Dreamer (all roles inherit from it)
HIVE_DREAMER_PROVIDER=google
HIVE_DREAMER_MODEL=gemini-2.0-flash

# Differentiated case: cheap extraction in Graphify + local fallback in the Dreamer
HIVE_GRAPHIFY_PROVIDER=ollama
HIVE_GRAPHIFY_MODEL=qwen2.5-coder:3b
HIVE_DREAMER_FALLBACK_PROVIDER=ollama
HIVE_DREAMER_FALLBACK_MODEL=qwen2.5-coder:7b
```

`setup-brain.py`/`setup-brain.sh` provides an interactive UI that asks **which role to configure**, shows the current value (or "inherits from Dreamer"), offers an optional fallback flow, lists models by provider (real-time API), tests connectivity before saving, detects available balance (DeepSeek, OpenRouter), and **explicitly recommends the model per cadence** when configuring `session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer` or `yearly_synthesizer`.

---

## 3. Hive-Dreamer — supported providers

The Dream Cycle uses LLMs for: Distiller (fact extraction), Validator (quality checking), Router (Atlas classification) and Dialectic Synthesis (P2P conflict resolution).

### 3.1 Provider table

| Provider | Authentication | Endpoint | Example model |
|----------|--------------|----------|-------------------|
| `google` | OAuth Device Flow | AI Studio / Vertex | `gemini-2.0-flash` |
| `antigravity` | native `agy` token in `~/.gemini/antigravity-cli/antigravity-oauth-token` | `agy` CLI | `gemini-3.5-flash`, `gemini-3.1-pro`, `claude-sonnet-4-6`, `gpt-oss-120b-maas` |
| `gemini-cli` | Gemini CLI OAuth / VS Code extension | Code Assist `cloudcode-pa` | `gemini-2.5-flash`, `gemini-3.1-flash-lite` |
| `openai` | Bearer token | api.openai.com | `gpt-4o`, `gpt-4.1-mini` |
| `anthropic` | Bearer token | api.anthropic.com | `claude-fable-5`, `claude-haiku-4-5` |
| `deepseek` | Bearer token | api.deepseek.com | `deepseek-v3`, `deepseek-r1` |
| `huggingface` | Bearer token | api-inference.huggingface.co | `meta-llama/Llama-3-8b-instruct` |
| `qwen` | Bearer token | dashscope.aliyuncs.com | `qwen-turbo`, `qwen-plus` |
| `nvidia` | Bearer token | integrate.api.nvidia.com | `meta/llama-3.3-70b-instruct` |
| `openrouter` | Bearer token | openrouter.ai/api/v1 | `google/gemini-flash-1.5` |
| `lmstudio` | No auth (local) | localhost:1234/v1 | model loaded in LM Studio |
| `ollama` | No auth (local) | localhost:11434/v1 | `qwen2.5-coder:3b`, `llama3.2` |

`antigravity` and `gemini-cli` do not use the legacy `google` provider. The preferred operational path for Antigravity is the native `agy` token; Gemini CLI OAuth remains supported only for the `gemini-cli`/Code Assist provider.

---

## 4. Structured Output (Pydantic)

All LLM calls in the Dream Cycle use JSON Schema derived from Pydantic models:

```
LLM call:
  input:  observation text + system prompt with JSON schema
  output: JSON → model_validate_json(response) → typed object

  If validation fails:
    → Distiller retries (max 2x)
    → If it persists: archived=2 (quarantine)
```

This guarantees that any provider (local Ollama or cloud Anthropic) produces the same processable structure.

### Handling reasoning models for structured output (v3.10.1)

Reasoning models (`qwen3.5:397b`, `gpt-oss-120b`) **ignore** strict `json_schema` and leak chain-of-thought into the content. The applied fix:

```text
reasoning_effort=none
+ json_object
+ retry on structured_output_not_json / schema_invalid
```

That is: for structured output, the reasoning model runs with `reasoning_effort=none` (no embedded chain-of-thought in the response), forces `json_object` as the response format, and retries on validation when the output is not JSON or violates the schema. This isolates reasoning from structure and avoids contaminating the content field.

---

## 5. Model Gateway (canonical LLM execution layer)

The Model Gateway is the **only** layer that executes LLM calls. It reads the legacy role configuration (`HIVE_{ROLE}_PROVIDER`/`MODEL`/`FALLBACK*` in `.env`) via `core.auth.PROVIDERS_CONFIG`, composes it with optional overrides from `config/model-gateway.yaml`, selects a `ModelProfile` per role + required capability and dispatches to a provider adapter.

```
Call site of Hive-Mind (Promotion Layer, Dream Cycle, ...)
  → core/llm_client.call_llm_with_fallback  (wrapper, R4)
      → core/model_gateway.ModelGateway.from_combined_config()
      → core/model_registry.ModelRegistry.from_combined_config()
          reads:
            core/auth.PROVIDERS_CONFIG (base_url, env_var, auth_type)
            HIVE_{ROLE}_PROVIDER/MODEL/FALLBACK* (primary, fallback, fallback2)
            config/model-gateway.yaml (capabilities, cost_mode, role overrides)
      → integrations/model_gateway/<adapter>
          (openai_compatible / litellm / native / lmstudio /
           llamacpp / vllm / sglang)
```

`core/llm_client.call_llm_with_fallback` is now a thin wrapper that delegates here — it is no longer a parallel execution path.

### 5.1 Vocabulary

- **Provider** (legacy, in `PROVIDERS_CONFIG`) — logical backend name configured in `.env`.
- **Adapter** (runtime, in `integrations/model_gateway/`) — the code that talks to the provider's HTTP API: `native`, `openai_compatible`, `litellm`, `lmstudio`, `llamacpp`, `vllm`, `sglang`.
- **Model profile** (`ModelProfile` in `core/model_registry.py`) — one per `(role, level)` triple, with `level ∈ {primary, fallback, fallback2}`.
- **Role** — logical purpose declared by the call site (`dreamer`, `graphify`, `vision`, `synthesis`, `claude_mem`, ...).
- **Adapter hint** — runtime adapter family to which a legacy provider maps (e.g., `ollama → openai_compatible`, `gemini-cli → native`). `unsupported_explicit` when there is no hint.

### 5.2 Operating modes (R5)

`MODEL_GATEWAY_MODE` is the canonical switch. `MODEL_GATEWAY_ENABLED` remains as a deprecated shim. `HIVE_FORCE_LEGACY_LLM` is the emergency bypass.

| `MODEL_GATEWAY_MODE` | Behavior | Legacy fallback? |
|---|---|---|
| `auto` *(default)* | Gateway via `ModelRegistry.from_combined_config()`. If the registry fails to validate or the call fails, the wrapper logs a structured warning (`gateway_attempted=true, gateway_failed=true, legacy_fallback_used=true`) and delegates to `_legacy_call_llm_with_fallback`. | **Yes**, with an explicit warning + telemetry. Never silent. |
| `on` | Gateway mandatory. If it fails end to end, the wrapper raises a structured `RuntimeError` and NEVER falls back. | **No.** Set `HIVE_FORCE_LEGACY_LLM=true` for bypass. |
| `off` *(deprecated)* | Gateway off, `_legacy_call_llm_with_fallback` runs directly. Emits a deprecation warning. | Always. |
| `HIVE_FORCE_LEGACY_LLM=true` | Emergency bypass — overrides any `MODEL_GATEWAY_MODE`. Emits a warning on stderr. | Always. |

```bash
# config/model-gateway.env.example — copied to .env by install.sh
MODEL_GATEWAY_MODE=auto
# HIVE_FORCE_LEGACY_LLM=false   # emergency bypass; do NOT set by default
# MODEL_GATEWAY_ENABLED=false   # DEPRECATED; use MODEL_GATEWAY_MODE

LMSTUDIO_BASE_URL=http://localhost:1234/v1
LLAMACPP_BASE_URL=http://localhost:8080/v1
VLLM_BASE_URL=http://localhost:8000/v1
SGLANG_BASE_URL=http://localhost:30000/v1
LITELLM_BASE_URL=http://localhost:4000/v1
LITELLM_API_KEY=
```

### 5.3 Provider → adapter mapping (R2)

`core/model_registry.PROVIDER_ADAPTER_HINT` is the single source of truth:

| Legacy provider | Runtime adapter |
|---|---|
| `openai`, `openrouter`, `deepseek`, `nvidia`, `qwen`, `omniroute`, `ollama`, `ollama-cloud`, `anthropic` | `openai_compatible` |
| `google`, `gemini`, `huggingface` | `litellm` |
| `gemini-cli`, `antigravity` | `native` (legacy bridge) |
| `lmstudio` | `lmstudio` |
| `llamacpp`, `vllm`, `sglang` | dedicated (already delivered) |

Every provider in `PROVIDERS_CONFIG` is mapped to an adapter or reported as `unsupported_explicit` in `ModelRegistry.validate()`.

### 5.4 Configuration sources

The registry combines three sources, in this order of priority:

1. **`HIVE_{ROLE}_PROVIDER/MODEL` in `.env`** — primary, fallback, fallback2 per role. Inherited roles fall back to `HIVE_DREAMER_*` as before.
2. **`PROVIDERS_CONFIG` in `core/auth.py`** — base URL, env var, auth type per legacy provider.
3. **`config/model-gateway.yaml`** — OPTIONAL override layer: `providers.<name>` (adapter_hint, cost_mode, capabilities) and `roles.<name>` (require, prefer, priority, cost_mode, context_window, max_output_tokens). `roles.<name>.provider`/`model` are ignored unless `role_override: true`.

### 5.5 Known limitations

- **LiteLLM direct SDK mode out of scope** — only the HTTP proxy mode.
- **Streaming not implemented** — `chat()` always returns the full response.
- **JSON Schema → Pydantic is best-effort and flat** — internals of nested objects/arrays are accepted as opaque `dict`/`list`.
- **Vision delegated to the legacy path (R8)** — when `image_path` is passed, the wrapper emits `legacy_vision_bridge_used=true`.
- **Basic SSRF hardening** — blocks non-http(s) schemes and AWS/GCP metadata addresses; no DNS-rebinding protection.
- **Tool-calling declared but not exercised end to end.**

---

## 6. Fallback chain

Each role resolves to a `(primary, fallback, fallback2)` chain in that strict order, mirroring the legacy `core/llm_client.py`.

### 6.1 Error classification and fallback policy

`core/llm_client.py` (`classify_llm_error()` + `call_llm_with_fallback()`):

| Error class | Examples | Action |
|----------------|----------|------|
| **Transient** | timeout, connection error, HTTP 429, 5xx | retry with backoff `min(2^n, 8s)` → fallback (if defined) → quarantine `archived=2` |
| **Auth/balance** | HTTP 401/402/403, "insufficient balance/quota" | **direct fallback, no retry** → otherwise quarantine + warning |
| **Pydantic validation** | LLM output failed schema validation | retry on the **same model** → quarantine. **NEVER triggers fallback** (quality problem, not availability) |
| **Unknown** | any other exception | treated as transient |

### 6.2 Gateway R6 rules

- **Explicit and logged** — every attempt is recorded via `record_call` (legacy) or `record_gateway_attempt`/`record_gateway_failure`/`record_legacy_fallback_used` (gateway).
- **Skips disabled profiles** automatically.
- **Detects cycles** in the YAML `fallback_chain` and stops, instead of looping.
- **Never returns fabricated success** — if all models in the chain fail, the gateway returns `ok=False` with classified `error`/`error_chain`; the legacy path raises `LLMChainFailure` preserving `primary_exc` and `fallback_exc`.
- **Validation errors never trigger fallback** (R6 §1) — the caller retries on the same model up to `max_retries`, then raises `LLMValidationError`.
- **Auth / 401 / 403 / 402 / balance** bypass retries and go directly to the next pair (R6 §3).
- **429 / 5xx / timeouts** retry with exponential backoff (8s ceiling), then fallback (R6 §2/§4).

### 6.3 Escape hatches (rollback to the legacy llm_client)

1. **Per process** — `HIVE_FORCE_LEGACY_LLM=true` bypasses the entire gateway for every call. Recovery path when the gateway misbehaves in production. Emits a warning on stderr.
2. **Whole mode** — `MODEL_GATEWAY_MODE=off` (deprecated) turns the gateway off for the process.

The legacy `core/llm_client.py` is preserved verbatim as `_legacy_call_llm_with_fallback` to maintain the callers' contract (`LLMValidationError`, `LLMChainFailure` with `chain`, `primary_exc`, `fallback_exc`).

---

## 7. Embeddings

### 7.1 Embedding model

| Model | Dimensions | Use | Where |
|--------|-----------|-----|------|
| `snowflake-arctic-embed2:latest` | 1024 | semantic KNN search in the UMC | sqlite-vec HNSW (env `HNSW_DIM=1024`) |
| `snowflake-arctic-embed2:latest` | 1024 | semantic search of observations | sqlite-vec HNSW |
| `snowflake-arctic-embed2:latest` | 1024 | memory embeddings for LightRAG | `core/lightrag_index.py` (P4) |

The model is loaded via **local Ollama** (`OLLAMA_EMBED_MODEL=snowflake-arctic-embed2:latest`), exposed by `OllamaEmbedder` in `core/database.py:get_embedder()`. It does not require an API key. Vectors persist in the `search_vec` virtual table (vec0, 1024d) inside `hive_mind.db`. `core/hnsw_index.py` maintains an incremental HNSW index (via `hnswlib`) over the same 1024d vectors.

**Why snowflake-arctic-embed2 (1024d)?**

- Maintains the 1024d dimension already used by sqlite-vec, HNSW, LightRAG and Graphiti.
- In local tests (2026-06-27), had 0 NaNs on problematic triggers.
- Had better PT↔EN separation vs unrelated content than `bge-m3` and `qwen3-embedding:0.6b`.
- Local Ollama removes cloud API dependency for embeddings.

### 7.2 VectorBackend and collection identity (K1/K10)

`VectorBackend` operates over **seven canonical collections** with identity `(name, embedding_model, dim)`. Embedding model/dimension are part of the contract — a collection loads `snowflake-arctic-embed2:latest` at **1024d** unless overridden by env.

```text
collection carries (embedding_model, dim) in the identity
upsert with a diverging model: rejected or goes to a new collection (never mixed)
migration: online re-embed per workspace, dual-write (old+new model) until cutover
metric: vectors_model_mismatch = 0 within a collection
```

**Typical embedding migration plan:**

1. Create a new collection with `(name, new_model, new_dim)`.
2. Dual-write: new vectors go to both old and new collections during cutover.
3. Backfill old embeddings in batch (offline) into the new collection.
4. Cutover: `sinapse_query` and `RetrievalRouter` query the new collection.
5. The old collection enters `forget` (`superseded`) — tombstone, no silent physical delete.

### 7.3 Relevant environment variables

| Variable | Function | Default |
|---|---|---|
| `HNSW_DIM` | HNSW dimension (sqlite-vec) | `1024` |
| `OLLAMA_EMBED_MODEL` | Ollama model for embeddings | `snowflake-arctic-embed2:latest` |
| `HIVE_RETRIEVAL_RERANKER` | enables deterministic lexical rerank in the `RetrievalRouter` via the LlamaIndex adapter (§31.1) | off |
| `HIVE_RERANKER_PROVIDER`/`HIVE_RERANKER_MODEL` | enables a strong local cross-encoder with the extra `reranker` (`uv sync --extra reranker`) | off |
| `HIVE_PROMOTION_BUDGET_*` | promotion cost ceiling per workspace (§30.5) | no ceiling |

---

## 8. Graphify — indexing models

| Model | Provider | Backend flag | Quality |
|--------|----------|-------------|-----------|
| `gemini-2.5-flash` | Google AI | `--backend gemini` | High (cloud) |
| `qwen2.5-coder:3b` | local Ollama | `--backend ollama` | Medium (local, free) |
| `tree-sitter + regex` | Deterministic | `--backend ast` | Structural (no LLM) |

`scripts/build-graph.sh` reads `HIVE_GRAPHIFY_PROVIDER/MODEL` from `.env` (inheriting from `HIVE_DREAMER_*` if absent) and maps the provider to the Graphify backend. With no config defined, it uses the deterministic tree-sitter + regex fallback (AST-only, always works).

---

## 9. LightRAG — entity extraction + graph (P4)

LightRAG is the **second extractor** alongside Graphify: while Graphify extracts entities from **code** (AST + LLM), LightRAG extracts entities and relationships from **memories consolidated** by the Dream Cycle (free text, decisions, learnings).

```
  Dream Cycle (Stage 3 — Synthesis)
       │ synthesis.final_content
       ▼
  core/lightrag_index.py:index_memory()
       │
       ├──> LightRAG working_dir: claude-mem/data/lightrag/
       │    ├── graph.npz (NetworkX)         — entities + edges
       │    ├── vdb_chunks.json              — chunk embeddings (snowflake-arctic-embed2)
       │    ├── vdb_entities.json            — entity embeddings
       │    └── vdb_relationships.json       — relationship embeddings
       ▼
  sinapse_rag_query(question, mode="hybrid")
       ▼
  MCP: returns relevant entities + relationships + chunks
```

| Model | Provider | Justification |
|--------|----------|---------------|
| `qwen2.5:3b` | local Ollama | ~1.9 GB · PT/EN multilingual · extracts entities/relationships better than `granite3-dense:2b` in real tests |

- No remote fallback: if the local Ollama model fails, `index_memory` returns `False` and the Dream Cycle continues.
- `.env` (`HIVE_LIGHTRAG_MODEL`) overrides the default; `qwen2.5:7b` can be used on machines with more VRAM.

**Query modes (`sinapse_rag_query`):** `naive` (simple vector search), `local` (mentioned entities + neighbors), `global` (edge traversal), `hybrid` (default — best for multi-hop questions).

---

## 10. NeuralMemory — no LLM

NeuralMemory uses **spreading activation** — a purely mathematical algorithm, with no LLM call (TF-IDF + cosine → activation propagated across 24 edge types, 0.7 attenuation per hop).

---

## 11. Models NOT used (and why)

| Model | Why not |
|--------|-------------|
| GPT-4 / Claude Opus | Overkill for extraction; prohibitive cost for daily indexing |
| Multilingual BERT | Heavier than Qwen 2.5 Coder 3B for the same NER |
| Proprietary fine-tunes | Maintenance complexity incompatible with model sovereignty |
| OpenAI Embeddings (text-embedding-3) | API dependency; local snowflake-arctic-embed2 via Ollama is sufficient |
| ChromaDB + all-MiniLM-L6-v2 | Replaced by sqlite-vec + snowflake-arctic-embed2 (1024d) in the UMC |
| all-MiniLM-L6-v2 (384d) | Replaced by the local 1024d embedding in Ollama |

---

## 12. Capability matrix per scenario

| Scenario | Graphify (code) | LightRAG (text) | Embeddings | Dream Cycle | Recall |
|---------|-------------------|------------------|-----------|-------------|--------|
| Cloud (API keys) | configured provider | Qwen 2.5 3B (local) | snowflake-arctic-embed2 (local) | configured provider | Spreading Activation |
| Local (Ollama) | Qwen 2.5 Coder 3B | Qwen 2.5 3B (local) | snowflake-arctic-embed2 (local) | configured Ollama | Spreading Activation |
| Offline (no Ollama) | tree-sitter + regex | Unavailable (best-effort) | Unavailable | Unavailable | Spreading Activation |
| Minimal (no Python) | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable |

The system degrades gracefully: even in the minimal scenario, the Obsidian vault remains readable and FTS5 searches keep working. LightRAG is the first to fail in minimal environments — `index_memory` is best-effort (try/except) and dialectic synthesis is never aborted by a graph failure.

---

## 13. Secret governance and telemetry (R10)

- `record_call` accepts only metadata fields — its signature has no `prompt`/`content`/`response` parameter.
- New hooks follow the same discipline: no payload, secrets redacted via `core.redactor.redact_for_export` before any write.
- API keys are resolved from `ModelProfile.api_key_env` at call time (`profile.api_key()`) — never stored on the profile object, never logged.
- `record_gateway_attempt`/`record_gateway_failure`/`record_legacy_fallback_used`/`record_setup_brain_role_configured` maintain the same rigor.

---

## 14. Cross-references

- [`data-pipeline.md`](data-pipeline.md) — the complete data flow that consumes these models (K3/K4/K5/K6/K7).
- [`architecture.md`](architecture.md) — §24 (VectorBackend), §26 (RetrievalRouter), §27 (K3/K4), §29 (cadence), §30 (workspace/federation), §31 (rerank/forget).
- [`runtime.md`](runtime.md) — services and jobs that run the Dream Cycle and `sinapse-consolidate`.
- [`installation.md`](installation.md) — `setup-brain`, agent registration, `install.sh` and the gateway env block.
- [`operations.md`](operations.md) — fallback operation, quarantine and escape hatches (`HIVE_FORCE_LEGACY_LLM`).
- [`observability.md`](observability.md) — `ModelGateway.health()`, benchmark CLI (`model_benchmark.py`), gateway telemetry.
- Source documents: [`02-ai-models.md`](02-ai-models.md), [`ai-models.md`](ai-models.md), [`03-data-pipeline.md`](03-data-pipeline.md).
