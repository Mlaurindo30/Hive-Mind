# Installation Guide — Hive-Mind

> Detailed installation reference. For the fastest path, copy the install prompt from the
> [main README](../README.md#-quick-start--configure-with-your-ai-agent) into your AI agent.

---

## Prerequisites

| Dependency | Required? | Used by |
|------------|-----------|---------|
| Python 3.10+ | Yes | UMC, Dream Cycle, MCP, API |
| SQLite 3 + sqlite-vec | Yes (installed via pip) | UMC |
| hnswlib | Yes (pip) | Incremental HNSW index (HM-11) |
| duckdb | Yes (pip) | Analytics layer (HM-12) |
| Node.js 18+ / Bun 1.0+ | For claude-mem | Temporal layer |
| Rust (cargo) | For RTK | Execution layer |
| Ollama | Optional | Local LLM / embeddings |
| Obsidian | Optional | Visual vault interface |
| Syncthing | Optional | P2P synchronization |

---

## Quick install

```bash
git clone <repo-url> ~/Documentos/Projects/Hive-Mind
cd ~/Documentos/Projects/Hive-Mind
./install.sh
```

For headless / CI environments (no interactive terminal):

```bash
HIVE_DREAMER_PROVIDER=google HIVE_DREAMER_MODEL=gemini-2.0-flash \
GOOGLE_API_KEY=<your_key> ./install.sh --non-interactive
```

---

## Windows install (via WSL2)

**Hive-Mind** is fully supported on Windows through **WSL2** (Windows Subsystem for Linux).
This ensures native dependencies and complex C/Rust builds (`sqlite-vec`, `RTK`) work at full
performance without compiler friction.

1. **Install and start WSL2** (preferably Ubuntu 22.04 LTS or newer).
2. **Clone the repository on the Windows filesystem** (so you can open the vault in Obsidian for
   Windows). In the WSL2 terminal, navigate to your projects folder and clone:

   ```bash
   mkdir -p /mnt/c/Projects
   cd /mnt/c/Projects
   git clone <repo-url> Hive-Mind
   cd Hive-Mind
   ```
3. **Run the installer:**

   ```bash
   ./install.sh
   ```
4. **Multimodal onboarding (Vision / screen capture):** the vision utility (`visual_capture.py`)
   natively detects the WSL2 environment and transparently invokes the Windows host `powershell.exe`
   to take physical Windows screenshots — no extra image servers or X11 servers required.
5. **Opening the vault:** open Obsidian on your Windows host and select the physical folder
   `C:\Projects\Hive-Mind\cerebro` as a new vault. Any edit made in Obsidian for Windows is synced in
   real time with SQLite/UMC inside WSL2 in under 2 seconds.

---

## What `install.sh` does (12 steps)

```
  [1/12]  Prerequisites and Python 3.12 managed by uv
  [2/12]  Reproducible Python environment (.venv + uv.lock)
  [3/12]  Local Graphify and FTS / sqlite-vec / HNSW indexes
  [4/12]  Skills into detected agents
  [5/12]  Global Claude-Mem via npx / marketplace
  [6/12]  Local NeuralMemory
  [7/12]  RTK pinned and compiled
  [8/12]  Hermes MCP
  [9/12]  Single synchronization cron
  [10/12] Hermes sinapse-memory plugin
  [11/12] Intelligence configuration
  [12/12] Three managed MCPs into external agents and services
```

After install finishes, the installer itself asks whether to configure the LLM provider
(Gemini, OpenAI, Anthropic, Ollama, ...) via `setup-brain.sh`. Answer **Y** and follow the menu to
choose provider, model and API keys. Then restart your agent.

---

## Components reference

| Component | Path | Language | Role |
|-----------|------|----------|------|
| Unified Memory Core | `hive_mind.db` + `core/umc_schema.sql` | SQLite | Single store: graph, logs, vectors, FTS, multimodal, secrets |
| Connection / Schema | `core/database.py` | Python | Connections with sqlite-vec, WAL, busy_timeout |
| LLM Authentication | `core/auth.py` | Python | 10 providers (API key + OAuth), refresh, model discovery |
| Pydantic Schemas | `core/schemas/` | Python | Structured output: Distiller, Validator, Router, Synthesis, Vision |
| Hive-Dreamer | `scripts/dream/dream_cycle.py` | Python | Consolidation: observations → validated facts → Atlas |
| Brain Selector | `scripts/setup/setup-brain.sh` | Python | Terminal UI: provider/model/auth for every role + fallback |
| Watcher | `scripts/services/start-watcher.sh` | Python/watchdog | Real-time sync Obsidian → SQLite (~2s) |
| P2P Auditor | `scripts/health/audit_memory.py` | Python | Vault ↔ SQLite integrity |
| Semantic Diff | `scripts/dream/semantic_diff.py` | Python | Classifies P2P conflicts (vector + LLM) |
| Doc Ingestion | `scripts/knowledge/document_ingest.py` | Python | PDF/DOCX → observation queue |
| Visual Capture | `scripts/capture/visual_capture.py` | Python/mss | Screenshots → `visual_memories` |
| Visual Portal | `scripts/knowledge/generate_portal.py` | Python | Generates `portal.canvas` (Obsidian Canvas) |
| REST API | `scripts/services/sinapse-api.py` | FastAPI | Authenticated remote access to UMC (port 37702) |
| MCP Server | `scripts/services/sinapse-mcp.py` | Python | 15 tools via stdio JSON-RPC |
| CLI | `scripts/services/sinapse-write.py` | Python | Subcommands: decision, learning, query, health, session-end |
| Graphify | `graphify/` | Python | Structural vault indexer |
| claude-mem | `~/.claude-mem` + upstream plugin | TypeScript/Bun | Global multi-project event tracking (port 37700) |
| RTK | `integrations/rtk/` | Rust | Cross-cutting shell-command optimization per agent/CLI |
| NeuralMemory | `integrations/neural-memory/` | Python | Associative recall (spreading activation) |
| Hermes Plugin | `plugins/hermes/sinapse-memory.py` | Python | Automatic read/write via hooks |
| Vault | `cerebro/` | Markdown | Single source of truth (Obsidian) |

Full anatomy (brain lobes → directory mapping) and design rationale: [`docs/01-architecture.md`](01-architecture.md).
