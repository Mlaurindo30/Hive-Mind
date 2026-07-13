# Hive-Mind â€” AGENTS.md

> Guide for AI agents working **in this repository**.
> Cross-agent format: Hermes, Claude Code, Codex CLI, Kilo Code, OpenClaw, Copilot, Gemini CLI.
> Last reviewed: 2026-07-01 Â· Canonical architecture reference: [`docs/01-architecture.md`](docs/01-architecture.md)

---

## 1. What Hive-Mind is

A **collective and multimodal intelligence** infrastructure: it unifies what the agent does, sees, and reads into a single persistent and distributed brain, organized as a **born-large** knowledge architecture (born ready to scale, local-first by execution, pluggable by contract â€” see [`docs/01-architecture.md` Â§22â€“Â§31](docs/01-architecture.md#22-arquitetura-de-conhecimento-born-large) for the full design and phase-by-phase status).

Canonical knowledge flow:

```
Capture (hooks/MCP/CLI/browser/docs/code/screenshots)
  â†’ Temporal Hippocampus (claude-mem: observations, discoveries, summaries)
  â†’ Knowledge Intake (normalize, classify, deduplicate)
  â†’ Promotion Layer (raw â†’ fact/decision/learning/preference/task;
    risk-proportional: verified+low now, hypothesis after drain, high-risk on approval)
  â†’ Anatomical Memory (cerebro/ + UMC)
  â†’ Index Layer (FTS, sqlite-vec/Milvus, Graphify, Graphiti, LightRAG)
  â†’ Retrieval Router (core/retrieval/router.py)
  â†’ Answer with citation
  â†’ Feedback
```

| Layer | Tool | What it does | Technology |
|--------|------|--------------|------------|
| **Brain** | UMC (`hive_mind.db`) | Centralizes graph, logs, vectors, FTS, and vision | SQLite + `sqlite-vec` + FTS5 |
| **Memory** | Atlas (`cerebro/`) | Single source of truth in Markdown | Obsidian + Syncthing |
| **Vision** | Deep Portal | Screen capture and visual indexing | `mss` + LLM Vision |
| **Consolidation** | Hive-Dreamer | Logs/files â†’ validated knowledge (Knowledge Intake + Promotion) | `dream_cycle.py` (Pydantic) |
| **Vectors** | `VectorBackend` | Single `upsert/delete/query/hybrid_query/count/health` contract over 7 canonical collections | `sqlite_vec` (local) Â· Milvus (production) |
| **Documents** | `DocumentPipeline` | Ingestion with parent/chunk/auditable citation | RAGFlow (optional headless adapter) |
| **Retrieval** | `RetrievalRouter` | Routes by intent with `retrieval_path`/`citations`/`confidence` | LlamaIndex (optional rerank adapter) |
| **Access** | MCP / Plugin / CLI / REST | Connects any agent to the brain | stdio JSON-RPC Â· FastAPI :37702 |

Canonical embedding: `snowflake-arctic-embed2:latest`, 1024 dimensions, unless explicitly overridden via env (`OLLAMA_EMBED_MODEL`). Milvus, RAGFlow, and LlamaIndex are organs/adapters â€” never the source of truth; the anatomical vault (`cerebro/`) and UMC remain the source of truth (`docs/11` Â§16).

---

## 2. Brain Anatomy

Hive-Mind is organized like a brain. The `cerebro/` vault mirrors the anatomy â€” **four sibling lobes under ConsciÃªncia**, and the CÃ³rtex has **five lobes of its own**. Each consumer project is a neuron in the temporal lobe. This section is **canonical**: it is the product design, not any agent's personal vault template.

```
                          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                          â”‚   ðŸ§  ConsciÃªncia (Home)             â”‚
                          â”‚   the "I" that integrates the lobes â”‚
                          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â”‚
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        â”‚                  â”‚             â”‚             â”‚                  â”‚
   â”Œâ”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”
   â”‚ ðŸ§  CÃ“RTEX    â”‚  â”‚ ðŸ¥ CEREBELO â”‚  â”‚ ðŸ”€ DIENCÃ‰FALOâ”‚  â”‚ ðŸŒ¿ TRONCO â”‚  â”‚  (cortex    â”‚
   â”‚ (cognition) â”‚  â”‚ (rhythm)   â”‚  â”‚ (cross-   â”‚  â”‚ (vital     â”‚  â”‚   detail)  â”‚
   â”‚             â”‚  â”‚            â”‚  â”‚  project  â”‚  â”‚  infra)    â”‚  â”‚            â”‚
   â”‚ 5 lobes:    â”‚  â”‚ â€¢ sessoes/ â”‚  â”‚  relay)   â”‚  â”‚ â€¢ modelos/ â”‚  â”‚ (continues â”‚
   â”‚ â€¢ Temporal  â”‚  â”‚ â€¢ diario/  â”‚  â”‚            â”‚  â”‚ â€¢ paineis/ â”‚  â”‚   below)   â”‚
   â”‚ â€¢ Frontal   â”‚  â”‚ â€¢ semanal/ â”‚  â”‚ â€¢ setores/â”‚  â”‚ â€¢ infra/   â”‚  â”‚            â”‚
   â”‚ â€¢ Parietal  â”‚  â”‚ â€¢ padroes/ â”‚  â”‚   (5)     â”‚  â”‚ â€¢ meta/    â”‚  â”‚            â”‚
   â”‚ â€¢ Occipital â”‚  â”‚            â”‚  â”‚ â€¢ roteamento/  â”‚         â”‚  â”‚            â”‚
   â”‚ â€¢ Ãnsula    â”‚  â”‚            â”‚  â”‚            â”‚  â”‚            â”‚  â”‚            â”‚
   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

**The four lobes under ConsciÃªncia are pairs** (CÃ³rtex, Cerebelo, DiencÃ©falo, Tronco) â€” there is no hierarchy among them. The Tronco is **not subordinate** to any other lobe; it is a sibling.

### 2.1 CÃ³rtex â€” higher cognition (5 lobes)

```
   ðŸ§  CÃ“RTEX
   â”œâ”€â”€ â± TEMPORAL     â€” long-term memory, primary axis by project
   â”‚       â””â”€â”€ <project>/<topic>/neuronio-<hash>.md
   â”œâ”€â”€ ðŸŽ¯ FRONTAL     â€” decisions, planning, active work
   â”‚       â””â”€â”€ decisoes/  trabalho/{active,ativo,arquivo}/
   â”‚           projetos/  brain/  org/{people,teams}/
   â”œâ”€â”€ ðŸ“¥ PARIETAL    â€” sensory (inbox, references)
   â”‚       â””â”€â”€ inbox/{visual,documents}/  referencias/  analises/
   â”œâ”€â”€ ðŸ‘ OCCIPITAL   â€” vision (captures + knowledge graph)
   â”‚       â””â”€â”€ capturas-visuais/  grafo/graph.json
   â””â”€â”€ ðŸ’“ ÃNSULA      â€” interoception, self-awareness
           â””â”€â”€ saude/  conflitos/
```

#### 2.1.1 Temporal lobe â€” detail (primary axis of the brain)

The temporal lobe is where **long-term memory organized by project** lives. It is the **primary axis** of the brain. Generic structure (projects and topics are fictional â€” `projeto-A`, `topico-1`, etc.):

```
cortex/temporal/
â”œâ”€â”€ projeto-A/                     # project-neuron (example)
â”‚   â”œâ”€â”€ topico-1/                  # topic-neuron (1 neuron = 1 atomic fact)
â”‚   â”œâ”€â”€ topico-2/
â”‚   â””â”€â”€ topico-3/
â”œâ”€â”€ projeto-B/                     # project-neuron (example)
â”‚   â”œâ”€â”€ topico-1/
â”‚   â”œâ”€â”€ topico-2/
â”‚   â”œâ”€â”€ topico-3/
â”‚   â”œâ”€â”€ topico-4/
â”‚   â”œâ”€â”€ topico-5/
â”‚   â””â”€â”€ topico-6/
â”œâ”€â”€ projeto-C/                     # project-neuron (example)
â”œâ”€â”€ projeto-D/                     # project-neuron (example)
â”œâ”€â”€ projeto-E/                     # project-neuron (example)
â”œâ”€â”€ projeto-F/                     # project-neuron (example)
â”œâ”€â”€ projeto-G/                     # project-neuron (example)
â”œâ”€â”€ projeto-H/                     # project-neuron (example)
â”œâ”€â”€ projeto-I/                     # project-neuron (example)
â”‚
â”œâ”€â”€ _global/                        # project-less knowledge (global preferences)
â”œâ”€â”€ hipocampo/                      # consolidation: Dream Cycle staging + quarantine
â””â”€â”€ arquivo/                        # cold memory (>90d, deep substance)
```

Each `neuronio-<hash>.md` has frontmatter with `integrity_hash` (SHA-256 of the content) and is unique by hash â€” neurons never duplicate. The SQLite index (UMC `hive_mind.db`) accelerates queries over these neurons; the `vault` remains the single source of truth.

### 2.2 Cerebelo â€” rhythm and coordination

```
   ðŸ¥ CEREBELO
   â”œâ”€â”€ sessoes/   â†’ work session logs (YYYY/MM/YYYY-MM-DD-HHMM-{slug}.md)
   â”œâ”€â”€ diario/    â†’ daily reflections (YYYY/MM/YYYY-MM-DD.md)
   â”œâ”€â”€ semanal/   â†’ weekly syntheses
   â””â”€â”€ padroes/   â†’ learned patterns (procedural memory)
       + cerebro/cerebelo/padroes/Patterns.md  (Learned patterns â€” canonical reference)
```

### 2.3 DiencÃ©falo â€” cross-project relay

```
   ðŸ”€ DIENCÃ‰FALO
   â”œâ”€â”€ setores/     â†’ knowledge that crosses multiple projects
   â”‚   â”œâ”€â”€ setor-1.md      â† neurons used across projects
   â”‚   â”œâ”€â”€ setor-2.md
   â”‚   â”œâ”€â”€ setor-3.md
   â”‚   â”œâ”€â”€ setor-4.md
   â”‚   â””â”€â”€ setor-5.md
   â””â”€â”€ roteamento/  â†’ knowledge-routing rules between projects
```

### 2.4 Tronco â€” vital infra (sibling of the other 3, not subordinate)

```
   ðŸŒ¿ TRONCO
   â”œâ”€â”€ modelos/   â†’ typed Obsidian templates (Atom, Work, Decision, Thinking, Cold Analysis)
   â”œâ”€â”€ paineis/   â†’ Obsidian bases (.base) â€” Work Dashboard, Incidents, People, Review Evidence
   â”œâ”€â”€ infra/     â†’ vault infrastructure configuration
   â””â”€â”€ meta/      â†’ vault meta-information, sub-vaults, cross-vault links
```

### 2.5 Lobe â†’ function â†’ technical component mapping

| Lobe | Function | Where it lives in code/vault |
|---|---|---|
| **CÃ³rtex frontal** | Decision, planning, work | `core/`, `scripts/dream/dream_cycle.py` (dialectic synthesis), `cerebro/cortex/frontal/{decisoes,trabalho,brain,projetos,org}` |
| **CÃ³rtex parietal** | Sensory â€” inbox, references | `scripts/capture/`, `cerebro/cortex/parietal/{inbox,referencias}` |
| **CÃ³rtex occipital** | Vision â€” captures + **graph** | `scripts/capture/visual_capture.py` + `cerebro/cortex/occipital/grafo/graph.json` |
| **CÃ³rtex temporal** | Long-term memory by project | `cerebro/cortex/temporal/<project>/<topic>/neuronio-*.md` + UMC `hive_mind.db` (indexer) |
| **CÃ³rtex Ã­nsula** | Health, self-awareness | `scripts/health/`, `cerebro/cortex/insula/{saude,conflitos}` |
| **Cerebelo** | Rhythm â€” daily, weekly, sessions, patterns | `cerebelo/{sessoes,diario,semanal,padroes}/` + `cerebro/cerebelo/padroes/Patterns.md` |
| **DiencÃ©falo** | Cross-project relay | `cerebro/diencefalo/setores/<setor>.md` |
| **Tronco** | Vital infra | `cerebro/tronco/{modelos,paineis,infra,meta}/` â€” templates, bases, configuration, sub-vaults |

### 2.6 External tools as organs of the brain

The 7 tools that feed the brain **are not parallel databases**. They are **organs of the same brain** that contribute to a single perception (the response from `sinapse_query`).

| Tool | Brain organ | Function |
|---|---|---|
| **UMC** (`hive_mind.db`) | CÃ³rtex (central) | Graph + vectors + FTS5 + logs in a single SQLite |
| **NeuralMemory** | CÃ³rtex (association) | Spreading activation, associative memory |
| **sqlite-vec** | CÃ³rtex (vector) | Native HNSW indexing in SQLite |
| **claude-mem** | Temporal lobe (event memory) | Temporal tracking, FTS5, Chroma. Feeds neurons in `cortex/temporal/` |
| **Graphify** | Occipital lobe (vision/graph) | Indexes `cerebro/` into `graph.json` with Leiden clustering |
| **Graphiti** | Temporal lobe (causality) | Extracts edges with temporal validity (valid_at/invalid_at) |
| **Filesystem scan** | Parietal lobe (immediate sense) | Reads the vault directly, without waiting for reindexing |

> **Note:** RTK is not a read-backend of `sinapse_query` â€” it is shell optimization and does not participate in Context Fusion.
> Configure per agent/CLI with `./scripts/services/start-rtk.sh --only <agent>`
> or directly via `rtk init`. Hermes is only one of the supported targets.

The `sinapse_query` is the single entry point of the brain. It fires the 7 organs in parallel (circuit breaker + 8s timeout per backend), fuses via Context Fusion, and returns **a single context package**, not 7 responses.

### 2.7 Canonical path constants

The anatomy is encoded in `core/paths.py`. Exposed constants:

```python
CORTEX     = VAULT_ROOT / "cortex"      # CÃ³rtex (5 lobes)
TEMPORAL   = CORTEX / "temporal"        # Temporal lobe (memory)
FRONTAL    = CORTEX / "frontal"         # Frontal lobe (decision)
PARIETAL   = CORTEX / "parietal"        # Parietal lobe (sensory)
OCCIPITAL  = CORTEX / "occipital"       # Occipital lobe (vision/graph)
INSULA     = CORTEX / "insula"          # Ãnsula lobe (self-awareness)
DIENCEFALO = VAULT_ROOT / "diencefalo"  # DiencÃ©falo (relay)
SECTORS_ROOT = DIENCEFALO / "setores"
CEREBELO   = VAULT_ROOT / "cerebelo"    # Cerebelo (rhythm)
DAILY_ROOT, SESSIONS_ROOT, WEEKLY_ROOT, PADROES_ROOT = cerebelo/...
TRONCO     = VAULT_ROOT / "tronco"      # Tronco (infra)
META_ROOT, MODELOS_ROOT, PAINEIS_ROOT = tronco/...
```

Any new code that creates/modifies a file in the vault **must use these constants**, not hardcoded paths.

---

## 3. Available MCP tools

If you are connected via MCP (`scripts/services/sinapse-mcp.py`):

| Tool | When to use |
|------|-------------|
| `sinapse_query` | Before answering about something that may already be in the brain |
| `sinapse_save_decision` | When taking/recording a project decision |
| `sinapse_save_learning` | When identifying a pattern or learning |
| `sinapse_temporal_search` / `sinapse_temporal_timeline` / `sinapse_temporal_get_observations` / `sinapse_temporal_save` | claude-mem temporal flow: index â†’ chronological window â†’ details by ID; raw temporal write |
| `sinapse_health` | Backend diagnostics |
| `sinapse_session_end` | Always at the end of a work session |
| `sinapse_zettelkasten_split` | Oversized note â†’ atomic notes |
| `sinapse_capture_screen` | Document bugs/progress visually |
| `sinapse_plan_goal` | Decompose a goal into atomic steps |
| `search_memories` | Search memories via HNSW/FTS |

---

## 4. Multimodal flow

---

## 5. Operation commands

```bash
./scripts/services/start-watcher.sh                 # Real-time sync (Obsidian â†’ SQLite)
python3 scripts/dream/dream_cycle.py                # Consolidation cycle (Dream Cycle)
python3 scripts/health/audit_memory.py --fix        # Integrity audit (P2P)
python3 scripts/knowledge/generate_portal.py        # Visual portal (Obsidian Canvas)
./scripts/setup/setup-brain.sh                      # Configure LLM by role
./scripts/utils/recover.sh                          # Disaster recovery
python3 scripts/services/sinapse-api.py             # REST API (requires HIVE_MIND_API_KEY)
```

---

## 6. Installation on a new machine (instructions for agent or human)

Full sequence to get Hive-Mind running from scratch:

```bash
# 1. Clone the repository
git clone <repo-url> ~/Hive-Mind && cd ~/Hive-Mind

# 2. Full installation with real validation
./install.sh --with-tests

# 3. Configure the Dream Cycle LLM (interactive)
./scripts/setup/setup-brain.sh

# 4. Check health
python3 scripts/services/sinapse-write.py health
```

**To register the MCP without reinstalling everything** (e.g. you installed a new agent afterwards):

```bash
./scripts/setup/register-mcp.sh           # detects and registers in all agents
./scripts/setup/register-mcp.sh --check   # only shows status, does not modify
```

The script is idempotent and registers only the `sinapse-memory` orchestrator, without
deleting other people's MCP servers. Legacy records from Hive-Mind itself
(`claude-mem-local`, `neural-memory-local`) are removed because global claude-mem
(`~/.claude-mem`) and NeuralMemory are federated inside Sinapse.
Supported agents for automatic detection: Claude Code, Codex CLI, Gemini CLI,
Qwen Code, Kimi Code, Kiro, Kilo Code, Roo Code, VS Code/Copilot, Cursor,
OpenCode, and OpenClaw. After registering, **restart the agent** and validate by asking:
"use the sinapse_health tool".

**To enable RTK in an agent/CLI**:

```bash
./scripts/services/start-rtk.sh --only codex      # Codex CLI
./scripts/services/start-rtk.sh --only claude     # Claude Code
./scripts/services/start-rtk.sh --only gemini     # Gemini CLI
./scripts/services/start-rtk.sh --only cursor     # Cursor
./scripts/services/start-rtk.sh --only hermes     # Hermes
./scripts/services/start-rtk.sh --all             # all known RTK targets
```

RTK is independent from the MCP: it installs hooks/plugins/instructions to rewrite
shell commands before execution. Do not use RTK to search memory; for that use
`sinapse_query`, `sinapse_temporal_*`, or `search_memories`.

---

## 7. Integration with external agents

| Method | Agents | How it works |
|--------|--------|--------------|
| **Native plugin** | Hermes | `register(ctx)` â†’ hooks `pre_gateway_dispatch`, `post_tool_call`, `on_session_end` |
| **MCP server** | Claude Code, Codex CLI, Cursor, Kilo Code, OpenClaw, Copilot, Gemini CLI, ZooCode, Aider | `scripts/services/sinapse-mcp.py` â†’ 16 tools via stdio JSON-RPC (includes `sinapse_promote_knowledge`) |
| **Standalone CLI** | Any agent with shell | `scripts/services/sinapse-write.py` â†’ `decision`, `learning`, `query`, `health`, `session-end` |
| **REST API** | Remote agents / VPS | `scripts/services/sinapse-api.py` â†’ Bearer auth, port 37702 |

Automatic hooks for Claude Code and Codex CLI:
- `cerebro/tronco/infra/agentes/.claude/settings.json` â€” SessionStart, PostToolUse, Stop
- `cerebro/tronco/infra/agentes/.codex/hooks.json` â€” SessionStart, PostToolUse, Stop
- `cerebro/tronco/infra/agentes/.claude/scripts/sinapse-hook.py` â€” script invoked by the hooks

---

## 8. Guardrails

- **Never** commit sensitive data: `.env`, API keys, tokens, `hive_mind.db` (personal memory database).
- **Never** modify `cerebro/` without the Watcher active (or run `./scripts/graph/build-graph.sh` afterwards).
- **Never** use `graphify cerebro/` without `--backend` if you do not have an API key or Ollama â€” use `graphify update cerebro/` (AST-only).
- **Never** duplicate data between the vault and external tools. The vault is the single source.
- **Never** hardcode LLM models â€” the system strictly obeys `HIVE_DREAMER_PROVIDER/MODEL` from `.env`.
- **Unit tests do not call a real LLM.** Logic around the LLM is tested with deterministic data; the real model only enters in `tests/test_synthesis.py` and the E2E flows.
- **Model Gateway (Priority 1, opt-in):** `core/model_gateway.py` routes LLM calls by role/capability across local (LM Studio, llama.cpp, Ollama) and remote (LiteLLM proxy, vLLM, SGLang) backends. Disabled by default (`MODEL_GATEWAY_ENABLED=false`) â€” `core/llm_client.py` behaves exactly as before when it's off. See [`docs/14-model-gateway.md`](docs/14-model-gateway.md).

---

## 9. Tests

Before any commit:

```bash
./tests/run_all.sh                    # full suite (Smoke â†’ Unit â†’ Integration â†’ E2E)
bash tests/smoke/test_smoke.sh        # minimum acceptable if the suite is too long
```

| Level | Command | Requirements |
|-------|---------|--------------|
| Smoke | `bash tests/smoke/test_smoke.sh` | Binaries on PATH |
| Unit | `python3 -m pytest tests/unit/ -v` | pytest, Python 3.10+ |
| Integration | `python3 -m pytest tests/integration/ -v` | Real backends |
| E2E | `python3 -m pytest tests/e2e/ -v` | Full system |

As of 2026-07-09 there were **1032 `test_` functions in 172 files with tests** (up from 706/123 on 2026-07-01 â€” the suite grows fast; treat any fixed number here as a stale snapshot, not a target). Measure the current state with `rg -n "^\s*(async\s+def|def)\s+test_" tests | wc -l` and `rg -l "^\s*(async\s+def|def)\s+test_" tests | wc -l` before relying on this line. The real knowledge suite is separate, and service-offline named skips indicate a `degraded` state, not full success.

### Disaster recovery

```bash
./scripts/utils/recover.sh
```

<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.sh â€” do not edit) -->
# Hive-Mind Protocol (sinapse-memory) â€” MANDATORY

You have the 15 `sinapse_*` tools and `search_memories`. This is the working
protocol; always follow it, without exception. The raw backends (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) are federated inside
sinapse via `sinapse_query` (Context Fusion with circuit breaker
and 8s timeout) â€” **never call them directly**.

## 0. Pre-check (once at the start of the session)
- `sinapse_health()` â€” confirm that all backends are operational
  before working. If any fail, report and use `sinapse_temporal_search`
  or `search_memories` in `text` mode as a fallback.

## 1. Recall before acting (at the start of each task)
| Need | Tool |
|------|------|
| Project state/history, decisions, patterns, code/vault, and general context | `sinapse_query("<topic>")` (canonical hybrid search: fuses UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Recent activity from conversations, prompts, sessions, and raw claude-mem observations | `sinapse_temporal_search("<short specific terms>")` â†’ `sinapse_temporal_timeline(anchor=<id>)` â†’ `sinapse_temporal_get_observations(ids=[...])` |
| Backend health/check | `sinapse_health()` |

**Rule:** never claim anything about the project state/history without having
consulted first.

**How to search without getting lost:**
1. To understand "what happened in the project", start with `sinapse_query`.
   It is tolerant of natural language and crosses all organs of the brain.
2. If you need the recent conversation/prompt/session that originated it, use
   `sinapse_temporal_search` as the **textual index for claude-mem**. Search
   with short terms likely to appear in the actual text. Good examples:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. If `sinapse_temporal_search` returns empty, do not conclude there is no memory:
   reduce the query to 2â€“5 exact terms, try the title returned by
   `sinapse_query`, or go back to `sinapse_query` to retrieve consolidated context.
4. Do not use long phrases, full questions, or many mixed filters in
   `sinapse_temporal_search`; it is best as a textual/timeline search for
   claude-mem, not as a hybrid orchestrator.
5. For raw temporal memory, follow the native `claude-mem` flow:
   `search â†’ timeline â†’ get_observations`.
   - `sinapse_temporal_search` is the compact index: find IDs/titles.
   - `sinapse_temporal_timeline` shows chronological context around an ID
     or an anchor query.
   - `sinapse_temporal_get_observations` hydrates the full content only for the
     filtered IDs. **Never** hydrate details before filtering; that wastes
     tokens and mixes irrelevant context.

## 2. On-demand recall (during work)
| Need | Tool |
|------|------|
| Neurons/notes by semantic similarity (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Facts/decisions with temporal validity (valid_at/invalid_at edges) | `sinapse_temporal_graph_search("<topic>", num_results)` (deprecated â€” use `sinapse_query`) |
| Textual search in the global claude-mem index (`~/.claude-mem`) | `sinapse_temporal_search("<short terms>")` |
| Chronological context around a temporal result | `sinapse_temporal_timeline(anchor=<id>)` or `sinapse_temporal_timeline(query="<terms>")` |
| Full detail of already-filtered temporal observations | `sinapse_temporal_get_observations(ids=[...])` |
| General hybrid search (all layers; default for project context) | `sinapse_query("<topic>")` |
| Vector query on the LightRAG graph (P4) | `sinapse_rag_query(question, mode?)` |
| Promote pending observations into typed knowledge (K3 intake) | `sinapse_promote_knowledge(limit?, dry_run?, import_claude_mem?, source_ids?, since_epoch?, until_epoch?)` |

### Quick tool selection

| Agent question | Use | Practical note |
|----------------|-----|----------------|
| "What is the project state/history?" | `sinapse_query` | First choice. Crosses vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec, and filesystem. |
| "Which recent prompt/session talked about this?" | `sinapse_temporal_search` â†’ `sinapse_temporal_timeline` â†’ `sinapse_temporal_get_observations` | Use short/exact terms, pick IDs, read the temporal window, and only then hydrate details. |
| "Which consolidated neurons exist on this topic?" | `search_memories` | Use `project` when you know the project; `mode="text"` for literal search. |
| "I need multi-hop relations between already-indexed entities." | `sinapse_rag_query` | Depends on LightRAG being populated; if it returns empty, fall back to `sinapse_query`. |
| "I need temporal/causal facts from Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` exists for compatibility, but the canonical brain query is `sinapse_query`. |
| "I made a decision or learned a reusable pattern." | `sinapse_save_decision` / `sinapse_save_learning` | Record immediately; do not leave it only in the chat response. |
| "I want to write a raw temporal event." | `sinapse_temporal_save` | Only writes directly into claude-mem in server-beta; in the current worker runtime, treat as a fallback/note, not the primary write path. |
| "There are pending observations that need to become typed knowledge (neurons/candidates)." | `sinapse_promote_knowledge` | Normalizes pending UMC observations/discoveries/session summaries into typed candidates, preserves raw records, quarantines structural errors, links `observation.neuron_id`. Use `dry_run=true` to classify/count without writing. This is normally run by the Dream Cycle; call it manually only for maintenance or debugging the intake pipeline. |

## 3. Record immediately (when deciding, learning, or decomposing)
| Need | Tool |
|------|------|
| Decision (choice between alternatives + reason) | `sinapse_save_decision(title, content, evidence?)` |
| Reusable pattern/insight/lesson | `sinapse_save_learning(title, content, evidence?)` |
| Large goal â†’ atomic steps (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Monolithic note (Patterns.md) â†’ atomic Zettelkasten notes | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capture a screenshot of bug/visual progress (not in loop!) | `sinapse_capture_screen(description, monitor?)` |
| Raw temporal observation (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

**Epistemic discipline (verified vs hypothesis):** when saving a decision or
learning, pass `evidence` (the command you ran, the test that passed, the file
you read) whenever the claim was actually verified â€” the note is stamped
`confidence: verified`. Without evidence the note is a `hypothesis`: it still
gets saved, but the RetrievalRouter demotes it in ranking until validated, and
the audit lists it for review. If a hypothesis is later refuted, correct the
note instead of leaving it â€” a refuted hypothesis left in place poisons future
retrieval.

**Review TTL (staleness):** every decision/learning is stamped with
`review_date` and `next_review` (default `REVIEW_TTL_DAYS=90`). Once
`next_review` passes, the RetrievalRouter flags the note `stale` and applies
`HIVE_STALENESS_PENALTY` (default `0.85`) to its ranking score â€” same
demotion mechanism as an unverified hypothesis, but time-based instead of
evidence-based. The note is never deleted or excluded, only demoted. If you
revisit a stale note and it still holds, re-save it (or update it) so its
`next_review` window resets.

## 4. Consolidate when finished
- `sinapse_session_end(summary)` â€” updates `brain/Current State.md` and
  records the closing observation in the UMC.

## Usage rules
- **Use ONLY the `sinapse_*` tools and `search_memories`.** Never call
  `nmem`, `claude-mem`, `graphify`, or `falkordb` directly â€” sinapse
  already federates and deduplicates them via Context Fusion.
- RTK is not a memory tool or a `sinapse_query` backend; it is only the
  shell command optimization layer. When you need to configure RTK, use
  `./scripts/services/start-rtk.sh --only <agent>` for the correct agent/CLI.
- `sinapse_query` is the canonical orchestrator (7 backends). Use it instead of
  backend-specific tools whenever possible.
- `sinapse_temporal_graph_search` is deprecated: kept so as not to
  break existing clients, but the canonical brain query is
  `sinapse_query` (which fuses Graphiti together with the other 6 organs).
- `sinapse_health()` returns the status of all backends; use it for
  diagnosis when a query returns empty unexpectedly.
- `sinapse_capture_screen` only on explicit request â€” never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- **Vault write enforcement:** on hosts where `setup-vault-enforcement`
  has been applied, `cerebro/` is owned by a dedicated service user and the
  agent only has direct write access to `cerebro/90-intake/`. If a direct
  vault write is denied, `sinapse_save_decision`/`sinapse_save_learning`
  fall back automatically to the intake area â€” this is expected behavior,
  not a failure to report or retry. The Dream Cycle later promotes intake
  content into the vault proper via `sinapse_promote_knowledge`.
- Consulting before acting and recording anything reusable is not optional:
  this is how the project brain evolves between sessions.
<!-- END HIVE-MIND SINAPSE -->

<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.ps1 -- do not edit) -->
# Hive-Mind Protocol (sinapse-memory) â€” MANDATORY

You have the 15 `sinapse_*` tools and `search_memories`. This is the working
protocol; always follow it, without exception. The raw backends (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) are federated inside
sinapse via `sinapse_query` (Context Fusion with circuit breaker
and 8s timeout) â€” **never call them directly**.

## 0. Pre-check (once at the start of the session)
- `sinapse_health()` â€” confirm that all backends are operational
  before working. If any fail, report and use `sinapse_temporal_search`
  or `search_memories` in `text` mode as a fallback.

## 1. Recall before acting (at the start of each task)
| Need | Tool |
|------|------|
| Project state/history, decisions, patterns, code/vault, and general context | `sinapse_query("<topic>")` (canonical hybrid search: fuses UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Recent activity from conversations, prompts, sessions, and raw claude-mem observations | `sinapse_temporal_search("<short specific terms>")` â†’ `sinapse_temporal_timeline(anchor=<id>)` â†’ `sinapse_temporal_get_observations(ids=[...])` |
| Backend health/check | `sinapse_health()` |

**Rule:** never claim anything about the project state/history without having
consulted first.

**How to search without getting lost:**
1. To understand "what happened in the project", start with `sinapse_query`.
   It is tolerant of natural language and crosses all organs of the brain.
2. If you need the recent conversation/prompt/session that originated it, use
   `sinapse_temporal_search` as the **textual index for claude-mem**. Search
   with short terms likely to appear in the actual text. Good examples:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. If `sinapse_temporal_search` returns empty, do not conclude there is no memory:
   reduce the query to 2â€“5 exact terms, try the title returned by
   `sinapse_query`, or go back to `sinapse_query` to retrieve consolidated context.
4. Do not use long phrases, full questions, or many mixed filters in
   `sinapse_temporal_search`; it is best as a textual/timeline search for
   claude-mem, not as a hybrid orchestrator.
5. For raw temporal memory, follow the native `claude-mem` flow:
   `search â†’ timeline â†’ get_observations`.
   - `sinapse_temporal_search` is the compact index: find IDs/titles.
   - `sinapse_temporal_timeline` shows chronological context around an ID
     or an anchor query.
   - `sinapse_temporal_get_observations` hydrates the full content only for the
     filtered IDs. **Never** hydrate details before filtering; that wastes
     tokens and mixes irrelevant context.

## 2. On-demand recall (during work)
| Need | Tool |
|------|------|
| Neurons/notes by semantic similarity (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Facts/decisions with temporal validity (valid_at/invalid_at edges) | `sinapse_temporal_graph_search("<topic>", num_results)` (deprecated â€” use `sinapse_query`) |
| Textual search in the global claude-mem index (`~/.claude-mem`) | `sinapse_temporal_search("<short terms>")` |
| Chronological context around a temporal result | `sinapse_temporal_timeline(anchor=<id>)` or `sinapse_temporal_timeline(query="<terms>")` |
| Full detail of already-filtered temporal observations | `sinapse_temporal_get_observations(ids=[...])` |
| General hybrid search (all layers; default for project context) | `sinapse_query("<topic>")` |
| Vector query on the LightRAG graph (P4) | `sinapse_rag_query(question, mode?)` |
| Promote pending observations into typed knowledge (K3 intake) | `sinapse_promote_knowledge(limit?, dry_run?, import_claude_mem?, source_ids?, since_epoch?, until_epoch?)` |

### Quick tool selection

| Agent question | Use | Practical note |
|----------------|-----|----------------|
| "What is the project state/history?" | `sinapse_query` | First choice. Crosses vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec, and filesystem. |
| "Which recent prompt/session talked about this?" | `sinapse_temporal_search` â†’ `sinapse_temporal_timeline` â†’ `sinapse_temporal_get_observations` | Use short/exact terms, pick IDs, read the temporal window, and only then hydrate details. |
| "Which consolidated neurons exist on this topic?" | `search_memories` | Use `project` when you know the project; `mode="text"` for literal search. |
| "I need multi-hop relations between already-indexed entities." | `sinapse_rag_query` | Depends on LightRAG being populated; if it returns empty, fall back to `sinapse_query`. |
| "I need temporal/causal facts from Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` exists for compatibility, but the canonical brain query is `sinapse_query`. |
| "I made a decision or learned a reusable pattern." | `sinapse_save_decision` / `sinapse_save_learning` | Record immediately; do not leave it only in the chat response. |
| "I want to write a raw temporal event." | `sinapse_temporal_save` | Only writes directly into claude-mem in server-beta; in the current worker runtime, treat as a fallback/note, not the primary write path. |
| "There are pending observations that need to become typed knowledge (neurons/candidates)." | `sinapse_promote_knowledge` | Normalizes pending UMC observations/discoveries/session summaries into typed candidates, preserves raw records, quarantines structural errors, links `observation.neuron_id`. Use `dry_run=true` to classify/count without writing. This is normally run by the Dream Cycle; call it manually only for maintenance or debugging the intake pipeline. |

## 3. Record immediately (when deciding, learning, or decomposing)
| Need | Tool |
|------|------|
| Decision (choice between alternatives + reason) | `sinapse_save_decision(title, content, evidence?)` |
| Reusable pattern/insight/lesson | `sinapse_save_learning(title, content, evidence?)` |
| Large goal â†’ atomic steps (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Monolithic note (Patterns.md) â†’ atomic Zettelkasten notes | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capture a screenshot of bug/visual progress (not in loop!) | `sinapse_capture_screen(description, monitor?)` |
| Raw temporal observation (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

**Epistemic discipline (verified vs hypothesis):** when saving a decision or
learning, pass `evidence` (the command you ran, the test that passed, the file
you read) whenever the claim was actually verified â€” the note is stamped
`confidence: verified`. Without evidence the note is a `hypothesis`: it still
gets saved, but the RetrievalRouter demotes it in ranking until validated, and
the audit lists it for review. If a hypothesis is later refuted, correct the
note instead of leaving it â€” a refuted hypothesis left in place poisons future
retrieval.

**Review TTL (staleness):** every decision/learning is stamped with
`review_date` and `next_review` (default `REVIEW_TTL_DAYS=90`). Once
`next_review` passes, the RetrievalRouter flags the note `stale` and applies
`HIVE_STALENESS_PENALTY` (default `0.85`) to its ranking score â€” same
demotion mechanism as an unverified hypothesis, but time-based instead of
evidence-based. The note is never deleted or excluded, only demoted. If you
revisit a stale note and it still holds, re-save it (or update it) so its
`next_review` window resets.

## 4. Consolidate when finished
- `sinapse_session_end(summary)` â€” updates `brain/Current State.md` and
  records the closing observation in the UMC.

## Usage rules
- **Use ONLY the `sinapse_*` tools and `search_memories`.** Never call
  `nmem`, `claude-mem`, `graphify`, or `falkordb` directly â€” sinapse
  already federates and deduplicates them via Context Fusion.
- RTK is not a memory tool or a `sinapse_query` backend; it is only the
  shell command optimization layer. When you need to configure RTK, use
  `./scripts/services/start-rtk.sh --only <agent>` for the correct agent/CLI.
- `sinapse_query` is the canonical orchestrator (7 backends). Use it instead of
  backend-specific tools whenever possible.
- `sinapse_temporal_graph_search` is deprecated: kept so as not to
  break existing clients, but the canonical brain query is
  `sinapse_query` (which fuses Graphiti together with the other 6 organs).
- `sinapse_health()` returns the status of all backends; use it for
  diagnosis when a query returns empty unexpectedly.
- `sinapse_capture_screen` only on explicit request â€” never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- **Vault write enforcement:** on hosts where `setup-vault-enforcement`
  has been applied, `cerebro/` is owned by a dedicated service user and the
  agent only has direct write access to `cerebro/90-intake/`. If a direct
  vault write is denied, `sinapse_save_decision`/`sinapse_save_learning`
  fall back automatically to the intake area â€” this is expected behavior,
  not a failure to report or retry. The Dream Cycle later promotes intake
  content into the vault proper via `sinapse_promote_knowledge`.
- Consulting before acting and recording anything reusable is not optional:
  this is how the project brain evolves between sessions.
<!-- END HIVE-MIND SINAPSE -->

<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.ps1 -- do not edit) -->
# Hive-Mind Protocol (sinapse-memory) â€” MANDATORY

You have the 15 `sinapse_*` tools and `search_memories`. This is the working
protocol; always follow it, without exception. The raw backends (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) are federated inside
sinapse via `sinapse_query` (Context Fusion with circuit breaker
and 8s timeout) â€” **never call them directly**.

## 0. Pre-check (once at the start of the session)
- `sinapse_health()` â€” confirm that all backends are operational
  before working. If any fail, report and use `sinapse_temporal_search`
  or `search_memories` in `text` mode as a fallback.

## 1. Recall before acting (at the start of each task)
| Need | Tool |
|------|------|
| Project state/history, decisions, patterns, code/vault, and general context | `sinapse_query("<topic>")` (canonical hybrid search: fuses UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Recent activity from conversations, prompts, sessions, and raw claude-mem observations | `sinapse_temporal_search("<short specific terms>")` â†’ `sinapse_temporal_timeline(anchor=<id>)` â†’ `sinapse_temporal_get_observations(ids=[...])` |
| Backend health/check | `sinapse_health()` |

**Rule:** never claim anything about the project state/history without having
consulted first.

**How to search without getting lost:**
1. To understand "what happened in the project", start with `sinapse_query`.
   It is tolerant of natural language and crosses all organs of the brain.
2. If you need the recent conversation/prompt/session that originated it, use
   `sinapse_temporal_search` as the **textual index for claude-mem**. Search
   with short terms likely to appear in the actual text. Good examples:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. If `sinapse_temporal_search` returns empty, do not conclude there is no memory:
   reduce the query to 2â€“5 exact terms, try the title returned by
   `sinapse_query`, or go back to `sinapse_query` to retrieve consolidated context.
4. Do not use long phrases, full questions, or many mixed filters in
   `sinapse_temporal_search`; it is best as a textual/timeline search for
   claude-mem, not as a hybrid orchestrator.
5. For raw temporal memory, follow the native `claude-mem` flow:
   `search â†’ timeline â†’ get_observations`.
   - `sinapse_temporal_search` is the compact index: find IDs/titles.
   - `sinapse_temporal_timeline` shows chronological context around an ID
     or an anchor query.
   - `sinapse_temporal_get_observations` hydrates the full content only for the
     filtered IDs. **Never** hydrate details before filtering; that wastes
     tokens and mixes irrelevant context.

## 2. On-demand recall (during work)
| Need | Tool |
|------|------|
| Neurons/notes by semantic similarity (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Facts/decisions with temporal validity (valid_at/invalid_at edges) | `sinapse_temporal_graph_search("<topic>", num_results)` (deprecated â€” use `sinapse_query`) |
| Textual search in the global claude-mem index (`~/.claude-mem`) | `sinapse_temporal_search("<short terms>")` |
| Chronological context around a temporal result | `sinapse_temporal_timeline(anchor=<id>)` or `sinapse_temporal_timeline(query="<terms>")` |
| Full detail of already-filtered temporal observations | `sinapse_temporal_get_observations(ids=[...])` |
| General hybrid search (all layers; default for project context) | `sinapse_query("<topic>")` |
| Vector query on the LightRAG graph (P4) | `sinapse_rag_query(question, mode?)` |
| Promote pending observations into typed knowledge (K3 intake) | `sinapse_promote_knowledge(limit?, dry_run?, import_claude_mem?, source_ids?, since_epoch?, until_epoch?)` |

### Quick tool selection

| Agent question | Use | Practical note |
|----------------|-----|----------------|
| "What is the project state/history?" | `sinapse_query` | First choice. Crosses vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec, and filesystem. |
| "Which recent prompt/session talked about this?" | `sinapse_temporal_search` â†’ `sinapse_temporal_timeline` â†’ `sinapse_temporal_get_observations` | Use short/exact terms, pick IDs, read the temporal window, and only then hydrate details. |
| "Which consolidated neurons exist on this topic?" | `search_memories` | Use `project` when you know the project; `mode="text"` for literal search. |
| "I need multi-hop relations between already-indexed entities." | `sinapse_rag_query` | Depends on LightRAG being populated; if it returns empty, fall back to `sinapse_query`. |
| "I need temporal/causal facts from Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` exists for compatibility, but the canonical brain query is `sinapse_query`. |
| "I made a decision or learned a reusable pattern." | `sinapse_save_decision` / `sinapse_save_learning` | Record immediately; do not leave it only in the chat response. |
| "I want to write a raw temporal event." | `sinapse_temporal_save` | Only writes directly into claude-mem in server-beta; in the current worker runtime, treat as a fallback/note, not the primary write path. |
| "There are pending observations that need to become typed knowledge (neurons/candidates)." | `sinapse_promote_knowledge` | Normalizes pending UMC observations/discoveries/session summaries into typed candidates, preserves raw records, quarantines structural errors, links `observation.neuron_id`. Use `dry_run=true` to classify/count without writing. This is normally run by the Dream Cycle; call it manually only for maintenance or debugging the intake pipeline. |

## 3. Record immediately (when deciding, learning, or decomposing)
| Need | Tool |
|------|------|
| Decision (choice between alternatives + reason) | `sinapse_save_decision(title, content, evidence?)` |
| Reusable pattern/insight/lesson | `sinapse_save_learning(title, content, evidence?)` |
| Large goal â†’ atomic steps (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Monolithic note (Patterns.md) â†’ atomic Zettelkasten notes | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capture a screenshot of bug/visual progress (not in loop!) | `sinapse_capture_screen(description, monitor?)` |
| Raw temporal observation (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

**Epistemic discipline (verified vs hypothesis):** when saving a decision or
learning, pass `evidence` (the command you ran, the test that passed, the file
you read) whenever the claim was actually verified â€” the note is stamped
`confidence: verified`. Without evidence the note is a `hypothesis`: it still
gets saved, but the RetrievalRouter demotes it in ranking until validated, and
the audit lists it for review. If a hypothesis is later refuted, correct the
note instead of leaving it â€” a refuted hypothesis left in place poisons future
retrieval.

**Review TTL (staleness):** every decision/learning is stamped with
`review_date` and `next_review` (default `REVIEW_TTL_DAYS=90`). Once
`next_review` passes, the RetrievalRouter flags the note `stale` and applies
`HIVE_STALENESS_PENALTY` (default `0.85`) to its ranking score â€” same
demotion mechanism as an unverified hypothesis, but time-based instead of
evidence-based. The note is never deleted or excluded, only demoted. If you
revisit a stale note and it still holds, re-save it (or update it) so its
`next_review` window resets.

## 4. Consolidate when finished
- `sinapse_session_end(summary)` â€” updates `brain/Current State.md` and
  records the closing observation in the UMC.

## Usage rules
- **Use ONLY the `sinapse_*` tools and `search_memories`.** Never call
  `nmem`, `claude-mem`, `graphify`, or `falkordb` directly â€” sinapse
  already federates and deduplicates them via Context Fusion.
- RTK is not a memory tool or a `sinapse_query` backend; it is only the
  shell command optimization layer. When you need to configure RTK, use
  `./scripts/services/start-rtk.sh --only <agent>` for the correct agent/CLI.
- `sinapse_query` is the canonical orchestrator (7 backends). Use it instead of
  backend-specific tools whenever possible.
- `sinapse_temporal_graph_search` is deprecated: kept so as not to
  break existing clients, but the canonical brain query is
  `sinapse_query` (which fuses Graphiti together with the other 6 organs).
- `sinapse_health()` returns the status of all backends; use it for
  diagnosis when a query returns empty unexpectedly.
- `sinapse_capture_screen` only on explicit request â€” never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- **Vault write enforcement:** on hosts where `setup-vault-enforcement`
  has been applied, `cerebro/` is owned by a dedicated service user and the
  agent only has direct write access to `cerebro/90-intake/`. If a direct
  vault write is denied, `sinapse_save_decision`/`sinapse_save_learning`
  fall back automatically to the intake area â€” this is expected behavior,
  not a failure to report or retry. The Dream Cycle later promotes intake
  content into the vault proper via `sinapse_promote_knowledge`.
- Consulting before acting and recording anything reusable is not optional:
  this is how the project brain evolves between sessions.
<!-- END HIVE-MIND SINAPSE -->

<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.ps1 -- do not edit) -->
# Hive-Mind Protocol (sinapse-memory) â€” MANDATORY

You have the 15 `sinapse_*` tools and `search_memories`. This is the working
protocol; always follow it, without exception. The raw backends (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) are federated inside
sinapse via `sinapse_query` (Context Fusion with circuit breaker
and 8s timeout) â€” **never call them directly**.

## 0. Pre-check (once at the start of the session)
- `sinapse_health()` â€” confirm that all backends are operational
  before working. If any fail, report and use `sinapse_temporal_search`
  or `search_memories` in `text` mode as a fallback.

## 1. Recall before acting (at the start of each task)
| Need | Tool |
|------|------|
| Project state/history, decisions, patterns, code/vault, and general context | `sinapse_query("<topic>")` (canonical hybrid search: fuses UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Recent activity from conversations, prompts, sessions, and raw claude-mem observations | `sinapse_temporal_search("<short specific terms>")` â†’ `sinapse_temporal_timeline(anchor=<id>)` â†’ `sinapse_temporal_get_observations(ids=[...])` |
| Backend health/check | `sinapse_health()` |

**Rule:** never claim anything about the project state/history without having
consulted first.

**How to search without getting lost:**
1. To understand "what happened in the project", start with `sinapse_query`.
   It is tolerant of natural language and crosses all organs of the brain.
2. If you need the recent conversation/prompt/session that originated it, use
   `sinapse_temporal_search` as the **textual index for claude-mem**. Search
   with short terms likely to appear in the actual text. Good examples:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. If `sinapse_temporal_search` returns empty, do not conclude there is no memory:
   reduce the query to 2â€“5 exact terms, try the title returned by
   `sinapse_query`, or go back to `sinapse_query` to retrieve consolidated context.
4. Do not use long phrases, full questions, or many mixed filters in
   `sinapse_temporal_search`; it is best as a textual/timeline search for
   claude-mem, not as a hybrid orchestrator.
5. For raw temporal memory, follow the native `claude-mem` flow:
   `search â†’ timeline â†’ get_observations`.
   - `sinapse_temporal_search` is the compact index: find IDs/titles.
   - `sinapse_temporal_timeline` shows chronological context around an ID
     or an anchor query.
   - `sinapse_temporal_get_observations` hydrates the full content only for the
     filtered IDs. **Never** hydrate details before filtering; that wastes
     tokens and mixes irrelevant context.

## 2. On-demand recall (during work)
| Need | Tool |
|------|------|
| Neurons/notes by semantic similarity (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Facts/decisions with temporal validity (valid_at/invalid_at edges) | `sinapse_temporal_graph_search("<topic>", num_results)` (deprecated â€” use `sinapse_query`) |
| Textual search in the global claude-mem index (`~/.claude-mem`) | `sinapse_temporal_search("<short terms>")` |
| Chronological context around a temporal result | `sinapse_temporal_timeline(anchor=<id>)` or `sinapse_temporal_timeline(query="<terms>")` |
| Full detail of already-filtered temporal observations | `sinapse_temporal_get_observations(ids=[...])` |
| General hybrid search (all layers; default for project context) | `sinapse_query("<topic>")` |
| Vector query on the LightRAG graph (P4) | `sinapse_rag_query(question, mode?)` |
| Promote pending observations into typed knowledge (K3 intake) | `sinapse_promote_knowledge(limit?, dry_run?, import_claude_mem?, source_ids?, since_epoch?, until_epoch?)` |

### Quick tool selection

| Agent question | Use | Practical note |
|----------------|-----|----------------|
| "What is the project state/history?" | `sinapse_query` | First choice. Crosses vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec, and filesystem. |
| "Which recent prompt/session talked about this?" | `sinapse_temporal_search` â†’ `sinapse_temporal_timeline` â†’ `sinapse_temporal_get_observations` | Use short/exact terms, pick IDs, read the temporal window, and only then hydrate details. |
| "Which consolidated neurons exist on this topic?" | `search_memories` | Use `project` when you know the project; `mode="text"` for literal search. |
| "I need multi-hop relations between already-indexed entities." | `sinapse_rag_query` | Depends on LightRAG being populated; if it returns empty, fall back to `sinapse_query`. |
| "I need temporal/causal facts from Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` exists for compatibility, but the canonical brain query is `sinapse_query`. |
| "I made a decision or learned a reusable pattern." | `sinapse_save_decision` / `sinapse_save_learning` | Record immediately; do not leave it only in the chat response. |
| "I want to write a raw temporal event." | `sinapse_temporal_save` | Only writes directly into claude-mem in server-beta; in the current worker runtime, treat as a fallback/note, not the primary write path. |
| "There are pending observations that need to become typed knowledge (neurons/candidates)." | `sinapse_promote_knowledge` | Normalizes pending UMC observations/discoveries/session summaries into typed candidates, preserves raw records, quarantines structural errors, links `observation.neuron_id`. Use `dry_run=true` to classify/count without writing. This is normally run by the Dream Cycle; call it manually only for maintenance or debugging the intake pipeline. |

## 3. Record immediately (when deciding, learning, or decomposing)
| Need | Tool |
|------|------|
| Decision (choice between alternatives + reason) | `sinapse_save_decision(title, content, evidence?)` |
| Reusable pattern/insight/lesson | `sinapse_save_learning(title, content, evidence?)` |
| Large goal â†’ atomic steps (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Monolithic note (Patterns.md) â†’ atomic Zettelkasten notes | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capture a screenshot of bug/visual progress (not in loop!) | `sinapse_capture_screen(description, monitor?)` |
| Raw temporal observation (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

**Epistemic discipline (verified vs hypothesis):** when saving a decision or
learning, pass `evidence` (the command you ran, the test that passed, the file
you read) whenever the claim was actually verified â€” the note is stamped
`confidence: verified`. Without evidence the note is a `hypothesis`: it still
gets saved, but the RetrievalRouter demotes it in ranking until validated, and
the audit lists it for review. If a hypothesis is later refuted, correct the
note instead of leaving it â€” a refuted hypothesis left in place poisons future
retrieval.

**Review TTL (staleness):** every decision/learning is stamped with
`review_date` and `next_review` (default `REVIEW_TTL_DAYS=90`). Once
`next_review` passes, the RetrievalRouter flags the note `stale` and applies
`HIVE_STALENESS_PENALTY` (default `0.85`) to its ranking score â€” same
demotion mechanism as an unverified hypothesis, but time-based instead of
evidence-based. The note is never deleted or excluded, only demoted. If you
revisit a stale note and it still holds, re-save it (or update it) so its
`next_review` window resets.

## 4. Consolidate when finished
- `sinapse_session_end(summary)` â€” updates `brain/Current State.md` and
  records the closing observation in the UMC.

## Usage rules
- **Use ONLY the `sinapse_*` tools and `search_memories`.** Never call
  `nmem`, `claude-mem`, `graphify`, or `falkordb` directly â€” sinapse
  already federates and deduplicates them via Context Fusion.
- RTK is not a memory tool or a `sinapse_query` backend; it is only the
  shell command optimization layer. When you need to configure RTK, use
  `./scripts/services/start-rtk.sh --only <agent>` for the correct agent/CLI.
- `sinapse_query` is the canonical orchestrator (7 backends). Use it instead of
  backend-specific tools whenever possible.
- `sinapse_temporal_graph_search` is deprecated: kept so as not to
  break existing clients, but the canonical brain query is
  `sinapse_query` (which fuses Graphiti together with the other 6 organs).
- `sinapse_health()` returns the status of all backends; use it for
  diagnosis when a query returns empty unexpectedly.
- `sinapse_capture_screen` only on explicit request â€” never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- **Vault write enforcement:** on hosts where `setup-vault-enforcement`
  has been applied, `cerebro/` is owned by a dedicated service user and the
  agent only has direct write access to `cerebro/90-intake/`. If a direct
  vault write is denied, `sinapse_save_decision`/`sinapse_save_learning`
  fall back automatically to the intake area â€” this is expected behavior,
  not a failure to report or retry. The Dream Cycle later promotes intake
  content into the vault proper via `sinapse_promote_knowledge`.
- Consulting before acting and recording anything reusable is not optional:
  this is how the project brain evolves between sessions.
<!-- END HIVE-MIND SINAPSE -->

<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.ps1 -- do not edit) -->
# Hive-Mind Protocol (sinapse-memory) â€” MANDATORY

You have the 15 `sinapse_*` tools and `search_memories`. This is the working
protocol; always follow it, without exception. The raw backends (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) are federated inside
sinapse via `sinapse_query` (Context Fusion with circuit breaker
and 8s timeout) â€” **never call them directly**.

## 0. Pre-check (once at the start of the session)
- `sinapse_health()` â€” confirm that all backends are operational
  before working. If any fail, report and use `sinapse_temporal_search`
  or `search_memories` in `text` mode as a fallback.

## 1. Recall before acting (at the start of each task)
| Need | Tool |
|------|------|
| Project state/history, decisions, patterns, code/vault, and general context | `sinapse_query("<topic>")` (canonical hybrid search: fuses UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Recent activity from conversations, prompts, sessions, and raw claude-mem observations | `sinapse_temporal_search("<short specific terms>")` â†’ `sinapse_temporal_timeline(anchor=<id>)` â†’ `sinapse_temporal_get_observations(ids=[...])` |
| Backend health/check | `sinapse_health()` |

**Rule:** never claim anything about the project state/history without having
consulted first.

**How to search without getting lost:**
1. To understand "what happened in the project", start with `sinapse_query`.
   It is tolerant of natural language and crosses all organs of the brain.
2. If you need the recent conversation/prompt/session that originated it, use
   `sinapse_temporal_search` as the **textual index for claude-mem**. Search
   with short terms likely to appear in the actual text. Good examples:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. If `sinapse_temporal_search` returns empty, do not conclude there is no memory:
   reduce the query to 2â€“5 exact terms, try the title returned by
   `sinapse_query`, or go back to `sinapse_query` to retrieve consolidated context.
4. Do not use long phrases, full questions, or many mixed filters in
   `sinapse_temporal_search`; it is best as a textual/timeline search for
   claude-mem, not as a hybrid orchestrator.
5. For raw temporal memory, follow the native `claude-mem` flow:
   `search â†’ timeline â†’ get_observations`.
   - `sinapse_temporal_search` is the compact index: find IDs/titles.
   - `sinapse_temporal_timeline` shows chronological context around an ID
     or an anchor query.
   - `sinapse_temporal_get_observations` hydrates the full content only for the
     filtered IDs. **Never** hydrate details before filtering; that wastes
     tokens and mixes irrelevant context.

## 2. On-demand recall (during work)
| Need | Tool |
|------|------|
| Neurons/notes by semantic similarity (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Facts/decisions with temporal validity (valid_at/invalid_at edges) | `sinapse_temporal_graph_search("<topic>", num_results)` (deprecated â€” use `sinapse_query`) |
| Textual search in the global claude-mem index (`~/.claude-mem`) | `sinapse_temporal_search("<short terms>")` |
| Chronological context around a temporal result | `sinapse_temporal_timeline(anchor=<id>)` or `sinapse_temporal_timeline(query="<terms>")` |
| Full detail of already-filtered temporal observations | `sinapse_temporal_get_observations(ids=[...])` |
| General hybrid search (all layers; default for project context) | `sinapse_query("<topic>")` |
| Vector query on the LightRAG graph (P4) | `sinapse_rag_query(question, mode?)` |
| Promote pending observations into typed knowledge (K3 intake) | `sinapse_promote_knowledge(limit?, dry_run?, import_claude_mem?, source_ids?, since_epoch?, until_epoch?)` |

### Quick tool selection

| Agent question | Use | Practical note |
|----------------|-----|----------------|
| "What is the project state/history?" | `sinapse_query` | First choice. Crosses vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec, and filesystem. |
| "Which recent prompt/session talked about this?" | `sinapse_temporal_search` â†’ `sinapse_temporal_timeline` â†’ `sinapse_temporal_get_observations` | Use short/exact terms, pick IDs, read the temporal window, and only then hydrate details. |
| "Which consolidated neurons exist on this topic?" | `search_memories` | Use `project` when you know the project; `mode="text"` for literal search. |
| "I need multi-hop relations between already-indexed entities." | `sinapse_rag_query` | Depends on LightRAG being populated; if it returns empty, fall back to `sinapse_query`. |
| "I need temporal/causal facts from Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` exists for compatibility, but the canonical brain query is `sinapse_query`. |
| "I made a decision or learned a reusable pattern." | `sinapse_save_decision` / `sinapse_save_learning` | Record immediately; do not leave it only in the chat response. |
| "I want to write a raw temporal event." | `sinapse_temporal_save` | Only writes directly into claude-mem in server-beta; in the current worker runtime, treat as a fallback/note, not the primary write path. |
| "There are pending observations that need to become typed knowledge (neurons/candidates)." | `sinapse_promote_knowledge` | Normalizes pending UMC observations/discoveries/session summaries into typed candidates, preserves raw records, quarantines structural errors, links `observation.neuron_id`. Use `dry_run=true` to classify/count without writing. This is normally run by the Dream Cycle; call it manually only for maintenance or debugging the intake pipeline. |

## 3. Record immediately (when deciding, learning, or decomposing)
| Need | Tool |
|------|------|
| Decision (choice between alternatives + reason) | `sinapse_save_decision(title, content, evidence?)` |
| Reusable pattern/insight/lesson | `sinapse_save_learning(title, content, evidence?)` |
| Large goal â†’ atomic steps (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Monolithic note (Patterns.md) â†’ atomic Zettelkasten notes | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capture a screenshot of bug/visual progress (not in loop!) | `sinapse_capture_screen(description, monitor?)` |
| Raw temporal observation (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

**Epistemic discipline (verified vs hypothesis):** when saving a decision or
learning, pass `evidence` (the command you ran, the test that passed, the file
you read) whenever the claim was actually verified â€” the note is stamped
`confidence: verified`. Without evidence the note is a `hypothesis`: it still
gets saved, but the RetrievalRouter demotes it in ranking until validated, and
the audit lists it for review. If a hypothesis is later refuted, correct the
note instead of leaving it â€” a refuted hypothesis left in place poisons future
retrieval.

**Review TTL (staleness):** every decision/learning is stamped with
`review_date` and `next_review` (default `REVIEW_TTL_DAYS=90`). Once
`next_review` passes, the RetrievalRouter flags the note `stale` and applies
`HIVE_STALENESS_PENALTY` (default `0.85`) to its ranking score â€” same
demotion mechanism as an unverified hypothesis, but time-based instead of
evidence-based. The note is never deleted or excluded, only demoted. If you
revisit a stale note and it still holds, re-save it (or update it) so its
`next_review` window resets.

## 4. Consolidate when finished
- `sinapse_session_end(summary)` â€” updates `brain/Current State.md` and
  records the closing observation in the UMC.

## Usage rules
- **Use ONLY the `sinapse_*` tools and `search_memories`.** Never call
  `nmem`, `claude-mem`, `graphify`, or `falkordb` directly â€” sinapse
  already federates and deduplicates them via Context Fusion.
- RTK is not a memory tool or a `sinapse_query` backend; it is only the
  shell command optimization layer. When you need to configure RTK, use
  `./scripts/services/start-rtk.sh --only <agent>` for the correct agent/CLI.
- `sinapse_query` is the canonical orchestrator (7 backends). Use it instead of
  backend-specific tools whenever possible.
- `sinapse_temporal_graph_search` is deprecated: kept so as not to
  break existing clients, but the canonical brain query is
  `sinapse_query` (which fuses Graphiti together with the other 6 organs).
- `sinapse_health()` returns the status of all backends; use it for
  diagnosis when a query returns empty unexpectedly.
- `sinapse_capture_screen` only on explicit request â€” never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- **Vault write enforcement:** on hosts where `setup-vault-enforcement`
  has been applied, `cerebro/` is owned by a dedicated service user and the
  agent only has direct write access to `cerebro/90-intake/`. If a direct
  vault write is denied, `sinapse_save_decision`/`sinapse_save_learning`
  fall back automatically to the intake area â€” this is expected behavior,
  not a failure to report or retry. The Dream Cycle later promotes intake
  content into the vault proper via `sinapse_promote_knowledge`.
- Consulting before acting and recording anything reusable is not optional:
  this is how the project brain evolves between sessions.
<!-- END HIVE-MIND SINAPSE -->

