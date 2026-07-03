# 02 — AI Models and Providers

> **Hive-Mind v3.0.0** — Hive-Dreamer models, embeddings, providers, and fallback chain.
> Last reviewed: 2026-06-30 · Embeddings 1024d snowflake-arctic-embed2 · LightRAG qwen2.5:3b (P4) · **K5 cadence (session/daily/weekly/monthly/yearly) with dedicated roles**

---

## 1. Overview

Hive-Mind **does not train proprietary models**. It uses third-party models in three distinct contexts, all role-configurable via `HIVE_{ROLE}_*`:

1. **Graphify** — structural vault indexing (entity and relation extraction)
2. **Hive-Dreamer** — offline semantic consolidation (Dream Cycle, K3 Knowledge Intake + K4 Promotion Layer)
3. **Cadence** — cadence writers (K5: `session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer`, `yearly_synthesizer`), each with its own model or Dreamer inheritance

In all cases, model choice is **user-configurable** through environment variables and the `setup-brain.sh` script. No model is hardcoded.

---

## 2. Hive-Dreamer — 10 Supported Providers

The Dream Cycle uses LLMs for: Distiller (fact extraction), Validator (quality verification), Router (Atlas classification), and Dialectical Synthesis (P2P conflict resolution). From K3/K4 onward, the promotion pipeline is **layered** (Knowledge Intake + Promotion Layer; see [`01-architecture.md` §27](01-architecture.md#27-knowledge-promotion-pipeline-k3k4)).

### 2.1 Role-based configuration

Each LLM-consuming role has its own configuration, with Dreamer inheritance and opt-in fallback (full rules in [`01-architecture.md`](01-architecture.md) §11.1 and ADR-009):

```bash
# In .env — minimal case: only Dreamer (all roles inherit from it)
HIVE_DREAMER_PROVIDER=google
HIVE_DREAMER_MODEL=gemini-2.0-flash

# Differentiated case: cheap extraction in Graphify + local fallback in Dreamer
HIVE_GRAPHIFY_PROVIDER=ollama
HIVE_GRAPHIFY_MODEL=qwen2.5-coder:3b
HIVE_DREAMER_FALLBACK_PROVIDER=ollama
HIVE_DREAMER_FALLBACK_MODEL=qwen2.5-coder:7b
```

### 2.1.0 Canonical roles (constant `HIVE_LLM_ROLES` in `core/auth.py`)

The roles below are canonical in code (case-insensitive, `-` becomes `_`); empty or non-string names raise `ValueError`. Resolution is centralized in `get_role_config()` (`core/auth.py`).

| Role | Used by | Call profile |
|-------|----------|-------------------|
| `dreamer` | Knowledge Intake + Distiller, Validator, Router (legacy) | Reasoning — quality matters |
| `graphify` | Entity/relation extraction during indexing | Volume — cost matters |
| `vision` | Screenshot description (Phase 10) | Requires multimodal model |
| `synthesis` | P2P Dialectical Synthesis | Critical reasoning — decides truth |
| `planner` | Goal decomposition (`sinapse_plan_goal`, `scripts/planner.py`) | Structural reasoning — generates goal tree; inherits from `HIVE_DREAMER_*` |
| `claude_mem` | `claude_mem_bridge.py` bridge (K4) — classifies `knowledge_type` | Cheap and fast; inherits from Dreamer if undefined |
| **`session_summarizer`** (K5) | `session_consolidator.py` — session summary | Small/fast; compresses local logs |
| **`daily_writer`** (K5) | `daily_writer.py` — daily synthesis | Small or medium; aggregates daily sessions |
| **`weekly_synthesizer`** (K5) | `weekly_synthesizer.py` — weekly synthesis | **Medium/strong**; crosses multiple days, detects patterns |
| **`monthly_synthesizer`** (K5) | `monthly_synthesizer.py` — monthly synthesis | **Strong**; produces goals, drift, risks |
| **`yearly_synthesizer`** (K5) | `yearly_synthesizer.py` — yearly synthesis | **Strong/offline batch**; historical memory, principles |
| `alias_miner` | Alias mining (slugs) | Cheap |
| `topic_router` | Fact routing to the temporal lobe | Cheap |
| `sector_classifier` | Cross-project sector (Diencephalon) | Cheap |
| `drift_detector` | Drift detection (>90d → cold archive) | Cheap |
| `decision_promoter` | Decision promotion to the Frontal Cortex | Short reasoning |
| `project_synthesizer` | Project synthesis | Medium/strong |
| `pattern_distiller` | Pattern distillation to `cerebelo/padroes/` | Medium reasoning |
| `conflict_detector` | Conflict detection in the Insula | Cheap |
| `graphiti` | Graphiti/FalkorDB causal extraction | Cheap |
| `lightrag` | LightRAG extraction (entities + relations) | local `qwen2.5:3b` (see §4) |
| **`reranker`** (optional, §31.1) | Local lexical rerank via `HIVE_RETRIEVAL_RERANKER=1`; strong local cross-encoder opt-in via `HIVE_RERANKER_PROVIDER/MODEL` + `reranker` extra | Small local; off by default in `local-min` |

**Cadence rule** (K5): session and daily can use small models (local compression); weekly uses medium/strong models; monthly and yearly **must not** be automatically downgraded without warning. Fail-closed: a role with no own model and no `dreamer` inheritance records an auditable failure and does not fabricate synthesis.

The `setup-brain.py` / `setup-brain.sh` script provides an interactive UI that asks **which role to configure**, shows the current value (or "inherits from Dreamer"), and offers optional fallback flow (Enter skips). It also:
- lists available models per provider (via real-time API)
- tests connectivity before saving
- detects and displays available balance (DeepSeek, OpenRouter)
- **explicitly recommends the model per cadence** when configuring `session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer`, or `yearly_synthesizer`

### 2.1.1 Error classification and fallback policy

Implemented in `core/llm_client.py` (`classify_llm_error()` + `call_llm_with_fallback()`):

| Error class | Examples | Action |
|----------------|----------|------|
| **Transient** | timeout, connection error, HTTP 429, 5xx | retry with backoff `min(2^n, 8s)` → fallback (if defined) → quarantine `archived=2` |
| **Auth/balance** | HTTP 401/402/403, "insufficient balance/quota", insufficient balance | **direct fallback, no retry** → otherwise quarantine + warning |
| **Pydantic validation** | LLM output failed schema validation | retry on the **same model** → quarantine. **NEVER triggers fallback** (quality issue, not availability) |
| **Unknown** | any other exception | treated as transient |

When fallback is triggered, logs record: `[Fallback] Role 'X': switching from A/B to C/D (reason)`. In all final failure paths, the observation goes to quarantine (`archived=2`) — **nothing is lost** (ADR-008).

### 2.2 Provider Table

| Provider | Authentication | Endpoint | Model Example |
|----------|-------------|----------|-------------------|
| `google` | OAuth Device Flow | AI Studio / Vertex | `gemini-2.0-flash` |
| `antigravity` | Native `agy` token in `~/.gemini/antigravity-cli/antigravity-oauth-token` | `agy` CLI | `gemini-3.5-flash`, `gemini-3.1-pro`, `claude-sonnet-4-6`, `gpt-oss-120b-maas` |
| `gemini-cli` | Gemini CLI / Google VS Code extension OAuth | Code Assist `cloudcode-pa` | `gemini-2.5-flash`, `gemini-3.1-flash-lite` |
| `openai` | Bearer token | api.openai.com | `gpt-4o`, `gpt-4.1-mini` |
| `anthropic` | Bearer token | api.anthropic.com | `claude-fable-5`, `claude-haiku-4-5` |
| `deepseek` | Bearer token | api.deepseek.com | `deepseek-v3`, `deepseek-r1` |
| `huggingface` | Bearer token | api-inference.huggingface.co | `meta-llama/Llama-3-8b-instruct` |
| `qwen` | Bearer token | dashscope.aliyuncs.com | `qwen-turbo`, `qwen-plus` |
| `nvidia` | Bearer token | integrate.api.nvidia.com | `meta/llama-3.3-70b-instruct` |
| `openrouter` | Bearer token | openrouter.ai/api/v1 | `google/gemini-flash-1.5` |
| `lmstudio` | No auth (local) | localhost:1234/v1 | model loaded in LM Studio |
| `ollama` | No auth (local) | localhost:11434/v1 | `qwen2.5-coder:3b`, `llama3.2` |

`antigravity` and `gemini-cli` do not use the legacy `google` provider. The
preferred operational path for Antigravity is the native `agy` token; Gemini
CLI OAuth remains supported only for the `gemini-cli`/Code Assist provider
while that endpoint still responds for the account.

### 2.3 Structured Output (Pydantic)

All LLM calls in the Dream Cycle use JSON Schema derived from Pydantic models:

```
LLM call:
  input:  observation text + system prompt with JSON schema
  output: JSON → model_validate_json(response) → typed object

  If validation fails:
    → Distiller retries (max 2x)
    → If it persists: archived=2 (quarantine)
```

This ensures that any provider (local Ollama or cloud Anthropic) produces the same processable structure.

---

## 3. Graphify — Indexing Models

### 3.1 Entity and Relation Extraction

| Model | Provider | Backend Flag | Quality |
|--------|----------|-------------|-----------|
| `gemini-2.5-flash` | Google AI | `--backend gemini` | High (cloud) |
| `qwen2.5-coder:3b` | Local Ollama | `--backend ollama` | Medium (local, free) |
| `tree-sitter + regex` | Deterministic | `--backend ast` | Structural (no LLM) |

**Backend selection (via `graphify` role):**

`scripts/build-graph.sh` reads `HIVE_GRAPHIFY_PROVIDER/MODEL` from `.env` (inheriting from `HIVE_DREAMER_*` if absent) and maps provider to Graphify backend:

```
HIVE_GRAPHIFY_* (or inherited from Dreamer) defined?
    │
    ├── Yes → maps provider → backend:
    │     google → gemini       anthropic → claude
    │     openai → openai       deepseek  → deepseek
    │     ollama → ollama       lmstudio  → ollama (OLLAMA_BASE_URL=127.0.0.1:1234/v1)
    │     huggingface/qwen/nvidia/openrouter → no equivalent,
    │                                          AST-only with warning
    │
    └── No → deterministic fallback: tree-sitter + regex (AST-only)
              (extracts functions, classes, imports, WikiLinks, YAML frontmatter)
              (always works, no external dependency)
```

### 3.2 Embeddings (sqlite-vec, 1024 dimensions — Ollama snowflake-arctic-embed2)

| Model | Dimensions | Use | Where |
|--------|-----------|-----|------|
| `snowflake-arctic-embed2:latest` | 1024 | Semantic KNN search in UMC | sqlite-vec HNSW (env `HNSW_DIM=1024`) |
| `snowflake-arctic-embed2:latest` | 1024 | Semantic observation search | sqlite-vec HNSW |
| `snowflake-arctic-embed2:latest` | 1024 | Memory embeddings for LightRAG | `core/lightrag_index.py` (P4) |

The model is loaded via **local Ollama** (`OLLAMA_EMBED_MODEL=snowflake-arctic-embed2:latest`), exposed by `OllamaEmbedder` in `core/database.py:get_embedder()`. It does not require an API key. Vectors are persisted in virtual table `search_vec` (vec0, 1024d) inside `hive_mind.db`. Migration from legacy 384d to 1024d happened in P0; switching from `bge-m3` to `snowflake-arctic-embed2` keeps 1024d and only requires re-embedding/index rebuild.

Module `core/hnsw_index.py` maintains an incremental HNSW index (via `hnswlib`) over the same 1024d vectors. The index is updated on each ingestion without full rebuild.

**Why snowflake-arctic-embed2 (1024d)?**
- Maintains the 1024d dimension already used by sqlite-vec, HNSW, LightRAG, and Graphiti.
- In local tests on 2026-06-27, it had 0 NaNs in problematic triggers.
- It had better PT↔EN separation vs unrelated content than `bge-m3` and `qwen3-embedding:0.6b`.
- Local Ollama removes cloud API dependency for embeddings.

---

## 4. LightRAG — Entity Extraction + Knowledge Graph (P4)

LightRAG (HKUDS/EMNLP 2025) is the **second extractor** alongside Graphify: while Graphify extracts entities from **code** (AST + LLM), LightRAG extracts entities and relations from **consolidated memories** produced by the Dream Cycle (free text, decisions, learnings).

```
  Dream Cycle (Stage 3 — Synthesis)
       │
       │ synthesis.final_content
       ▼
  core/lightrag_index.py:index_memory()
       │
       ├──> LightRAG working_dir: claude-mem/data/lightrag/
       │    ├── graph.npz (NetworkX)         — entities + edges
       │    ├── vdb_chunks.json              — chunk embeddings (snowflake-arctic-embed2)
       │    ├── vdb_entities.json            — entity embeddings
       │    └── vdb_relationships.json       — relation embeddings
       ▼
  sinapse_rag_query(question, mode="hybrid")
       │
       ▼
  MCP: returns relevant entities + relations + chunks
```

**LightRAG LLM model (local by design):**
| Model | Provider | Rationale |
|--------|----------|---------------|
| `qwen2.5:3b` | Local Ollama | ~1.9 GB · PT/EN multilingual · extracts entities/relations from prose better than `granite3-dense:2b` in real tests · fits alongside 1024d embedder on local dev machine |

- No remote fallback: if local Ollama model fails, `index_memory` returns `False` and Dream Cycle continues.
- With model-switch UI in `setup-brain.sh`: menu `Local extraction (Graphiti/LightRAG)` writes `HIVE_LIGHTRAG_MODEL`.
- `.env` (`HIVE_LIGHTRAG_MODEL`) overrides default for local dev/production; `qwen2.5:7b` can be used on machines with more VRAM.
- `install.sh` pulls `qwen2.5:3b` as a sufficiently small local model for Graphiti/LightRAG.

**Query mode (`sinapse_rag_query`):**
| Mode | Behavior |
|------|---------------|
| `naive` | Simple vector search (similar to KNN) |
| `local` | Entities mentioned in query + their neighbors |
| `global` | Edge traversal (relations between entities) |
| `hybrid` (default) | Combines local + global — best for multi-hop questions |

**Practical difference vs FTS5 + KNN:**
- FTS5: exact keyword matching (does not understand synonyms or context)
- KNN: semantic similarity between query and document (does not understand relational structure)
- LightRAG: understands **relationships** — "who created X?", "which tools does Y use?", "what is the relation between A and B?"

**Validation:** current real tests use `qwen2.5:3b` by default in `core/lightrag_index.py`, with structured schema (`name`, `type`, `description`, `source`, `target`, `keywords`) to prevent empty entities and relation descriptions.

---

## 4. NeuralMemory — No LLM

NeuralMemory (`neural-memory/`) uses **spreading activation** — a purely mathematical algorithm, with no LLM call:

```
Input: query string
   ↓
TF-IDF + Cosine Similarity → initial candidate concepts
   ↓
Spreading Activation:
   for each concept with activation > threshold:
     propagate activation to neighbors via 24 edge types
     (causes, prevents, requires, is_a, part_of, enables, ...)
   attenuation of 0.7 per hop
   ↓
Output: list of activated concepts with activation score
```

The edge weights (24 relation types) were defined based on cognitive psychology and do not change dynamically.

---

## 5. Models NOT Used (and why)

| Model | Why not |
|--------|------------|
| GPT-4 / Claude Opus | Overkill for entity extraction; prohibitive cost for daily indexing |
| Multilingual BERT | Heavier than Qwen 2.5 Coder 3B for the same NER result |
| Proprietary fine-tunes | Maintenance complexity incompatible with model-sovereignty principle |
| OpenAI Embeddings (text-embedding-3) | API dependency; local snowflake-arctic-embed2 via Ollama is sufficient |
| ChromaDB + all-MiniLM-L6-v2 | Replaced by sqlite-vec + built-in snowflake-arctic-embed2 (1024d) in UMC (eliminates separate process) |
| all-MiniLM-L6-v2 (384d) | Replaced by local 1024d embedding in Ollama — multilingual and better recall |

---

## 6. Capability Matrix by Scenario

| Scenario | Graphify (code) | LightRAG (text) | Embeddings | Dream Cycle | Recall |
|---------|-------------------|------------------|-----------|-----------|--------|
| Cloud (API keys) | Configured provider | Qwen 2.5 3B (local) | snowflake-arctic-embed2 (local) | Configured provider | Spreading Activation |
| Local (Ollama) | Qwen 2.5 Coder 3B | Qwen 2.5 3B (local) | snowflake-arctic-embed2 (local) | Configured Ollama | Spreading Activation |
| Offline (without Ollama) | tree-sitter + regex | Unavailable (best-effort) | Unavailable | Unavailable | Spreading Activation |
| Minimal (without Python) | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable |

The system degrades gracefully: even in minimal scenario, the Obsidian vault remains readable and FTS5 searches keep working. LightRAG is the earliest component to fail in minimal environments — so `index_memory` is best-effort (try/except) and dialectical synthesis is never aborted due to graph failure.

---

## 7. VectorBackend and Collection Identity (K1/K10)

From the Born-Large Knowledge front, `VectorBackend` (§24 of [`01-architecture.md`](01-architecture.md#24-vectorbackend-contrato-coleções-canônicas-e-escala)) operates over **seven canonical collections** with identity `(name, embedding_model, dim)`. Embedding model/dimension are part of the contract — a collection carries `snowflake-arctic-embed2:latest` at **1024d** unless explicitly overridden by env.

### 7.1 Embedding migration contract (K10)

Changing embedding model at scale is not a one-shot script. Vector space is versioned:

```text
collection carries (embedding_model, dim) in identity
upsert with divergent model: rejected or goes to new collection (never mixed)
migration: online re-embed per workspace, dual-write (old+new model) until cutover
metric: vectors_model_mismatch (§28 of 01-architecture.md) = 0 within a collection
```

Relevant environment variables:

| Variable | Function | Default |
|---|---|---|
| `HNSW_DIM` | HNSW dimension (sqlite-vec) | `1024` |
| `OLLAMA_EMBED_MODEL` | Ollama model for embeddings | `snowflake-arctic-embed2:latest` |
| `HIVE_RETRIEVAL_RERANKER` | Enables deterministic lexical rerank in `RetrievalRouter` via LlamaIndex adapter (§31.1) | off (no rerank) |
| `HIVE_RERANKER_PROVIDER` / `HIVE_RERANKER_MODEL` | Enables strong local cross-encoder when `reranker` extra is installed (`uv sync --extra reranker`) (§31.1) | off |
| `HIVE_PROMOTION_BUDGET_*` | Promotion cost ceiling per workspace (§30.5) | no ceiling |

**Typical migration plan:**

1. Create new collection with `(name, new_model, new_dim)`.
2. Dual-write: new vectors go to old and new collections during cutover.
3. Backfill old embeddings in batch (offline) into new collection.
4. Cutover: `sinapse_query` and `RetrievalRouter` query the new collection.
5. Old collection enters `forget` (`superseded` reason, §31.2) — tombstone, no silent physical delete.

---

## 8. Phase Acceptance (K0–K10) and Real-No-Mock Criterion

The Born-Large Knowledge front uses `tests/real/` (`tests/real/service_registry.py` + hook in `tests/real/conftest.py`) and **does not count mocks as closure**. The `requires_service` marker contract:

```text
if required real service is online: run and fail if behavior fails
if required real service is offline: explicit skip with reason and named service
if test does not depend on external service: always run
```

Known services today: `ollama`, `milvus`, `falkordb`, `claude_mem`, `ragflow`. Each new real backend must register its fixture or service registry before becoming a phase gate.

Suite `./tests/run_all.sh` covers Smoke → Unit → Integration → E2E. On 2026-07-01 the repo had **706 `test_` functions in 123 files with tests**; real K9 suite (`tests/run_real_knowledge.sh`) is separate and, in validated `local-full` profile, runs real Milvus, RAGFlow, FalkorDB, claude-mem, and Ollama with 59/59 passed and 0 skipped.
