# Architecture — Hive-Mind v3.0.0

> Canonical architecture reference. Updated on 2026-06-30.
> For quick use: [`../README.md`](../README.md)
> **This revision consolidates the Born-Large Knowledge Architecture (K0–K10)** defined in [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md), with execution plan in [`12-knowledge-implementation-plan.md`](12-knowledge-implementation-plan.md).

---

## Index

1. [Design Principles](#1-design-principles)
1.1. [Nomenclature](#11-nomenclature)
2. [Brain Anatomy](#2-brain-anatomy)
3. [System Macro View](#3-system-macro-view)
4. [Unified Memory Core (UMC)](#4-unified-memory-core-umc)
5. [Read Flow](#5-read-flow)
6. [Write Flow](#6-write-flow)
7. [The Dream Cycle (Hive-Dreamer)](#7-the-dream-cycle-hive-dreamer)
8. [P2P Synchronization and Semantic Fusion](#8-p2p-synchronization-and-semantic-fusion)
9. [Multimodal Layer](#9-multimodal-layer)
10. [Access Layer](#10-access-layer)
11. [Multi-Provider Authentication](#11-multi-provider-authentication)
12. [Vault Structure](#12-vault-structure)
13. [Automation and Cron](#13-automation-and-cron)
14. [How to Extend for New Agents](#14-how-to-extend-for-new-agents)
15. [Tests and Quality](#15-tests-and-quality)
16. [Disaster Recovery](#16-disaster-recovery)
17. [Configuration Reference](#17-configuration-reference)
18. [HM-11 Phase: Deep Reflection](#18-hm-11-phase-deep-reflection-long-term-reasoning)
19. [HM-12 Phase: Federated Swarm](#19-hm-12-phase-federated-swarm)
20. [Design Decisions (ADRs)](#20-design-decisions-adrs)
21. [Phase Governance](#21-phase-governance)
22. [Born-Large Knowledge Architecture](#22-born-large-knowledge-architecture)
23. [Capture → Promotion → Retrieval Flow](#23-capture--promotion--retrieval-flow)
24. [VectorBackend: contract, canonical collections, and scale](#24-vectorbackend-contract-canonical-collections-and-scale)
25. [DocumentPipeline (K6) — born-large ingestion](#25-documentpipeline-k6--born-large-ingestion)
26. [RetrievalRouter (K7) — intent routing](#26-retrievalrouter-k7--intent-routing)
27. [Knowledge Promotion Pipeline (K3/K4)](#27-knowledge-promotion-pipeline-k3k4)
28. [Knowledge Health Metrics (K8)](#28-knowledge-health-metrics-k8)
29. [Hierarchical Writing Cadence](#29-hierarchical-writing-cadence)
30. [Scale and Isolation — Workspace and Federation](#30-scale-and-isolation--workspace-and-federation)
31. [Pending Contracts (Reranker, Forget, Eval, Harness)](#31-pending-contracts-reranker-forget-eval-harness)
32. [Design Decisions (ADRs)](#32-design-decisions-adrs)

---

## 1. Design Principles

1. **Single source of human-readable truth.** The Obsidian vault (`cerebro/`) is the canonical layer. SQLite is the index; Markdown is the truth. In case of divergence, the auditor reconciles in favor of the vault.
2. **Local-first.** Fully works offline on one machine. Cloud and P2P are optional and additive.
3. **One database, multiple dimensions.** Instead of graph JSON + claude-mem SQLite + vector Chroma, UMC centralizes everything in a single `hive_mind.db`. Cross-dimension queries become simple SQL.
4. **Agent and LLM agnosticism.** Any agent connects via MCP/CLI/REST. Any LLM serves the Dream Cycle through `HIVE_DREAMER_PROVIDER/MODEL`. No model is hardcoded.
5. **Fail-safe, not fail-silent.** A failing pipeline sends data to quarantine (`archived=2`), never discards it. API without key does not start. Backend with 3+ failures enters circuit breaker (30s cooldown).
6. **No version suffixes in files, code, or schema.** Do not use `v2`, `v3`, `v4`, etc. in filenames (`umc_schema_v2.sql`), classes, functions, or tables. For schema evolution, use semantic suffixes that describe the property (`umc_schema_crr.sql` for CRR-compatible schema; `setup_crdt.py` instead of `migrate_to_v2.py`). Migrations must become `setup_<feature>.py` or `migrate_<feature>.py`. **Exception**: upstream references (`OmniParser v2`, `MiniLM-L6-v2`, HuggingFace models) keep upstream names.

---

## 2. Brain Anatomy

Hive-Mind is organized like a brain. The `cerebro/` vault mirrors the anatomy — **four sibling lobes under Consciousness**, and Cortex has **five of its own sub-lobes**. This section is **canonical** for understanding where each code piece lives.

```
                          ┌─────────────────────────────────────┐
                          │   🧠 Consciousness (Home)           │
                          │   "self" integrating the lobes      │
                          └──────────────┬──────────────────────┘
                                         │
        ┌──────────────────┬─────────────┼─────────────┬──────────────────┐
        │                  │             │             │                  │
   ┌────▼─────────┐  ┌──────▼─────┐  ┌────▼─────┐  ┌────▼────────┐  ┌────▼────────┐
   │ 🧠 CORTEX    │  │ 🥁 CEREBELLUM│ │ 🔀 DIENCEPHALON│ │ 🌿 STEM   │  │  (cortex    │
   │ (cognition) │  │ (rhythm)   │  │ (cross-   │  │ (vital     │  │   detail)  │
   │             │  │            │  │  project  │  │  infra)    │  │            │
   │ 5 sublobes: │  │ • sessoes/ │  │  relay)   │  │ • modelos/ │  │ (continues │
   │ • Temporal  │  │ • diario/  │  │            │  │ • paineis/ │  │   below)   │
   │ • Frontal   │  │ • semanal/ │  │ • setores/ │  │ • infra/   │  │            │
   │ • Parietal  │  │ • padroes/ │  │   (5)      │  │ • meta/    │  │            │
   │ • Occipital │  │            │  │ • roteamento/  │         │  │            │
   │ • Insula    │  │            │  │            │  │            │  │            │
   └─────────────┘  └────────────┘  └────────────┘  └────────────┘  └────────────┘
```

**The four lobes under Consciousness are peers** (Cortex, Cerebellum, Diencephalon, Stem) — there is no hierarchy between them. The Stem is **not a descendant** of any other lobe; it is a sibling.

### 2.1 Cortex — higher cognition (5 sub-lobes)

```
   🧠 CORTEX
   ├── ⏱ TEMPORAL     — long-term memory, primary axis by project
   │       └── <projeto>/<topico>/neuronio-<hash>.md
   ├── 🎯 FRONTAL     — decisions, planning, active work
   │       └── decisoes/  trabalho/{active,ativo,arquivo}/
   │           projetos/  brain/  org/{people,teams}/
   ├── 📥 PARIETAL    — sensory (inbox, references)
   │       └── inbox/{visual,documents}/  referencias/  analises/
   ├── 👁 OCCIPITAL   — vision (captures + knowledge graph)
   │       └── capturas-visuais/  grafo/graph.json
   └── 💓 INSULA      — interoception, self-awareness
           └── saude/  conflitos/
```

#### 2.1.1 Temporal Lobe — detail (primary axis of the brain)

The temporal lobe is where **project-organized long-term memory** lives. It is the brain's **primary axis**. Generic structure (projects and topics are fictional — `projeto-A`, `topico-1`, etc.):

```
cortex/temporal/
├── projeto-A/                     # project-neuron (example)
│   ├── topico-1/                  # topic-neuron (1 neuron = 1 atomic fact)
│   ├── topico-2/
│   └── topico-3/
├── projeto-B/                     # project-neuron (example)
│   ├── topico-1/
│   ├── topico-2/
│   ├── topico-3/
│   ├── topico-4/
│   ├── topico-5/
│   └── topico-6/
├── projeto-C/                     # project-neuron (example)
├── projeto-D/                     # project-neuron (example)
├── projeto-E/                     # project-neuron (example)
├── projeto-F/                     # project-neuron (example)
├── projeto-G/                     # project-neuron (example)
├── projeto-H/                     # project-neuron (example)
├── projeto-I/                     # project-neuron (example)
│
├── _global/                        # project-less knowledge (global preferences)
├── hipocampo/                      # consolidation: Dream Cycle staging + quarantine
└── arquivo/                        # cold memory (>90d, deep substance)
```

Each `neuronio-<hash>.md` has frontmatter with `integrity_hash` (SHA-256 of content) and is unique by hash — neurons never duplicate. The SQLite index (UMC `hive_mind.db`) accelerates queries over these neurons; the `vault` remains the single source of truth.

### 2.2 Cerebellum — rhythm and coordination

```
   🥁 CEREBELLUM
   ├── sessoes/   → work session logs (YYYY/MM/YYYY-MM-DD-HHMM-{slug}.md)
   ├── diario/    → daily reflections (YYYY/MM/YYYY-MM-DD.md)
   ├── semanal/   → weekly syntheses (YYYY-Wxx.md)
   ├── mensal/    → monthly syntheses (YYYY-MM.md) — strong model
   ├── anual/     → yearly syntheses (YYYY.md) — strong/batch model
   └── padroes/   → learned patterns (procedural memory)
       └── cerebro/cerebelo/padroes/Patterns.md  (Patterns is the canonical human reference, but **not** the only learning neuron — each learning becomes an atom in `cortex/temporal/`)
```

The hierarchical cadence (session → daily → weekly → monthly → yearly) is the temporal axis of the brain (see §29). Each layer has its own purpose, model, and promotion rule.

### 2.3 Diencephalon — cross-project relay

```
   🔀 DIENCEPHALON
   ├── setores/     → knowledge crossing multiple projects
   │   ├── setor-1.md      ← neurons used by several projects
   │   ├── setor-2.md
   │   ├── setor-3.md
   │   ├── setor-4.md
   │   └── setor-5.md
   └── roteamento/  → knowledge routing rules between projects
```

### 2.4 Stem — vital infrastructure (sibling of the other 3, not descendant)

```
   🌿 STEM
   ├── modelos/   → typed Obsidian templates (Atom, Work, Decision, Thinking, Cold Analysis)
   ├── paineis/   → Obsidian bases (.base) — Work Dashboard, Incidents, People, Review Evidence
   ├── infra/     → vault infrastructure configuration
   └── meta/      → vault meta-information, sub-vaults, cross-vault links
```

### 2.5 Lobe → function → technical component mapping

| Lobe | Function | Where it lives in code/vault |
|---|---|---|
| **Frontal cortex** | Decision, planning, work | `core/`, `scripts/dream/dream_cycle.py` (dialectical synthesis), `cerebro/cortex/frontal/{decisoes,trabalho,brain,projetos,org}`, `core/knowledge/decision_promoter.py`, `core/knowledge/work_tracker.py`, MCP `save_decision`/`plan_goal` |
| **Parietal cortex** | Sensory — inbox, references, documents | `scripts/capture/`, `core/knowledge/document_ingest.py` (→ `DocumentPipeline`), `cerebro/cortex/parietal/{inbox,referencias}`, `cerebro/cortex/parietal/inbox/documents/` |
| **Occipital cortex** | Vision — captures + **graph** | `scripts/capture/visual_capture.py`, MCP `sinapse_capture_screen` (→ `visual_memories`, `capturas-visuais/`), `integrations/graphify/` (→ `cerebro/cortex/occipital/grafo/graph.json`), visual stage in Dream Cycle |
| **Temporal cortex** | Long-term memory by project | `cerebro/cortex/temporal/<projeto>/<topico>/neuronio-*.md` + UMC `hive_mind.db` (indexer); `core/knowledge/claude_mem_bridge.py` (→ Dream Cycle), `core/knowledge/drift_detector.py`, `core/knowledge/topic_consolidator.py`, `core/knowledge/alias_miner.py` |
| **Insula cortex** | Health, self-awareness, ambiguities | `scripts/health/{health_dashboard,alert_dispatcher,review_writer,conflict_detector}.py`, `cerebro/cortex/insula/{saude,conflitos}`, `core/knowledge/ambiguities.py` (dialectical synthesis) |
| **Cerebellum** | Rhythm — session, daily, weekly, monthly, yearly, patterns | `scripts/dream/{session_consolidator,daily_writer,weekly_synthesizer,monthly_synthesizer,yearly_synthesizer,pattern_distiller}.py`, `cerebro/cerebelo/{sessoes,diario,semanal,mensal,anual,padroes}/` + `cerebro/cerebelo/padroes/Patterns.md` |
| **Diencephalon** | Cross-project relay | `core/knowledge/sector_classifier.py`, `core/knowledge/generate_mocs.py`, `cerebro/diencefalo/{setores,roteamento}` |
| **Stem** | Vital infrastructure | `cerebro/tronco/{modelos,paineis,infra,meta}/` — templates, bases, config, sub-vaults; more static than promoted |

### 2.6 External tools as brain organs

Tools feeding the brain **are not parallel databases**. They are **organs of the same brain** contributing to one single perception (`sinapse_query` response and `RetrievalRouter` response). Starting with K0–K2 (2026-06-30), the canonical list includes RAGFlow, Milvus, and LlamaIndex as **first-class in adapters/contracts**, without turning them into parallel sources of truth.

| Tool | Brain organ | Function | Integration form |
|---|---|---|---|
| **UMC** (`hive_mind.db`) | Cortex (central) | Graph + vectors + FTS5 + logs in one SQLite | **Wrapper** (directory in repo) |
| **NeuralMemory** | Cortex (association) | Spreading activation, associative memory | **Clone** in `integrations/neural-memory/` (via `components.lock.json`) |
| **sqlite-vec** | Cortex (local vector) | Native HNSW indexing in SQLite — local-first, offline, operational cache | Mandatory (runtime extension loaded) |
| **claude-mem** | Temporal cortex (hippocampus) | `user_prompts`, `observations`, `discoveries`, `session_summaries` — temporal evidence source | **Wrapper** (HTTP worker `:37700`) |
| **Graphify** | Occipital cortex (structural graph) | Indexes `cerebro/` to `graph.json` with Leiden clustering | **Clone** in `integrations/graphify/` |
| **Graphiti** | Temporal lobe (causality) | Edges with temporal validity (`valid_at`/`invalid_at`) | **Wrapper** (`integrations/graphiti/` + `docker-compose.yml` with digest-pinned image) |
| **LightRAG/GraphRAG** | Diencephalon (multi-hop) | Multi-hop relations and global questions | Wrapper or pip, expandable |
| **RAGFlow** | Parietal cortex (document ingestion) | Adapter for layout-aware parsing, structural chunking, citations | **Wrapper** headless (`integrations/ragflow/` + `ragflow-sdk`); **never** source of truth — output flows to `document_vectors` + UMC |
| **Milvus** | Cortex (production vector) | Production vector backend for large collections (multi-collection, partition by `workspace_id`) | **Wrapper** (`integrations/milvus/` + `pymilvus`); official production backend for `VectorBackend` |
| **LlamaIndex** | Cortex (composite retrieval) | Adapter for rerank and retrieval workflows | **Pip** (`llama-index` in `pyproject.toml`); **does not** decide route nor become source of truth |
| **Filesystem scan** | Parietal cortex (immediate sense) | Reads vault directly without waiting for reindex | Internal |
| **RTK** | Shell optimization | Hooks/plugins/instructions by agent/CLI for command rewriting | **Clone** in `integrations/rtk/` — **not** a `sinapse_query` read backend |

> **Vendoring rule** (negative contract): `components.lock.json` accepts only clones (`graphify`, `neural-memory`, `rtk`, `omniparser`, `crsqlite`). Wrappers (Milvus, RAGFlow, Graphiti) are container/SDK. Pip covers only LlamaIndex and utilities. If Milvus, RAGFlow, or LlamaIndex appear in `components.lock.json` for this front, the implementation is wrong.

`sinapse_query` is the brain's single entrypoint. It triggers organs in parallel (circuit breaker + 8s timeout/backend), fuses via Context Fusion, and returns **one context package**. K7 `RetrievalRouter` (see §26) adds: classify query intent, choose specialized route (temporal, memory, document, code, graph, multi-hop, hybrid), and return `retrieval_path`, `citations`, `confidence`, and `missing_context`.

**RTK** is installed per agent/CLI (`codex`, `claude`, `gemini`, `cursor`, `hermes`, etc.) via `./scripts/services/start-rtk.sh --only <agent>`. It is not a `sinapse_query` read backend — it is shell optimization, not part of Context Fusion.

### 2.7 Canonical path constants

Anatomy is encoded in `core/paths.py`. Exposed constants:

```python
CORTEX     = VAULT_ROOT / "cortex"      # Cortex (5 sub-lobes)
TEMPORAL   = CORTEX / "temporal"        # Temporal lobe (memory)
FRONTAL    = CORTEX / "frontal"         # Frontal lobe (decision)
PARIETAL   = CORTEX / "parietal"        # Parietal lobe (sensory)
OCCIPITAL  = CORTEX / "occipital"       # Occipital lobe (vision/graph)
INSULA     = CORTEX / "insula"          # Insula lobe (self-awareness)
DIENCEFALO = VAULT_ROOT / "diencefalo"  # Diencephalon (relay)
SECTORS_ROOT = DIENCEFALO / "setores"
CEREBELO   = VAULT_ROOT / "cerebelo"    # Cerebellum (rhythm)
DAILY_ROOT, SESSIONS_ROOT, WEEKLY_ROOT, PADROES_ROOT = cerebelo/...
TRONCO     = VAULT_ROOT / "tronco"      # Stem (infra)
META_ROOT, MODELOS_ROOT, PAINEIS_ROOT = tronco/...
```

Any new code creating/modifying files in the vault **must use these constants**, not hardcoded paths. Details per lobe in `cerebro/cortex/cortex.md`, `cerebro/cerebelo/cerebelo.md`, `cerebro/diencefalo/diencefalo.md`, `cerebro/tronco/tronco.md` and `cerebro/cortex/{frontal,parietal,occipital,temporal,insula}/*.md`.

---

## 3. System Macro View

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                          AI AGENTS                                   │
  │                                                                      │
  │  ┌────────────┐ ┌──────────┐ ┌────────┐ ┌────────┐ ┌─────────────┐  │
  │  │Claude Code │ │Codex CLI │ │Cursor  │ │Gemini  │ │Hermes/Thoth │  │
  │  │Kilo Code   │ │          │ │Aider   │ │CLI     │ │(native plugin│  │
  │  └──────┬─────┘ └─────┬────┘ └───┬────┘ └───┬────┘ └──────┬──────┘  │
  └─────────┼─────────────┼──────────┼───────────┼─────────────┼─────────┘
            │             │          │           │             │
            └──────────┬──┴──────────┘           │       (native hooks)
                       │                         │             │
                       ▼                         │             ▼
  ┌────────────────────────────────┐             │  ┌──────────────────────┐
  │  sinapse-mcp.py (MCP Server)  │             │  │ sinapse-memory.py    │
  │  16 tools · stdio JSON-RPC    │             │  │ Hermes plugin         │
  │                               │             │  │ pre_gateway_dispatch │
  │  sinapse-write.py (CLI)       │             │  │ post_tool_call       │
  │  sinapse-api.py (REST :37702) │             │  │ on_session_end       │
  └──────────────────┬────────────┘             │  └──────────┬───────────┘
                     └─────────────────────────┬┘             │
                                               │              │
                                               ▼              ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │                 UNIFIED MEMORY CORE — hive_mind.db               │
  │                                                                    │
  │  ┌──────────────┐  ┌────────────────┐  ┌───────────────────────┐  │
  │  │  neurons     │  │  observations  │  │  visual_memories      │  │
  │  │  synapses    │  │  archived: 0   │  │  document_memories    │  │
  │  │  (graph)     │  │  1=ok 2=quarant│  │  (multimodal)         │  │
  │  └──────┬───────┘  └───────┬────────┘  └───────────────────────┘  │
  │         │                  │                                        │
  │  ┌──────▼───────┐  ┌───────▼───────┐  ┌───────────────────────┐  │
  │  │  search_vec  │  │  search_fts   │  │  ambiguities          │  │
  │  │  (sqlite-vec │  │  (FTS5        │  │  (P2P conflicts)      │  │
  │  │   1024d HNSW)│  │   unicode61)  │  │  vault (secrets)      │  │
  │  └──────────────┘  └───────────────┘  └───────────────────────┘  │
  └─────────────────────────────┬──────────────────────────────────────┘
                                │                   ▲
               ┌────────────────┼──────────┐        │ reindex ~2s
               │                │          │        │
               ▼                ▼          │  ┌─────┴──────────────────┐
  ┌────────────────┐  ┌──────────────┐    │  │  Watcher (watchdog)    │
  │  Hive-Dreamer  │  │  REST API    │    │  │  + Graphify            │
  │  dream_cycle.py│  │  FastAPI     │    │  │  vault → neurons +     │
  │  nightly       │  │  :37702      │    │  │  embeddings + FTS      │
  └───────┬────────┘  └──────────────┘    │  └────────────────────────┘
          │                               │              ▲
          ▼                               │              │ edits
  ┌───────────────────────────────────┐   │              │
  │  Obsidian Vault — cerebro/        │───┘──────────────┘
  │  cortex/  cerebelo/               │
  │  diencefalo/  tronco/             │ ◄─── Syncthing P2P (optional)
  │  portal.canvas  (source of truth) │
  └───────────────────────────────────┘
```

### Responsibilities

| Component | Responsible for | Independent from |
|------------|-----------------|------------------|
| `cerebro/` | Canonical content | Everything (pure Obsidian vault works without the system) |
| `core/` | UMC schema, connections, auth, Pydantic schemas | Specific agents |
| `graphify/` | Structural indexing → neurons/synapses | claude-mem, RTK |
| `~/.claude-mem` | Global temporal event capture → observations | Graphify, RTK |
| `integrations/rtk/` | Shell command rewriting per agent/CLI | Everything (isolated hook) |
| `integrations/neural-memory/` | Associative recall (spreading activation) | Remaining layers |
| `scripts/` | Pipeline, servers, operations | — |
| `plugins/hermes/` | Bidirectional bridge Hermes ↔ UMC ↔ vault | — |
| `sinapse.yaml` | Central config (paths, ports, agents) | — |
| `install.sh` | Universal installation (10 steps) | — |

---

## 4. Unified Memory Core (UMC)

Single SQLite database (`hive_mind.db`) with `sqlite-vec` loaded at runtime. Schema at [`core/umc_schema.sql`](../core/umc_schema.sql).

### Entity Diagram

```
  neurons (UUID v4)              observations (UUID v4)
  ─────────────────              ──────────────────────
  id          PK                 id            PK
  label                          session_id
  type                           project
  source_file  (vault-relative)  type          decision|learning|event
  content                        title
  hash         SHA-256           content
  metadata     JSON              archived      0=pending 1=ok 2=quarantine
  community    Leiden cluster    neuron_id     FK→neurons (optional)
  visibility   private|shared|   goal_id       FK→goals (HM-11)
               public (HM-12)    why           TEXT (HM-11)
  indexed_at   TIMESTAMP (HM-11)
  created_at
  updated_at                     ambiguities (UUID v4)
       │                         ────────────────────
       │ triggers FTS sync       id            PK
       ▼                         neuron_id     FK→neurons
  search_fts (FTS5)              source_a_hash SHA-256
  ─────────────────              source_b_hash SHA-256
  neuron_id   UNINDEXED          content_a
  label                          content_b
  content                        status   pending|synthesized|branched
  tokenize=unicode61
                                 causal_edges (HM-11)
  search_vec (vec0)              ────────────────────
  ──────────────────             id             PK
  neuron_id   PK                 cause_neuron_id FK→neurons
  embedding   FLOAT[1024]        effect_neuron_id FK→neurons
                                 label, confidence, source
                                 (indexes on cause and effect)

  goals (HM-11)                  visual_memories / document_memories
  ─────────────                  ──────────────────────────────────
  id          PK                 id, path, description/summary
  description                    topics, hash (dedup), neuron_id FK
  steps_json  TEXT (JSON)
  status      active|…           vault (encrypted secrets)
  created_at                     ───────────────────────
                                 id             PK
  synapses (UUID v4)             encrypted_secret  BLOB (Fernet)
  ─────────────────              metadata          JSON
  id          PK
  source_id   FK→neurons
  target_id   FK→neurons
  relation    TEXT
  weight      FLOAT
```

### Technical guarantees

| Guarantee | Implementation |
|----------|----------------|
| Automatic FTS sync | `AFTER INSERT/UPDATE/DELETE` triggers on `neurons` |
| Impossible P2P collision | UUIDs v4 in all PKs |
| Divergence detection | SHA-256 of content in `neurons.hash` |
| Auditable queue | `observations.archived` is indexed (`idx_observations_archived`) — never LIKE in JSON |
| Performance | `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000` |

---

## 5. Read Flow

```
  User asks a question
         │
         ▼
  Agent receives query
         │
         ▼ (automatic hook or MCP tool)
  sinapse_query("pricing decision")
         │
         ├─────────────────────────────────────────────┐
         │                                             │
         ▼                                             ▼
  Parallel search in read backends/organs:    Filesystem scan (cerebro/*.md)
  ┌──────────────────────────────┐            cache TTL 30s
  │ UMC SQL                      │            direct search, zero gap
  │  search_fts MATCH 'pricing'  │
  │  search_vec KNN 1024d        │
  │  neurons/synapses            │
  │  observations FTS5           │
  └──────────────────────────────┘
         │                              │
         └──────────────┬───────────────┘
                        │
                        ▼
              merge + dedup + top-N cut
              (key: source_file + title + content)
              (relevance rerank is pending contract — docs/11 §17.1)
                        │
                        ▼
              top-N results ≤ 3000 chars
                        │
                        ▼
              injected into agent
              system_message (pre-prompt)
```

**Access by agent:** MCP agents call `sinapse_query` via tool; Hermes plugin can do automatic injection via `pre_gateway_dispatch`. Limits: `MAX_CONTEXT_CHARS=3000`, `MAX_NODES=5`.

**Circuit breaker:** backend with 3+ consecutive failures enters 30s cooldown. Only exceptions and timeouts count as failures (not empty results).

---

## 6. Write Flow

```
  Agent calls sinapse_save_decision("Migrar VPS", content)
         │
         ▼
  _sanitize_slug(title)  →  "2026-06-10-migrar-vps"
         │
         ▼
  _atomic_write()
  tempfile.mkstemp() → write → os.replace()  (atomic on Linux)
         │
         ▼
  cerebro/cortex/frontal/trabalho/ativo/2026-06-10-migrar-vps.md
  ─────────────────────────────────────────────
  ---
  tags: [decision]
  status: active
  created: 2026-06-10
  source: hermes-session
  ---
  # Migrar VPS
  content...
         │
         ▼
  Watcher detects filesystem change (~2s)
         │
         ▼
  Graphify reindexes → neurons + synapses + embeddings + FTS
         │
         ▼
  Available to any agent on the next query

  LEARNING SIGNALS detected in parallel:
  "aprendizado"|"learning"|"insight"|"padrão"|"pattern"|"lição"
         │
         ▼
  append to cerebro/cerebelo/padroes/Patterns.md (title dedup)

  at end of session:
  sinapse_session_end() → cerebro/cortex/frontal/brain/Current State.md updated
                        → closing observation in UMC
```

**Detected secrets** (API key regex, `sk-proj-*`, etc.) → field-level encryption (`vault` table, Fernet) → replaced with placeholder in final content.

---

## 7. The Dream Cycle (Hive-Dreamer)

`scripts/dream/dream_cycle.py` — offline consolidation with Pydantic-validated output. **Starting with K3/K4 (2026-06-28/29) the cycle is structured into distinct layers** (see §27 and [`11-knowledge-promotion-architecture.md` §3](11-knowledge-promotion-architecture.md#3-preenchimento-por-parte-do-cérebro)):

```
  ┌────────────────────────────────────────────────────────────────┐
  │                      STAGE 0 — CAPTURE                         │
  │                                                                │
  │  Capture Layer:                                                │
  │    - hooks (Claude Code, Codex, Kilo, …)                      │
  │    - MCP / CLI / browser / docs / code / screenshots          │
  │    - runtime events (sessions, tools, metrics)                │
  │       │                                                        │
  │       ▼                                                        │
  │  STAGE 0.5 — TEMPORAL HIPPOCAMPUS (claude-mem)                │
  │    user_prompts · observations · discoveries · session_summaries│
  │    facts · narrative · concepts · files_read / files_modified │
  │    prompt_number · generated_by_model                         │
  │       │                                                        │
  │       ▼                                                        │
  │  STAGE 1 — KNOWLEDGE INTAKE (core/knowledge/intake.py, K3)    │
  │    - normalizes fields (preserves source_id, project, workspace)│
  │    - extracts evidence / files / timestamps                   │
  │    - classifies knowledge_type                                │
  │    - deduplicates by source_id + content hash                │
  │       │                                                        │
  │       ▼                                                        │
  │  STAGE 2 — PROMOTION LAYER (core/knowledge/promotion.py, K4)  │
  │    Distiller (DistillerOutput Pydantic)                       │
  │      "extract structured facts from these observations"       │
  │       │                                                        │
  │       ▼                                                        │
  │    Validator (ValidatorOutput Pydantic)                       │
  │      "are these facts supported by original logs?"           │
  │       │ approved           │ rejected → feedback → Distiller  │
  │       ▼                                                        │
  │    Router (RouterOutput Pydantic)                             │
  │      "which project/topic in the temporal lobe gets each fact?"│
  │       │                                                        │
  │       ▼                                                        │
  │  Anatomical file + neuron UPSERT + vector_backend.upsert()    │
  │  observation.neuron_id = neuron.id;  archived=1               │
  │  structural failure → archived=2 (quarantine, never lost)     │
  └──────────────────────┬─────────────────────────────────────────┘
                          │ successful routing
  ┌──────────────────────▼─────────────────────────────────────────┐
  │              STAGE 2.5 — ANATOMICAL PERSISTENCE               │
  │                                                                │
  │  cérebro/cortex/temporal/<project>/<topic>/neuronio-*.md      │
  │  cérebro/cortex/frontal/{decisoes,trabalho,brain,projetos,org}│
  │  cérebro/cortex/{parietal,occipital,insula}/...               │
  │  cérebro/cerebelo/{sessoes,diario,semanal,mensal,anual,padroes}│
  │  cérebro/diencefalo/setores/<setor>.md                        │
  │                                                                │
  │  Atomic write via tempfile + os.replace(); SHA-256 of content;│
  │  1024d embedding (snowflake-arctic-embed2);                   │
  │  required workspace_id everywhere; canonical metadata          │
  │  (parent_id, brain_lobe, knowledge_type, source_uri, valid_at).│
  └──────────────────────┬─────────────────────────────────────────┘
                          │
  ┌──────────────────────▼─────────────────────────────────────────┐
  │      STAGE 3 — MULTI-COLLECTION INDEXING (FTS + Vector + Graph)│
  │                                                                │
  │  - FTS5 (search_fts, tokenize=unicode61)                      │
  │  - VectorBackend.upsert() in memory_vectors/observation_vectors│
  │  - Graphiti: push_neuron (causal_edges with valid_at/invalid_at)│
  │  - LightRAG: index_memory (entities + relations)              │
  │  - Graphify: reindexes structural graph if something changed  │
  └──────────────────────┬─────────────────────────────────────────┘
                          │
  ┌──────────────────────▼─────────────────────────────────────────┐
  │      STAGE 4 — DIALECTICAL SYNTHESIS (Phase 9)                │
  │                                                                │
  │  SELECT ambiguities WHERE status='pending'                    │
  │       │                                                        │
  │  semantic_diff (vector + LLM)                                 │
  │       ├── complement → merge → unified content               │
  │       ├── contradiction → choose → evidence-based version    │
  │       └── irreconcilable → branch → preserve both            │
  │       │                                                        │
  │       ▼                                                        │
  │  status='synthesized' | 'branched'                            │
  └──────────────────────┬─────────────────────────────────────────┘
                          │
  ┌──────────────────────▼─────────────────────────────────────────┐
  │     STAGE 5 — PUSH TO KNOWLEDGE GRAPHS (P2 + P4)              │
  │                                                                │
  │  For each synthesized neuron:                                  │
  │    1. push_neuron()   → Graphiti/FalkorDB (temporal)          │
  │    2. index_memory()  → LightRAG (entities + relations)       │
  │                                                                │
  │  Both are best-effort: try/except, never abort synthesis.     │
  │  Graphiti: temporal causal graph (queries "who influenced X")│
  │  LightRAG: entity graph + hybrid search (multi-hop queries    │
  │            that FTS5 + KNN cannot solve)                      │
  └────────────────────────────────────────────────────────────────┘
```

**Guarantees:**
- Archive only after successful routing
- Expired OAuth triggers automatic refresh (polling timeout: 300s)
- Hash determinism: each persisted fact carries SHA-256 of content
- `call_llm_structured()` validates LLM JSON output with `model_validate_json()`
- **Graph push** (Stage 5) is best-effort: Graphiti or LightRAG failure does not prevent dialectical synthesis from being marked `synthesized`. Logs go to `[LightRAG]` on stdout.
- **Automatic promotion rule** (K3/K4): allowed for `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, and `rationale` — all with traceable source. Forbidden: turn every bullet into fact, create neuron without source, vectorize duplicates without `parent_id`, promote temporary opinion as architecture decision, overwrite previous decisions without conflict or `invalid_at`.
- **Promotion failure preserves data**: transient error → `archived=0` (retry); structural error → `archived=2` (quarantine with reason). Nothing is deleted due to promotion failure.

**Writer cadence** (see §29): session/daily use small model; weekly uses medium/strong model; monthly/yearly use strong model or offline batch. Each role is configurable in `setup-brain` and inherits from `dreamer` when absent.

---

## 8. P2P Synchronization and Semantic Fusion

```
  Machine A           Syncthing (P2P)         Machine B
  ─────────           ───────────────         ─────────
  edits atlas/        ──────────────►          receives file
  pricing/fato.md                              (same file
                                               edited offline)
                                                    │
                                               audit_memory.py
                                               file hash ≠
                                               neuron hash
                                                    │
                                               INSERT ambiguities
                                               (content_a, content_b
                                                source_a_hash,
                                                source_b_hash,
                                                status='pending')
                                                    │
                                               dream_cycle.py
                                               semantic_diff
                                                    │
                             ┌──────────────────────┤
                             │                      │
                        complement          factual contradiction
                             │                      │
                           merge               choose (logic_applied)
                        unified content        evidence-based version
                             │                      │
                             └───────────┬──────────┘
                                         │
                                    status='synthesized'
                                    .md updated
                                    neuron updated
```

**Prerequisites:**

| Mechanism | Implementation |
|-----------|----------------|
| Collision-free IDs | UUID v4 in all PKs |
| Divergence detection | SHA-256 content in `neurons.hash` |
| Transport | Syncthing (no central server) |
| vault ↔ SQLite reconciliation | `audit_memory.py --fix` |
| Conflict classification | `semantic_diff.py` (vector + LLM) |
| Autonomous resolution | `dream_cycle.py` synthesis stage |

Full setup in [`07-p2p-sync-setup.md`](07-p2p-sync-setup.md).

---

## 9. Multimodal Layer

```
  INPUT                      PROCESSING                OUTPUT
  ─────                      ──────────                ──────
  visual_capture.py          dream_cycle.py            visual_memories
  tool sinapse_capture_screen  visual stage            (id, image_path,
  screenshot (mss)      ───►  LLM Vision              description,
                              VisionAnalysis Pydantic  ocr_text,
                              (description + OCR)      neuron_id)

  document_ingest.py         dream_cycle.py            document_memories
  PDF (PyMuPDF)         ───►  docs stage               (id, file_path,
  DOCX (python-docx)          summary + topics         file_hash UNIQUE,
                              → observations queue     summary, topics)

  generate_portal.py         composes visual memories  cerebro/portal.canvas
                             and UMC concepts     ───► (Obsidian Canvas)
```

The multimodal stage runs **inside** the Dream Cycle — images and documents enter the same consolidation queue as logs.

---

## 10. Access Layer

### 9.1 MCP Server (`scripts/services/sinapse-mcp.py`)

stdio JSON-RPC, compatible with any MCP client.

| Tool | Signature | Function |
|------|-----------|----------|
| `sinapse_query` | `(query, limit?)` | Hybrid search: FTS5 + vectors + graph + filesystem |
| `sinapse_save_decision` | `(title, content)` | Decision → `cerebro/cortex/frontal/trabalho/ativo/YYYY-MM-DD-slug.md` |
| `sinapse_save_learning` | `(title, content)` | Learning → `cerebro/cerebelo/padroes/Patterns.md` |
| `sinapse_health` | `()` | All backend status |
| `sinapse_session_end` | `(summary?)` | Closes session, updates Current State |
| `sinapse_temporal_search` | `(query, limit?, project?)` | claude-mem step 1: compact index with IDs/titles |
| `sinapse_temporal_timeline` | `(anchor? or query?, depth_before?, depth_after?, project?)` | claude-mem step 2: chronological window around ID/query |
| `sinapse_temporal_get_observations` | `(ids, orderBy?, limit?, project?)` | claude-mem step 3: full details only for filtered IDs |
| `sinapse_temporal_save` | `(content, type?)` | Observation (fallback: vault) |
| `sinapse_zettelkasten_split` | `(file_path)` | Monolithic note → atomic Zettelkasten notes |
| `sinapse_capture_screen` | `(description?)` | Screenshot → `visual_memories` |
| `sinapse_plan_goal` | `(goal, context?)` | Decomposes goal into atomic steps and saves to Intent Memory |
| `sinapse_temporal_graph_search` | `(query, num_results?)` | Graphiti/FalkorDB temporal graph — edges with `valid_at`/`invalid_at` (P2) |
| `sinapse_rag_query` | `(question, mode?)` | Hybrid LightRAG graph query (entities + relations) — multi-hop, fed by Dream Cycle (P4) |
| `search_memories` | `(query, top_k?, project?, mode?)` | HNSW/FTS search over vault |

Total: **16 tools** (includes `sinapse_promote_knowledge`). Automatic register/instructions via `register-mcp.sh`.

**Single source of operational instructions:** `config/sinapse-agent-prompt.md`.
- Loaded by `scripts/services/sinapse-mcp.py:_load_instructions()` (L38–53) and exposed as `instructions` in MCP `initialize`.
- Injected into `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `.github/copilot-instructions.md` / `.cursor/rules/hive-mind.md` by `register-mcp.sh:inject_instructions()` (L325–351), between markers `<!-- BEGIN HIVE-MIND SINAPSE -->` / `<!-- END HIVE-MIND SINAPSE -->`.
- Fixing this prompt is the only required action to propagate operational policy to all future clean installations.

**MCP configs per agent** (registered by `scripts/setup/register-mcp.sh`):
Claude Code: `<projeto>/.mcp.json` (project scope, `claude mcp add -s project` — **not** `~/.claude/.mcp.json`) · Codex: `~/.codex/config.toml` + `~/.codex/mcp.json` · Cursor: `~/.cursor/mcp.json` · Gemini: `~/.gemini/settings.json`

### 9.2 Hermes Plugin (`plugins/hermes/sinapse-memory.py`)

```python
def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", _pre_prompt_build)   # automatic read
    ctx.register_hook("post_tool_call",       _post_tool_use)      # automatic write
    ctx.register_hook("on_session_end",       _post_session_end)   # close
```

Only component aware of all layers. Built-in circuit breaker (3 failures → 30s cooldown). `health_check()` returns all backend status.

### 9.3 Standalone CLI (`scripts/services/sinapse-write.py`)

`decision` · `learning` · `query` · `health` · `session-end` — for agents without MCP.

### 9.4 REST API (`scripts/services/sinapse-api.py`)

FastAPI, port `HIVE_MIND_API_PORT` (default **37702**). Fail-closed without `HIVE_MIND_API_KEY`.

```
  ┌────────────────────────┬────────┬────────┬──────────┬────────────────────────────────────────────┐
  │ Endpoint               │ Method │ Auth   │ Rate     │ Description                                │
  ├────────────────────────┼────────┼────────┼──────────┼────────────────────────────────────────────┤
  │ /api/v1/health         │ GET    │ —      │ 60/min   │ Health check                               │
  │ /api/v1/observations   │ POST   │ Bearer │ 20/min   │ New observation                            │
  │ /api/v1/query          │ POST   │ Bearer │ 30/min   │ Hybrid search                              │
  │ /api/v1/semantic/…     │ GET    │ Bearer │ —        │ Semantic neighbors                          │
  │ /api/v1/vault/{id}     │ GET    │ Bearer │ 10/min   │ Encrypted secret                           │
  │ /api/v1/neurons/export │ POST   │ Bearer │ 10/min   │ Export shared/public neurons (HM-12)       │
  └────────────────────────┴────────┴────────┴──────────┴────────────────────────────────────────────┘
```

---

## 11. Multi-Provider Authentication

`PROVIDERS_CONFIG` in `core/auth.py` is the master provider registry. Active list is code-defined and includes API providers, local providers, and CLI/OpenAI-compatible bridges.

| Provider | Auth | Env var |
|----------|------|---------|
| google | API key + loopback OAuth | `GOOGLE_API_KEY` / `GOOGLE_OAUTH_CLIENT_*` |
| antigravity | Reused CLI OAuth | `ANTIGRAVITY_UNUSED` |
| gemini-cli | Reused CLI OAuth | `GEMINI_CLI_UNUSED` |
| omniroute | local OpenAI-compatible gateway | `OMNIROUTE_API_KEY` |
| openai | API key + OAuth Codex-handshake | `OPENAI_API_KEY` |
| anthropic | API key | `ANTHROPIC_API_KEY` |
| deepseek | API key | `DEEPSEEK_API_KEY` |
| openrouter | API key | `OPENROUTER_API_KEY` |
| nvidia | API key | `NVIDIA_API_KEY` |
| huggingface | API key | `HF_TOKEN` |
| qwen | API key | `DASHSCOPE_API_KEY` |
| lmstudio | local (no key) | — |
| ollama | local (no key) | — |

**Common capabilities:** automatic OAuth token refresh, polling timeout 300s, real-time model discovery (`discover_models_realtime()`), no hardcoded credentials.

### 11.1 LLM role resolution (`get_role_config`)

Each system stage that calls an LLM has a specific **role** configuration. Current canonical roles (`HIVE_LLM_ROLES` constant in `core/auth.py`): `dreamer`, `graphify`, `vision`, `synthesis`, `claude_mem`, `session_summarizer`, `daily_writer`, `alias_miner`, `topic_router`, `sector_classifier`, `weekly_synthesizer`, `monthly_synthesizer`, `yearly_synthesizer`, `drift_detector`, `decision_promoter`, `project_synthesizer`, `pattern_distiller`, `conflict_detector`, `graphiti`, `lightrag`. Function accepts any role name (case-insensitive, `-` becomes `_`); empty or non-string raises `ValueError`.

```python
get_role_config(role: str) -> Optional[Dict[str, Optional[str]]]
# returns {"provider", "model", "fallback_provider", "fallback_model"}
# or None if neither role nor Dreamer is configured
```

**Environment variables per role** (read exclusively from `os.environ` — `.env` is loaded by dotenv in `dream_cycle.py`):

| Role | Primary | Fallback (optional) |
|------|---------|---------------------|
| Dreamer (inheritance base) | `HIVE_DREAMER_PROVIDER` / `HIVE_DREAMER_MODEL` | `HIVE_DREAMER_FALLBACK_PROVIDER` / `HIVE_DREAMER_FALLBACK_MODEL` |
| Graphify | `HIVE_GRAPHIFY_PROVIDER` / `HIVE_GRAPHIFY_MODEL` | `HIVE_GRAPHIFY_FALLBACK_PROVIDER` / `HIVE_GRAPHIFY_FALLBACK_MODEL` |
| Vision | `HIVE_VISION_PROVIDER` / `HIVE_VISION_MODEL` | `HIVE_VISION_FALLBACK_PROVIDER` / `HIVE_VISION_FALLBACK_MODEL` |
| P2P Synthesis | `HIVE_SYNTHESIS_PROVIDER` / `HIVE_SYNTHESIS_MODEL` | `HIVE_SYNTHESIS_FALLBACK_PROVIDER` / `HIVE_SYNTHESIS_FALLBACK_MODEL` |
| Claude Mem | `HIVE_CLAUDE_MEM_PROVIDER` / `HIVE_CLAUDE_MEM_MODEL` | `HIVE_CLAUDE_MEM_FALLBACK_PROVIDER` / `HIVE_CLAUDE_MEM_FALLBACK_MODEL` |
| Live/intelligent memory | `HIVE_{ROLE}_PROVIDER` / `HIVE_{ROLE}_MODEL` | `HIVE_{ROLE}_FALLBACK_PROVIDER` / `HIVE_{ROLE}_FALLBACK_MODEL` |

**Resolution rules:**

```
  HIVE_{ROLE}_PROVIDER + HIVE_{ROLE}_MODEL defined (COMPLETE pair)?
       │
       ├── Yes → use role's own primary
       │          fallback: only explicit HIVE_{ROLE}_FALLBACK_*
       │          (NEVER inherits Dreamer fallback) — if absent, fallback=None
       │
       └── No (incomplete pair or absent)
             → inherit HIVE_DREAMER_PROVIDER/MODEL
             → without role-specific HIVE_{ROLE}_FALLBACK_*, also inherit
               HIVE_DREAMER_FALLBACK_PROVIDER/MODEL
```

- Fallback only counts as a **complete pair** PROVIDER+MODEL; incomplete pair is treated as absent (`None`).
- **API keys are never duplicated by role:** they are always resolved via `PROVIDERS_CONFIG` by provider name (`GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, ...).

### 11.2 Unified LLM client (`core/llm_client.py`)

Module centralizing structured calls (previously embedded in `dream_cycle.py`):

| Function/Class | Role |
|----------------|------|
| `call_llm_structured(...)` | Call with JSON Schema + Pydantic validation (moved from `dream_cycle.py`) |
| `classify_llm_error(exc)` | Classifies exception into `"validation"` \| `"auth"` \| `"transient"` |
| `call_llm_with_fallback(role, ...)` | Applies role retry/fallback policy |
| `LLMValidationError` | LLM output failed Pydantic validation |

Retry/fallback policy by error class: see table in [`02-ai-models.md`](02-ai-models.md). When switching models, log records: `[Fallback] Role 'X': switching from A/B to C/D`.

---

## 12. Vault Structure

```
  cerebro/
  ├── _Consciencia.md
  ├── cortex/
  │   ├── temporal/<projeto>/<topico>/neuronio-*.md
  │   ├── frontal/{decisoes,projetos,trabalho,brain,org}/
  │   ├── parietal/{inbox,referencias,analises}/
  │   │   └── inbox/documents/        ← parents of document_chunks (K6)
  │   ├── occipital/{capturas-visuais,grafo}/
  │   │   └── grafo/graph.json      ← canonical Graphify
  │   └── insula/{saude,conflitos}/
  ├── cerebelo/{sessoes,diario,semanal,mensal,anual,padroes}/
  │   └── padroes/Patterns.md
  ├── diencefalo/{setores,roteamento}/
  └── tronco/{modelos,paineis,infra,meta}/
```

**Critical convention (K3/K4):** large files can exist for human reading, but the searchable unit is atomic. `Patterns.md` is a consolidated human reference; each real learning must become individual `type=learning` in `cortex/temporal/`. Likewise, `document_chunks` in UMC are the atomic unit; parent document (in `inbox/documents/`) is retrievable context.

Conventions: mandatory YAML frontmatter (`tags`, `status`, `created`); WikiLinks create graph `synapses`; decisions live in `cerebro/cortex/frontal/trabalho/ativo/`; patterns in `cerebro/cerebelo/padroes/`; explicit captures in `cerebro/cortex/parietal/inbox/visual/`. Agent and migrated-trash directories live under `cerebro/tronco/infra/` and are excluded from indexing by `.graphifyignore` and shared exclusions in `core/vault_excludes.py`. Top-level UI/artifact directories still allowed (`.obsidian/`, `.smart-env/`) are also indexing-excluded.

---

## 13. Automation and Cron

| Process | Trigger | Action |
|---------|---------|--------|
| Watcher (`start-watcher.sh`) | continuous daemon | Obsidian → SQLite in ~2s |
| `build-graph.sh` | `0 */6 * * *` | safety reindex (SHA-256 cache) |
| `cron/sync-diario.sh` | `0 2 * * 0` | full rebuild `--force` (rotated logs, keep last 30) |
| `dream_cycle.py` | nightly (recommended) | memory consolidation |
| `audit_memory.py` | post P2P sync | vault ↔ SQLite reconciliation |
| `alias_miner.py` | memory cycle | alias mining (slugs) for neurons |

---

## 14. How to Extend for New Agents

```
  1. sinapse.yaml
     ─────────────
     agents:
       supported:
         - seu-agente           ← add here
       install_methods:
         seu-agente: "..."

  2. install.sh
     ─────────────
     AGENT_DETECTORS+=([seu-agente]="seu-agente")
     # in case "$agent":
     seu-agente)
         cp skills/sinapse-query.md ~/.seu-agente/skills/

  3. config/mcp/seu-agente.json (template)
     ───────────────────────────────────
     {
       "mcpServers": {
         "sinapse-memory": {
           "command": "python3",
          "args": ["<SINAPSE_HOME>/scripts/services/sinapse-mcp.py"]
         }
       }
     }

  4. Minimum test
     ─────────────
     Agent can call sinapse_query + sinapse_save_decision?
     → Full integration.
```

---

## 15. Tests and Quality

```bash
./tests/run_all.sh   # Smoke → Unit → Integration → E2E
```

| Suite | Location | Real LLM? | What it covers |
|-------|----------|-----------|----------------|
| Smoke | `tests/smoke/` | No | Binaries, system health |
| Unit | `tests/unit/` | **No** | Backends (HTTP/subprocess mocks), write helpers, Dream Cycle queue, audit regressions |
| Integration | `tests/integration/` | Real backends | Read/write flows, MCP, API, hybrid search |
| E2E | `tests/e2e/` | Real backends | Full session, graceful degradation, concurrency, recovery, edge cases |
| Synthesis | `tests/test_synthesis.py` | **Yes** | `run_synthesis_cycle()` with real model from `.env` |

The test set is dynamic; on 2026-07-01 there were **706 `test_` functions
in 123 files with tests**. Use `rg -n "^\s*(async\s+def|def)\s+test_"
tests | wc -l` and `rg -l "^\s*(async\s+def|def)\s+test_" tests | wc -l`
to measure current state. Rule: unit tests never call LLM —
they test logic around the model, not the model itself.

---

## 16. Disaster Recovery

```bash
./scripts/utils/recover.sh
```

1. Checks/rebuilds graph index
2. Verifies backup integrity (`hive_mind.db.bak`)
3. Restarts claude-mem worker
4. HTTP health check (:37700)
5. Verifies plugin load

**Operational variables:**

| Variable | Description | Default |
|----------|-------------|---------|
| `SINAPSE_HOME` | Project root | `~/Documentos/Projects/Hive-Mind` |
| `SINAPSE_DRY_RUN` | No side effects | `false` |
| `SINAPSE_LOG_JSON` | JSON logs | `false` |
| `SINAPSE_DECISION_TOOLS` | Tools triggering writes (csv) | `memory_add,observation_add,...` |
| `SINAPSE_LEARNING_SIGNALS` | Learning signals (csv) | default pt/en/es |

---

## 17. Configuration Reference

`sinapse.yaml` — summarized schema with inline comments in the file itself:

```yaml
project:        # name, version, description
vault:          # path (cerebro/), format (obsidian), language, indexer, watch
graphify:       # package, install_method, extras, output_dir=cerebro/cortex/occipital/grafo, mcp_port
claude_mem:     # port (37700), install_method, worker_autostart
neural_memory:  # package, src_dir, recall_timeout
rtk:            # source_dir, binary, wrapper, targets global/project
sinapse_mcp:    # command, transport (stdio), tools (list of 15)
agents:         # supported[], integration_methods, install_methods
mcp_servers:    # graphify, claude_mem, sinapse_memory
cloud:          # enabled, url, api_key  ← local→VPS switching
hybrid_search:  # backends[], filesystem (categories, cache_ttl=30s), dedup
cron:           # sync_schedule ("0 */6 * * *"), rebuild_schedule ("0 2 * * 0")
```

---

*Phase and delivery history: [`PROJECT_STATUS.md`](../PROJECT_STATUS.md) · [`IMPLEMENTATION.md`](../IMPLEMENTATION.md) · [`docs/plans/`](plans/)*

---

## 18. HM-11 Phase: Deep Reflection (Long-Term Reasoning)

### Intent Memory (goal_id / why)

Each observation can now carry `goal_id` (FK to `goals`) and `why` (textual reason). `DistillerOutput` (`core/schemas/dream_models.py`) also exposes these optional fields, so each extracted fact set in a Dream Cycle session is linked to its motivating active objective.

### Planner Agent (`scripts/planner.py`)

Goal decomposition into atomic steps via LLM with validated Pydantic output.

| Function | Signature | What it does |
|----------|-----------|--------------|
| `decompose_goal` | `(goal, context?) → list[dict]` | Calls LLM with structured prompt; returns list of steps `{id, action, why, depends_on}`; on failure returns fallback step with original objective |
| `save_goal` | `(goal, steps, db_conn?) → goal_id` | Persists objective and steps JSON into `goals`; creates table if missing (idempotent) |

Schemas: `GoalStep` (id, action, why, depends_on) and `GoalPlan` (list of GoalStep). MCP tool `sinapse_plan_goal` exposes both in one call (`goal` required, `context` optional).

### Causality Graph (`core/database.py`)

`causal_edges` table records cause→effect relationships between neurons. Function `get_causal_neighbors(conn, neuron_id, hops=2)` performs multi-hop BFS returning `[{neuron_id, label, confidence}]`. Indexes on `cause_neuron_id` and `effect_neuron_id` for efficient queries. Migration applied automatically through `ensure_migrations()`.

### Incremental HNSW Index (`core/hnsw_index.py`)

Vector index based on `hnswlib` (cosine, 1024 dimensions by default via `HNSW_DIM`), persisted in `hnsw_neurons.idx` in same folder as `hive_mind.db`. Gracefully degrades if `hnswlib` is not installed (warning log, no crash).

| Function | What it does |
|----------|--------------|
| `load_or_create(dim?)` | Loads index from disk or creates new (max_elements=10 000, M=16, ef_construction=200) |
| `add_neuron(neuron_id, vector, conn?)` | Adds/updates vector; marks `indexed_at` in DB if conn provided; auto-expands index when full |
| `search(query_vector, k=10)` | Returns top-k neighbors `[{neuron_id, distance}]` |
| `rebuild_from_db(conn, embed_fn)` | Rebuilds full index from all neurons with content |
| `incremental_update(conn, embed_fn)` | Indexes only neurons with `indexed_at IS NULL`; persists index if at least one was indexed |

---

## 19. HM-12 Phase: Federated Swarm

### Visibility Model

`visibility TEXT DEFAULT 'private'` column in `neurons`. Three values:

| Value | Meaning |
|-------|---------|
| `private` | Local-machine only — never exported |
| `shared` | Can be exported to trusted peers |
| `public` | Can be exported without restriction |

Export endpoint automatically filters to `visibility IN ('shared', 'public')`.

### Export Endpoint (`POST /api/v1/neurons/export`)

Requires Bearer token + rate limit 10/min. Request body:

```json
{
  "filters": { "type": "fact", "created_after": "2026-01-01" },
  "sign": false,
  "redact": true
}
```

Returns `{ neurons, count, exported_at, schema_version: "1.0" }`. Redaction enabled by default (`redact=true`). Signature disabled by default (`sign=false`).

### Ed25519 Signing (`core/signing.py`)

PEM keys stored at `config/keys/` (`SINAPSE_HOME/config/keys/`). Private key created with `chmod 0600`.

| Function | What it does |
|----------|--------------|
| `generate_keypair(name="default")` | Generates Ed25519 pair and persists as `{name}_privkey.pem` / `{name}_pubkey.pem`; returns `{name, fingerprint, pubkey_path}` |
| `load_private_key(name)` / `load_public_key(name)` | Loads PEM from disk |
| `sign_neuron(neuron, key_name)` | Returns neuron copy with `_signature` (Ed25519 base64) and `_pubkey_fingerprint` (public DER SHA-256 hex) |
| `verify_neuron(neuron, pubkey)` | Verifies signature; returns `True`/`False`; never raises on invalid signature |
| `fingerprint(pubkey)` | SHA-256 hex of public key DER |

Canonical payload excludes volatile fields (`created_at`, `updated_at`, `indexed_at`) and signature fields to guarantee determinism between nodes.

### PII Redaction (`core/redactor.py`)

Irreversible redaction applied to neuron `content` and `label` before export. Local neurons are never modified.

| Function | What it does |
|----------|--------------|
| `redact_for_export(text)` | Applies all rules sequentially; returns new PII-free string |
| `redact_neuron(neuron)` | Deep-copy dict; redacts `content` and `label`; other fields pass unchanged |

8 rule categories (order matters — specific first):
1. API tokens (`sk-*`, `GOCSPX-*`, `ghp_*`, JWTs, `Bearer …`)
2. Emails
3. IPv4
4. IPv6
5. Absolute paths (`/home/`, `/root/`, `/Users/`, `/var/`)
6. SSH/PEM private key blocks
7. CPF / CNPJ (before phone to avoid overlap)
8. Phone numbers (broad pattern, runs last)

---

## 20. Design Decisions (ADRs) — placeholder

> ADR content moved to [§32](#32-design-decisions-adrs) (numbering increased after Born-Large Knowledge Architecture integration). Sections §21 and §22 below were preserved.

---

### ADR-001 — Obsidian Vault as single source of truth

**Decision:** Obsidian vault with YAML frontmatter + WikiLinks as primary storage.
**Rationale:** plain-text Markdown is git-friendly, tool-agnostic, and human-readable without special software. Obsidian is a mature editor with graph view, backlinks, and plugin ecosystem.
**Trade-off:** dependency on Watcher to keep SQLite synced; Obsidian is optional (vault works without it).

### ADR-002 — Parallel hybrid search

**Decision:** parallel search across 7 backends/organs (UMC, NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem — see §2.6) with fusion and cross-backend dedup.
**Rationale:** FTS5 finds exact terms; vectors find similar concepts; graph finds connections; filesystem guarantees fresh writes (zero gap). No single backend covers all cases.
**Trade-off:** slightly higher I/O use; mitigated by circuit breaker (30s cooldown after 3+ failures).

### ADR-003 — MCP as universal integration protocol

**Decision:** expose tools through MCP stdio instead of building agent-specific plugins.
**Rationale:** MCP is an open standard adopted by Anthropic, OpenAI, GitHub, and community. One server (`sinapse-mcp.py`) serves all agents without adaptation.
**Trade-off:** less automatic integration (hooks) than native plugins; compensated by CLI and external hooks (SessionStart, PostToolUse, Stop).

### ADR-004 — Atomic writes via os.replace()

**Decision:** `tempfile.mkstemp()` + `os.replace()` instead of `open().write()`.
**Rationale:** `os.replace()` is atomic on Linux (rename(2) syscall) — if process dies during write, target file stays intact (tmp becomes orphan, not target).
**Trade-off:** slightly more complex; justified for persistent memory data.

### ADR-005 — Cloud Memory API (FastAPI :37702)

**Decision:** lightweight FastAPI REST microservice protected by Bearer token for VPS deployment.
**Rationale:** allows local agents to use VPS-hosted memory without local physical vault. Fail-closed: does not start without `HIVE_MIND_API_KEY`.
**Trade-off:** requires stable network; automatic fallback to local mode when `cloud.enabled=false`.

### ADR-006 — Pydantic structured output in Dream Cycle

**Decision:** all LLM calls use JSON Schema derived from Pydantic models; response validated with `model_validate_json()`.
**Rationale:** ensures any provider (local Ollama or cloud Anthropic) returns processable structure; feedback loop (Validator rejects → Distiller reprocesses) improves quality without human intervention.
**Trade-off:** adds one LLM validation call per pipeline execution.

### ADR-007 — UUID v4 in all PKs

**Decision:** migrate sequential IDs to UUID v4 in all UMC tables.
**Rationale:** sequential IDs collide across machines in P2P scenario (A and B both create `id=1`). UUID v4 collision probability is 1 in 10^36.
**Trade-off:** less readable IDs in logs; irrelevant for programmatic use.

### ADR-008 — Quarantine instead of discard

**Decision:** failing pipeline sets `archived=2` instead of deleting or ignoring observation.
**Rationale:** memory data is valuable; transient failures (network down, API credit zero) should not cause permanent context loss.
**Trade-off:** quarantined data accumulation requires periodic manual or automated cleanup.

### ADR-009 — Per-role LLM config with inheritance and explicit fallback

**Decision:** each LLM-consuming role (`dreamer`, `graphify`, `vision`, `synthesis`) has own config via `HIVE_{ROLE}_PROVIDER/MODEL`, inheriting from Dreamer when absent, with **opt-in** fallback via `HIVE_{ROLE}_FALLBACK_PROVIDER/MODEL`. Resolution centralized in `get_role_config()` (`core/auth.py`); calls and retry/fallback policy centralized in `core/llm_client.py`.
**Rationale:** roles have opposite profiles — entity extraction (many cheap frequent calls) and dialectical synthesis (few high-reasoning calls) cannot be served by same model without waste or quality loss. **Automatic provider cascade was rejected** to preserve user sovereignty: Dialectical Synthesis decides memory truth and cannot switch model silently. Fallback only exists when explicitly configured by user. **Pydantic validation failure never triggers fallback** — it is output quality, not availability; blind model switching would mask the issue. API keys remain one per provider (never per role), avoiding secret duplication.
**Trade-off:** more environment variables (up to 16 with fallbacks); mitigated by inheritance — minimal case remains 2 vars (`HIVE_DREAMER_PROVIDER/MODEL`).

### ADR-010 — Layered Knowledge Promotion Pipeline (K3/K4)

**Decision:** split promotion into **Knowledge Intake** (normalize/classify/dedup) and **Promotion Layer** (Distiller → Validator → Router → Persistence → Indexing), implemented in `core/knowledge/intake.py` and `core/knowledge/promotion.py`. Canonical claude-mem bridge in `core/knowledge/claude_mem_bridge.py` (read-only SQL path accepting `source_id` and time window).

**Rationale:** previous Dream Cycle did everything in one stage; splitting intake/promotion makes promotion **idempotent**, **testable** without real LLM, and exposes `candidate-only` mode (output `candidate` without persistence) for orchestration. Promotion is never 1-to-1 — it is batch with queue and workspace priority (§30.5). Canonical knowledge types (§27.2) and automatic/forbidden promotion rules (§27.3) become contract, not heuristic.

**Trade-off:** more upfront code; mitigated by `KnowledgePromotionPipeline` return in `candidate-only` mode for callers not persisting.

### ADR-011 — Separate canonical vector collections (K1)

**Decision:** `VectorBackend` operates on **seven canonical collections** — `memory_vectors`, `observation_vectors`, `document_vectors`, `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors` — each with canonical metadata (`parent_id`, `parent_type`, `brain_lobe`, `knowledge_type`, `project`, `source_uri`, `hash`, `valid_at`, `workspace_id`). Official backends: `sqlite_vec` (local/dev/offline) and `milvus` (production).

**Rationale:** one "everything" collection pollutes ranking and makes per-type coverage impossible. Separation enables production gates per collection (§28), selective pruning (forgetting orphan `document_chunks` does not affect `memory_vectors`), and per-collection embedding-model versioning (§30.4).

**Trade-off:** more UMC tables; mitigated by auxiliary `vector_metadata` and collection identity `(name, embedding_model, dim)`.

### ADR-012 — VectorBackend: single contract, multiple backends

**Decision:** all application vector access uses contract `upsert/delete/query/hybrid_query/count/health`, independent of backend. Milvus, sqlite-vec, and any future backend obey same contract. **Application never calls Milvus directly outside the contract.**

**Rationale:** switching `sqlite_vec` to `milvus` (and vice versa) becomes config change, not code change. Enables same `DocumentPipeline`, `RetrievalRouter`, and `KnowledgePromotionPipeline` to run in dev (sqlite-vec) and production (Milvus) without branching.

**Trade-off:** contract must remain stable; Milvus schema changes require versioned embedding migration (§30.4).

### ADR-013 — DocumentPipeline with mandatory parent/chunk/citation (K6)

**Decision:** every ingested document becomes one `document_memories` (parent) with `document_chunks` (atoms) and `document_vectors` entries (vectors with canonical metadata). Query returns **auditable citations** (`source_uri`, offsets, parent), not only "best snippet".

**Rationale:** without parent, chunk is loose text — not auditable, deduplicable, or re-ingestable. `document / chunk / vector` separation enables K6 born-large. RAGFlow is adapter/headless, never source of truth; its store is ingestion cache.

**Trade-off:** more metadata per vector; mitigated by auxiliary `vector_metadata` index and fixed Milvus schema.

### ADR-014 — RetrievalRouter classifies intent before searching (K7)

**Decision:** `RetrievalRouter` (`core/retrieval/router.py`) is query entrypoint; it classifies intent, chooses specialized route (temporal, memory, document, code, graph, multi-hop, hybrid), and returns `retrieval_path`, `citations`, `confidence`, `missing_context`. LlamaIndex is optional rerank adapter only; it does not choose route or become source of truth.

**Rationale:** `sinapse_query` fuses 7 organs without understanding intent — good for broad search, weak for precision. Router explicitly routes "decision" to `memory_vectors`, "document" to `document_vectors`+parent, "code" to `code_vectors`+Graphify, etc. `query_route_distribution` telemetry (query hash, not text) feeds K8 health metric.

**Trade-off:** intent classifiers can fail; mitigated by fallback to `sinapse_query`/Context Fusion on low confidence, and `intent_accuracy` metric in golden set (§31.3).

### ADR-015 — Workspace as isolation boundary (K8/§30)

**Decision:** every critical UMC table (`neurons`, `observations`, `synapses`, `goals`, `document_memories`, `visual_memories`, `ambiguities`, `causal_edges`, `vault`) carries `workspace_id` (default `'default'`). Every `RetrievalRouter` and promotion query filters by `workspace_id`. Milvus uses `partition_key=workspace_id` for partition isolation.

**Rationale:** Hive-Mind starts single-user local-first, but product is open-source with per-install scale vector, multi-user per instance, and federation across instances. Adding `workspace_id` later would require structural migration — now it is a column. Cross-workspace leak is a security bug, not ranking issue.

**Trade-off:** every query must carry `workspace_id`; mitigated by `(workspace_id, ...)` hot indexes and default `'default'` (no impact to single-user).

### ADR-016 — Promotion failure preserves data, never discards

**Decision:** promotion contract explicitly distinguishes transient error (`archived=0`, future retry) and structural error (`archived=2`, quarantine with reason). Nothing is deleted by promotion failure. `Knowledge Intake` (K3) is first layer using this contract; `Promotion Layer` (K4) enforces it.

**Rationale:** memory data is valuable; transient failures (network down, API credit zero, new schema) should not cause permanent loss. Normative contract is fail-safe, not fail-silent.

**Trade-off:** quarantine accumulation; mitigated by `K8 knowledge_health` exposing `observations_pending` and `discoveries_pending` as gate, and manual/automatic reprocessing pipeline.

### ADR-017 — Hierarchical session→yearly cadence with dedicated LLM roles

**Decision:** temporal memory is organized in **five cadences** (session, daily, weekly, monthly, yearly) with own writers, inputs, outputs, models, and promotion rules. Each cadence has configurable LLM role (`session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer`, `yearly_synthesizer`) and inherits from `dreamer` if no override. Fail-closed: role without own model and no inheritance logs auditable failure and does not invent synthesis.

**Rationale:** monthly/yearly produce strategic memory (goals, drift, principles) that cannot be generated by small model without quality loss. Session/daily can use small model because task is local compression. Cost/quality by cadence is the correct design.

**Trade-off:** more roles to configure; mitigated by `setup-brain` inheritance from `dreamer` in minimal case.

### ADR-018 — Negative vendoring contract via `components.lock.json`

**Decision:** `components.lock.json` accepts only source **clones** built/patched by `install.sh` (`graphify`, `neural-memory`, `rtk`, `omniparser`, `crsqlite` binary). Wrappers (Milvus, RAGFlow, Graphiti) enter through container/SDK; pip covers only LlamaIndex and utilities. If Milvus, RAGFlow, or LlamaIndex appear in `components.lock.json` for this front, implementation is wrong.

**Rationale:** explicit clone vs wrapper rules reduce operational ambiguity. Contract is also negative (declares what **does not** belong there) to prevent regression.

**Trade-off:** lock-file maintenance; mitigated by generation from `install.sh` and PR review.

---

## 21. Phase Governance

### Phase Namespace

Each project uses a unique prefix to avoid numbering collisions:

| Project | Prefix | Example |
|---------|--------|---------|
| Hive-Mind | `HM-` | HM-10, HM-11, HM-12 |
| Thoth | `TH-` | TH-33, TH-34 |
| Ruflo | `RF-` | RF-01, RF-02 |

### Phase Completion Rule

No phase can be marked `✅ Completed` without:

1. **Commit** — all delivery files versioned in git
2. **Test** — at least one test covering the main delivery path
3. **Green CI** — test suite passing at merge time

Violating this rule caused the divergence between declared and real state identified in 2026-06-10 audit.

### Current Status of HM- and K- Phases

| Phase | Name | Status | Ref. |
|------|------|--------|------|
| HM-01 to HM-09 | Foundation (UMC, search, P2P, synthesis) | ✅ Completed | — |
| HM-10 | Deep Portal (multimodal) | ✅ Completed | — |
| HM-11 | Deep Reflection (long-term reasoning) | ✅ Completed | — |
| HM-12 | Federated Swarm (selective sharing) | ✅ Completed | — |
| K0 | `VectorBackend` contract (sqlite-vec + Milvus adapter) | ✅ Completed | §24, [11-§9](../11-knowledge-promotion-architecture.md#9-contrato-vectorbackend) |
| K1 | Canonical collection split + canonical metadata | ✅ Completed | §24, [11-§8](../11-knowledge-promotion-architecture.md#8-estrategia-de-vector-search) |
| K2 | `DocumentPipeline` (K6) parent/chunk/citation | ✅ Completed | §25, [11-§10](../11-knowledge-promotion-architecture.md#10-documentpipeline-born-large) |
| K3 | Knowledge Intake (intake.py) | ✅ Completed | §27, [11-§5](../11-knowledge-promotion-architecture.md#5-fluxo-ideal-de-promocao) |
| K4 | Promotion Layer (promotion.py) + claude-mem bridge | ✅ Completed | §27, [11-§6](../11-knowledge-promotion-architecture.md#6-claude-mem-nao-e-apenas-dado-bruto) |
| K5 | Hierarchical session→yearly cadence | ✅ Completed | §29, [11-§14](../11-knowledge-promotion-architecture.md#14-cadencia-hierarquica-de-escrita) |
| K6 | `DocumentPipeline` parent/chunk/citation | ✅ Completed | §25 |
| K7 | `RetrievalRouter` (router.py) | ✅ Completed (v3.5.0, 2026-06-30) | §26, [11-§11](../11-knowledge-promotion-architecture.md#11-retrievalrouter-born-large) |
| K8 | Health metrics (knowledge_health.py) | ✅ Completed (v3.6.0, 2026-06-30) | §28, [11-§13](../11-knowledge-promotion-architecture.md#13-metricas-de-saude) |
| K9 | Real acceptance harness (`tests/real/`) | ✅ Contract (implementation in [12-§17.4](../11-knowledge-promotion-architecture.md#174-harness-real-e-skip-de-servicos)) | §31.4 |
| K10 | Born-large (workspace, federation, versioned embedding) | ✅ Contract | §30 |

### Vault files with old convention

The files below in `cerebro/cortex/frontal/trabalho/ativo/` use old numbering without prefix and should be
renamed in the next manual vault edit (NOT via git — vault syncs through Syncthing):

- `2026-06-01-PHASE-33-TTS-Integration-Closeout-Final.md` (correct prefix: TH-33)
- `2026-06-02-PHASE-34-Disk-Cache-persistente-para-TTS-design-rationale-e.md` (correct prefix: TH-34)
- `2026-06-02-PHASE-34-FFmpeg-Transcoding-no-Thoth-Telegram-Voice-Bubble.md` (correct prefix: TH-34)
- `2026-05-30-Implementacao-das-4-Fases-do-Sinapse-Agent.md` (Sinapse Agent phases without project prefix)

---

## 22. Born-Large Knowledge Architecture

Hive-Mind is not only local RAG — it is a **persistent brain** with temporal capture, consolidated memory, documents, code, vision, structural graph, temporal causality, and hybrid/vector search. Knowledge architecture must **separate capture, promotion, storage, indexing, and retrieval from day one** — without depending on later structural refactoring to support Milvus, advanced document pipelines, or composite routers.

Detailed normative reference lives in [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md), and detailed phase execution plan (K0–K10) is in [`12-knowledge-implementation-plan.md`](12-knowledge-implementation-plan.md). Sections §23–§31 in this document **distill** that canonical reference at architecture level.

### 22.1 Product decision

| Tool | Role in Hive-Mind | Architectural status |
|---|---|---|
| RAGFlow | Headless adapter for document ingestion, layout-aware parsing, chunking, citations | first-class in `DocumentPipeline` |
| Milvus | Production vector backend for large collections (multi-collection, partition by `workspace_id`) | first-class in `VectorBackend` |
| LlamaIndex | Adapter for rerank and composite retrieval workflows | first-class in `RetrievalRouter` |
| sqlite-vec | Local/dev/offline backend and operational cache | mandatory for local-first |
| claude-mem | Temporal hippocampus: `user_prompts`, `observations`, `discoveries`, `session_summaries` | mandatory |
| Graphify | Structural vault/code graph | mandatory |
| Graphiti | Causality and temporal validity (`valid_at`/`invalid_at`) | mandatory |
| LightRAG/GraphRAG | Multi-hop relations and global questions | mandatory/expandable |

### 22.2 Final rule

Hive-Mind must be:

```text
local-first by operation
born-large by architecture
pluggable by contract
anatomical by source of truth
auditable by evidence
```

No external backend can replace the brain. External backends **accelerate, scale, or specialize indexes**. Truth remains in anatomical vault (`cerebro/`) and UMC. `components.lock.json` is also a **negative contract**: if Milvus, RAGFlow, or LlamaIndex appear there for this front, implementation is wrong — they enter via wrapper/compose+SDK and pip, respectively.

### 22.3 Vendoring: clone vs wrapper vs pip

- **Clone** (`integrations/<name>/` via `components.lock.json`): only what `install.sh` builds/patches from source — `graphify`, `neural-memory`, `rtk`, `omniparser`, `crsqlite` binary.
- **Wrapper** (`client.py` + `docker-compose.yml` with digest-pinned image): service run via container/SDK — `graphiti`, **Milvus** (`pymilvus`), **RAGFlow** (`ragflow-sdk`, headless).
- **Pip**: **LlamaIndex** (`llama-index` in `pyproject.toml`).

Milvus and RAGFlow are **not cloned**. RAGFlow runs headless: output flows into `document_vectors` + UMC; its store is ingestion cache, not source of truth.

### 22.4 Derived sections summary

| Section | Content |
|---|---|
| [§23](#23-capture--promotion--retrieval-flow) | 9-step flow (Capture → Temporal → Intake → Promotion → Anatomical → Index → Retrieval → Answer+Citation → Feedback) |
| [§24](#24-vectorbackend-contract-canonical-collections-and-scale) | `VectorBackend` contract and 7 canonical collections |
| [§25](#25-documentpipeline-k6--born-large-ingestion) | `DocumentPipeline` (K6): `document_memories` + `document_chunks` + `document_vectors` |
| [§26](#26-retrievalrouter-k7--intent-routing) | `RetrievalRouter` (K7): intent routes, return contract |
| [§27](#27-knowledge-promotion-pipeline-k3k4) | `Knowledge Intake` + `Promotion Layer` (K3/K4) |
| [§28](#28-knowledge-health-metrics-k8) | K8 health metrics and production gate |
| [§29](#29-hierarchical-writing-cadence) | Session → yearly cadence with roles and models by cadence |
| [§30](#30-scale-and-isolation--workspace-and-federation) | `workspace_id`, collection partitioning, inter-instance federation, embedding migration |
| [§31](#31-pending-contracts-reranker-forget-eval-harness) | Reranker, intentional forgetting, retrieval evaluation, real harness |

---

## 23. Capture → Promotion → Retrieval Flow

Canonical 9-step flow (from [`11-knowledge-promotion-architecture.md` §2](11-knowledge-promotion-architecture.md#2-fluxo-completo)):

```text
Agent / Human / System
        |
        v
[1] Capture Layer
    hooks, MCP, CLI, browser, documents, code, screenshots, runtime
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
    raw -> summary -> fact / learning / decision / preference / task / rationale
        |
        v
[5] Anatomical Memory
    cerebro/ + UMC:
      cortex temporal · frontal · parietal · occipital · insula
      cerebelo · diencefalo · tronco
        |
        v
[6] Index Layer
    FTS · sqlite-vec · Milvus · vec_observations · Graphify · Graphiti · LightRAG
        |
        v
[7] Retrieval Router (core/retrieval/router.py — K7)
    chooses temporal · memory · document · code · graph · chunk · hybrid
        |
        v
[8] Answer + Citation
    answer with source, evidence, path, and date
        |
        v
[9] Feedback
    new observation, decision, learning, or task
```

**Edge rules** (normative):

1. Each step is loosely coupled: failure in [4] does not block [1]–[3] (observation returns as `archived=0` or `archived=2`).
2. Each writer declares explicit write contract (§27.3): creates observation? anatomical file? neuron? vector? edge? task/goal? evidence? idempotency key?
3. Nothing is deleted by promotion failure: transient error → `archived=0` (retry); structural error → `archived=2` (quarantine with reason).

---

## 24. VectorBackend: contract, canonical collections, and scale

### 24.1 Contract

Every vector backend implements the same contract (`core/vector_backend.py`):

```text
upsert(collection, id, vector, metadata)
delete(collection, id)
query(collection, vector, top_k, filters)
hybrid_query(collection, text, vector, filters)
count(collection, filters)
health()
```

Application **never** calls Milvus directly outside this contract. This prevents replacing brain anatomy with infrastructure detail.

### 24.2 Canonical collections

Hive-Mind **separates collections by content type** — it does not put everything in one ranking:

| Collection | Content | Local backend | Production backend |
|---|---|---|---|
| `memory_vectors` | facts, decisions, learnings, preferences | UMC `hive_mind.db/search_vec` | Milvus |
| `observation_vectors` | claude-mem observations/discoveries | `~/.claude-mem/claude-mem.db/vec_observations` (sqlite-vec, read-only) | Milvus |
| `document_vectors` | document chunks/vault docs | UMC `vec_documents` + `vector_metadata` | Milvus |
| `code_vectors` | code symbols/files | UMC `vec_code` + `vector_metadata` | Milvus |
| `visual_vectors` | screenshots/visual descriptions | UMC `vec_visual` + `vector_metadata` | Milvus |
| `graph_vectors` | entity/relation summaries | UMC `vec_graph` + `vector_metadata` | Milvus + graph |
| `summary_vectors` | cadence summaries (session→yearly) | UMC `vec_summary` + `vector_metadata` | Milvus |

`sqlite-vec` is mandatory for local-first/offline. Milvus is production backend, **not replacing source of truth** — it only scales vector index.

### 24.3 Canonical metadata per vector item

Each item carries: `parent_id`, `parent_type`, `brain_lobe`, `knowledge_type`, `project`, `source_uri`, `hash`, `valid_at`, `workspace_id`. In UMC, helper collections store these in `vector_metadata`; in Milvus they are required schema fields. Embedding model and dimension are controlled by global contract: `snowflake-arctic-embed2:latest`, **1024d**, unless explicit env override.

### 24.4 Official backends

| Backend | Role |
|---|---|
| `sqlite_vec` | local/dev/offline/cache — mandatory |
| `milvus` | production/scale/multi-collection — first class |

---

## 25. DocumentPipeline (K6) — born-large ingestion

Inspired by RAGFlow, but **preserving Hive-Mind anatomy** (K6 implemented in `core/knowledge/document_pipeline.py`):

```text
document input
        |
        v
parse layout-aware
        |
        v
normalize
        |
        v
chunk by structure
        |
        v
metadata + citations
        |
        v
embedding
        |
        v
document_vectors + parent document
        |
        v
optional promotion to facts/learnings (via KnowledgePromotionPipeline)
```

### 25.1 Three levels to avoid "loose text"

| Level | Table/collection | Content | Why it exists |
|---|---|---|---|
| Parent document | `document_memories` | `document_id`, `source_uri`, `file_hash`, `project`, `workspace_id`, metadata | Source proof and reingestion unit |
| Chunk | `document_chunks` | `parent_id`, `parent_type=document`, `chunk_index`, `heading`, offsets, `hash`, metadata | Atomic retrievable unit |
| Vector | `document_vectors` | chunk embedding + canonical metadata | Local/Milvus semantic search without losing parent context |

Mandatory metadata in `document_vectors`: `parent_id`, `parent_type=document`, `brain_lobe=parietal`, `knowledge_type=document_chunk`, `project`, `source_uri`, `hash`, `valid_at`, `workspace_id`. Without these fields, vector is considered incomplete for K6 design.

### 25.2 Query with parent context

```text
query
  -> document_vectors
  -> document_chunks
  -> document_memories
  -> citations[{source_uri, offset_start, offset_end, score, parent}]
```

Return **cannot** be only "best snippet": it must include excerpt, score, `source_uri`, offsets, and enough parent context for auditing.

### 25.3 RAGFlow: role and boundaries

RAGFlow is allowed as **parser/headless** for complex documents, with explicit boundaries:

- **not** source of truth;
- **not** replacing `document_memories`, `document_chunks`, or `document_vectors`;
- proprietary cache/store **not** part of retrieval contract;
- RAGFlow unavailability **must not** break local-first path;
- any reused output must be normalized to UMC before becoming retrievable by brain.

Document-to-durable-knowledge promotion (fact/decision/learning) is done by `KnowledgePromotionPipeline` (see §27), **not** by `DocumentPipeline` alone. This separation avoids polluting durable memory with every document chunk and preserves difference between retrievable evidence and promoted knowledge.

---

## 26. RetrievalRouter (K7) — intent routing

Inspired by LlamaIndex, but implemented as **own contract** (delivered in `core/retrieval/router.py` in v3.5.0, 2026-06-30). Router classifies intent, executes specialized routes, preserves fallback to `sinapse_query`/Context Fusion, and returns `retrieval_path`, `citations`, `confidence`, `missing_context` in all queries. `core/search.py` exposes `route_retrieval()` as internal adapter.

**LlamaIndex is only an optional rerank adapter**; it does not choose route or become source of truth.

```text
query
  |
  +-- recent / "what happened"         -> claude-mem temporal
  +-- decision / preference             -> memory_vectors + FTS
  +-- learning                          -> learning atoms + Patterns parent
  +-- document                          -> document_vectors + parent context
  +-- code                              -> code_vectors + Graphify
  +-- causality / when was true         -> Graphiti
  +-- global question / multi-hop       -> LightRAG/GraphRAG
  +-- health / self-awareness           -> insula (saude/conflitos)
  +-- config / operational / model      -> tronco (operational_fact)
  +-- sector / cross-project            -> diencefalo + Graphiti
  +-- ambiguous                         -> hybrid + reranker
```

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

`query_route_distribution` (§28 metric) is populated from `query_route_log` in best-effort mode. Stored query is always hash — raw question text never enters telemetry.

---

## 27. Knowledge Promotion Pipeline (K3/K4)

### 27.1 Knowledge Intake (K3) — `core/knowledge/intake.py`

Layer [3] of the flow (see §23). Responsibilities:

- normalizes claude-mem observation fields (`observations`, `discoveries`, `session_summaries`, `facts`, `narrative`, `concepts`, `files_read/files_modified`, `prompt_number`, `generated_by_model`);
- preserves stable `source_id` (`claude-mem:<table>:<id>`);
- extracts evidence / files / timestamps;
- classifies `knowledge_type` (§27.2);
- deduplicates by `source_id` + content hash.

### 27.2 Canonical knowledge types

| Type | Common origin | Promotes to | Note |
|---|---|---|---|
| `event_raw` | hook/claude-mem/runtime | temporal only or investigation | never delete |
| `user_prompt` | claude-mem | evidence/intent | preserves original question |
| `session_summary` | claude-mem | cerebelo/session | contains investigated, done, pending |
| `discovery` | claude-mem | fact/learning/rationale/task | not discardable raw |
| `fact` | Dream Cycle/discovery | cortex temporal | validated atomic fact |
| `preference` | conversation/decision | cortex temporal/_global | user/project preference |
| `decision` | MCP/summary/discovery | cortex frontal + temporal | decision with reason |
| `learning` | discovery/Patterns | cerebelo + temporal | atomic learning |
| `rationale` | code/decision | temporal/frontal | why something exists |
| `operational_fact` | health/runtime/audit | tronco/insula | verifiable real state |
| `document_chunk` | docs/PDF/vault | parietal | small chunk + parent |
| `code_symbol` | Graphify/code scan | occipital/structural | function/class/module |
| `visual_observation` | screenshot | occipital/parietal | image + description |
| `next_step` | session summary/discovery | goal/task | becomes trackable work |

### 27.3 Promotion Layer (K4) — `core/knowledge/promotion.py`

Layer [4] of the flow. Automatic promotion rules:

- **Allowed**: `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` — all with traceable source.
- **Forbidden**: turning every bullet into fact; creating neuron without source; vectorizing duplicates without `parent_id` and content hash; promoting temporary opinion to architecture decision; overwriting prior decisions without creating conflict or `invalid_at`.

### 27.4 Writer contract per writer

Every tool or pipeline writing memory must declare:

| Question | Mandatory |
|---|---|
| Creates observation? | yes/no |
| Creates anatomical file? | path |
| Creates neuron? | type |
| Creates vector? | collection |
| Creates edge? | Graphiti/Graphify/LightRAG |
| Creates task/goal? | yes/no |
| Which evidence? | source ids/files |
| How reprocesses? | idempotency key/hash |

Example:

```yaml
writer: sinapse_save_learning
observation: true
file: cerebro/cerebelo/padroes/Patterns.md
neuron: learning
vector_collection: memory_vectors
edges:
  - related_to
promotion_required: false
idempotency: title+content_hash
```

### 27.5 Canonical claude-mem bridge (K4)

Reading from claude-mem for promotion/backfill uses `core/knowledge/claude_mem_bridge.py` (read-only SQL in `~/.claude-mem/claude-mem.db`). This is the path accepting `source_id` and time window without relying on text search. Interactive workflow `search → timeline → get_observations` (via MCP) remains the path to retrieve raw context before picking IDs.

Findings: `session_summaries` always exists; `discoveries` may not exist — when absent, they come from `observations.type='discovery'` with fields `facts`, `narrative`, `concepts`, and `files_*`. Stable `source_id`: `claude-mem:<table>:<id>`, preserved in metadata and evidence.

---

## 28. Knowledge Health Metrics (K8)

Delivered in `scripts/health/knowledge_health.py` (v3.6.0, 2026-06-30). This module **adds** knowledge-coverage metrics; it **does not replace** `health_dashboard.py`, `alert_dispatcher.py`, or `review_writer.py`, which remain Insula health. `sinapse_health` includes a read-only `knowledge_health` block in quick mode, and REST API exposes `GET /api/v1/knowledge/health` for full gate.

| Metric | Signal |
|---|---|
| `neurons_total` | consolidated memory size |
| `neurons_vectorized_pct` | vector coverage |
| `observations_pending` | temporal backlog |
| `observations_linked_pct` | effective promotion |
| `discoveries_pending` | risk of learning loss |
| `learnings_atomized` | granular learning |
| `document_chunks_total` | document ingestion |
| `code_symbols_total` | structural coverage |
| `milvus_sync_lag` | local/production divergence |
| `orphan_vectors` | dirty index |
| `query_route_distribution` | which layers answer |
| `*_vectorized_pct` | coverage by canonical collection (memory/observation/document/code/visual/graph/summary) |
| `promotion_lag` | promotion backlog by workspace |
| `promotion_cost` | LLM cost by workspace |
| `vectors_model_mismatch` | embedding-model divergence inside a collection |

K8 explicitly measures the **seven canonical collections** — gate cannot only inspect `neurons_vectorized_pct`.

**Minimum production gate:**

```text
neurons_vectorized_pct >= 99%
observations_linked_pct increasing per cycle
discoveries_pending within SLA
0 orphan vectors
all chunks with parent_id
citations present in document answers
```

---

## 29. Hierarchical Writing Cadence

Hive-Mind memory does not depend on one giant summary. It rises in layers: **session → daily → weekly → monthly → yearly**. Each layer has own purpose, model, and promotion rule.

| Cadence | Writer | Input | Anatomical output | Default model | Promotes |
|---|---|---|---|---|---|
| Session | `session_consolidator.py` | raw logs, tool calls, notes | `cerebelo/sessoes/YYYY/MM/YYYY-MM-DD-HHMM-{slug}.md` | small/fast | decisions, open questions, candidate evidence |
| Daily | `daily_writer.py` | sessions + summaries | `cerebelo/diario/YYYY/MM/YYYY-MM-DD.md` | small or medium | candidate learnings, progress, next steps |
| Weekly | `weekly_synthesizer.py` | dailies, facts, decisions, metrics | `cerebelo/semanal/YYYY-Wxx.md` | medium/strong | patterns, strategic decisions, priorities |
| Monthly | `monthly_synthesizer.py` | weeklies, projects, discoveries, metrics | `cerebelo/mensal/YYYY-MM.md` | strong | executive synthesis, strategic drift, goals, risks |
| Yearly | `yearly_synthesizer.py` | monthlies, milestones, durable patterns | `cerebelo/anual/YYYY.md` | strong/offline batch | historical memory, principles, durable lessons learned |

### 29.1 What goes in and what does not

| Source | Goes to long-term memory | Does not go |
|---|---|---|
| Raw session log | only referenceable evidence and important events | repetitive tool calls, temporary errors, terminal noise |
| Session summary | decisions, open questions, tasks, sourced discoveries | narrative bullets without consequence |
| Daily | learnings, project progress, recurring blockers | complete list of read files/commands |
| Weekly | patterns, direction changes, consolidated status, priorities | micro-details already covered by sessions/dailies |
| Monthly | executive synthesis, structural risks, goals, strategic drift | operational progress without durable impact |
| Yearly | principles, architecture retrospective, major decisions, durable lessons learned | repeated weeklies/monthlies without new abstraction |

**Golden rule:** the higher the cadence, the less text it copies and the more it consolidates causality, decisions, patterns, and consequences.

### 29.2 Promotion contract by cadence

Each summary is a source with `source_id`, `period_start`, `period_end`, `cadence`, and `parent_summary_id`. Model follows `setup-brain` and inherits from `dreamer` when no override exists. For clean machine: fail-closed rule — if role has neither own model nor `dreamer` inheritance, writer must register auditable failure and not invent synthesis. For low cost, session/daily may use small model; monthly/yearly **must not** be auto-downgraded without notice.

---

## 30. Scale and Isolation — Workspace and Federation

Hive-Mind is an open-source product born to scale. It is not B2B SaaS: scale axis is (a) **per-install** (one user accumulates years of corpus), (b) **multi-user per instance** (self-hosted team), (c) **federation** between instances. Isolation is born in schema — not patched later — and single-user local-first does not notice (default `workspace_id='default'`).

### 30.1 Workspace (isolation boundary)

```text
workspace_id column in: neurons, observations, synapses, goals, document_memories,
                        visual_memories, ambiguities, causal_edges, vault
  default: 'default'  (single-user does not need to set it; born-large at no local cost)
index: (workspace_id, ...) in hot queries
filter: EVERY read/write of RetrievalRouter and promotion carries workspace_id
vault: cerebro/ can be workspace subtree in multi-user mode
```

**Rule:** no neuron/vector/edge crosses `workspace_id` without going through federation layer. Cross-workspace leakage is a security bug, not ranking issue.

**Structural migrations** creating this boundary: migration failure is fail-closed by default. Only bypass is `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` (legacy DB diagnostics, with visible log and without marking install healthy).

### 30.2 Vector collection partitioning

```text
sqlite-vec (local/dev): filter by workspace_id in metadata
Milvus (production):    partition-key = workspace_id (isolation + partition pruning)
```

### 30.3 Federation between instances (reuses HM-12)

Already exists and is not reimplemented: `visibility` (private|shared|public), Ed25519 signing (`core/signing.py`), PII redaction in export (`core/redactor.py`). Born-large contract:

```text
inter-instance export: only visibility in (shared, public) + redact + sign
import: verifies signature; imported neuron enters with destination workspace_id
        and provenance (origin_instance, origin_signature) preserved
never: import cross-instance raw without redaction; overwrite local without invalid_at
```

### 30.4 Versioned embedding migration

Changing embedding model at scale is not a one-shot script. Vector space is versioned:

```text
collection identity carries (embedding_model, dim)
upsert with divergent model: rejected or goes to new collection (never mix)
migration: online reembed per workspace, dual-write (old+new model) until cutover
metric: vectors_model_mismatch (§28) = 0 inside a collection
```

### 30.5 Promotion cost/throughput by workspace

Each promoted observation = 1 LLM (classify) + 1 embedding. At scale this is queue with backpressure and workspace cost cap:

```text
batch promotion (not 1-to-1), queue with priority
workspace cap (env HIVE_PROMOTION_BUDGET_*), overflow remains archived=0 (retry)
metric: promotion_lag and promotion_cost by workspace
```

---

## 31. Pending Contracts (Reranker, Forget, Eval, Harness)

Capabilities **already existing** (do not reimplement): merge/dedup in promotion (Dream Cycle Router `append|create_new|merge` + `ambiguities` table + `register_ambiguity` + learning dedup by title + cross-backend dedup in `context_fusion`); PII/secret redaction (`core/redactor.py`, in federated export).

Gaps below are evolutionary contracts. When a first slice already exists,
text explicitly states what is delivered and what remains pending.

### 31.1 Reranker (reorder by relevance)

Today `context_fusion._fuse_contexts` dedups and **truncates** by backend order.
Inside `RetrievalRouter`, reranker is already delivered:
`HIVE_RETRIEVAL_RERANKER=1` triggers `integrations/llama_index/client.py::rerank`.
By default it uses deterministic/fail-open lexical rerank gated by
`assert_health()` from LlamaIndex. With
`HIVE_RERANKER_PROVIDER=sentence-transformers` + `HIVE_RERANKER_MODEL`, it tries
opt-in local cross-encoder. Contract:

```text
rerank(query, candidates[]) -> reordered candidates[]
  input: raw top-N from fusion (e.g.: 30)
  current activation: HIVE_RETRIEVAL_RERANKER=1 (deterministic local lexical)
  opt-in cross-encoder: env HIVE_RERANKER_PROVIDER/MODEL + reranker extra
  output: top-K (e.g.: 5) ordered by relevance score
  fail-open: no model/error -> current order (dedup+truncate), no breakage
```

Hook is already plugged between fusion and `RetrievalRouter` return (§26),
off by default in `local-min`. Permanent real coverage:
`tests/real/test_retrieval_router_real.py` validates overlap-based reordering,
opt-in cross-encoder config, and `retrieval_path` with
`reranker/llama_index: hit`.

### 31.2 Intentional forgetting (forget / retention)

Rule "never delete on failure" (§27) covers failure, not deliberate forgetting. Missing: deleting leaked secret, expiring ephemeral data, pruning orphans. Contract:

```text
forget(target, reason) -> auditable tombstone (never silent physical delete)
  reasons: secret_leak | expired | superseded | user_request | orphan_vector
  CRDT-safe: delete in CR-SQLite + tombstone; corresponding vector removed in backend
  audit: record in insula (reason, who, when); raw preserved only if not secret
```

K8 implements first contract slice for orphan vectors: `knowledge_health.py` calls `forget_vector()` with reason `orphan_vector`, removes item from local sqlite-vec collection, cleans `vector_metadata` when applicable, and writes `knowledge_tombstones` with `target_type`, `target_id`, `collection`, `reason`, `actor`, `workspace_id`, and auditable metadata. Future extensions for `secret_leak`, `expired`, `superseded`, and `user_request` must reuse same tombstone table.

### 31.3 Retrieval evaluation (eval)

§28 measures **coverage** (plumbing), not response **quality**. Contract:

```text
golden set: tests/real/golden_retrieval.jsonl
  each case: {query, expected_source_ids[], expected_intent}
metrics: precision@k, recall@k, citation_correctness, intent_accuracy
gate: regression over threshold blocks front (with real harness K9)
```

Small and hand-curated; grows with each reproducible retrieval bug added as case.

### 31.4 Real harness and service skips

Acceptance for knowledge front uses `tests/real/` and does not count mock as closure. `requires_service` marker contract:

```text
if required real service is online: run and fail on behavior failure
if required real service is offline: explicit skip with reason and service name
if test has no external service dependency: always run
```

Skip must be implemented by service fixture/hook, not only comment in `pytest.ini`. Every new real backend (Milvus, FalkorDB, claude-mem, RAGFlow) must register own fixture or service registry before becoming phase gate.

Current implementation: `tests/real/service_registry.py` + hook in `tests/real/conftest.py`. Known services: `ollama`, `milvus`, `falkordb`, `claude_mem`, `ragflow`. Unknown service is test error; offline service is explicit skip with service name and reason.

---

## 32. Design Decisions (ADRs)

Record of architecture decisions shaping current design. Each ADR documents context, chosen decision, rationale, and accepted trade-offs. ADRs **001–009** were inherited from v2.0.0 architecture; **010–018** were created in Born-Large Knowledge front (K0–K10) and mirrored in [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md). In case of divergence, this canonical section prevails.

### ADR-001 — Obsidian Vault as single source of truth

**Decision:** Obsidian vault with YAML frontmatter + WikiLinks as primary storage.
**Rationale:** plain-text Markdown is git-friendly, tool-agnostic, and human-readable without special software. Obsidian is a mature editor with graph view, backlinks, and plugin ecosystem.
**Trade-off:** dependency on Watcher to keep SQLite synced; Obsidian is optional (vault works without it).

### ADR-002 — Parallel hybrid search

**Decision:** parallel search across 7+ backends/organs (UMC, NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem — see §2.6) with cross-backend fusion and dedup via `sinapse_query`/Context Fusion. K7 `RetrievalRouter` (§26) adds intent classification before fusion.
**Rationale:** FTS5 finds exact terms; vectors find similar concepts; graph finds connections; filesystem guarantees fresh writes (zero gap). No single backend covers all cases.
**Trade-off:** slightly higher I/O use; mitigated by circuit breaker (30s cooldown after 3+ failures) and optional rerank (§31.1).

### ADR-003 — MCP as universal integration protocol

**Decision:** expose tools through MCP stdio instead of building agent-specific plugins.
**Rationale:** MCP is an open standard adopted by Anthropic, OpenAI, GitHub, and community. One server (`sinapse-mcp.py`) serves all agents without adaptation.
**Trade-off:** less automatic integration (hooks) than native plugins; compensated by CLI and external hooks (SessionStart, PostToolUse, Stop).

### ADR-004 — Atomic writes via os.replace()

**Decision:** `tempfile.mkstemp()` + `os.replace()` instead of `open().write()`.
**Rationale:** `os.replace()` is atomic on Linux (rename(2) syscall) — if process dies during write, target file stays intact (tmp becomes orphan, not target).
**Trade-off:** slightly more complex; justified for persistent memory data.

### ADR-005 — Cloud Memory API (FastAPI :37702)

**Decision:** lightweight FastAPI REST microservice protected by Bearer token for VPS deployment.
**Rationale:** allows local agents to use VPS-hosted memory without local physical vault. Fail-closed: does not start without `HIVE_MIND_API_KEY`.
**Trade-off:** requires stable network; automatic fallback to local mode when `cloud.enabled=false`.

### ADR-006 — Pydantic structured output in Dream Cycle

**Decision:** all LLM calls use JSON Schema derived from Pydantic models; response validated with `model_validate_json()`.
**Rationale:** ensures any provider (local Ollama or cloud Anthropic) returns processable structure; feedback loop (Validator rejects → Distiller reprocesses) improves quality without human intervention.
**Trade-off:** adds one LLM validation call per pipeline execution.

### ADR-007 — UUID v4 in all PKs

**Decision:** migrate sequential IDs to UUID v4 in all UMC tables.
**Rationale:** sequential IDs collide across machines in P2P scenario (A and B both create `id=1`). UUID v4 collision probability is 1 in 10^36.
**Trade-off:** less readable IDs in logs; irrelevant for programmatic use.

### ADR-008 — Quarantine instead of discard

**Decision:** failing pipeline sets `archived=2` instead of deleting or ignoring observation. Extended by ADR-016: transient error becomes `archived=0` (retry), structural error becomes `archived=2` (quarantine with reason).
**Rationale:** memory data is valuable; transient failures (network down, API credit zero) should not cause permanent context loss.
**Trade-off:** quarantined data accumulation requires periodic manual/automated cleanup via `forget()` (§31.2).

### ADR-009 — Per-role LLM config with inheritance and explicit fallback

**Decision:** each LLM-consuming role (`dreamer`, `graphify`, `vision`, `synthesis`, and K5 five cadence roles) has own config via `HIVE_{ROLE}_PROVIDER/MODEL`, inheriting from Dreamer when absent, with **opt-in** fallback via `HIVE_{ROLE}_FALLBACK_PROVIDER/MODEL`. Resolution centralized in `get_role_config()` (`core/auth.py`); calls and retry/fallback policy centralized in `core/llm_client.py`.
**Rationale:** roles have opposite profiles — entity extraction (many cheap frequent calls) and dialectical synthesis (few high-reasoning calls) cannot be served by same model without waste or quality loss. **Automatic provider cascade was rejected** to preserve user sovereignty: Dialectical Synthesis decides memory truth and cannot switch model silently. Fallback only exists when explicitly configured by user. **Pydantic validation failure never triggers fallback** — it is output quality, not availability; blind model switching would mask issue. API keys remain one per provider (never per role), avoiding secret duplication.
**Trade-off:** more environment variables (up to 16 with fallbacks); mitigated by inheritance — minimal case remains 2 vars (`HIVE_DREAMER_PROVIDER/MODEL`).

### ADR-010 — Layered Knowledge Promotion Pipeline (K3/K4)

**Decision:** split promotion into **Knowledge Intake** (normalize/classify/dedup) and **Promotion Layer** (Distiller → Validator → Router → Persistence → Indexing), implemented in `core/knowledge/intake.py` and `core/knowledge/promotion.py`. Canonical claude-mem bridge in `core/knowledge/claude_mem_bridge.py` (read-only SQL path accepting `source_id` and time window).
**Rationale:** previous Dream Cycle did everything in one stage; splitting intake/promotion makes promotion **idempotent**, **testable** without real LLM, and exposes `candidate-only` mode (output `candidate` without persistence) for orchestration. Promotion is never 1-to-1 — it is batch with queue and workspace priority (§30.5). Canonical knowledge types (§27.2) and automatic/forbidden promotion rules (§27.3) become contract, not heuristic.
**Trade-off:** more upfront code; mitigated by `KnowledgePromotionPipeline` return in `candidate-only` mode for callers not persisting.

### ADR-011 — Separate canonical vector collections (K1)

**Decision:** `VectorBackend` operates on **seven canonical collections** — `memory_vectors`, `observation_vectors`, `document_vectors`, `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors` — each with canonical metadata (`parent_id`, `parent_type`, `brain_lobe`, `knowledge_type`, `project`, `source_uri`, `hash`, `valid_at`, `workspace_id`). Official backends: `sqlite_vec` (local/dev/offline) and `milvus` (production).
**Rationale:** one "everything" collection pollutes ranking and makes per-type coverage impossible. Separation enables production gate per collection (§28), selective pruning (forgetting orphan `document_chunks` does not affect `memory_vectors`), and per-collection embedding-model versioning (§30.4).
**Trade-off:** more UMC tables; mitigated by auxiliary `vector_metadata` and collection identity `(name, embedding_model, dim)`.

### ADR-012 — VectorBackend: single contract, multiple backends

**Decision:** all application vector access uses contract `upsert/delete/query/hybrid_query/count/health`, independent of backend. Milvus, sqlite-vec, and future backend obey same contract. **Application never calls Milvus directly outside contract.**
**Rationale:** switching `sqlite_vec` to `milvus` (and vice versa) becomes config change, not code change. Enables same `DocumentPipeline`, `RetrievalRouter`, and `KnowledgePromotionPipeline` to run in dev (sqlite-vec) and production (Milvus) without branching.
**Trade-off:** contract must remain stable; Milvus schema changes require versioned embedding migration (§30.4).

### ADR-013 — DocumentPipeline with mandatory parent/chunk/citation (K6)

**Decision:** every ingested document becomes one `document_memories` (parent) with `document_chunks` (atoms) and `document_vectors` entries (vectors with canonical metadata). Query returns **auditable citations** (`source_uri`, offsets, parent), not only "best snippet".
**Rationale:** without parent, chunk is loose text — not auditable, deduplicable, or re-ingestable. `document / chunk / vector` separation enables K6 born-large. RAGFlow is adapter/headless, never source of truth; its store is ingestion cache.
**Trade-off:** more metadata per vector; mitigated by auxiliary `vector_metadata` index and fixed Milvus schema.

### ADR-014 — RetrievalRouter classifies intent before searching (K7)

**Decision:** `RetrievalRouter` (`core/retrieval/router.py`) is query entrypoint; it classifies intent, chooses specialized route (temporal, memory, document, code, graph, multi-hop, hybrid), and returns `retrieval_path`, `citations`, `confidence`, `missing_context`. LlamaIndex is optional rerank adapter only; it does not choose route or become source of truth.
**Rationale:** `sinapse_query` fuses 7 organs without intent understanding — good for broad search, weak for precision. Router explicitly routes "decision" to `memory_vectors`, "document" to `document_vectors`+parent, "code" to `code_vectors`+Graphify, etc. `query_route_distribution` telemetry (query hash, not text) feeds K8 health metric.
**Trade-off:** intent classifiers can fail; mitigated by fallback to `sinapse_query`/Context Fusion on low confidence, and `intent_accuracy` metric in golden set (§31.3).

### ADR-015 — Workspace as isolation boundary (K8/§30)

**Decision:** every critical UMC table (`neurons`, `observations`, `synapses`, `goals`, `document_memories`, `visual_memories`, `ambiguities`, `causal_edges`, `vault`) carries `workspace_id` (default `'default'`). Every `RetrievalRouter` and promotion query filters by `workspace_id`. Milvus uses `partition_key=workspace_id` for partition isolation.
**Rationale:** Hive-Mind starts single-user local-first, but product is open-source with per-install scale vector, multi-user per instance, and federation across instances. Adding `workspace_id` later would require structural migration — now it is a column. Cross-workspace leak is a security bug, not ranking issue.
**Trade-off:** every query must carry `workspace_id`; mitigated by `(workspace_id, ...)` hot indexes and default `'default'` (no impact to single-user).

### ADR-016 — Promotion failure preserves data, never discards

**Decision:** promotion contract explicitly distinguishes transient error (`archived=0`, future retry) and structural error (`archived=2`, quarantine with reason). Nothing is deleted by promotion failure. `Knowledge Intake` (K3) is first layer using this contract; `Promotion Layer` (K4) enforces it.
**Rationale:** memory data is valuable; transient failures (network down, API credit zero, new schema) should not cause permanent loss. Normative contract is fail-safe, not fail-silent.
**Trade-off:** quarantine accumulation; mitigated by `K8 knowledge_health` exposing `observations_pending` and `discoveries_pending` as gate, and manual/automatic reprocessing pipeline.

### ADR-017 — Hierarchical session→yearly cadence with dedicated LLM roles

**Decision:** temporal memory is organized in **five cadences** (session, daily, weekly, monthly, yearly) with own writers, inputs, outputs, models, and promotion rules. Each cadence has configurable LLM role (`session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer`, `yearly_synthesizer`) and inherits from `dreamer` if no override. Fail-closed: role without own model and no inheritance logs auditable failure and does not invent synthesis.
**Rationale:** monthly/yearly produce strategic memory (goals, drift, principles) that cannot be generated by small model without quality loss. Session/daily can use small model because task is local compression. Cost/quality by cadence is the correct design.
**Trade-off:** more roles to configure; mitigated by `setup-brain` inheritance from `dreamer` in minimal case.

### ADR-018 — Negative vendoring contract via `components.lock.json`

**Decision:** `components.lock.json` accepts only source **clones** built/patched by `install.sh` (`graphify`, `neural-memory`, `rtk`, `omniparser`, `crsqlite` binary). Wrappers (Milvus, RAGFlow, Graphiti) enter through container/SDK; pip covers only LlamaIndex and utilities. If Milvus, RAGFlow, or LlamaIndex appear in `components.lock.json` for this front, implementation is wrong.
**Rationale:** explicit clone vs wrapper rules reduce operational ambiguity. Contract is also negative (declares what **does not** belong there) to prevent regression.
**Trade-off:** lock-file maintenance; mitigated by generation from `install.sh` and PR review.

### ADR-019 — Model Gateway as an opt-in layer in front of `core/llm_client.py` (Priority 1)

**Decision:** `core/model_gateway.py` + `core/model_registry.py` route LLM calls by role/capability (structured output, tools, vision, embeddings, rerank, cost, health) across `native` (the existing `core/llm_client.py` role config), and OpenAI-compatible backends (LM Studio, llama.cpp, vLLM, SGLang, LiteLLM proxy — one shared adapter class). Gated by `MODEL_GATEWAY_ENABLED` (default `false`): `call_llm_with_fallback` checks the flag first and, when off, runs the exact pre-existing code path unchanged. See [`14-model-gateway.md`](14-model-gateway.md).
**Rationale:** new inference backends should be addable via `config/model-gateway.yaml`, not by touching call sites; explicit fallback (never silent success) and redacted telemetry keep the same operational guarantees as the legacy path.
**Trade-off:** a second selection/config layer to maintain alongside `get_role_config()`/`core/auth.py`; mitigated by making the gateway strictly additive and fail-open to the legacy path on any failure.

---

*This section consolidates ADRs inherited from v2.0.0 (001–009), ADRs created by Born-Large Knowledge front (010–018), and Priority 1 (019). In case of divergence, this canonical section prevails over [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md).*