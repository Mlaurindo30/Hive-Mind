# Agent registration

Registering Hive-Mind with an AI agent means three things: adding the
`sinapse-memory` MCP server to that agent's config, optionally installing the
operational instruction block into its prompt file, and being able to check or
undo either. All of it is `hive-mind agents`.

## One implementation

Until D009-R6 this lived twice — `scripts/setup/register-mcp.ps1` (456 lines)
and `scripts/setup/register-mcp.sh` (444 lines) — and the two diverged. The
`.sh` kept re-wiring a deprecated capture path the `.ps1` had dropped; the
`.ps1` supported three targets where the `.sh` supported thirteen.

Both are now wrappers. They locate the `hive-mind` executable, forward their
arguments, preserve stdout and stderr, and return the exit code. Nothing else.
The behaviour is in `src/hive_mind/agents/`, so there is one answer per
question regardless of platform.

```bash
./scripts/setup/register-mcp.sh --only codex --apply     # POSIX
```
```powershell
./scripts/setup/register-mcp.ps1 --only codex --apply    # Windows
```
```bash
hive-mind agents register --only codex --apply           # the actual command
```

## Commands

| Command | What it does |
|---|---|
| `hive-mind agents detect` | which agents are installed on this machine |
| `hive-mind agents list` | every provider the registry knows |
| `hive-mind agents register` | add the MCP server — **reports only, unless `--apply`** |
| `hive-mind agents doctor` | read-only diagnosis; writes nothing |
| `hive-mind agents unregister` | remove the Hive-Mind entry — `--apply` to write |

### Nothing is written unless you ask

`register` and `unregister` are dry-run by default. This differs from the old
scripts, which wrote immediately. The callers that relied on the old default —
`install.ps1`, `install.sh`, `npm/bin/hive-mind.js` — now pass `--apply`
explicitly, so the intent is visible at the call site instead of implied by a
default.

### Options

Every option the old scripts accepted still works, because the callers still
use them. The translation lives in `src/hive_mind/agents/compat.py`, not in
the wrappers.

| Option | Meaning |
|---|---|
| `--only <agent>` (also `--self`, `--agent`, or a bare agent name) | one provider instead of all detected |
| `--apply` | actually write |
| `--instructions` | also install the managed instruction block |
| `--no-instructions`, `HIVE_SKIP_PROMPT=1` | never touch prompt files |
| `--check` | diagnose only (routes to `doctor`) |
| `--list` | print the valid agent keys |
| `--claude-only`, `--codex-only` | shorthands the PowerShell script had |
| `--project-root <path>` | resolve project files from somewhere else |
| `--json` | machine-readable output |

Valid agent keys: `claude codex gemini qwen kimi kiro kilo roo vscode cursor
opencode openclaw swarmclaw`.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success; for `--check` / `doctor`, every **detected** provider is fully configured |
| 1 | the diagnosis is incomplete — something detected is not configured |
| 2 | unknown agent key |

An agent that is not installed is not a failure: there is nothing to configure
for an absent provider. A fresh machine with no agents exits 0. A machine with
agents that were never registered exits 1 — which is the honest answer, and
why the old contract (`--check` always exits 0) was replaced. That contract
made `--check` useless as a gate.

## What registration touches

| Provider | Config | Prompt file |
|---|---|---|
| claude | `~/.claude.json`, `.mcp.json` | `CLAUDE.md` |
| codex | `~/.codex/config.toml`, `~/.codex/mcp.json` | `AGENTS.md` |
| gemini | `~/.gemini/settings.json` | `GEMINI.md` |
| vscode | `.vscode/mcp.json` (root key `servers`, `type: stdio`) | `.github/copilot-instructions.md` |
| cursor | `~/.cursor/mcp.json` | `.cursor/rules/hive-mind.md` |
| others | see `hive-mind agents list` | — |

Writes are transactional: the file is parsed before anything is written, an
existing file is backed up to `*.hive-bak`, the new content goes to a temp file
on the same volume and is renamed into place, and the result is re-parsed. A
config that fails to parse is refused rather than half-written.

Only the `sinapse-memory` orchestrator is registered. It federates the raw
backends internally, so `claude-mem-local` and `neural-memory-local` are
removed if an older install left them behind. Third-party MCP servers are never
touched.

The instruction block is delimited by `<!-- BEGIN HIVE-MIND SINAPSE -->` /
`<!-- END HIVE-MIND SINAPSE -->`. Re-running replaces the block instead of
appending a second one, including blocks written by the PowerShell-era script.
Everything outside the markers is yours and is preserved.

## Undo

```bash
hive-mind agents unregister --only codex --apply                  # config only
hive-mind agents unregister --only codex --apply --instructions   # and the prompt block
```

Only the `sinapse-memory` entry is removed. Third-party servers, unrelated
config keys, TOML comments and your own prompt text all survive — verified in
`tests/integration/test_registration_through_wrappers.py`.

## Related

- [installation.md](installation.md) — where registration fits in a full install
- [implementation/DELIVERY-LEDGER.md](implementation/DELIVERY-LEDGER.md) — D009-R6
