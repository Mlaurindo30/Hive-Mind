# Installation — Hive-Mind

> **Hive-Mind v3.10.1** — complete installation guide: profiles, native Windows
> installation, Linux installation, Docker greenfield, and rollback.
>
> References: [runtime.md](runtime.md) (services/scheduler),
> [operations.md](operations.md) (post-install and maintenance),
> [cli.md](cli.md) (agent and job registration),
> [15-windows-clean-install.md](15-windows-clean-install.md) (Windows clean
> install acceptance), [04-infrastructure.md](04-infrastructure.md)
> (requirements and variables).

---

## 1. Installation profiles

Installation is parameterized by **profile**. The profile defines the
prerequisites contract and which services are `required`.

| Profile | Description | Backends | Required services |
|---|---|---|---|
| `local-min` | Local SQLite/vector path. Minimum for daily use. | SQLite + `sqlite-vec` + claude-mem + Graphify + FalkorDB (Graphiti) | `sinapse-claude-mem`, `sinapse-sqlite-vec`, `sinapse-capture-realtime` |
| `local-full` | Full stack with Docker. | + Milvus, RAGFlow, FalkorDB, Syncthing | those of `local-min` + `docker-desktop`, `falkordb`, `milvus`, `ragflow`, `syncthing-watcher` |

The profile contract lives in `config/profiles/<profile>.env.example`. The
installer **fails** (non-zero exit) if any `required` service of the selected
profile does not become `healthy`.

> The canonical source of the service catalog and the `required` semantics is
> `config/runtime.yaml` — see [runtime.md](runtime.md) §12–13.

---

## 2. Prerequisites

### 2.1 General table

| Dependency | Minimum version | Use | Required? |
|---|---|---|---|
| Python | 3.12 (Windows) / 3.10+ (POSIX) | Core, UMC, Dream Cycle, MCP, API | Yes |
| uv | 0.4+ | Canonical package manager | Yes |
| SQLite | 3.44+ (with `sqlite-vec`) | UMC | Yes (via pip) |
| Node.js | 18+ | Service supervisor and claude-mem | Yes |
| Bun | 1.0+ | claude-mem (TypeScript) | Yes |
| Rust / Cargo | 1.70+ | RTK compilation | Yes |
| Ollama | — | Local LLM/embeddings | Yes (validation) |
| Docker Desktop | — | Milvus/RAGFlow/FalkorDB | Only `local-full` |
| Syncthing | 1.27+ | Vault P2P | Only `local-full` |
| WSL 2 | — | `local-full` (validation) | Only `local-full` |
| Visual Studio Build Tools | 2022 | MSBuild (build prerequisite) | Only `local-full` |
| Git | — | Bootstrap of pinned integrations | Yes |
| Obsidian | — | Vault visual interface | Optional |

### 2.2 Python dependencies

`fastapi`, `uvicorn`, `pydantic≥2.7`, `cryptography≥42`, `watchdog≥4`, `pypdf`,
`python-docx`, `PyMuPDF`, `mss`, `pyyaml`, `httpx`, `hnswlib≥0.8`, `duckdb≥0.10`,
`fastembed` (legacy/fallback). Resolved by `uv sync --frozen` from `uv.lock`.

---

## 3. Windows installation (native)

### 3.1 Entrypoint chain

The native Windows path does not use WSL2 and runs against a project-local
`.venv`:

```
install.bat
  └─> scripts/setup/windows_install_entry.py   (normalizes switches -foo -> --foo)
        └─> src/hive_mind/install/windows.py   (canonical Python installer)
```

`install.bat` is a thin wrapper: it uses `.venv\Scripts\python.exe` if it
already exists, otherwise `py.exe -3`.

### 3.2 Quick command

```powershell
git clone <repo-url> Hive-Mind
cd Hive-Mind
install.bat --profile local-min --install-prerequisites
```

For the full stack:

```powershell
install.bat --profile local-full --install-prerequisites
```

### 3.3 Switches

`install.bat` accepts the old PowerShell spelling (`-Profile`, `-WithTests`,
…), translated in
[windows_install_entry.py](../scripts/setup/windows_install_entry.py). The
Python installer accepts the `--` spelling:

| Switch | `--` equivalent | Effect |
|---|---|---|
| `-Profile local-min\|local-full` | `--profile` | Installation profile (default `local-min`) |
| `-InstallPrerequisites` | `--install-prerequisites` | Installs prerequisites via winget |
| `-PrerequisitesOnly` | `--prerequisites-only` | Only prepares prerequisites and exits |
| `-SkipPrerequisites` | `--skip-prerequisites` | Skips the prerequisites bootstrap |
| `-WithTests` | `--with-tests` | Runs `pytest tests/unit tests/integration tests/e2e` |
| `-WithRealTests` | `--with-real-tests` | Runs `tests/real -m real` (JUnit in `logs/`) |
| `-SkipAgents` | `--skip-agents` | Does not register MCP in agents |
| `-SkipServices` | `--skip-services` | Does not install services/jobs/autostart |
| `-NonInteractive` | `--non-interactive` | No prompts |
| `-Force` | `--force` | Reinstalls (does not wipe `.venv` automatically) |
| `-DryRun` | `--dry-run` | Only validates the prerequisites contract |
| `-Repair` | `--repair` | Repairs an existing installation |
| `-Update` | `--update` | Updates |
| `-Uninstall` | `--uninstall` | Uninstalls |
| `-PreserveVault` | `--preserve-vault` | Keeps the vault |
| `-PreserveDatabase` | `--preserve-database` | Keeps the `hive_mind.db` |
| `-SystemService` | `--system-service` | Installs as a system service |

### 3.4 Windows prerequisites (winget)

Detected/installed by
[windows_prereqs.py](../src/hive_mind/install/windows_prereqs.py):

| Prerequisite | winget ID | Required |
|---|---|---|
| Git | `Git.Git` | yes |
| uv | `astral-sh.uv` | yes |
| Bun | `Oven-sh.Bun` | yes |
| Node LTS | `OpenJS.NodeJS.LTS` | yes |
| Rustup | `Rustlang.Rustup` | yes |
| Ollama | `Ollama.Ollama` | yes |
| Docker Desktop | `Docker.DockerDesktop` | `local-full` |
| Syncthing | `Syncthing.Syncthing` | `local-full` |
| WSL 2 | — (`wsl --install`) | `local-full` |
| Visual Studio Build Tools | `Microsoft.VisualStudio.2022.BuildTools` | `local-full` |

If a prerequisite requires a restart (winget code `3010`/`1641`), the installer
writes `backups/install-state/prerequisites.json` and asks for a re-run.

### 3.5 Installation flow (step by step)

The native Windows installer runs, in order:

1. **Protected memory snapshot** — `backups/` (pre-install verification).
2. **Host prerequisites** — winget bootstrap (when `local-full` or
   `--install-prerequisites`).
3. **Preflight** — checks `uv`, `git`, `node`.
4. **Project virtual environment** — `ensure_python_runtime` (`.venv`).
5. **Environment file** — copies `.env.example` → `.env`, applies the profile
   contract, and generates `HIVE_MIND_API_KEY` (if absent).
6. **Container stack** (`local-full`) — brings up FalkorDB, Milvus, RAGFlow via
   `docker compose up -d --quiet-pull`, starts Syncthing, and writes
   `VECTOR_BACKEND=milvus`, `MILVUS_URI`, `FALKORDB_*`, `RAGFLOW_BASE`; validates
   readiness (`local-min` writes `VECTOR_BACKEND=sqlite_vec`).
7. **Ollama local models** — `ollama pull` of the configured models
   (`snowflake-arctic-embed2:latest`, `qwen2.5:3b`, …).
8. **Pinned integrations** — `scripts/setup/components.py bootstrap`
   (Graphify, NeuralMemory, RTK; `git safe.directory`).
9. **Python dependencies** — `uv sync --frozen --all-groups`; creates `pythonw`
   GUI launchers and validates `pydantic`, `watchdog`.
10. **Wrapper and UMC setup** — `verify_wrappers.py` (with `--require-docker`
    on `local-full`) + `setup_umc.py`.
11. **Vault materialization** — `sync_vault_templates` + creates the anatomical
    tree (`cortex/`, `cerebelo/`, `diencefalo/`, `tronco/`, `90-intake`).
12. **Graph/index bootstrap** — `python -m graphify update cerebro`.
13. **MCP registration** — `hive-mind agents register --apply --instructions`
    (unless `--skip-agents`).
14. **claude-mem native runtime** — `npx claude-mem@13.6 install --ide codex-cli`.
15. **RTK** — `cargo build --locked --release` in `integrations/rtk`.
16. **Services** — `service manifest`, `node npm/bin/hive-mind.js services
    restart/wait/status`.
17. **Scheduled knowledge jobs** — `hive-mind service windows-jobs --apply`.
18. **Windows autostart** — `hive-mind service windows-runtime --apply`.
19. **Done**.

### 3.6 Clean install acceptance

Acceptance procedure (detailed in
[15-windows-clean-install.md](15-windows-clean-install.md)):

1. `install.bat --profile local-min --install-prerequisites`.
2. `node npm/bin/hive-mind.js services status` — exit 0 only if every `required`
   service is `healthy`.
3. `node npm/bin/hive-mind.js doctor` — exit 0 only with healthy API + services.
4. Restart Windows and inspect `logs/post-reboot-validation.json`
   (`unhealthy_required_services` empty).

Release checks (offline, `windows-latest`):

```powershell
python scripts/release/validate_package.py --source-root .
./tests/install/test_windows_bootstrap.ps1
install.bat --profile local-min --dry-run
install.bat --profile local-full --dry-run
node --test npm/test/supervisor.test.js npm/test/doctor.test.js
```

---

## 4. Linux installation (`install.sh`)

### 4.1 Quick command

```bash
git clone <repo-url> ~/Documentos/Projects/Hive-Mind
cd ~/Documentos/Projects/Hive-Mind
./install.sh
```

Headless / CI (without an interactive terminal):

```bash
HIVE_DREAMER_PROVIDER=google HIVE_DREAMER_MODEL=gemini-2.0-flash \
GOOGLE_API_KEY=<your_key> ./install.sh --non-interactive
```

### 4.2 What `install.sh` does (12 steps)

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

At the end, the installer asks whether to configure the LLM provider via
`setup-brain.sh` (Gemini, OpenAI, Anthropic, Ollama…). Answer **Y** and follow
the menu, then restart the agent.

### 4.3 User-level services (systemd)

The service installer
([runtime_services.py](../src/hive_mind/maintenance/runtime_services.py))
installs idempotent user-level units in `~/.config/systemd/user/` and enables
the safe timers (bridge, daily, weekly, topics, health, alert, decisions,
projects, patterns, conflicts, work, review, backup). The `dream` is **not**
enabled by default — its go-live is gated by M9 green ≥ 7 days. See
[runtime.md](runtime.md) §15.2.

### 4.4 WSL2

Hive-Mind runs well on WSL2 (Ubuntu 22.04+). `visual_capture.py` detects WSL2
and invokes the host's `powershell.exe` to capture the physical Windows screens.
Open `C:\Projects\Hive-Mind\cerebro` in the host's Obsidian to edit the vault
in real time.

---

## 5. Docker greenfield

Container deployment for a clean host, with no local Python/Node installation.

### 5.1 Components

| File | Role |
|---|---|
| `Dockerfile` | `python:3.12-slim` + `uv` image; copies the full source (`core/`, `scripts/`, `integrations/`, `plugins/`, `config/`, `templates/`); `uv sync --frozen --no-dev` |
| `docker-compose.yml` | Unified orchestration: FalkorDB + app (`local-min` core) + Milvus + RAGFlow (`--profile full`) |
| `docker/entrypoint.sh` | Materializes the vault on first volume run, then delegates to `hive-mindd` |

### 5.2 Vault materialization (first run)

`entrypoint.sh` replicates `materialize_vault()` from `install.sh` idempotently:

- If `vault-manifest.json` and `cortex/temporal` already exist → **does nothing**.
- Otherwise, copies `templates/vault/` to `cerebro/` and creates the complete
  anatomical tree (`cortex/{temporal,frontal,insula,occipital,parietal}`,
  `cerebelo/{diario,semanal,mensal,anual,sessoes,padroes}`,
  `diencefalo/{roteamento,setores}`, `tronco/infra`) + `.gitignore`.

### 5.3 Usage

```bash
docker build -t hive-mind .
docker compose up -d                     # local core: FalkorDB + app
docker compose --profile full up -d      # + Milvus + RAGFlow (production)
```

The `app` container runs the control-plane daemon in managed mode:

```dockerfile
CMD ["uv", "run", "hive-mindd", "run", "--serve", "--host", "0.0.0.0", "--port", "37780"]
```

Volumes and ports:

| Item | Mapping |
|---|---|
| `./cerebro` | `:/app/cerebro` (mounted vault) |
| `hive-mind-data` | `:/app/data` (hive_mind.db) |
| `./logs` | `:/app/logs` |
| `./config` | `:/app/config:ro` |
| `.env` | mounted only if it exists on the host (`env_file required: false`) |
| Ports | `37702` (API), `37780` (daemon HTTP) |

Container environment variables: `SINAPSE_HOME=/app`,
`FALKORDB_URL=redis://falkordb:6379`, `HIVE_MIND_API_KEY` (from the host).

> **Note:** the API (:37702) requires `HIVE_MIND_API_KEY` — fail-closed: without
> the key, the API does not start. See [security.md](security.md).

---

## 6. Post-install

1. **Configure the LLM per role** — `./scripts/setup/setup-brain.sh` (or
   `setup-brain.bat`) chooses the provider/model/API key of each role.
2. **Register the MCP** — `hive-mind agents register --apply --instructions`
   (see [cli.md](cli.md) §agents). Restart the agent.
3. **Validate** — `hive-mind doctor`, `hive-mind service status`,
   `sinapse_health`.
4. **Armed post-reboot validation** — `python -m
   hive_mind.maintenance.runtime_services arm-post-reboot` (POSIX).

---

## 7. Rollback and uninstall

### 7.1 Protected snapshot

The installer creates a verified snapshot in `backups/` **before** any mutation
(`create_install_snapshot`). On failure, the snapshot is the return point.

### 7.2 Uninstall (Windows)

```powershell
install.bat --uninstall --preserve-vault --preserve-database
```

`--preserve-vault` and `--preserve-database` keep the brain content; omitting
both removes the installation completely.

### 7.3 Re-register the agents

To register/unregister MCP without reinstalling everything:

```powershell
hive-mind agents register --only claude --apply     # or --only codex, etc.
hive-mind agents unregister --only claude --apply   # removes the entry
```

### 7.4 Restore Task Scheduler tasks

Job registration exports the previous XML to `logs/scheduled-tasks/` and
`~/.hive-mind/backups/windows-runtime/` before overwriting. To restore,
re-import the XML with `schtasks /create /tn <name> /xml <backup> /f`. See
[runtime.md](runtime.md) §15.1.

---

## 8. Cross-references

- **Runtime/daemon/scheduler**: [runtime.md](runtime.md)
- **Operations/maintenance**: [operations.md](operations.md)
- **Full CLI**: [cli.md](cli.md)
- **Windows acceptance**: [15-windows-clean-install.md](15-windows-clean-install.md)
- **Infra/ports/variables**: [04-infrastructure.md](04-infrastructure.md)
- **Architecture**: [architecture.md](architecture.md)
- **Security (fail-closed, keys)**: [security.md](security.md)
