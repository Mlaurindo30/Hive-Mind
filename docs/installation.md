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

## Windows install (native, no WSL2 — 🚧 beta)

**Hive-Mind** also has a native Windows install path that runs directly against a project-local
`.venv`, with no WSL2 requirement, via PowerShell scripts sharing a common helper module
(`scripts/lib/HiveMind.Windows.psm1`). This is the path exercised when host agents (Claude Code,
Cursor, Copilot) need to reach the memory directly on a machine without WSL2/Git installed for
Linux tooling — see the README's platform table.

```powershell
git clone <repo-url> Hive-Mind
cd Hive-Mind
install.bat --profile local-min
```

Useful switches: `-Profile local-min|local-full`, `-WithTests`, `-WithRealTests`,
`-SkipAgents`, `-SkipServices`, `-NonInteractive`, `-Force`. `install.bat` and
`setup-brain.bat` are thin wrappers that just invoke the matching `.ps1` under
`powershell.exe -ExecutionPolicy Bypass`. Register/re-register MCP for a single agent with:

```powershell
python scripts/setup/register_mcp.py --claude-only --apply   # or --codex-only, or neither for every detected agent
```

The Python entrypoint and `register-mcp.sh` are adapters over
`hive-mind agents register` (D009-R6) — same implementation, same option set,
same results on either platform. See [agents.md](agents.md).

**Known gaps versus `install.sh`'s 12-step process (as of 2026-07-09), so you aren't surprised:**

- No automatic Ollama model pull — if you want local embeddings/vision, pull
  `snowflake-arctic-embed2:latest` / `qwen2.5:3b` / `minicpm-v4.6:latest` yourself first.
- `scripts/graph/build-graph.ps1` always does structural (AST-only) reindexing; it doesn't yet
  select a semantic-extraction backend (Gemini/Ollama) the way `build-graph.sh` does.
- ~~`register-mcp.ps1` registers fewer targets than `register-mcp.sh`~~ — **closed in D009-R6.**
  Both are now wrappers over the same native implementation, so the 13 agent keys and the
  `config/sinapse-agent-prompt.md` injection (`--instructions`) are identical on both platforms.
- No cron/Task Scheduler equivalent is installed yet — periodic jobs (graph rebuild, Dream Cycle,
  backups, quarantine drain) need to be scheduled by hand (e.g. via `Register-ScheduledTask`) or run
  manually.
- `scripts/capture/copilot-wrapper.ps1` is currently a plain passthrough — it does not capture
  Copilot CLI sessions into claude-mem the way the bash wrapper does.
- claude-mem native-plugin detection currently targets Codex CLI only; other IDEs need their hooks
  installed by hand if you're not also running Codex.

None of this blocks day-to-day use of the memory itself (MCP, CLI, REST all work once installed) —
it mainly means the *automated* onboarding/maintenance a Linux/WSL2 install gets for free is, for
now, something you do once by hand on native Windows.

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
| MCP Server | `scripts/services/sinapse-mcp.py` | Python | 16 tools via stdio JSON-RPC |
| CLI | `scripts/services/sinapse-write.py` | Python | Subcommands: decision, learning, query, health, session-end |
| Graphify | `graphify/` | Python | Structural vault indexer |
| claude-mem | `~/.claude-mem` + upstream plugin | TypeScript/Bun | Global multi-project event tracking (port 37700) |
| RTK | `integrations/rtk/` | Rust | Cross-cutting shell-command optimization per agent/CLI |
| NeuralMemory | `integrations/neural-memory/` | Python | Associative recall (spreading activation) |
| Hermes Plugin | `plugins/hermes/sinapse-memory.py` | Python | Automatic read/write via hooks |
| Vault | `cerebro/` | Markdown | Single source of truth (Obsidian) |
| Model Gateway | `core/model_gateway.py` + `core/model_registry.py` | Python | Priority 1 (canonical) — role/capability LLM routing over `native`/LM Studio/llama.cpp/vLLM/SGLang/LiteLLM; `MODEL_GATEWAY_MODE=auto` by default, see [`14-model-gateway.md`](14-model-gateway.md) |

O bloco de variáveis do Model Gateway fica em
`config/model-gateway.env.example` porque `.env.example` não pôde ser
alterado nesta sessão. O install/documentation deve apontar para esse
arquivo como fonte canônica do exemplo de ambiente do Model Gateway.

Full anatomy (brain lobes → directory mapping) and design rationale: [`docs/01-architecture.md`](01-architecture.md).
