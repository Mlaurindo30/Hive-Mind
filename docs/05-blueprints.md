# 05 — Blueprints and Flowcharts

> **Hive-Mind v3.0.0** — Architecture diagrams and flows in ASCII (compatible with any Markdown editor).
> Last review: 2026-06-30. Includes the **canonical 9-step flow** (K0–K10), `RetrievalRouter` (K7), `DocumentPipeline` (K6), hierarchical cadence (K5), and the extended anatomy with `workspace_id` (K10). Normative reference in [`01-architecture.md` §22–§31](01-architecture.md#22-arquitetura-de-conhecimento-born-large) (see [`docs/README.md`](README.md) for a note on why `docs/11-*` is not a separate file in this checkout).

---

## 1. 4-Layer Architecture

```
  ┌───────────────────────────────────────────────────────────────────┐
  │                            AI AGENTS                              │
  │                                                                   │
  │   ┌──────────┐  ┌────────────┐  ┌───────────┐  ┌─────────────┐  │
  │   │  Hermes  │  │ Claude Code│  │ Codex CLI  │  │ Other MCP   │  │
  │   │  Agent   │  │ (hooks +   │  │ (hooks +   │  │ (Cursor,    │  │
  │   │ (plugin) │  │  MCP)      │  │  MCP)      │  │  OpenClaw)  │  │
  │   └────┬─────┘  └─────┬──────┘  └─────┬─────┘  └──────┬──────┘  │
  └────────┼──────────────┼───────────────┼───────────────┼──────────┘
           │              │               │               │
  ┌────────▼──────────────▼───────────────▼───────────────▼──────────┐
  │                     INTEGRATION LAYER                             │
  │                                                                   │
  │  sinapse-memory.py   sinapse-mcp.py   sinapse-hook.py            │
  │  (Native plugin)     (MCP stdio)      (Universal hook)           │
  │                              │                                    │
  │                       sinapse-api.py                              │
  │                       (REST :37702)                               │
  │                       POST /export  (HM-12, visibility filter)   │
  │                       sinapse-write.py                            │
  │                       (Standalone CLI)                            │
  └──────────────────────────────┬────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼────────────────────────────────────┐
  │                       MEMORY BACKENDS                             │
  │                                                                   │
  │  ┌───────────────┐  ┌─────────────┐  ┌──────────┐  ┌─────────┐  │
  │  │ UMC (SQLite)  │  │  claude-mem │  │  Neural  │  │   RTK   │  │
  │  │ FTS5 + vec    │  │  :37700     │  │  Memory  │  │  (Rust) │  │
  │  │ neurons +     │  │  temporal   │  │ spreading│  │  shell  │  │
  │  │ synapses +    │  │  tracking   │  │activation│  │  optim. │  │
  │  │ causal_edges +│  │             │  │          │  │         │  │
  │  │ goals (HM-11) │  │             │  │          │  │         │  │
  │  └───────┬───────┘  └──────┬──────┘  └────┬─────┘  └─────────┘  │
  └──────────┼─────────────────┼──────────────┼──────────────────────┘
             │                 │              │
  ┌──────────▼─────────────────▼──────────────▼──────────────────────┐
  │                           STORAGE                                 │
  │                                                                   │
  │   hive_mind.db          cerebro/              backups/            │
  │   (UMC — SQLite +       (Obsidian Vault)      (daily cp)          │
  │    sqlite-vec)          cortex/ cerebelo/ tronco/                 │
  │   hnsw_neurons.idx      cortex/frontal/trabalho/ativo/            │
  │   (Incremental HNSW,    config/keys/                              │
  │    HM-11)               (Ed25519, gitignored)                     │
  └───────────────────────────────────────────────────────────────────┘
```

---

## 2. Read Flow (Read Path)

```
  User writes a message to the agent
                │
                ▼
  SessionStart hook / pre_gateway_dispatch
                │
                ▼
  _query_vault_knowledge(query, timeout=8s)
                │
        ┌───────┴────────────────────────────────────┐
        │                (parallel)                  │
        ▼               ▼              ▼             ▼
  ┌──────────┐   ┌──────────┐   ┌──────────┐  ┌──────────┐
  │ UMC SQL  │   │claude-mem│   │NeuralMem │  │Filesystem│
  │ FTS5     │   │ HTTP     │   │spreading │  │scan *.md │
  │ KNN vec  │   │ :37700   │   │activation│  │TTL 30s   │
  │          │   │ timeout3s│   │timeout 5s│  │          │
  └────┬─────┘   └────┬─────┘   └────┬─────┘  └────┬─────┘
       │              │              │              │
       └──────────────┴──────────────┴──────────────┘
                             │
                     merge + dedup
                    (source_file + title)
                             │
                     format(top-5, max 3000 chars)
                             │
                             ▼
              inject into the agent system_message
                             │
                             ▼
  Agent responds with vault context
```

---

## 3. Write Flow (Write Path)

```
  Agent calls memory tool
  (sinapse_save_decision | sinapse_save_learning | memory_add)
                │
                ▼
  PostToolUse hook detects DECISION_TOOLS
                │
                ├── _sanitize_slug(title)
                │     "Minha Decisão" → "2026-06-10-minha-decisao"
                │
                ├── _validate_frontmatter_yaml()
                │     checks: tags, status, created
                │
                ├── secret_scan(content)
                │     regex: sk-proj-*, AKIA*, Bearer, api_key=
                │     → Fernet encrypt → vault table
                │     → replace with "[SECRET:uuid]" in content
                │
                ├── _atomic_write(path, content)
                │     mkstemp() → write → os.replace()  ← atomic
                │
                └── If LEARNING_SIGNALS in content:
                      _save_learning() → cerebelo/padroes/Patterns.md
                      _dedup_check() → does not duplicate same title
                                │
                                ▼ (~2 seconds)
              Watcher detects FileModifiedEvent
                                │
                                ▼
              Graphify reindexes file:
              UPDATE neurons / synapses / FTS5 / vec

  ─ ─ ─ ─ ─ ─ ─ End of session ─ ─ ─ ─ ─ ─ ─

  Stop hook / on_session_end
                │
                ├── _update_current_state()
                │     brain/Current State.md
                │     (WikiLinks to session decisions)
                │
                └── INSERT observations(type='session_end')
```

---

## 4. Dream Cycle — Consolidation Pipeline

```
  hive_mind.db
  observations (archived=0, unprocessed)
         │
         ▼  (batch of up to N per run)
  ┌──────────────────────┐
  │      DISTILLER       │
  │  LLM → DistilledFact │
  │  JSON schema via     │
  │  Pydantic            │
  └──────────┬───────────┘
             │ DistilledFact
             ▼
  ┌──────────────────────┐         ┌──────────────────────┐
  │      VALIDATOR       │──rejec→ │     QUARANTINE       │
  │  LLM: approved?      │ ted     │  archived=2           │
  │  max 2 retries       │         │  (not lost)           │
  └──────────┬───────────┘         └──────────────────────┘
             │ approved
             ▼
  ┌──────────────────────┐
  │       ROUTER         │
  │  classify destination│
  │  duplicate check     │
  │  cosine > 0.92       │
  └──────────┬───────────┘
             │
      ┌──────┴────────┐
      │               │
      ▼ new           ▼ duplicate
  ┌─────────────┐  ┌───────────────┐
  │ ATLAS WRITE │  │ MERGE         │
  │ atomic write│  │ append unique │
  │ INSERT neuron│ │ insights only │
  └──────┬──────┘  └───────┬───────┘
         │                 │
         └────────┬────────┘
                  │
                  ▼
  UPDATE observations SET archived=1
  (consolidated_at = NOW())
```

---

## 5. Circuit Breaker (Fallback Chain)

```
  Query arrives at search engine
         │
         ▼
  ┌──────────────────┐      3+ failures  ┌───────────────┐
  │ UMC SQL (FTS5 +  │──────────────────▶│   COOLDOWN    │
  │  KNN vec)        │   cooldown 30s    │   30 seconds  │
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  ┌──────────────────┐      3+ failures  ┌───────────────┐
  │ claude-mem       │──────────────────▶│   COOLDOWN    │
  │ HTTP :37700      │   cooldown 30s    │   30 seconds  │
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  ┌──────────────────┐      3+ failures  ┌───────────────┐
  │ NeuralMemory     │──────────────────▶│   COOLDOWN    │
  │ spreading activ. │   cooldown 30s    │   30 seconds  │
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  ┌──────────────────┐      3+ failures  ┌───────────────┐
  │ Filesystem scan  │──────────────────▶│   None        │
  │ cerebro/*.md     │                   │ (no context)  │
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  result returned to the agent

  Note: empty results (not found) do NOT count as failure.
        Only Python exceptions and timeouts trigger the circuit breaker.
```

---

## 6. Graphify Pipeline (Structural Indexing)

```
  cerebro/*.md  (Obsidian vault)
         │
         ▼
  ┌──────────────┐
  │   PARSER     │
  │  frontmatter │  extracts: title, tags, WikiLinks
  │  YAML        │
  └──────┬───────┘
         │
         ▼
  ┌───────────────────────────────────────────┐
  │  BACKEND (chosen by availability)         │
  │                                           │
  │  1st: Gemini 2.5 Flash (cloud)            │
  │      NER: entities + relations            │
  │                                           │
  │  2nd: Ollama Qwen 2.5 Coder 3B (local)   │
  │      Local NER, no API key               │
  │                                           │
  │  3rd: tree-sitter + regex (deterministic)│
  │      syntactic parsing, always works     │
  └──────┬────────────────────────────────────┘
         │ entities + relations
         ▼
  ┌──────────────────┐
  │   EMBEDDING      │
  │  snowflake-      │  1024 dimensions, local Ollama
  │  arctic-embed2   │
  └──────┬───────────┘
         │ vector 1024d
         ▼
  ┌────────────────────────────────────────────┐
  │  hive_mind.db                              │
  │  INSERT/UPDATE neurons (id, title, hash)   │
  │  (MOCs type:moc stay out of the index)     │
  │  INSERT/UPDATE synapses (source, target)   │
  │  UPDATE search_fts (automatic trigger)     │
  │  UPDATE search_vec (vec0 HNSW)             │
  └────────────────────────────────────────────┘
```

---

## 7. Multi-Agent Integration

```
  ┌────────────────────────────────────────────────────────────────┐
  │  HERMES (Native Plugin)                                        │
  │   pre_gateway_dispatch → post_tool_call → on_session_end       │
  │   File: plugins/hermes/sinapse-memory.py                       │
  └────────────────────────────────┬───────────────────────────────┘
                                   │
  ┌────────────────────────────────┼───────────────────────────────┐
  │  CLAUDE CODE (MCP + Hooks)     │                               │
  │   SessionStart ────────────────┤                               │
  │   PostToolUse  ────────────────┤──▶  sinapse-hook.py           │
  │   Stop         ────────────────┤                               │
  │   MCP tools ──────────────────▶│──▶  sinapse-mcp.py (16 tools) │
  └────────────────────────────────┤───────────────────────────────┘
                                   │
  ┌────────────────────────────────┼───────────────────────────────┐
  │  CODEX CLI (MCP + Hooks)       │                               │
  │   SessionStart ────────────────┤                               │
  │   PostToolUse  ────────────────┤──▶  sinapse-hook.py           │
  │   Stop         ────────────────┤                               │
  │   MCP tools ──────────────────▶│──▶  sinapse-mcp.py (16 tools) │
  └────────────────────────────────┤───────────────────────────────┘
                                   │
  ┌────────────────────────────────┼───────────────────────────────┐
  │  OTHERS (MCP only)             │                               │
  │  Cursor, OpenClaw, KiloCode ───┤──▶  sinapse-mcp.py (10 tools) │
  └────────────────────────────────┤───────────────────────────────┘
                                   │
  ┌────────────────────────────────▼───────────────────────────────┐
  │  REST API (cloud mode)                                         │
  │  sinapse-api.py :37702 (Bearer token)                          │
  │  /api/v1/query  /api/v1/observations  /api/v1/health           │
  │  /api/v1/neurons/export  (HM-12, visibility filter + redact)   │
  └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                          hive_mind.db (UMC)
```

---

## 8. Atomic Write

```
  _atomic_write(filepath, content)
         │
         ▼
  mkstemp(dir=parent_dir)
         │ returns (fd, tmppath)
         ▼
  write(fd, content.encode('utf-8'))
         │
         ▼
  close(fd)
         │
         ▼
  os.replace(tmppath, filepath)
         │                         ← ATOMIC on Linux/POSIX
         ▼                           rename(2) syscall
  final file integrity preserved

  Failure scenarios:
    Process dies before replace:
      tmppath remains orphaned (does not affect filepath)
    Process dies during replace:
      Kernel guarantees atomicity — filepath is either old or new
    Disk full during write:
      write() raises OSError — tmppath discarded, filepath intact
```

---

## 9. P2P Sync (Multi-Machine Synchronization)

```
  Machine A                    Syncthing                    Machine B
  (cerebro/)                   (transport)                  (cerebro/)
     │                              │                            │
     │ file.md created/edited       │                            │
     │──────────────────────────────▶                            │
     │                              │──────────────────────────▶│
     │                              │  file.md received         │
     │                                                           │
     │                                    Watcher detects (~2s) │
     │                                    OR cron audit_memory.py│
     │                                                           │
     │                                    audit_memory.py --fix  │
     │                                       │                   │
     │                                       ▼                   │
     │                                    SHA-256(file.md)       │
     │                                       │                   │
     │                                 hash == neurons.hash?     │
     │                                    │         │            │
     │                               yes (ok)   no (divergence)  │
     │                                    │         │            │
     │                                  skip    reindex neuron   │
     │                                           + INSERT        │
     │                                          ambiguities      │
     │                                               │           │
     │                                        Dream Cycle:       │
     │                                        Dialectical Synthesis│
     │                                        (merge/choose/     │
     │                                         branch)           │
```

---

## 10. HM-11 — Intent & Causality Flow

```
  USER GOAL
        |
        v
  [ sinapse_plan_goal ] --- LLM ---> steps (GoalStep[])
        |                                  |
        v                                  v
  goals TABLE                    observations (goal_id, why)

  neurons ---> causal_edges ---> get_causal_neighbors (BFS 2-hop)
               (causa_id,
                efeito_id)
```

Components involved:

| Componente | Arquivo | Responsabilidade |
|------------|---------|-----------------|
| Planner | `scripts/planner.py` | Decomposes goal into GoalStep[] via LLM |
| MCP tool | `sinapse_plan_goal` | Exposes planner as an MCP tool |
| Tabela goals | `hive_mind.db` | Persists goals and steps |
| Intent metadata | `observations.goal_id`, `.why` | Links observation to active goal |
| Causal graph | `causal_edges` | Causal edge -> effect between neurons |
| BFS causal | `get_causal_neighbors()` | Retrieves causal neighbors up to 2 hops |
| HNSW Index | `core/hnsw_index.py` | Incremental index, writes `indexed_at` |

---

## 11. HM-12 — Federated Export Flow

```
  POST /api/v1/neurons/export
        |
        v
  visibility IN ('shared', 'public')
  + optional filters: type, created_after
        |
        |-- redact_neuron()  <-- core/redactor.py  (PII removal)
        |   API tokens, email, IPv4/6, absolute paths,
        |   SSH keys, CPF/CNPJ, phone
        |   (does not modify local neuron)
        |
        |-- sign_neuron()    <-- core/signing.py   (Ed25519)
        |   canonical JSON (excludes timestamps and _prefixed fields)
        |   verify_neuron() for receiver-side validation
        |   Keys in config/keys/ (gitignored)
        |
        v
  JSON response
  { neurons[], signature?, pubkey_fingerprint? }
```

Components involved:

| Componente | Arquivo | Responsabilidade |
|------------|---------|-----------------|
| Export endpoint | `scripts/services/sinapse-api.py` | `POST /api/v1/neurons/export`, authenticated |
| Visibility filter | `neurons.visibility` | `private` (default) / `shared` / `public` |
| Redactor | `core/redactor.py` | Irreversibly removes PII before export |
| Signing | `core/signing.py` | Ed25519 keypair, signs/verifies canonical JSON |

---

## 12. Components — v3.0.0 Overview

| Componente | Arquivo | Fase | Descricao |
|------------|---------|------|-----------|
| UMC core | `hive_mind.py` | base | SQLite + FTS5 + sqlite-vec |
| Graphify watcher | `graphify/` | base | Real-time indexing |
| Dream Cycle | `scripts/dream/dream_cycle.py` | base | Offline consolidation |
| sinapse-api | `scripts/services/sinapse-api.py` | base | REST :37702 |
| sinapse-mcp | `scripts/services/sinapse-mcp.py` | base | MCP stdio (16 tools) |
| sinapse-hook | `cerebro/tronco/infra/agentes/.claude/scripts/sinapse-hook.py` | base | Universal hooks |
| HNSW Index | `core/hnsw_index.py` | HM-11 | Incremental 1024d index with canonical embedding `snowflake-arctic-embed2` |
| Planner | `scripts/analytics/planner.py` | HM-11 | LLM goal decomposer |
| Signing | `core/signing.py` | HM-12 | Ed25519 signing/verification |
| Redactor | `core/redactor.py` | HM-12 | Irreversible PII removal |

---

## 13. VPS Deployment

```
  Internet
     │ HTTPS (TLS via nginx/Caddy)
     ▼
  ┌──────────────────────────────────────────────────────────┐
  │  VPS                                                     │
  │                                                          │
  │  nginx/Caddy (:443) → proxy → sinapse-api.py (:37702)  │
  │                                                          │
  │  systemd units:                                          │
  │    hive-mind-api.service      (sinapse-api.py)           │
  │    hive-mind-watcher.service  (start-watcher.sh)         │
  │    claude-mem.service         (bun run serve :37700)     │
  │    syncthing.service          (P2P sync)                 │
  │    ollama.service             (:11434)                   │
  │                                                          │
  │  cron:                                                   │
  │    0 */6 * * * build-graph.sh                            │
  │    0 * * * * audit_memory.py --fix                       │
  │    0 2 * * * dream_cycle.py --once --real                │
  │    0 3 * * * backup_databases.py                         │
  │    15 3 1 * * monthly_synthesizer.py --real              │
  │    30 3 1 1 * yearly_synthesizer.py --real               │
  │    45 3 * * * vector-sync summary_vectors (if Milvus)    │
  │                                                          │
  │  hive_mind.db ← Watcher ← cerebro/ ← Syncthing ──────┐ │
  │                                                       │ │
  └───────────────────────────────────────────────────────┼─┘
                                                          │
                                                   ┌──────┴──────┐
                                                   │  Other      │
                                                   │  machines   │
                                                   │  (Syncthing)│
                                                   └─────────────┘
```

---

## 13. Canonical 9-Step Flow (K0–K10)

Complete version of the knowledge flow ([`01-architecture.md` §23](01-architecture.md#23-fluxo-de-captura--promoção--recuperação)):

```text
  Agent / Human / System
          |
          v
  [1] Capture Layer
      hooks · MCP · CLI · browser · documents · code · screenshots · runtime
          |
          v
  [2] Temporal Hippocampus (claude-mem)
      user_prompts · observations · discoveries · session_summaries
      facts / narrative / concepts · files_read / files_modified
          |
          v
  [3] Knowledge Intake (core/knowledge/intake.py — K3)
      normalize · classify · deduplicate · preserve evidence
          |
          v
  [4] Promotion Layer (core/knowledge/promotion.py — K4)
      Distiller → Validator → Router
      raw -> summary -> fact / learning / decision / preference / task / rationale
          |
          v
  [5] Anatomical Memory
      cerebro/ + UMC:
        temporal · frontal · parietal · occipital · insula cortex
        cerebelo · diencefalo · tronco
          |
          v
  [6] Index Layer
      FTS · sqlite-vec · Milvus · vec_observations · Graphify · Graphiti · LightRAG
      (7 canonical collections — K1)
          |
          v
  [7] Retrieval Router (core/retrieval/router.py — K7)
      classify intent → choose temporal · memory · document · code · graph · chunk · hybrid
          |
          v
  [8] Answer + Citation
      answer with source · evidence · path · date
      (citations[{source_uri, offset_start, offset_end, score, parent}])
          |
          v
  [9] Feedback
      new observation, decision, learning, or task
```

**Edge rule:** each stage is loosely coupled. Failure in [4] does not block [1]–[3] (the observation returns with `archived=0` or `archived=2`). Nothing is deleted due to promotion failure (ADR-016).

---

## 14. RetrievalRouter (K7) — Intent-Based Routing

```text
                            query
                              |
                              v
                +----------- RetrievalRouter ----------+
                |          (K7, classifies intent)      |
                |                                      |
                v                                      v
      classified intent                      low confidence?
                |                                      |
        +-------+-------+-------+-------+             v
        |       |       |       |       |      fallback to
        v       v       v       v       v      sinapse_query
   temporal  memory   doc     code    graph   (Context Fusion)
   (claude-  (memory  (doc    (code   (Graphiti/
    mem)    vectors) vectors) vectors) LightRAG)
                |
                v
       response with
       retrieval_path + citations + confidence + missing_context
```

**Canonical routes (from [`01-architecture.md` §26](01-architecture.md#26-retrievalrouter-k7--roteamento-por-intenção)):**

- recent / "what happened" → claude-mem temporal
- decision / preference → memory_vectors + FTS
- learning → learning atoms + Patterns parent
- document → document_vectors + parent context
- code → code_vectors + Graphify
- causality / when it was true → Graphiti
- global / multi-hop question → LightRAG/GraphRAG
- health / self-awareness → Ínsula (health/conflicts)
- config / operational / model → Tronco (operational_fact)
- sector / cross-project → Diencéfalo + Graphiti
- ambiguous → hybrid + reranker (optional, §31.1)

**Return contract** (every K7 query returns):

```json
{
  "answer_context": [],
  "citations": [],
  "retrieval_path": [],
  "confidence": 0.0,
  "missing_context": []
}
```

Telemetry `query_route_distribution` (query hash, not text) is written to `query_route_log` to feed K8 health metrics.

---

## 15. DocumentPipeline (K6) — Born-Large Ingestion

Inspired by RAGFlow, while **preserving Hive-Mind anatomy**:

```text
  document (.md / .txt / .pdf / .docx)
              |
              v
  layout-aware parse
  (RAGFlow headless OR local parser)
              |
              v
  normalize
              |
              v
  chunk by structure
  (300-800 tokens; by section for MD; by symbol for code)
              |
              v
  metadata + citations
  (parent_id, offsets, source_uri, hash, heading, workspace_id)
              |
              v
  embedding 1024d
  (snowflake-arctic-embed2)
              |
              v
  document_memories (parent) + document_chunks (atoms) + document_vectors
              |
              v
  optional: KnowledgePromotionPipeline (K3/K4)
            -> fact / learning / decision / preference / rationale
```

**Three levels to avoid "loose text" (K6):**

| Nível | Tabela/coleção | Conteúdo | Por que existe |
|---|---|---|---|
| Parent document | `document_memories` | `document_id`, `source_uri`, `file_hash`, `project`, `workspace_id`, metadata | Proof of origin and re-ingestion unit |
| Chunk | `document_chunks` | `parent_id`, `parent_type=document`, `chunk_index`, `heading`, offsets, `hash`, metadata | Recoverable atomic unit |
| Vector | `document_vectors` | chunk embedding + canonical metadata | Local/Milvus semantic search without losing parent context |

**RAGFlow:** optional adapter/headless; never source of truth. Any reused output must be normalized into UMC before becoming retrievable. RAGFlow unavailability **does not** break the local-first path.

---

## 16. VectorBackend — 7 Canonical Collections (K1)

```text
                          VectorBackend
                       (single contract, §24)
                              |
        +---------+-----------+-----------+-----------+---------+--------+
        |         |           |           |           |         |        |
        v         v           v           v           v         v        v
   memory    observation  document    code      visual    graph   summary
   _vectors  _vectors     _vectors    _vectors   _vectors  _vectors _vectors
   (facts)   (claude-mem) (chunks)   (symbols)  (shots)   (entities)(session
                                                          +rels    ->yearly)
        |         |           |           |           |         |        |
        v         v           v           v           v         v        v
   sqlite-vec  sqlite-vec   sqlite-vec   sqlite-vec  sqlite-vec sqlite-vec sqlite-vec
   (UMC)       (claude-mem) (UMC)        (UMC)       (UMC)      (UMC)     (UMC)
   (local)     (read-only)  (local)      (local)     (local)    (local)   (local)
                                                                     
   ─────────────────────────────────────────────────────────────────────
                              Milvus (production)
                              partition_key = workspace_id
```

**Canonical metadata per vector item** (required in all collections):

- `parent_id`, `parent_type`
- `brain_lobe` (cortex temporal / frontal / parietal / occipital / insula / cerebelo / diencefalo / tronco)
- `knowledge_type` (event_raw, user_prompt, fact, decision, learning, document_chunk, code_symbol, visual_observation, …)
- `project`, `workspace_id` (K10)
- `source_uri`, `hash`, `valid_at`

**Collection identity** = `(name, embedding_model, dim)`. Embedding migration (K10): online re-embed by workspace, dual-write until cutover, `vectors_model_mismatch` metric = 0 within a collection.

---

## 17. Hierarchical Cadence (K5) — Session → Yearly

```text
  +---------------+     +-----------------+     +-----------------+
  |   session      |     |   daily          |     |   weekly        |
  | session_       |     |  daily_writer    |     |  weekly_        |
  | summarizer     |     |  (small/medium)  |     |  synthesizer    |
  | (small)        |     |                 |     |  (medium/strong)|
  +-------+--------+     +--------+--------+     +--------+---------+
          |                       |                       |
          v                       v                       v
  cerebelo/sessoes/         cerebelo/diario/         cerebelo/semanal/
  YYYY/MM/YYYY-MM-          YYYY/MM/YYYY-MM-         YYYY-Wxx.md
  DD-HHMM-{slug}.md         DD.md
  summary_vectors           summary_vectors           summary_vectors

  +---------------+     +-----------------+
  |   monthly      |     |   yearly        |
  |  monthly_      |     |  yearly_        |
  |  synthesizer   |     |  synthesizer    |
  |  (strong)      |     |  (strong/batch) |
  +-------+-------+     +--------+--------+
          |                       |
          v                       v
  cerebelo/mensal/         cerebelo/anual/
  YYYY-MM.md               YYYY.md
  summary_vectors          summary_vectors
```

**Golden rule:** the higher the cadence, the less it copies text and the more it consolidates causality, decision, pattern, and consequence.

**Cadence-based promotion rule (from [`01-architecture.md` §29.2](01-architecture.md#292-contrato-de-promoção-por-cadência)):**

- **Allowed:** `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` — all with traceable source.
- **Forbidden:** turning every bullet into fact; creating a neuron without source; vectorizing duplicates without `parent_id`; promoting temporary opinion as architectural decision; overwriting previous decisions without conflict or `invalid_at`.

**Fail-closed:** a role without its own model or `dreamer` inheritance records an auditable failure and does not invent synthesis.

---

## 18. Scale and Isolation (K10) — Workspace and Federation

```text
  ┌──────────────────────────┐        ┌──────────────────────────┐
  │ Instance A (workspace=   │  P2P   │ Instance B (workspace=   │
  │ "default")               │  ───►  │ "team-1")                │
  │                          │  ◄───  │                          │
  │  all tables:             │        │  all tables:             │
  │   workspace_id = 'default'│       │   workspace_id = 'team-1'│
  │                          │        │                          │
  │  Milvus:                 │        │  Milvus:                 │
  │   partition_key =        │        │   partition_key =        │
  │   workspace_id           │        │   workspace_id           │
  │                          │        │                          │
  │  export:                 │        │  import:                 │
  │   visibility in          │        │   verify_neuron()        │
  │   (shared, public)       │        │   destination workspace_id│
  │   + redact + sign        │        │   origin_instance        │
  │                          │        │   origin_signature       │
  └──────────────────────────┘        └──────────────────────────┘
```

**Critical rule:** no neuron/vector/edge crosses `workspace_id` without going through the federation layer. Cross-workspace leakage is a security bug, not a ranking issue.

---

## 19. VectorBackend & Vector Migration (K10)

```text
  collection loads (embedding_model, dim) as identity
  ex.:  memory_vectors  ·  snowflake-arctic-embed2:latest  ·  1024

  +---------------------------+
  | embedding migration       |
  +---------------------------+
  1. create new collection with (name, new_model, new_dim)
  2. dual-write (old + new) during cutover
  3. backfill old embeddings in batch (offline)
  4. cutover: sinapse_query + RetrievalRouter start querying the new one
  5. forget() on old collection (reason 'superseded' — tombstone, no physical delete)
```

**Edge contract:** `vectors_model_mismatch` = 0 inside a collection after cutover.

---

## 20. Knowledge Promotion Pipeline (K3/K4) — Layers

```text
  claude-mem (observations, discoveries, session_summaries, facts, narrative, concepts, files_*)
        |
        v
  Knowledge Intake (K3) — core/knowledge/intake.py
    - normalize fields
    - preserve source_id (claude-mem:<table>:<id>)
    - extract evidence (files, timestamps, project, workspace_id)
    - classify knowledge_type
    - deduplicate by source_id + content hash
        |
        v
  Promotion Layer (K4) — core/knowledge/promotion.py
    Distiller  (DistillerOutput Pydantic)         "extract structured facts"
        |
        v
    Validator  (ValidatorOutput Pydantic)         "are these facts supported by logs?"
        | approved         | rejected → feedback → Distiller
        v
    Router  (RouterOutput Pydantic)              "which project/topic does it go to?"
        |
        +-- transient failure → archived=0 (retry)
        +-- structural failure → archived=2 (quarantine with reason)
        +-- success
              v
        Anatomical Persistence (cerebro/ + UMC)
              v
        Multi-Collection Indexing (K1)
          - FTS5
          - VectorBackend.upsert() in memory/observation/summary_vectors
          - Graphiti: push_neuron (causal_edges)
          - LightRAG: index_memory (entities + relations)
          - Graphify: reindexes structural graph
              v
        observation.neuron_id = neuron.id
        archived=1
```

**Automatic promotion rule:**

- **Allowed:** `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` — all with traceable source.
- **Forbidden:** turning every bullet into fact; creating a neuron without source; vectorizing duplicates without `parent_id` and hash; promoting temporary opinion as architectural decision; overwriting previous decisions without conflict or `invalid_at`.
