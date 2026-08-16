# Data Pipeline

> **Hive-Mind v3.10.1** — Complete data flow: capture → intake (K3) → promotion (K4) → persistence (Atlas + UMC) → indexing (vector/graph/FTS) → retrieval (RetrievalRouter).
> Revision 2026-08-15. Fully integrates the [`cerebro-filling-map.md`](cerebro-filling-map.md) (the "who fills what" map) and the 9-stage flow from [`03-data-pipeline.md`](03-data-pipeline.md).
> Normative reference: [`architecture.md`](architecture.md) §22–§31 (Born-Large knowledge front, K0–K10).

---

## 1. Flow overview

The v3.x pipeline has **three parallel flows** — real time (write → read), offline (Dream Cycle), and document (`DocumentPipeline`) — over a single persistent anatomy:

```text
  ┌────────────────────────────────────────────────────────────────────────┐
  │                         FLUXO TEMPO REAL                                │
  │                                                                        │
  │  Agente / Humano                                                       │
  │       │                                                                │
  │       ▼                                                                │
  │  [ CAPTURA ]──── escrita atômica ──→ vault (cerebro/*.md)              │
  │       │                                   │                           │
  │       │                     Watcher ~2s   │                           │
  │       │                                   ▼                           │
  │       │              [ INDEXAÇÃO TEMPO REAL ] → hive_mind.db           │
  │       │               neurônios + sinapses + FTS5 + sqlite-vec 1024d   │
  │       │                           │                                   │
  │       │                           ├──→ Índice HNSW (hnsw_neurons.idx)  │
  │       │                           │    (incremental, 1024d)            │
  │       │                           ├──→ causal_edges (grafo causa→efeito)│
  │       │                           └──→ goals (planner via              │
  │       │                                sinapse_plan_goal)              │
  │       │                                                                │
  │       ▼                                                                │
  │  [ CONSULTA ] ← RetrievalRouter (K7) → sinapse_query (Context Fusion)  │
  └────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────────┐
  │                    FLUXO OFFLINE (Dream Cycle)                         │
  │                                                                        │
  │  observations (pendentes, archived=0)                                  │
  │       │                                                                │
  │       ▼     execução manual ou agendada (cron 0 */4 * * *)             │
  │  [ DREAM CYCLE ] ─────────────────────────────────────────────────    │
  │    Knowledge Intake (K3) → Distiller → Validator → Router (K4)        │
  │       │                                                                │
  │       ▼                                                                │
  │  Persistência anatômica + indexação multi-coleção                       │
  │  (memory_vectors / observation_vectors / summary_vectors / Graphiti    │
  │   / LightRAG) + cadência session/daily/weekly/monthly/yearly (K5)      │
  │       │                                                                │
  │       ▼                                                                │
  │  Síntese Dialética (Fase 9) + Push para grafos                         │
  └────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────────┐
  │                 FLUXO DOCUMENTAL (DocumentPipeline, K6)                │
  │                                                                        │
  │  documento (.md / .txt / .pdf / .docx)                                 │
  │       │                                                                │
  │       ▼     DocumentPipeline.ingest(path, project)                     │
  │  parse layout-aware → normalizar → chunk por estrutura                │
  │       │                                                                │
  │       ▼     metadados canônicos + citações + embedding 1024d           │
  │  document_memories (pai) + document_chunks (átomos) + document_vectors │
  │       │                                                                │
  │       ▼     opcional: KnowledgePromotionPipeline                      │
  │  fact / learning / decision / preference / rationale (cortex)         │
  └────────────────────────────────────────────────────────────────────────┘
```

The canonical knowledge flow (AGENTS.md §1) is a condensed reading of these three flows:

```
Captura (hooks/MCP/CLI/browser/docs/code/screenshots)
  → Hippocampus Temporal (claude-mem: observations, discoveries, summaries)
  → Knowledge Intake (normalizar, classificar, deduplicar)
  → Promotion Layer (raw → fact/decision/learning/preference/task)
  → Memória Anatômica (cerebro/ + UMC)
  → Index Layer (FTS, sqlite-vec/Milvus, Graphify, Graphiti, LightRAG)
  → Retrieval Router (core/retrieval/router.py)
  → Resposta com citação
  → Feedback
```

---

## 2. Capture and orchestration flow (consolidate_loop + Dream Cycle)

Diagram kept verbatim from [`cerebro-filling-map.md`](cerebro-filling-map.md):

```
┌────────────────────────────────────────────────────────────────────────┐
│  CAPTURA — claude-mem (worker v13.15.0, vendored)                       │
│  captura nativa de TODOS os providers (codex, copilot, hermes,          │
│  antigravity, kimi, qwen, kilo, roo, mimo, openclaw, swarmclaw)         │
│  → grava observations + session_summaries no claude-mem.db (projeto)     │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│  consolidate_loop.py (serviço sinapse-consolidate, loop contínuo)       │
│  FAST (60s)     → bridge → promote → materialize  (cortex/temporal)      │
│  MEDIUM (5min)  → decision_promoter, work_tracker, project_synthesizer,  │
│                   health_dashboard, daily_writer (lobos derivados)       │
│  SLOW (1h)      → topic_consolidator (merge de tópicos)                  │
│  DAILY (6h)     → weekly/monthly/yearly_synthesizer (cadência longa)     │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Dream Cycle (dream_cycle.py) — Hive-Dreamer, cron 0 */4 * * *           │
│  Distiller → Validator → Router (LLM) → escreve neurônios .md no vault    │
│  + Graph Push (Graphiti + LightRAG)                                       │
└────────────────────────────────────────────────────────────────────────┘
```

**Golden rule:**

- **Deterministic** (⚙️) reorganizes what already exists — cheap, always runs.
- **LLM** (🧠) generates new knowledge — expensive, runs at the right cadence.
- **Manual** (✍️) is edited by the human/agent on demand.

---

## 3. Vault anatomy (lobes)

Anatomical diagram kept verbatim from [`cerebro-filling-map.md`](cerebro-filling-map.md):

```
cerebro/
├── cortex/                          ← CÓRTEX (cognição) — 5 lóbulos
│   ├── temporal/                    ← memória de longo prazo (eixo primário)
│   │   ├── <projeto>/<tópico>/neuronio-*.md
│   │   ├── _global/
│   │   ├── hipocampo/
│   │   └── arquivo/
│   ├── frontal/                     ← decisão, planejamento, trabalho ativo
│   │   ├── decisoes/
│   │   ├── trabalho/{ativo,arquivo}/
│   │   ├── projetos/
│   │   ├── brain/
│   │   └── org/{people,teams}/
│   ├── parietal/                    ← sensorial (inbox, referências)
│   │   ├── inbox/{visual,documents}/
│   │   ├── referencias/
│   │   └── analises/
│   ├── occipital/                   ← visão (capturas + grafo)
│   │   ├── capturas-visuais/
│   │   └── grafo/
│   └── insula/                      ← interocepção, self-awareness
│       ├── saude/
│       └── conflitos/
├── cerebelo/                        ← CEREBELO (ritmo e coordenação)
│   ├── sessoes/
│   ├── diario/
│   ├── semanal/
│   ├── mensal/
│   ├── anual/
│   └── padroes/
├── diencefalo/                      ← DIENCÉFALO (relay cross-projeto)
│   ├── setores/
│   └── roteamento/
└── tronco/                          ← TRONCO (infra vital — irmão, não subordinado)
    ├── modelos/
    ├── paineis/
    ├── infra/
    └── meta/
```

The paths are exposed as constants in [`core/paths.py`](core/paths.py) (`CORTEX`, `TEMPORAL`, `FRONTAL`, `PARIETAL`, `OCCIPITAL`, `INSULA`, `DIENCEFALO`, `SECTORS_ROOT`, `CEREBELO`, `DAILY_ROOT`, `SESSIONS_ROOT`, `WEEKLY_ROOT`, `PADROES_ROOT`, `TRONCO`, `META_ROOT`, `MODELOS_ROOT`, `PAINEIS_ROOT`). All code that creates/modifies a file in the vault must use these constants, never hardcoded paths.

---

## 4. Stage 1 — Capture (write)

### 4.1 Data sources

| Source | Format | Trigger | Destination |
|-------|---------|---------|---------|
| Agent (decision) | `sinapse_save_decision` tool | PostToolUse hook | `trabalho/ativo/YYYY-MM-DD-slug.md` |
| Agent (learning) | `sinapse_save_learning` tool | PostToolUse hook | `brain/Patterns.md` (append) |
| Agent (session end) | Stop hook | `on_session_end` | `brain/Current State.md` |
| Screenshot | `sinapse_capture_screen` tool | on demand | `inbox/visual/` + `visual_memories` |
| PDF/DOCX document | `document_ingest.py` | manual / cron | `inbox/documents/` + `observations` |
| Human (Obsidian) | Markdown editor | manual save | any `.md` in the vault |
| claude-mem | SQLite observations | periodic sync | `observations` table in the UMC |

### 4.2 File format (vault)

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

### 4.3 Write guarantees

| Guarantee | Mechanism |
|----------|-----------|
| Atomicity | `tempfile.mkstemp()` + `os.replace()` (atomic on Linux) |
| Deduplication | slug check before creating a new file |
| Validation | `_validate_frontmatter_yaml()` — validates `tags`, `status`, `created` |
| Secret detection | regex `sk-proj-*`, `AKIA*`, Bearer token → Fernet → `vault` table |
| Dry-run | `SINAPSE_DRY_RUN=1` — zero side effects |

---

## 5. Stage 2 — Real-time indexing (Watcher)

The `watchdog` monitors `cerebro/` continuously. Any change triggers reindexing in ~2 seconds — eliminating the 6-hour gap from v1.x.

```
  Arquivo salvo/modificado em cerebro/
         │
         ▼ (watchdog FileModifiedEvent, ~2s)
  Graphify reindexa o arquivo:
    ├── Extrai entidades + relacionamentos (LLM ou tree-sitter)
    ├── Gera embedding 1024d (snowflake-arctic-embed2 via Ollama local)
    ├── UPDATE neurons SET title, content, hash, embedding, indexed_at
    ├── UPDATE/INSERT synapses (WikiLinks como arestas)
    ├── UPDATE search_fts (automático via trigger SQL)
    ├── UPDATE search_vec (vec0, HNSW sqlite-vec 1024d)
    └── INSERT/UPDATE hnsw_neurons.idx  ← core/hnsw_index.py
         (incremental, M=16, ef_construction=200, espaço cosseno)

  Resultado: hive_mind.db + hnsw_neurons.idx atualizados em disco (modo WAL)
```

> **384d → 1024d migration:** commit `56f1e98` (2026-06-21). The global embedding contract is `snowflake-arctic-embed2:latest` at **1024d**, unless explicitly overridden via env (`OLLAMA_EMBED_MODEL`, `HNSW_DIM`). Model changes follow the versioned contract (K10): online re-embed per workspace, dual-write until cutover, metric `vectors_model_mismatch = 0` within a collection.

---

## 6. Stage 3 — Dream Cycle (offline consolidation)

The Dream Cycle processes raw observations and elevates them to structured facts in the Atlas. In v3.10.1 it runs scheduled every **4h** (`PT4H`, cron `0 */4 * * *`), with the split of roles:

- **Distiller** and **Router**: instruct local `granite4.1:8b` (via role config).
- **Validator**: reasoning `qwen3.5:397b` (cloud).

### 6.1 Stage 1 — Distiller

```
  SELECT * FROM observations
    WHERE archived = 0
    ORDER BY created_at
    LIMIT batch_size

  Para cada observação:
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

### 6.2 Stage 2 — Validator

```
  Para cada DistilledFact:
    prompt = system_prompt_validator + fact.json()
    verdict = ValidatorVerdict.model_validate_json(llm_call(...))

    se verdict.approved:
      → vai para o Router
    senão se retries < 2:
      → reenvia ao Distiller com feedback
    senão:
      → UPDATE observations SET archived=2  (quarentena)
```

### 6.3 Stage 3 — Router

```
  Para cada fato aprovado:
    Classifica o destino:
      └── category em ["decision", "learning", "insight", "fact", "entity"]
      └── target_path = atlas/{category}/YYYY-MM-DD-{slug}.md

    Verifica duplicata por similaridade de embedding (cosseno > 0.92):
      └── Se duplicata: merge (append de insights únicos)
      └── Se novo: INSERT neurons + escreve atlas/*.md
```

### 6.4 Stage 4 — Persistence in the Atlas

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

### 6.5 Complete flow (ASCII)

```
  observations (archived=0)
       │
       ▼
  ┌─────────────┐
  │  DISTILLER  │ ← LLM (JSON schema obrigatório)
  └──────┬──────┘
         │ DistilledFact
         ▼
  ┌─────────────┐   rejeita    ┌─────────────┐
  │  VALIDATOR  │─────────────▶│  QUARENTENA │ archived=2
  └──────┬──────┘              └─────────────┘
         │ aprovado
         ▼
  ┌─────────────┐
  │   ROUTER    │ classifica destino + verificação de duplicata
  └──────┬──────┘
         │
         ▼
  ┌─────────────────┐
  │ ATLAS (cerebro/ │ escrita atômica + UPDATE neurons
  │  atlas/*.md)    │ archived=1
  └─────────────────┘
```

The Dream Cycle is the **only source of neurons with groundedness** (Evidence + synapses): it writes `neuronio-*.md` in the vault + a neuron in the UMC + a vector + Graphiti/LightRAG. K3 (`promote_pending_observations`) is the fast deterministic path (no LLM) that materializes simple observations into neurons.

---

## 7. K3 — Knowledge Intake

`core/knowledge/intake.py`. Layer [3] of the canonical flow. Input: raw claude-mem observations (and candidates from other backends via `KnowledgePromotionPipeline`). Output: normalized/classified/deduplicated candidates, ready for the Promotion Layer.

**Responsibilities:**

- normalize fields (`observations`, `discoveries`, `session_summaries`, `facts`, `narrative`, `concepts`, `files_read`/`files_modified`, `prompt_number`, `generated_by_model`);
- preserve stable `source_id` (`claude-mem:<table>:<id>`);
- extract evidence (files, timestamps, `project`, `workspace_id`);
- classify `knowledge_type`;
- deduplicate by `source_id` + content hash.

**claude-mem read path (K4):** `core/knowledge/claude_mem_bridge.py` is the canonical bridge via read-only SQL over `~/.claude-mem/claude-mem.db`. The interactive `search → timeline → get_observations` workflow (via MCP `sinapse_temporal_*`) is the path to **retrieve raw context before choosing IDs**; the bridge is the batch promotion/backfill path.

---

## 8. K4 — Promotion Layer

`core/knowledge/promotion.py`. Layer [4] of the flow. The `Distiller → Validator → Router` operations remain; each wrapper exposes an **idempotent `candidate-only`** output with `workspace_id` for centralized orchestration, and final persistence executes `UPSERT neurons` + `VectorBackend.upsert()` on the canonical collection.

**Surfaces:** CLI `sinapse-write.py promotion`, MCP `sinapse_promote_knowledge`, Dream Cycle with candidate-only intake before legacy synthesis.

**Automatic promotion rules:**

- **Allowed:** `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` — all with a traceable source.
- **Forbidden:** turning every bullet into a fact; creating a neuron without a source; vectorizing duplicates without `parent_id` and content hash; promoting a temporary opinion as an architectural decision; overwriting previous decisions without creating a conflict or `invalid_at`.

**Promotion failure preserves data (ADR-016):**

```text
erro transitório  -> archived=0, nova tentativa futura
erro estrutural   -> archived=2, quarentena com razão
```

Nothing is erased by a promotion failure. See [`architecture.md` ADR-016](architecture.mdção-preserva-dados-nunca-descarta).

---

## 9. K5 — Hierarchical write cadence

Temporal memory advances through **five cadences** — session, daily, weekly, monthly, yearly — with dedicated writers, LLM roles, and promotion rules:

| Cadence | Writer | Default model | Promotes |
|---|---|---|---|
| Session | `session_consolidator.py` | `session_summarizer` (small) | decisions, open questions, evidence |
| Daily | `daily_writer.py` | `daily_writer` (small/medium) | learnings, progress, next steps |
| Weekly | `weekly_synthesizer.py` | `weekly_synthesizer` (medium/strong) | patterns, strategic decisions, priorities |
| Monthly | `monthly_synthesizer.py` | `monthly_synthesizer` (strong) | executive synthesis, drift, goals, risks |
| Yearly | `yearly_synthesizer.py` | `yearly_synthesizer` (strong/batch) | principles, durable lessons |

Each cadence produces a file in `cerebro/cerebelo/{sessoes,diario,semanal,mensal,anual}/...` and indexes it in `summary_vectors` (K1). Promotion contract per cadence: `source_id`, `period_start`, `period_end`, `cadence`, `parent_summary_id`.

**Golden rule:** the higher the cadence, the less it copies text and the more it consolidates causality, decision, pattern, and consequence. Monthly/yearly must not be automatically downgraded without notice.

**Fail-closed:** a role without a dedicated model and without inheriting from `dreamer` records an auditable failure and **does not invent a synthesis**.

---

## 10. K6 — DocumentPipeline

`core/document_pipeline.py`. Inspired by RAGFlow, but **preserving the Hive-Mind anatomy**.

```text
documento (.md / .txt / .pdf / .docx)
  |
  v
parse layout-aware (adaptador headless RAGFlow OU parser local)
  |
  v
normalizar
  |
  v
chunk por estrutura (300-800 tokens para texto regular; por seção para MD; por símbolo para código)
  |
  v
metadados + citações (parent_id, offsets, source_uri, hash)
  |
  v
embedding 1024d (snowflake-arctic-embed2)
  |
  v
document_memories (pai) + document_chunks (átomos) + document_vectors
  |
  v
opcional: KnowledgePromotionPipeline (K3/K4) → fact/learning/decision
```

**RAGFlow** is an optional headless adapter — never the source of truth. Every reused output must be normalized into the UMC before becoming retrievable. RAGFlow unavailability does **not** break the local-first path.

**Citation contract:** `DocumentPipeline.query(text)` returns `citations[{source_uri, offset_start, offset_end, score, parent}]` — the output cannot be just "best snippet".

---

## 11. K7 — RetrievalRouter (intent-based routing)

`core/retrieval/router.py` is the canonical query entry point. It classifies the intent, chooses the specialized route, and returns `{answer_context, citations, retrieval_path, confidence, missing_context}`. LlamaIndex is only an optional rerank adapter; it does not decide the route nor become a source of truth.

### 11.1 Routes by intent

| Detected intent | Canonical collection (K1) | Why this route |
|---|---|---|
| Recent / "what happened" | `observation_vectors` (claude-mem) | Events with recent timestamps |
| Decision / preference | `memory_vectors` + FTS | Validated atomic facts |
| Learning | `memory_vectors` (learning atoms) + parent Patterns | Reusable patterns |
| Document | `document_vectors` + parent context | `DocumentPipeline` (K6) with citations |
| Code | `code_vectors` + Graphify | AST symbols + relationships |
| Causality / when it was true | Graphiti/FalkorDB (auxiliary `graph_vectors`) | `valid_at`/`invalid_at` |
| Global / multi-hop question | LightRAG/GraphRAG | Entities + relationships |
| Health / self-awareness | Ínsula (health/conflicts) | operational_fact + ambiguities |
| Config / operation / model | Tronco (brainstem) | operational_fact |
| Sector / cross-project | Diencéfalo + Graphiti | Sector MOCs |
| Ambiguous | hybrid + reranker (§31.1) | Fallback + optional local lexical rerank |

### 11.2 Parallel backends (sinapse_query / Context Fusion)

```python
def _query_vault_knowledge(query: str, timeout=8.0) -> Optional[str]:
    results = []

    # Backend 1: UMC SQL (FTS5 + KNN sqlite-vec)
    results += umc_search(query)        # FTS5 MATCH + vec KNN (snowflake-arctic-embed2 1024d)
    # Backend 2: claude-mem
    results += claude_mem_search(query) # HTTP :37700, timeout 3s
    # Backend 3: NeuralMemory
    results += nmem_recall(query)       # spreading activation, timeout 5s
    # Backend 4: Filesystem
    results += fs_scan(query)           # scan cerebro/*.md, TTL 30s
    # Backend 5: LightRAG (P4) — entidades + relacionamentos + multi-hop
    results += lightrag_query(query)    # knowledge graph, timeout 8s
    # Backend 6: Graphiti (causalidade temporal)
    results += graphiti_query(query)    # causal_edges com valid_at/invalid_at
    # Backend 7: Graphify (estrutura do vault)
    results += graphify_query(query)    # comunidades + adjacências

    # Fusão + deduplicação + rerank opcional (§31.1)
    deduped = dedup(results, key=lambda r: (r.source_file, r.title, r.content))
    reranked = rerank(query, deduped) if HIVE_RETRIEVAL_RERANKER else deduped
    return format(top_n=5, max_chars=3000, results=reranked)
```

> **Note:** `sinapse_rag_query` (MCP) uses the same backend 5 (LightRAG), but with `naive|local|global|hybrid` modes, and returns the raw graph string (entities + relationships + chunks), not the other 6 backends.

### 11.3 Vector search (KNN)

```sql
SELECT n.id, n.title, n.content, n.source_file,
       vec_distance_cosine(v.embedding, :query_vec) AS distance
FROM search_vec v
JOIN neurons n ON n.id = v.neuron_id
ORDER BY distance
LIMIT 5
```

`query_vec` = `snowflake-arctic-embed2.encode(query)` via local Ollama — a **1024d** vector generated at query time.

### 11.4 Circuit breaker

| State | Condition | Behavior |
|--------|---------|---------------|
| Closed (normal) | Fewer than 3 failures | Backend active |
| Open (cooldown) | 3+ exceptions or timeouts | 30s cooldown, backend skipped |
| Half-open (test) | After 30s | One attempt to reopen |

Only Python exceptions and timeouts count as failures — empty results (not found) do not count.

---

## 12. K8 — Knowledge health metrics

`scripts/health/knowledge_health.py` **adds** coverage metrics; it **does not replace** `health_dashboard.py`, `alert_dispatcher.py` or `review_writer.py` (which remain Ínsula health). `sinapse_health` includes a read-only `knowledge_health` block in fast mode; the REST exposes `GET /api/v1/knowledge/health`.

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
| `query_route_distribution` | which layers respond | — |
| `*_vectorized_pct` | coverage per canonical collection | 7 collections |
| `promotion_lag` | promotion backlog per workspace | — |
| `promotion_cost` | LLM cost per workspace | — |
| `vectors_model_mismatch` | embedding model divergence (K10) | per collection |

**Minimum production gate:**

```text
neurons_vectorized_pct >= 99%
observations_linked_pct crescente por ciclo
discoveries_pending dentro do SLA
0 vetores órfãos
todos os chunks com parent_id
citações presentes nas respostas de documento
```

> **v3.10.1:** the `index_neuron_ids` fix (the `NameError` from the `embedding_text` import that blocked the sqlite-vec reindex path — root cause of the 32% non-vectorized neurons) raised vector coverage to **100%** (`neurons_vectorized_pct = 100%`).

---

## 13. K10 — Scale, isolation, and federation

`workspace_id` is the mandatory isolation boundary. Every critical UMC table carries `workspace_id` (default `'default'`). Every query in the `RetrievalRouter` and in promotion filters by `workspace_id`. Milvus uses `partition_key=workspace_id` for partition-level isolation.

**Boundary rules:**

- **Cross-workspace leakage is a security bug**, not a ranking problem.
- Structural migrations that create this boundary: failure is fail-closed by default. The only bypass is `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` (legacy DB diagnostics, with visible logging and without marking the installation as healthy).
- Federation between instances: reuses HM-12 (`visibility` private|shared|public + Ed25519 + PII redaction on export). An imported neuron enters with the destination `workspace_id` and preserved provenance. `origin_instance` and `origin_signature` are mandatory.
- Embedding migration: `vectors_model_mismatch = 0` within a collection; online re-embed per workspace, dual-write until cutover.
- Promotion cost: per-workspace cap via `HIVE_PROMOTION_BUDGET_*`; overflow stays `archived=0` (retry); `promotion_lag` and `promotion_cost` metrics per workspace.

---

## 14. HM-11 — Deep Reflection (Intent Memory + Causality)

### 14.1 Goal Planner

`scripts/planner.py` receives a natural-language goal, calls the LLM, and returns a list of atomic steps (`GoalStep`). Each goal is persisted in the `goals` table and exposed via the MCP tool `sinapse_plan_goal`.

```
  META DO USUÁRIO
        │
        ▼
  sinapse_plan_goal (ferramenta MCP)
        │
        ▼
  scripts/planner.py
        │
        ├── prompt + goal → LLM
        │
        ▼
  GoalStep[] (passos atômicos)
        │
        ├──→ INSERT goals TABLE (hive_mind.db)
        │
        └──→ observations criadas com:
               goal_id  → referência à meta ativa
               why      → rationale / intenção
```

### 14.2 Causality graph

The `causal_edges` table records cause → effect edges between neurons. `get_causal_neighbors(conn, neuron_id, hops=2)` traverses the graph with BFS up to 2 hops.

```
  neurons
     │
     ▼
  causal_edges (causa_id → efeito_id)
     │
     ▼
  get_causal_neighbors(conn, neuron_id, hops=2)
     │   BFS no grafo de causalidade
     ▼
  vizinhos causais (até 2 hops)
```

### 14.3 Intent metadata on observations

| Column | Type | Description |
|--------|------|-----------|
| `goal_id` | TEXT (FK) | Reference to the active goal in `goals.id` |
| `why` | TEXT | Rationale / intent of the observation |

---

## 15. HM-12 — Federated Swarm (federated export)

### 15.1 Neuron visibility

The `visibility` column in `neurons` controls which neurons can be exported:

| Value | Description |
|-------|-----------|
| `private` | Default. Not exported. |
| `shared` | Exportable to authorized partners. |
| `public` | Exportable without recipient restriction. |

### 15.2 Export endpoint

`POST /api/v1/neurons/export` — authenticated via Bearer token. Accepted filters: `type`, `created_after`. Options: `redact` (PII removal) and/or `sign` (Ed25519 signature).

```
  POST /api/v1/neurons/export
        │
        ▼
  SELECT neurons WHERE visibility IN ('shared', 'public')
        │  + filtros: type, created_after
        │
        ├─ redact_neuron()   ← core/redactor.py
        │   PII irreversível: tokens de API, email, IPv4/6,
        │   caminhos absolutos, chaves SSH, CPF/CNPJ, telefone
        │   (aplicado a conteúdo e label; não modifica dados locais)
        │
        ├─ sign_neuron()     ← core/signing.py
        │   Par de chaves Ed25519 (config/keys/, gitignored)
        │   Assina JSON canônico (exclui timestamps e campos _prefixados)
        │   verify_neuron() para validação no receptor
        │
        └─ resposta JSON
             { neurons[], signature?, pubkey_fingerprint? }
```

---

## 16. "Who fills what" map (by lobe)

Tables kept verbatim from [`cerebro-filling-map.md`](cerebro-filling-map.md).

### 16.1 CÓRTEX — `cortex/temporal/` (long-term memory)

| Path (from `cerebro/`) | Content | Who fills it | Type | Frequency |
|----------|----------|---------------|------|------------|
| `cortex/temporal/<project>/<topic>/neuronio-*.md` | atomic neurons (1 fact per note) | **Dream Cycle** (Distiller→Validator→Router) + **K3 promotion** (`promote_pending_observations`) | 🧠 + ⚙️ | FAST 60s (K3) / 4h (Dream) |
| `cortex/temporal/_global/` | project-less knowledge | Dream Cycle | 🧠 | 4h |
| `cortex/temporal/hipocampo/` | consolidation staging | Dream Cycle | 🧠 | 4h |
| `cortex/temporal/arquivo/` | cold memory (>90 days) | `drift_detector.py` | ⚙️ | monthly cron |
| (topic merge) | consolidation of similar topics | `topic_consolidator.py` | ⚙️ | SLOW 1h |
| (aliases) | search synonyms | `alias_miner.py` | ⚙️ | daily cron |

**What the Dream Cycle fills exactly in the temporal lobe:** it is the **Hive-Dreamer**: reads claude-mem observations, extracts facts (Distiller), validates grounding against the source (Validator), routes the topic (Router), and writes `neuronio-*.md` in the vault + a neuron in the UMC + a vector + Graphiti/LightRAG. It is the **only source of neurons with groundedness** (Evidence + synapses). K3 (`promote_pending_observations`) is the fast deterministic path (no LLM) that materializes simple observations into neurons.

### 16.2 CÓRTEX — `cortex/frontal/` (decision, planning, work)

| Path (from `cerebro/`) | Content | Who fills it | Type | Frequency |
|----------|----------|---------------|------|------------|
| `cortex/frontal/decisoes/<project>/dec-*.md` | decision records (Context/Rationale/Alternatives/Consequences) | `decision_promoter.py` (`--with-llm`) | 🧠 | MEDIUM 5min |
| `cortex/frontal/trabalho/ativo/` | active work items (next steps) | `work_tracker.py` | ⚙️ | MEDIUM 5min |
| `cortex/frontal/trabalho/arquivo/` | completed | agent moves active→archive | ✍️ | on demand |
| `cortex/frontal/projetos/` | aggregated status per project (human name) | `project_synthesizer.py` | 🧠 + ⚙️ | MEDIUM 5min |
| `cortex/frontal/brain/Current State.md` | current brain state + session decisions/learnings | `sinapse_session_end` (MCP) | ⚙️ | session end |
| `cortex/frontal/org/people/` | people (individual profile) | agent (`Person Note` template) | ✍️ | on demand |
| `cortex/frontal/org/teams/` | teams | agent | ✍️ | on demand |

### 16.3 CÓRTEX — `cortex/parietal/` (sensory: inbox, references)

| Path (from `cerebro/`) | Content | Who fills it | Type | Frequency |
|----------|----------|---------------|------|------------|
| `cortex/parietal/inbox/visual/` | received visual captures | `visual_capture.py` + `sinapse_capture_screen` | ⚙️ | on demand |
| `cortex/parietal/inbox/documents/` | received documents | DocumentPipeline (`document_pipeline.py`) | ⚙️ | on demand |
| `cortex/parietal/referencias/` | external references | agent (`sinapse_save_*`) | ✍️ | on demand |
| `cortex/parietal/analises/` | analyses | agent | ✍️ | on demand |

### 16.4 CÓRTEX — `cortex/occipital/` (vision)

| Path (from `cerebro/`) | Content | Who fills it | Type | Frequency |
|----------|----------|---------------|------|------------|
| `cortex/occipital/capturas-visuais/` | screenshots indexed with description | `sinapse_capture_screen` → visual_memories | 🧠 | on demand |
| `cortex/occipital/grafo/graph.json` | knowledge graph (Leiden clusters) | **Graphify** (external organ) | ⚙️ | continuous watch |

### 16.5 CÓRTEX — `cortex/insula/` (interoception, self-awareness)

| Path (from `cerebro/`) | Content | Who fills it | Type | Frequency |
|----------|----------|---------------|------|------------|
| `cortex/insula/saude/` | system health snapshots | `health_dashboard.py` + `audit_memory.py` (knowledge_health) | ⚙️ + 🧠 | MEDIUM 5min / daily cron |
| `cortex/insula/conflitos/` | detected contradictions for human review | `conflict_detector.py` + `review_writer.py` | 🧠 | weekly cron |

### 16.6 CEREBELO — `cerebelo/` (rhythm and coordination — hierarchical cadence)

| Path (from `cerebro/`) | Content | Who fills it | Type | Frequency |
|----------|----------|---------------|------|------------|
| `cerebelo/sessoes/` | session logs | `session_consolidator.py` + `bridge_session_summaries.py` (imports from claude-mem) | ⚙️ | continuous |
| `cerebelo/diario/` | daily reflections | `daily_writer.py` | 🧠 | MEDIUM 5min |
| `cerebelo/semanal/` | weekly syntheses | `weekly_synthesizer.py` | 🧠 | DAILY 6h |
| `cerebelo/mensal/` | monthly syntheses | `monthly_synthesizer.py` | 🧠 | DAILY 6h |
| `cerebelo/anual/` | yearly historical memory | `yearly_synthesizer.py` | 🧠 | DAILY 6h |
| `cerebelo/padroes/Patterns.md` | learned patterns (canonical reference) | `pattern_distiller.py` + `sinapse_save_learning` (MCP) | 🧠 | weekly cron / on demand |

**Hierarchical cadence** (the cerebellum ascends in granularity): `sessoes → diario → semanal → mensal → anual`. Each layer consolidates the previous one.

### 16.7 DIENCÉFALO — `diencefalo/` (cross-project relay)

| Path (from `cerebro/`) | Content | Who fills it | Type | Frequency |
|----------|----------|---------------|------|------------|
| `diencefalo/setores/setor-*.md` | knowledge that spans multiple projects (ai-infra, dev-tools, pkm, infra, finance, health, research) | `sector_classifier.py` (classifies neurons) + `sector_aggregator.py` (aggregates into sectors) | 🧠 + ⚙️ | on demand / batch |
| `diencefalo/roteamento/` | routing rules between projects | `sector_classifier.py` + cross-linker | 🧠 | on demand |

### 16.8 TRONCO — `tronco/` (vital infrastructure — sibling of the others, not subordinate)

| Path (from `cerebro/`) | Content | Who fills it | Type | Frequency |
|----------|----------|---------------|------|------------|
| `tronco/modelos/` | typed Obsidian templates (Atom, Work, Decision, Person...) | manual (static) | ✍️ | setup |
| `tronco/paineis/` | `.base` bases (Work Dashboard, Incidents, People...) | manual (static) | ✍️ | setup |
| `tronco/infra/` | agents, hooks, configuration | manual (static) | ✍️ | setup |
| `tronco/meta/` | sub-vaults, cross-vault links | manual (design decision) | ✍️ | setup |

### 16.9 Vault root

| File | Content | Who fills it | Type | Frequency |
|---------|----------|---------------|------|------------|
| `_Consciencia.md` | root MOC (index of all lobes) | `generate_mocs.py` | ⚙️ | on demand |
| `Home.md` | entry point | manual | ✍️ | setup |
| `vault-manifest.json` | vault manifest | manual | ✍️ | setup |

---

## 17. Summary by filler type

### 🧠 LLM (generates new knowledge)

| Script | Fills | Recommended model |
|--------|----------|--------------------|
| `dream_cycle.py` (Distiller/Validator/Router) | neurons `.md` + Graphiti/LightRAG | instruct `granite4.1:8b` local (Distiller/Router) + reasoning `qwen3.5:397b` (Validator) |
| `daily_writer.py` | daily | instruct 3-7b local |
| `weekly_synthesizer.py` | weekly | light reasoning API |
| `monthly_synthesizer.py` | monthly | reasoning API |
| `yearly_synthesizer.py` | yearly | strong reasoning API |
| `pattern_distiller.py` | patterns | reasoning API |
| `decision_promoter.py` | decisions | short reasoning API |
| `conflict_detector.py` | conflicts | light reasoning API |
| `sector_classifier.py` | sectors | instruct 3-7b local |

### ⚙️ Deterministic (reorganizes)

| Script | Fills |
|--------|----------|
| `consolidate_loop.py` (bridge→promote→materialize) | orchestrates the continuous flow |
| `work_tracker.py` | active work |
| `session_consolidator.py` | sessions |
| `bridge_session_summaries.py` | imports session_summaries from claude-mem |
| `topic_consolidator.py` | topic merge |
| `alias_miner.py` | aliases |
| `drift_detector.py` | cold archive |
| `generate_mocs.py` | MOCs |
| `sector_aggregator.py` | aggregates sectors |
| `health_dashboard.py` / `audit_memory.py` | health + metrics |

### ✍️ Manual (on demand from human/agent)

| What | Who |
|-------|------|
| `org/people`, `org/teams` | agent (Person Note template) |
| `referencias/`, `analises/` | agent |
| `tronco/modelos`, `paineis`, `infra`, `meta` | manual setup |
| `trabalho/arquivo/` | agent moves active→archive |

---

## 18. How everything connects (the orchestrator)

The **`consolidate_loop.py`** (`sinapse-consolidate` service) is the heart that keeps the brain alive in a cascade:

```
FAST (60s):     bridge() → promote_pending_observations() → materialize_orphan_neurons()
                → escreve neurônios no lobo temporal (via K3 determinístico)

MEDIUM (5min):  decision_promoter --with-llm  → cortex/frontal/decisoes
                work_tracker --apply          → cortex/frontal/trabalho
                project_synthesizer --apply   → cortex/frontal/projetos
                health_dashboard              → cortex/insula/saude
                daily_writer --no-llm         → cerebelo/diario

SLOW (1h):      topic_consolidator            → merge de tópicos no temporal

DAILY (6h):     weekly/monthly/yearly_synthesizer → cadência longa do cerebelo
```

The **Dream Cycle** (`dream_cycle.py`, cron `0 */4 * * *`) complements it with the high-quality LLM pipeline (Distiller→Validator→Router) for neurons that require groundedness and evidence — it is the semantic enrichment, not the volume flow.

---

## 19. Update frequency

| Pipeline | Frequency | Trigger |
|----------|-----------|---------|
| Decision/learning write | Immediate | PostToolUse / Stop hook |
| UMC indexing (Watcher) | ~2 seconds | watchdog FileModifiedEvent |
| Dream Cycle | 4h (cron `0 */4 * * *`) | `python3 scripts/dream/dream_cycle.py` |
| P2P audit | 1x per hour | cron `audit_memory.py --fix` |
| UMC backup | daily 3h | cron `cp hive_mind.db backups/` |

---

## 20. Data volume

| Metric | Typical value |
|---------|-------------|
| neurons in UMC | 1,200+ |
| synapses in UMC | 1,300+ |
| causal_edges in UMC | grows with use |
| goals (planner) | per planning session |
| pending observations (per session) | 5-30 |
| atlas/*.md (consolidated facts) | grows with use |
| hive_mind.db size | 50-200MB |
| hnsw_neurons.idx size | ~5-20MB (depends on neurons) |
| claude-mem/data/lightrag/ size | ~5-50MB (graph + entity/relation vdb) |
| reindex time per file | ~1-3s |
| KNN search (10k vectors, 1024d) | ~5-10ms |
| HNSW search (1024d) | ~1-2ms |
| FTS5 search | ~2ms |
| LightRAG query (hybrid, ~1k entities) | ~100-300ms (local LLM) |

### Database tables (hive_mind.db)

| Table | Purpose | Phase |
|--------|-----------|------|
| `neurons` | knowledge nodes (with `visibility` in v3 + `workspace_id` in K10) | base + K10 |
| `synapses` | WikiLink edges between neurons | base |
| `observations` | raw data with `goal_id`/`why` (HM-11) + `workspace_id` + `source_id` (K4) | base + HM-11 + K4 + K10 |
| `search_fts` | Full-Text Search index (FTS5) | base |
| `search_vec` | vector index (vec0 sqlite-vec, 1024d) | base + K1 |
| `causal_edges` | cause→effect causality graph | HM-11 |
| `goals` | goals decomposed by the planner | HM-11 |
| `vector_metadata` | canonical metadata (parent_id, brain_lobe, knowledge_type, source_uri, valid_at, workspace_id) | K1 |
| `ambiguities` | P2P conflicts (content_a, content_b, hashes, status) | base + K10 |
| `vault` | encrypted secrets (Fernet) | base |
| `document_memories` | document parents (K6) | K6 |
| `document_chunks` | document atoms (offsets, parent_id, hash) | K6 |
| `document_vectors` | chunk vectors (K6, with canonical metadata) | K6 |
| `knowledge_tombstones` | auditable tombstones from `forget()` (§31.2) | K8 |
| `query_route_log` | query hash × route (K7) — `query_route_distribution` telemetry | K7 |

---

## 21. Governance: rollback, fallback, lineage, and classification

The data flow is governed by data discipline principles (Data & AI):

### 21.1 Structured rollback and fallback

- **Promotion fail-closed and data preservation (ADR-016):** transient error → `archived=0` (future retry); structural error → `archived=2` (quarantine with reason). Nothing is erased by a promotion failure.
- **LLM fallback (ADR-008):** in any final failure path, the observation goes to quarantine (`archived=2`) — **nothing is lost**.
- **Real-time indexing:** the Watcher reindexes from the source file in the vault, so any index inconsistency can be rebuilt from the vault (source of truth) without loss.
- **Embedding migration (K10):** dual-write until cutover; the old collection enters `forget` (tombstone), never silent physical deletion.

### 21.2 Explicit lineage

- `source_id` stable (`claude-mem:<table>:<id>`) is preserved from intake to promotion.
- Atlas persistence frontmatter carries `agent`, `consolidated_at`, `source_observation_ids`, `confidence`.
- Federation requires `origin_instance` and `origin_signature` in the imported neuron.
- Route telemetry (`query_route_log`) stores only the query hash, never raw text.

### 21.3 Data classification

- The canonical `knowledge_type` classifies each fact at K3 (fact/decision/learning/preference/task/…).
- `visibility` (private|shared|public) governs federated export (HM-12).
- PII is redacted irreversibly on export (`core/redactor.py`) and never in local data.
- Secrets detected on write go to the `vault` table (Fernet), never in plain text.

---

## 22. Cross-references

- [`architecture.md`](architecture.md) — Born-Large anatomy (K0–K10), §22–§31, ADRs.
- [`ai-models.md`](ai-models.md) — LLM roles, reasoning, Model Gateway, embeddings, fallback chain.
- [`runtime.md`](runtime.md) — `hive-mindd` daemon and the declarative service manifest (includes `sinapse-consolidate`).
- [`installation.md`](installation.md) — installation, setup-brain, agent registration.
- [`operations.md`](operations.md) — Dream Cycle operation, watcher, backup, P2P audit.
- [`observability.md`](observability.md) — K8 health, `sinapse_health`, gateway metrics and collections.
- Source documents: [`03-data-pipeline.md`](03-data-pipeline.md), [`cerebro-filling-map.md`](cerebro-filling-map.md), [`02-ai-models.md`](02-ai-models.md), [`ai-models.md`](ai-models.md), [`architecture.md`](architecture.md).
