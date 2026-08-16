# Agent registration (MCP)

How Hive-Mind is registered in an AI agent. Target audience: those who install,
administer, or diagnose Hive-Mind's integration with external agents.

Registering Hive-Mind in an agent means **three things**:

1. adding the `sinapse-memory` MCP server to the agent's configuration;
2. optionally, installing the operational instruction block into the agent's
   prompt file;
3. being able to verify or undo either one.

All of that is `hive-mind agents`.

---

## A single implementation

Until delivery D009-R6 the registration lived **duplicated** —
`scripts/setup/register-mcp.ps1` (456 lines) and
`scripts/setup/register-mcp.sh` (444 lines) — and the two diverged. The `.sh`
kept re-linking an obsolete capture path that the `.ps1` had already removed;
the `.ps1` supported three targets while the `.sh` supported thirteen.

Today the two are **wrappers**: they locate the `hive-mind` executable, forward
the arguments, preserve `stdout` and `stderr`, and return the exit code. Nothing
more. The behavior lives in `src/hive_mind/agents/`, so there is **one answer
per question**, regardless of platform.

```bash
./scripts/setup/register-mcp.sh --only codex --apply       # POSIX
```

```powershell
python scripts/setup/register_mcp.py --only codex --apply  # Windows
```

```bash
hive-mind agents register --only codex --apply             # the real command
```

The translation of the old options (compatibility) lives in
`src/hive_mind/agents/compat.py`, not in the wrappers.

---

## Commands

| Command | What it does |
|---|---|
| `hive-mind agents detect` | discovers which agents are installed on this machine |
| `hive-mind agents list` | lists all providers the registry knows |
| `hive-mind agents register` | adds the MCP server — **only reports, except with `--apply`** |
| `hive-mind agents doctor` | read-only diagnosis; writes nothing |
| `hive-mind agents unregister` | removes the Hive-Mind entry — `--apply` to write |

### Nothing is written unless you ask

`register` and `unregister` are **dry-run by default**. This differs from the old
scripts, which wrote immediately. The callers that relied on the old default —
`install.ps1`, `install.sh`, `npm/bin/hive-mind.js` — now pass `--apply`
explicitly, so that the intent is visible at the call site instead of implicit
in a default.

---

## Options

Every option the old scripts accepted still works, because callers still use
them.

| Option | Meaning |
|---|---|
| `--only <agent>` (also `--self`, `--agent`, or a bare agent name) | one provider instead of all detected |
| `--apply` | actually write |
| `--instructions` | also install the managed instruction block |
| `--no-instructions`, `HIVE_SKIP_PROMPT=1` | never touch the prompt files |
| `--check` | diagnose only (routes to `doctor`) |
| `--list` | print the valid agent keys |
| `--claude-only`, `--codex-only` | shortcuts the PowerShell script had |
| `--project-root <path>` | resolve the project files from somewhere else |
| `--json` | machine-readable output |

Valid agent keys:

```
claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode openclaw swarmclaw
```

---

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success; for `--check` / `doctor`, **every detected provider** is fully configured |
| 1 | the diagnosis is incomplete — something detected is not configured |
| 2 | unknown agent key |

An agent that is **not installed** is not a failure: there is nothing to
configure for an absent provider. A new machine with no agents exits 0. A
machine with agents that were never registered exits 1 — which is the honest
answer, and the reason the old contract (`--check` always exited 0) was
replaced. That contract made `--check` useless as a gate.

---

## What the registration touches

| Provider | Config | Prompt file |
|---|---|---|
| claude | `~/.claude.json`, `.mcp.json` | `CLAUDE.md` |
| codex | `~/.codex/config.toml`, `~/.codex/mcp.json` | `AGENTS.md` |
| gemini | `~/.gemini/settings.json` | `GEMINI.md` |
| vscode | `.vscode/mcp.json` (root key `servers`, `type: stdio`) | `.github/copilot-instructions.md` |
| cursor | `~/.cursor/mcp.json` | `.cursor/rules/hive-mind.md` |
| others | see `hive-mind agents list` | — |

### Transactional writes

The writes are transactional:

1. the file is **parsed before** any write;
2. an existing file is copied to a `*.hive-bak` backup;
3. the new content goes to a **temporary file on the same volume** and is
   renamed into place;
4. the result is **re-parsed**.

A configuration that fails to parse is **refused** instead of being written
halfway.

### What is registered

Only the `sinapse-memory` orchestrator is registered. It federates the raw
backends internally, so `claude-mem-local` and `neural-memory-local` are
**removed** if an older installation left them behind. Third-party MCP servers
are **never touched**.

### Delimited instruction block

The instruction block is delimited by
`<!-- BEGIN HIVE-MIND SINAPSE -->` / `<!-- END HIVE-MIND SINAPSE -->`.
Re-running **replaces** the block instead of appending a second one, including
blocks written by the PowerShell-era script. Everything outside the markers is
yours and is preserved.

---

## Undo

```bash
hive-mind agents unregister --only codex --apply                  # config only
hive-mind agents unregister --only codex --apply --instructions   # and the prompt block
```

Only the `sinapse-memory` entry is removed. Third-party servers, unrelated
config keys, TOML comments, and your own prompt text **survive** — verified in
`tests/integration/test_registration_through_wrappers.py`.

---

## Related

- [installation.md](installation.md) — where registration fits into a complete installation
- [capture.md](capture.md) — what the hooks/parsers capture (independent of MCP registration)
- [cli.md](cli.md) — the native CLI of which `agents` is a subgroup
- [development.md](development.md) — how to test changes to the registration
-  — D009-R6
