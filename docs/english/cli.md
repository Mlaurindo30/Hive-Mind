# CLI — `hive-mind`

> **Hive-Mind v3.10.1** — complete reference of the native control-plane CLI.
> Entry point: [cli.py](../src/hive_mind/cli.py) (argparse). The version comes
> from `pyproject.toml::project.version` via `importlib.metadata` (single source
> of truth, matched to the wheel).
>
> References: [runtime.md](runtime.md) (daemon/services/scheduler),
> [installation.md](installation.md), [operations.md](operations.md).

---

## 1. Overview

```powershell
hive-mind --version            # "hive-mind 3.10.1"
hive-mind --help               # parser help
hive-mind <command> [subcommand] [options]
```

Cross-cutting CLI principles:

- **Dry-run by default** on everything that mutates: `register`/`unregister`,
  `windows-jobs`, `windows-runtime`, `backup run`, `vault repair-*`,
  `backup scrub-*`, `projects migrate-legacy`, `archive-topology`. Nothing is
  written without `--apply`.
- **`--json`** on almost every subcommand for machine-readable output.
- **`--project-root <dir>`** to resolve the project files from elsewhere
  (default: auto-detection — see §1.1).

### 1.1 Project root resolution

Resolution tries, in order: `--project-root` → `HIVE_MIND_HOME` (or
`SINAPSE_HOME`) → the `project-root` file in the user config dir → walking up
directories from the CWD looking for markers (`pyproject.toml`, `AGENTS.md`,
`config/sinapse.yaml`; ≥ 2 present). Fails with `ProjectRootNotFound` and exit
`78` (`EX_CONFIG`).

### 1.2 Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. In `doctor`/`--check`: every **detected** provider is configured |
| `1` | Incomplete diagnostics / failure / missing file |
| `2` | Unknown agent key / invalid usage |
| `69` | `EX_UNAVAILABLE` (managed daemon not implemented in the slice) |
| `78` | `EX_CONFIG` (project root not resolved) |

---

## 2. Master command table

| Group | Subcommands | Purpose |
|---|---|---|
| `project-root` | — | Prints the resolved project root |
| `projects` | `audit`, `migrate-legacy` | Inspects/migrates canonical project identity |
| `config` | `validate`, `show` | Declarative manifest `config/runtime.yaml` |
| `service` | `status`, `ping`, `windows-jobs`, `windows-runtime`, `manifest` | Daemon state and Windows tasks |
| `doctor` | — | Read-only diagnostics of agent integrations |
| `agents` | `detect`, `list`, `register`, `doctor`, `unregister` | Detection and management of agent integrations |
| `validate` | `agents`, `delivery`, `topology`, `vault` | Pipeline validation against real data |
| `vault` | `repair-frontmatter`, `repair-project-id`, `repair-encoding` | Controlled vault maintenance |
| `backup` | `run`, `status`, `verify`, `restore`, `archive-historical-outbox`, `scrub-capture-outbox`, `scrub-runtime-artifacts`, `scrub-env-backups`, `archive-topology`, `cleanup-topology-stale` | Verified backup + legacy data sanitation |
| `implementation` | `status`, `validate` | State/currency of the implementation documents |

---

## 3. `hive-mind project-root`

```powershell
hive-mind project-root [--project-root <dir>]
```

Prints the absolute path of the resolved project root. Exit `78` if it does not
resolve.

---

## 4. `hive-mind projects`

### 4.1 `projects audit`

**Read-only** inventory of legacy project labels (does not alter data).

| Option | Description |
|---|---|
| `--claude-mem-db <path>` | claude-mem SQLite (read-only) |
| `--hive-db <path>` | Hive-Mind SQLite (read-only) |
| `--vault-root <path>` | Markdown vault root (read-only) |
| `--registry <path>` | Canonical registry of project aliases |
| `--json` | JSON |

### 4.2 `projects migrate-legacy`

Controlled migration of legacy UMC rows — **dry-run by default**.

| Option | Description |
|---|---|
| `--claude-mem-db <path>` | claude-mem SQLite to recover preserved session labels |
| `--hive-db <path>` | Hive-Mind SQLite to inspect/mutate |
| `--registry <path>` | Canonical alias registry |
| `--source-workspace <w>` | Legacy bucket to inspect (default `unclassified/legacy`) |
| `--target-project <id>` | Restricts to a single canonical `project_id` |
| `--apply` | Rewrites the matching rows (default: dry-run) |
| `--json` | JSON |

---

## 5. `hive-mind config`

### 5.1 `config validate`

```powershell
hive-mind config validate [--manifest <file>]
```

Validates `config/runtime.yaml` (schema v3, Pydantic v2). Rejects nonexistent
dependencies, self-references, and cycles. Prints `Manifest valid.` and exits
`0`; otherwise lists the errors on stderr and exits `1`.

### 5.2 `config show`

```powershell
hive-mind config show [--manifest <file>] [--json]
```

Prints the normalized manifest (YAML by default, JSON with `--json`).

---

## 6. `hive-mind service`

### 6.1 `service status`

```powershell
hive-mind service status [--state-dir <dir>] [--project-root <dir>] [--json]
```

Reads the daemon state (managed → control socket → legacy Node supervisor state)
and prints `mode`, `profile`, `required`, and, per service: `ownership`,
`required`, `readiness`, `startup_order`. Without state, it exits `1` with a
clear message — it never invents "healthy".

### 6.2 `service ping`

```powershell
hive-mind service ping [--state-dir <dir>] [--project-root <dir>]
```

Pings the daemon control socket (3s timeout). Prints `pong` and exits `0` if
alive; `1` if unreachable.

### 6.3 `service windows-jobs`

```powershell
hive-mind service windows-jobs [--project-root <dir>] [--backup-dir <dir>] [--apply] [--json]
```

Registers the scheduled knowledge tasks in Task Scheduler (`HiveMind-DreamCycle`,
`HiveMind-ClaudeMemBridge`, `HiveMind-KnowledgeHealth`, `HiveMind-Backup`, and
the cadence jobs). Dry-run by default; `--apply` writes. Exports the previous
XML to `logs/scheduled-tasks/` (rollback). See [runtime.md](runtime.md) §15.1.

### 6.4 `service windows-runtime`

```powershell
hive-mind service windows-runtime [--project-root <dir>] [--apply] [--json]
```

Registers the runtime tasks `HiveMind-Supervisor` and
`HiveMind-PostRebootValidation` (`logon` trigger). Dry-run by default; `--apply`
writes with a transactional backup of the previous definitions in
`.hive-mind/backups/windows-runtime/`.

### 6.5 `service manifest`

```powershell
hive-mind service manifest [--project-root <dir>] [--json]
```

Emits the native service manifest (`manifest_version`, `root`,
`claude_mem_plugin_available`, service list) for the Node supervisor.

---

## 7. `hive-mind doctor`

```powershell
hive-mind doctor [--only <id>|--self <id>|--agent <id>] [--project-root <dir>] [--json]
```

**Read-only** diagnostics of agent integrations (writes nothing). Equivalent to
`hive-mind agents doctor`. Exit `0` only when every **detected** provider is
fully configured; `1` if something detected is incomplete. An uninstalled agent
is **not** a failure.

---

## 8. `hive-mind agents`

Single implementation in `src/hive_mind/agents/` (D009-R6). Valid agent keys:
`claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode openclaw
swarmclaw`.

### 8.1 `agents detect`

```powershell
hive-mind agents detect [--json]
```

Detects which agents are installed on this machine (with evidence).

### 8.2 `agents list`

```powershell
hive-mind agents list [--json]
```

Lists all providers the registry knows (`id` + `name`).

### 8.3 `agents register`

```powershell
hive-mind agents register [<provider>] [--only <id>] [--apply] [--instructions]
                          [--project-root <dir>] [--json]
```

Registers the `sinapse-memory` MCP server in the detected providers. **Reports
only, unless `--apply`.** `--instructions` also installs the managed block
(`config/sinapse-agent-prompt.md`).

Compatibility flags (from `compat.py`): `--self`/`--agent` (same as `--only`),
`--check` (routes to `doctor`), `--list` (prints the valid keys),
`--no-instructions`, `--claude-only`, `--codex-only`.

### 8.4 `agents doctor`

```powershell
hive-mind agents doctor [--only <id>] [--project-root <dir>] [--json]
```

Same as the top-level `doctor` (§7).

### 8.5 `agents unregister`

```powershell
hive-mind agents unregister [--only <id>] [--apply] [--instructions] [--project-root <dir>] [--json]
```

Removes the Hive-Mind entry from the provider config. `--apply` to write;
`--instructions` also removes the instructions block. Removes only the
`sinapse-memory` entry; third-party servers and own text are preserved.

### 8.6 What registration touches

| Provider | Config | Prompt file |
|---|---|---|
| claude | `~/.claude.json`, `.mcp.json` | `CLAUDE.md` |
| codex | `~/.codex/config.toml`, `~/.codex/mcp.json` | `AGENTS.md` |
| gemini | `~/.gemini/settings.json` | `GEMINI.md` |
| vscode | `.vscode/mcp.json` (`servers`, `type: stdio`) | `.github/copilot-instructions.md` |
| cursor | `~/.cursor/mcp.json` | `.cursor/rules/hive-mind.md` |
| others | see `agents list` | — |

Writes are transactional: parse before writing, backup to `*.hive-bak`, temp
file on the same volume, atomic rename, re-parse. Config that fails parsing is
rejected, never half-written.

---

## 9. `hive-mind validate`

### 9.1 `validate agents`

```powershell
hive-mind validate agents [--only <id>...] [--marker <m> --since <epoch>] [--json]
```

Multi-agent capture canary over real sources and real delivery state
(read-only). With `--marker`/`--since`/`--only`, it validates a fresh marker
chain already emitted by the provider (without running it). Exits `0` if the
report is `ok`.

### 9.2 `validate delivery`

```powershell
hive-mind validate delivery [--outbox-db <path>] [--hive-db <path>] [--json]
```

Inspects legacy UMC buckets and the historical capture backlog (read-only):
`outbox` (total/delivered/undelivered/dead_letter), `umc`
(observations/canonical/legacy), `recovery` (bridged recoverable sessions).

### 9.3 `validate topology`

```powershell
hive-mind validate topology [--project-root <dir>] [--json]
```

Inventories worktrees/copies and suggests a safe cleanup disposition
(read-only): `classification`, `disposition`, `exists`, `dirty`, `branch`,
`head`, `reason`.

### 9.4 `validate vault`

```powershell
hive-mind validate vault [--vault-root <dir>] [--json]
```

Audits vault Markdown/links/encoding (read-only): `total_md`, `empty_md`,
`invalid_frontmatter`, `missing_project_id`, `mojibake_files`,
`broken_wikilinks`, `orphan_notes`.

---

## 10. `hive-mind vault`

Controlled vault maintenance. All **dry-run by default**; `--apply` rewrites the
candidate notes.

| Command | What it does |
|---|---|
| `vault repair-frontmatter [--vault-root <d>] [--apply] [--json]` | Repairs invalid legacy YAML frontmatter |
| `vault repair-project-id [--vault-root <d>] [--apply] [--json]` | Repairs missing `project_id` in legacy temporal neurons |
| `vault repair-encoding [--vault-root <d>] [--apply] [--json]` | Repairs legacy cp1252 bytes preserved in Markdown notes |

---

## 11. `hive-mind backup`

Verified SQLite backup + legacy data sanitation. `run` and the `scrub-*` /
`archive-*` are dry-run by default. See [operations.md](operations.md) §2 and
[operations.md](operations.md).

| Command | Options | What it does |
|---|---|---|
| `backup run` | `--apply`, `--json` | Creates a verified backup (dry-run without `--apply`) |
| `backup status` | `--json` | Lists existing backups and per-component coverage |
| `backup verify` | `--manifest <p>`, `--json` | Re-verifies a backup manifest |
| `backup restore` | `--manifest <p>`, `--into <d>`, `--overwrite-live`, `--json` | Restores to an alternate directory (never in-place by default) |
| `backup archive-historical-outbox` | `--outbox-db <p>`, `--cutoff-occurred-at <iso>`, `--apply`, `--json` | Archives inert `capture_outbox` rows |
| `backup scrub-capture-outbox` | `--outbox-db <p>`, `--apply`, `--json` | Redacts secrets from the legacy capture outbox |
| `backup scrub-runtime-artifacts` | `--project-root <d>`, `--apply`, `--json` | Redacts secrets from log/audit artifacts |
| `backup scrub-env-backups` | `--project-root <d>`, `--apply`, `--json` | Redacts legacy `.env` secrets in `backups/` |
| `backup archive-topology` | `--project-root <d>`, `--archive-root <d>`, `--apply`, `--json` | Archives topology paths classified ARCHIVE |
| `backup cleanup-topology-stale` | `--project-root <d>`, `--archive-root <d>`, `--apply`, `--json` | Archives/removes stale `REMOVE_AFTER_APPROVAL` residue |

---

## 12. `hive-mind implementation`

```powershell
hive-mind implementation status [--json]      # dashboard derived from git + docs
hive-mind implementation validate             # fails if a doc disagrees with the repo
```

`status` exits `1` if there are findings; `validate` lists divergences between
the implementation documents and the repository.

---

## 13. Common flags

| Flag | Where | Meaning |
|---|---|---|
| `--json` | almost everywhere | Machine-readable output |
| `--apply` | mutations | Performs the write (default is dry-run) |
| `--project-root <d>` | cross-cutting | Resolves project files from elsewhere |
| `--only <id>` / `--self` / `--agent` | agents/doctor/validate | Restricts to one provider |
| `--instructions` / `--no-instructions` | agents register/unregister | Managed instructions block |
| `--check` | agents register | Diagnostics (routes to `doctor`) |

---

## 14. Cross-references

- **Daemon and services** (what the CLI inspects): [runtime.md](runtime.md)
- **Installation** (CLI usage in install): [installation.md](installation.md)
- **Operations** (routines with the CLI): [operations.md](operations.md)
- **Agents** (registration/detection): [agents.md](agents.md)
- **Data pipeline** (`validate`, `projects`): [data-pipeline.md](data-pipeline.md)
- **Security** (`backup scrub-*`, fail-closed): [security.md](security.md)
