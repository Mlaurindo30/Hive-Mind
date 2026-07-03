# 03 — Data Pipeline

> **Hive-Mind v3.0.0** — Full flow: collection → real-time indexing → Dream Cycle → query → Deep Reflection → Federated Export. **Review 2026-06-30:** consolidation of the Born-Large Knowledge front (K0–K10) with Knowledge Intake (K3), Promotion Layer (K4), hierarchical cadence (K5), `DocumentPipeline` (K6), `RetrievalRouter` (K7), K8 metrics, and workspace contracts (K10). Normative reference in [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md); distilled architecture in [`01-architecture.md` §22–§31](01-architecture.md#22-arquitetura-de-conhecimento-born-large).

---

## 1. Overview

The v3.0.0 pipeline has **three** parallel flows — real-time (write→read), offline (Dream Cycle), and **documental** (`DocumentPipeline`) — plus three additional layers (HM-11, HM-12, and the K0–K10 front):

```text
  ┌────────────────────────────────────────────────────────────────────────┐
  │                         REAL-TIME FLOW                                │
  │                                                                        │
  │  Agent / Human                                                         │
  │       │                                                                │
  │       ▼                                                                │
  │  [ COLLECTION ]──── atomic write ──→ vault (cerebro/*.md)              │
  │       │                                   │                           │
  │       │                     Watcher ~2s   │                           │
  │       │                                   ▼                           │
  │       │              [ REAL-TIME INDEXING ] → hive_mind.db            │
  │       │               neurons + synapses + FTS5 + sqlite-vec 1024d     │
  │       │                           │                                   │
  │       │                           ├──→ HNSW Index (hnsw_neurons.idx)  │
  │       │                           │    (incremental, 1024d)            │
  │       │                           │                                   │
  │       │                           ├──→ causal_edges (cause→effect     │
  │       │                           │    graph between neurons)         │
  │       │                           │                                   │
  │       │                           └──→ goals (planner via             │
  │       │                                sinapse_plan_goal)             │
  │       │                                observations.goal_id / why     │
  │       │                                                                │
  │       ▼                                                                │
  │  [ QUERY ] ← RetrievalRouter (K7) → sinapse_query (Context Fusion)    │
  └────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────────┐
  │                       OFFLINE FLOW (Dream Cycle)                       │
  │                                                                        │
  │  observations (pending, archived=0)                                    │
  │       │                                                                │
  │       ▼     manual or scheduled execution                              │
  │  [ DREAM CYCLE ] ─────────────────────────────────────────────────    │
  │    Knowledge Intake (K3) → Distiller → Validator → Router (K4)        │
  │       │                                                                │
  │       ▼                                                                │
  │  Anatomical Persistence + multi-collection indexing                     │
  │  (memory_vectors / observation_vectors / summary_vectors / Graphiti   │
  │   / LightRAG) + session/daily/weekly/monthly/yearly cadence (K5)      │
  │       │                                                                │
  │       ▼                                                                │
  │  Dialectical Synthesis (Phase 9) + Push to graphs                     │
  └────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────────┐
  │                  DOCUMENT FLOW (DocumentPipeline, K6)                 │
  │                                                                        │
  │  document (.md / .txt / .pdf / .docx)                                  │
  │       │                                                                │
  │       ▼     DocumentPipeline.ingest(path, project)                     │
  │  layout-aware parse → normalize → chunk by structure                  │
  │       │                                                                │
  │       ▼     canonical metadata + citations + 1024d embedding          │
  │  document_memories (parent) + document_chunks (atoms) + document_vectors │
  │       │                                                                │
  │       ▼     optional: KnowledgePromotionPipeline                      │
  │  fact / learning / decision / preference / rationale (cortex)         │
  └────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Step 1 — Collection (Write)

### 2.1 Data Sources

| Source | Format | Trigger | Destination |
|-------|---------|---------|---------|
| Agent (decision) | `sinapse_save_decision` tool | PostToolUse hook | `work/active/YYYY-MM-DD-slug.md` |
| Agent (learning) | `sinapse_save_learning` tool | PostToolUse hook | `brain/Patterns.md` (append) |
| Agent (session end) | Stop hook | `on_session_end` | `brain/Current State.md` |
| Screenshot | `sinapse_capture_screen` tool | On demand | `inbox/visual/` + `visual_memories` |
| PDF/DOCX document | `document_ingest.py` | Manual / cron | `inbox/documents/` + `observations` |
| Human (Obsidian) | Markdown editor | Manual save | Any `.md` in the vault |
| claude-mem | SQLite observations | Periodic sync | `observations` table in UMC |

### 2.2 File Format (Vault)

```
work/active/2026-06-10-migrar-vps-para-hetzner.md:

  ---
  tags: [decision]
  status: active
  created: 2026-06-10
  source: claude-code-session
  agent: claude-fable-5
  ---

  # Migrar VPS para Hetzner

  Conteúdo com contexto, rationale e implicações.
```

### 2.3 Write Guarantees

| Guarantee | Mechanism |
|----------|-----------|
| Atomicity | `tempfile.mkstemp()` + `os.replace()` (atomic on Linux) |
| Deduplication | Slug check before creating a new file |
| Validation | `_validate_frontmatter_yaml()` — checks `tags`, `status`, `created` |
| Secret detection | Regex `sk-proj-*, AKIA*, Bearer token` → Fernet → vault table |
| Dry-run | `SINAPSE_DRY_RUN=1` — zero side effects |

---

## 3. Step 2 — Real-Time Indexing (Watcher)

`watchdog` continuously monitors `cerebro/`. Any change triggers reindexing in ~2 seconds — eliminating the 6-hour gap from v1.x.

```
  File saved/modified in cerebro/
         │
         ▼ (watchdog FileModifiedEvent, ~2s)
  Graphify reindexes file:
    ├── Extracts entities + relationships (LLM or tree-sitter)
    ├── Generates 1024d embedding (snowflake-arctic-embed2 via local Ollama)
    ├── UPDATE neurons SET title, content, hash, embedding, indexed_at
    ├── UPDATE/INSERT synapses (WikiLinks as edges)
    ├── UPDATE search_fts (automatic via SQL trigger)
    ├── UPDATE search_vec (vec0, HNSW sqlite-vec 1024d)
    └── INSERT/UPDATE hnsw_neurons.idx  ← core/hnsw_index.py
         (incremental, M=16, ef_construction=200, cosine space)

  Result: hive_mind.db + hnsw_neurons.idx updated on disk (WAL mode)
```

> **Migration 384d → 1024d:** commit `56f1e98` (2026-06-21). The global embedding contract is `snowflake-arctic-embed2:latest` at **1024d** unless explicitly overridden by env (`OLLAMA_EMBED_MODEL`, `HNSW_DIM`). Model changes follow the versioned migration contract (K10, [`01-architecture.md` §30.4](01-architecture.md#30-escala-e-isolamento--workspace-e-federação)): online re-embed per workspace, dual-write until cutover, metric `vectors_model_mismatch` = 0 within a collection.

---

## 4. Step 3 — Dream Cycle (Offline Consolidation)

Dream Cycle processes raw observations and elevates them into structured facts in Atlas.

### 4.1 Stage 1 — Distiller

```
  SELECT * FROM observations
    WHERE archived = 0
    ORDER BY created_at
    LIMIT batch_size

  For each observation:
    prompt = system_prompt_distiller + observation.content
    response = llm_call(provider, model, prompt, json_schema=DistilledFact)
    fact = DistilledFact.model_validate_json(response)

    → DistilledFact {
        title: str
        summary: str
        key_insights: list[str]
        confidence: float (0-1)
        tags: list[str]
      }
```

### 4.2 Stage 2 — Validator

```
  For each DistilledFact:
    prompt = system_prompt_validator + fact.json()
    verdict = ValidatorVerdict.model_validate_json(llm_call(...))

    if verdict.approved:
      → goes to Router
    elif retries < 2:
      → resends to Distiller with feedback
    else:
      → UPDATE observations SET archived=2  (quarantine)
```

### 4.3 Stage 3 — Router

```
  For each approved fact:
    Classifies destination:
      └── category in ["decision", "learning", "insight", "fact", "entity"]
      └── target_path = atlas/{category}/YYYY-MM-DD-{slug}.md

    Checks duplicate by embedding similarity (cosine > 0.92):
      └── If duplicate: merge (append unique insights)
      └── If new: INSERT neurons + write atlas/*.md
```

### 4.4 Stage 4 — Atlas Persistence

```
  _atomic_write(target_path, markdown_with_frontmatter)
    └── frontmatter:
         agent: {provider}/{model}
         consolidated_at: {timestamp}
         source_observation_ids: [uuid1, uuid2]
         confidence: {float}

  UPDATE observations SET archived=1, consolidated_at=NOW()
    WHERE id IN (processed_ids)
```

### 4.5 Full Flow (ASCII)

```
  observations (archived=0)
       │
       ▼
  ┌─────────────┐
  │  DISTILLER  │ ← LLM (JSON schema mandatory)
  └──────┬──────┘
         │ DistilledFact
         ▼
  ┌─────────────┐   rejects    ┌─────────────┐
  │  VALIDATOR  │─────────────▶│  QUARANTINE │ archived=2
  └──────┬──────┘              └─────────────┘
         │ approved
         ▼
  ┌─────────────┐
  │   ROUTER    │ classifies destination + dedup check
  └──────┬──────┘
         │
         ▼
  ┌─────────────────┐
  │ ATLAS (cerebro/ │ atomic write + UPDATE neurons
  │  atlas/*.md)    │ archived=1
  └─────────────────┘
```

---

## 5. HM-11 — Deep Reflection (Intent Memory + Causality)

### 5.1 Goal Planner

`scripts/planner.py` receives a goal in natural language, calls the LLM, and returns a list of atomic steps (`GoalStep`). Each goal is persisted in the `goals` table and exposed through MCP tool `sinapse_plan_goal`.

```
  USER GOAL
        │
        ▼
  sinapse_plan_goal (MCP tool)
        │
        ▼
  scripts/planner.py
        │
        ├── prompt + goal → LLM
        │
        ▼
  GoalStep[] (atomic steps)
        │
        ├──→ INSERT goals TABLE (hive_mind.db)
        │
        └──→ observations created with:
               goal_id  → reference to active goal
               why      → rationale / intent
```

### 5.2 Causality Graph

The `causal_edges` table records cause → effect edges between neurons. Function `get_causal_neighbors(conn, neuron_id, hops=2)` traverses the graph with BFS to retrieve causal neighbors up to 2 hops.

```
  neurons
     │
     ▼
  causal_edges (causa_id → efeito_id)
     │
     ▼
  get_causal_neighbors(conn, neuron_id, hops=2)
     │   BFS in causality graph
     ▼
  causal neighbors (up to 2 hops)
```

### 5.3 Intent Metadata in Observations

Each observation can reference an active goal through additional columns:

| Column | Type | Description |
|--------|------|-----------|
| `goal_id` | TEXT (FK) | Reference to active goal in `goals.id` |
| `why` | TEXT | Observation rationale / intent |

---

## 6. HM-12 — Federated Swarm (Federated Export)

### 6.1 Neuron Visibility

The `visibility` column in `neurons` controls which neurons can be exported:

| Value | Description |
|-------|-----------|
| `private` | Default. Not exported. |
| `shared` | Exportable to authorized partners. |
| `public` | Exportable with no recipient restriction. |

### 6.2 Export Endpoint

`POST /api/v1/neurons/export` — authenticated via Bearer token.

Accepted filters: `type`, `created_after`. Options: `redact` (PII removal) and/or `sign` (Ed25519 signature).

```
  POST /api/v1/neurons/export
        │
        ▼
  SELECT neurons WHERE visibility IN ('shared', 'public')
        │  + filters: type, created_after
        │
        ├─ redact_neuron()   ← core/redactor.py
        │   Irreversible PII: API tokens, email, IPv4/6,
        │   absolute paths, SSH keys, CPF/CNPJ, phone
        │   (applied to content and label; does not modify local data)
        │
        ├─ sign_neuron()     ← core/signing.py
        │   Ed25519 keypair (config/keys/, gitignored)
        │   Signs canonical JSON (excludes timestamps and _prefixed fields)
        │   verify_neuron() for receiver-side validation
        │
        └─ JSON response
             { neurons[], signature?, pubkey_fingerprint? }
```

---

## 7. Step 4 — Query (RetrievalRouter K7 + sinapse_query)

From the K0–K10 front onward, canonical querying goes through **`RetrievalRouter`** ([`01-architecture.md` §26](01-architecture.md#26-retrievalrouter-k7--roteamento-por-intenção); `core/retrieval/router.py`). The router classifies query intent, selects the specialized route, and returns `retrieval_path`, `citations`, `confidence`, and `missing_context`. When confidence is low or the query is ambiguous, it falls back to `sinapse_query`/Context Fusion.

### 7.0 Intent-based Routes (K7)

| Detected intent | Canonical collection (K1) | Why this route |
|---|---|---|
| Recent / "what happened" | `observation_vectors` (claude-mem) | Events with recent timestamps |
| Decision / preference | `memory_vectors` + FTS | Validated atomic facts |
| Learning | `memory_vectors` (learning atoms) + Patterns parent | Reusable patterns |
| Document | `document_vectors` + parent context | `DocumentPipeline` (K6) with citations |
| Code | `code_vectors` + Graphify | AST symbols + relationships |
| Causality / when it was true | Graphiti/FalkorDB (`graph_vectors` auxiliary) | `valid_at`/`invalid_at` |
| Global / multi-hop question | LightRAG/GraphRAG | Entities + relationships |
| Health / self-awareness | Insula (health/conflicts) | operational_fact + ambiguities |
| Config / operations / model | Brainstem | operational_fact |
| Sector / cross-project | Diencephalon + Graphiti | Sector MOCs |
| Ambiguous | hybrid + reranker (§31.1) | Fallback + optional local lexical rerank; cross-encoder is future evolution |

### 7.1 Parallel Backends (sinapse_query / Context Fusion)

```python
def _query_vault_knowledge(query: str, timeout=8.0) -> Optional[str]:

    # 5+ backends in parallel (ThreadPoolExecutor) with circuit breaker
    results = []

    # Backend 1: UMC SQL (FTS5 + KNN sqlite-vec)
    results += umc_search(query)        # FTS5 MATCH + vec KNN (snowflake-arctic-embed2 1024d)

    # Backend 2: claude-mem
    results += claude_mem_search(query) # HTTP :37700, timeout 3s

    # Backend 3: NeuralMemory
    results += nmem_recall(query)       # spreading activation, timeout 5s

    # Backend 4: Filesystem
    results += fs_scan(query)           # scan cerebro/*.md, TTL 30s

    # Backend 5: LightRAG (P4) — entities + relationships + multi-hop
    results += lightrag_query(query)    # knowledge graph, timeout 8s

    # Backend 6: Graphiti (temporal causality)
    results += graphiti_query(query)    # causal_edges with valid_at/invalid_at

    # Backend 7: Graphify (vault structure)
    results += graphify_query(query)    # communities + adjacencies

    # Fusion and deduplication + optional rerank (§31.1)
    deduped = dedup(results, key=lambda r: (r.source_file, r.title, r.content))
    reranked = rerank(query, deduped) if HIVE_RETRIEVAL_RERANKER else deduped
    return format(top_n=5, max_chars=3000, results=reranked)
```

> **Note:** `sinapse_rag_query` (MCP) uses the same backend 5 (LightRAG), but with modes `naive|local|global|hybrid`, and returns the graph raw string (entities + relationships + chunks), not the other 6 backends.

### 7.2 Vector Search (KNN)

```sql
SELECT n.id, n.title, n.content, n.source_file,
       vec_distance_cosine(v.embedding, :query_vec) AS distance
FROM search_vec v
JOIN neurons n ON n.id = v.neuron_id
ORDER BY distance
LIMIT 5
```

`query_vec` = `snowflake-arctic-embed2.encode(query)` via local Ollama — **1024d** vector generated at query time. `search_vec` virtual table (vec0, 1024d). Migration from old 384d → 1024d happened in P0 (commit `56f1e98`, 2026-06-21).

### 7.3 Circuit Breaker

| State | Condition | Behavior |
|--------|---------|---------------|
| Closed (normal) | Fewer than 3 failures | Backend active |
| Open (cooldown) | 3+ exceptions or timeouts | 30s cooldown, backend skipped |
| Half-open (test) | After 30s | One attempt to reset |

Only Python exceptions and timeouts count as failures — empty results (not found) do not.

---

## 8. Update Frequency

| Pipeline | Frequency | Trigger |
|----------|-----------|---------|
| Decision/learning writes | Immediate | PostToolUse / Stop hook |
| UMC indexing (Watcher) | ~2 seconds | watchdog FileModifiedEvent |
| Dream Cycle | Manual or cron | `python3 scripts/dream/dream_cycle.py` |
| P2P audit | 1x per hour | Cron `audit_memory.py --fix` |
| UMC backup | Daily 3am | Cron `cp hive_mind.db backups/` |

---

## 9. Data Volume

| Metric | Typical value |
|---------|-------------|
| neurons in UMC | 1,200+ |
| synapses in UMC | 1,300+ |
| causal_edges in UMC | grows with usage |
| goals (planner) | per planning session |
| pending observations (per session) | 5-30 |
| atlas/*.md (consolidated facts) | grows with usage |
| hive_mind.db size | 50-200MB |
| hnsw_neurons.idx size | ~5-20MB (depends on neurons) |
| claude-mem/data/lightrag/ size | ~5-50MB (graph + entity/rel vdb) |
| Reindex time per file | ~1-3s |
| KNN search time (10k vectors, 1024d) | ~5-10ms |
| HNSW search time (1024d) | ~1-2ms |
| FTS5 search time | ~2ms |
| LightRAG query time (hybrid, ~1k entities) | ~100-300ms (local LLM) |

### Database Tables (hive_mind.db)

| Table | Purpose | Phase |
|--------|-----------|------|
| `neurons` | Knowledge nodes (with `visibility` in v3 + `workspace_id` in K10) | base + K10 |
| `synapses` | WikiLink edges between neurons | base |
| `observations` | Raw data with `goal_id`/`why` (HM-11) + `workspace_id` + `source_id` (K4) | base + HM-11 + K4 + K10 |
| `search_fts` | Full-Text Search index (FTS5) | base |
| `search_vec` | Vector index (vec0 sqlite-vec, 1024d) | base + K1 |
| `causal_edges` | Cause→effect causality graph | HM-11 |
| `goals` | Goals decomposed by planner | HM-11 |
| `vector_metadata` | Canonical metadata (parent_id, brain_lobe, knowledge_type, source_uri, valid_at, workspace_id) | K1 |
| `ambiguities` | P2P conflicts (content_a, content_b, hashes, status) | base + K10 |
| `vault` | Encrypted secrets (Fernet) | base |
| `document_memories` | Document parents (K6) | K6 |
| `document_chunks` | Document atoms (offsets, parent_id, hash) | K6 |
| `document_vectors` | Chunk vectors (K6, with canonical metadata) | K6 |
| `knowledge_tombstones` | Auditable `forget()` tombstones (§31.2) | K8 |
| `query_route_log` | Query hash × route (K7) — `query_route_distribution` telemetry | K7 |

---

## 10. K3 — Knowledge Intake

`core/knowledge/intake.py`. Layer [3] of the canonical flow ([`11-knowledge-promotion-architecture.md` §3](11-knowledge-promotion-architecture.md#3-preenchimento-por-parte-do-cérebro)). Input: raw claude-mem observations (and candidate records from other backends via `KnowledgePromotionPipeline`). Output: normalized/classified/deduplicated candidates, ready for Promotion Layer.

**Responsibilities:**

- normalize fields (`observations`, `discoveries`, `session_summaries`, `facts`, `narrative`, `concepts`, `files_read/files_modified`, `prompt_number`, `generated_by_model`);
- preserve stable `source_id` (`claude-mem:<table>:<id>`);
- extract evidence (files, timestamps, `project`, `workspace_id`);
- classify `knowledge_type` (see [`01-architecture.md` §27.2](01-architecture.md#272-tipos-canônicos-de-conhecimento));
- deduplicate by `source_id` + content hash.

**claude-mem read path (K4):** `core/knowledge/claude_mem_bridge.py` is the canonical bridge via read-only SQL on `~/.claude-mem/claude-mem.db`. Legacy `scripts/services/claude_mem_bridge.py` only delegates to core. The interactive `search → timeline → get_observations` workflow (via MCP `sinapse_temporal_*`) is the path to **retrieve raw context before choosing IDs**; the bridge is the promotion/backfill batch path.

**K3 status (2026-06-28):** real SQLite pipeline, Dream Cycle `--once --real`, query via CLI, and full suite `./tests/run_all.sh` green.

---

## 11. K4 — Promotion Layer

`core/knowledge/promotion.py`. Layer [4] of the flow. `Distiller → Validator → Router` operations remain; now each wrapper exposes **idempotent `candidate-only` output** with `workspace_id` for centralized orchestration, and final persistence performs `UPSERT neurons` + `VectorBackend.upsert()` in canonical collection.

**Surfaces:** CLI `sinapse-write.py promotion`, MCP `sinapse_promote_knowledge`, Dream Cycle with intake candidate-only before legacy synthesis.

**Automatic promotion rules:**

- **Allowed:** `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` — all with traceable source.
- **Forbidden:** turning every bullet into a fact; creating a neuron without source; vectorizing duplicates without `parent_id` and content hash; promoting temporary opinion as architectural decision; overwriting previous decisions without creating conflict or `invalid_at`.

**Promotion failure preserves data (ADR-016):**

```text
transient error -> archived=0, future retry
structural error  -> archived=2, quarantine with reason
```

Nothing is deleted due to promotion failure. See [`01-architecture.md` ADR-016](01-architecture.md#adr-016--falha-de-promoção-preserva-dados-nunca-descarta).

**K4 status (2026-06-29):** real bridge 2 passed, operational promotion against `~/.claude-mem/claude-mem.db` imported real records by `source_id`, CLI with system `python3` exited 0 via `.venv` re-exec, `./tests/run_all.sh` completed green. Real vision validation uses role `vision` configured in `setup-brain`/`.env` (`HIVE_VISION_*`), with no Ollama Cloud hardcode.

---

## 12. K5 — Hierarchical Write Cadence

The brain's temporal memory advances through **five cadences** — session, daily, weekly, monthly, yearly — with dedicated writers, LLM roles, and promotion rules. Normative details in [`11-knowledge-promotion-architecture.md` §14](11-knowledge-promotion-architecture.md#14-cadencia-hierarquica-de-escrita).

| Cadence | Writer | Default model | Promotes |
|---|---|---|---|
| Session | `session_consolidator.py` | `session_summarizer` (small) | decisions, open questions, evidence |
| Daily | `daily_writer.py` | `daily_writer` (small/medium) | learnings, progress, next steps |
| Weekly | `weekly_synthesizer.py` | `weekly_synthesizer` (medium/strong) | patterns, strategic decisions, priorities |
| Monthly | `monthly_synthesizer.py` | `monthly_synthesizer` (strong) | executive synthesis, drift, goals, risks |
| Yearly | `yearly_synthesizer.py` | `yearly_synthesizer` (strong/batch) | principles, durable lessons learned |

Each cadence produces a file under `cerebro/cerebelo/{sessoes,diario,semanal,mensal,anual}/...` and indexes into `summary_vectors` (K1). Cadence promotion contract: `source_id`, `period_start`, `period_end`, `cadence`, `parent_summary_id` (see [`01-architecture.md` §29.2](01-architecture.md#292-contrato-de-promoção-por-cadência)).

**Golden rule:** the higher the cadence, the less it copies text and the more it consolidates causality, decision, pattern, and consequence. Monthly/yearly should not be automatically downgraded without notice.

**Fail-closed:** a role without a dedicated model and without inheriting from `dreamer` records an auditable failure and does not invent synthesis.

---

## 13. K6 — DocumentPipeline

`core/knowledge/document_pipeline.py`. Inspired by RAGFlow, but **preserving Hive-Mind anatomy**. See [`01-architecture.md` §25](01-architecture.md#25-documentpipeline-k6--ingestao-born-large) for architectural details.

```text
document (.md / .txt / .pdf / .docx)
  |
  v
layout-aware parse (headless RAGFlow adapter OR local parser)
  |
  v
normalize
  |
  v
chunk by structure (300-800 tokens for regular text; by section for MD; by symbol for code)
  |
  v
metadata + citations (parent_id, offsets, source_uri, hash)
  |
  v
1024d embedding (snowflake-arctic-embed2)
  |
  v
document_memories (parent) + document_chunks (atoms) + document_vectors
  |
  v
optional: KnowledgePromotionPipeline (K3/K4) → fact/learning/decision
```

**RAGFlow** is an optional headless adapter — never a source of truth. Any reused output must be normalized into UMC before it is retrievable. RAGFlow unavailability **does not** break the local-first path.

**Citation contract:** `DocumentPipeline.query(text)` returns `citations[{source_uri, offset_start, offset_end, score, parent}]` — output cannot be just "best passage".

---

## 14. K7 — RetrievalRouter (Intent Routing)

`core/retrieval/router.py`. Canonical query entry point. It classifies intent, chooses specialized route, and returns `{answer_context, citations, retrieval_path, confidence, missing_context}`. LlamaIndex is only an optional rerank adapter; it does not decide route and does not become source of truth. Details in [`01-architecture.md` §26](01-architecture.md#26-retrievalrouter-k7--roteamento-por-intenção).

**Telemetered metrics** (query hash only, never raw text):

- `query_route_distribution` — which routes answer how often
- average `confidence` by route
- `missing_context` when router cannot find an appropriate layer (coverage gap signal)

---

## 15. K8 — Knowledge Health Metrics

`scripts/health/knowledge_health.py` (delivered in v3.6.0, 2026-06-30). This module **adds** knowledge coverage metrics; it **does not replace** `health_dashboard.py`, `alert_dispatcher.py`, or `review_writer.py` (which remain Insula health). `sinapse_health` includes a read-only `knowledge_health` block in quick mode; REST API exposes `GET /api/v1/knowledge/health` for the full gate.

| Metric | Signal | Canonical collection (K1) |
|---|---|---|
| `neurons_total` | consolidated memory size | — |
| `neurons_vectorized_pct` | vector coverage | `memory_vectors` |
| `observations_pending` | temporal backlog | `observation_vectors` |
| `observations_linked_pct` | effective promotion | — |
| `discoveries_pending` | risk of losing learning | `observation_vectors` |
| `learnings_atomized` | granular learning | `memory_vectors` |
| `document_chunks_total` | document ingestion | `document_vectors` |
| `code_symbols_total` | structural coverage | `code_vectors` |
| `milvus_sync_lag` | local/production divergence | all |
| `orphan_vectors` | dirty index (first slice of `forget()` §31.2) | all |
| `query_route_distribution` | which layers answer | — |
| `*_vectorized_pct` | coverage by canonical collection | 7 collections |
| `promotion_lag` | promotion backlog by workspace | — |
| `promotion_cost` | LLM cost by workspace | — |
| `vectors_model_mismatch` | embedding model divergence (K10) | by collection |

**Minimum production gate:**

```text
neurons_vectorized_pct >= 99%
observations_linked_pct increasing per cycle
discoveries_pending within SLA
0 orphan vectors
all chunks with parent_id
citations present in document responses
```

---

## 16. K10 — Scale, Isolation, and Federation

`workspace_id` is the mandatory isolation boundary ([`01-architecture.md` §30.1](01-architecture.md#30-escala-e-isolamento--workspace-e-federação)). Every critical UMC table carries `workspace_id` (default `'default'`). Every query in `RetrievalRouter` and promotion filters by `workspace_id`. Milvus uses `partition_key=workspace_id` for partition-level isolation.

**Boundary rules:**

- **Cross-workspace leakage is a security bug**, not a ranking issue.
- Structural migrations that create this boundary: failure is fail-closed by default. The only bypass is `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` (legacy DB diagnostics, with visible log and without marking installation as healthy).
- Federation across instances: reuses HM-12 (`visibility` private|shared|public + Ed25519 + PII redaction on export). Imported neuron enters with destination `workspace_id` and preserved provenance. `origin_instance` and `origin_signature` are mandatory.
- Embedding migration: `vectors_model_mismatch` = 0 within a collection; online re-embed by workspace, dual-write until cutover (§30.4).
- Promotion cost: ceiling by workspace via `HIVE_PROMOTION_BUDGET_*`; overflow remains `archived=0` (retry); metrics `promotion_lag` and `promotion_cost` by workspace.
