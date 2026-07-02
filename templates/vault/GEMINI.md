# Sinapse Agent — Vault (Gemini CLI)

> Template: [obsidian-mind](https://github.com/breferrari/obsidian-mind).
> Stack: Graphify + claude-mem + RTK.
> Agent principal: Thoth (Michel's AI agent).

This vault is built for multiple AI coding agents. The primary operating manual is `AGENTS.md` (cross-agent). Claude Code reads `CLAUDE.md` automatically.

## Hooks

The hook scripts in `tronco/infra/agentes/.claude/scripts/` are agent-agnostic TypeScript and shell, executed natively by Node via `--experimental-strip-types` — no build step, no runtime dependencies, no Claude SDK. Hook configs are provided for three agents:

| Agent | Config | Status |
|-------|--------|--------|
| Claude Code | `tronco/infra/agentes/.claude/settings.json` | Full support |
| Codex CLI | `tronco/infra/agentes/.codex/hooks.json` | Shared hook scripts |
| Gemini CLI | `tronco/infra/agentes/.gemini/settings.json` | Shared hook scripts |

| Script | Purpose | Claude event | Codex event | Gemini event |
|--------|---------|--------------|-------------|--------------|
| `session-start.ts` | Inject vault context at startup | SessionStart | SessionStart | SessionStart |
| `classify-message.ts` | Classify messages, inject routing hints | UserPromptSubmit | UserPromptSubmit | BeforeAgent |
| `validate-write.ts` | Validate frontmatter and wikilinks | PostToolUse | PostToolUse | AfterTool |
| `pre-compact.ts` | Back up transcript before compaction | PreCompact | — | PreCompress |

## Commands

18 commands in `tronco/infra/agentes/.claude/commands/` — agent-agnostic markdown with YAML frontmatter.

- **Claude Code / Gemini CLI**: invoke as `/om-standup`, `/om-dump`, etc.
- **Codex CLI**: type the command name as a regular prompt without the `/` prefix (e.g. `om-standup`). Codex will find and execute the command file.

## Memory

The vault's memory lives in `brain/` — `Memories.md`, `Patterns.md`, `Key Decisions.md`, `Gotchas.md`. These are plain markdown files that any agent can read and write. When you learn something worth remembering, write it to the relevant `brain/` topic note with a wikilink to context.

The `~/.claude/` auto-loaded memory index is Claude Code-specific — skip that section in `CLAUDE.md`. The vault-side `brain/` notes are the source of truth.

## Subagents

9 subagents in `tronco/infra/agentes/.claude/agents/` handle isolated tasks (brag spotting, vault auditing, cross-linking, etc.). The prompt content is agent-agnostic markdown. Codex CLI (`tronco/infra/agentes/.codex/agents/`) and Gemini CLI (`tronco/infra/agentes/.gemini/agents/`) support the same pattern — copy the files and adapt the YAML frontmatter fields to your agent's schema.

## What's Claude Code-specific

Only the `~/.claude/` auto-memory loader is truly Claude Code-specific. Everything else — hooks, commands, subagent prompts, vault memory — is portable.

## Setup

**Codex CLI**: Reads `AGENTS.md` natively. For direct access to `CLAUDE.md`, add to `~/.codex/config.toml`:
```toml
project_doc_fallback_filenames = ["CLAUDE.md"]
```

**Gemini CLI**: Reads `GEMINI.md` natively. For direct access to `CLAUDE.md`, add to `~/.gemini/settings.json`:
```json
{ "context": { "fileName": ["GEMINI.md", "CLAUDE.md"] } }
```

**Other agents** (Cursor, Windsurf, Copilot): Read `AGENTS.md` for vault conventions. Hook support varies by agent.

For more information, see the [README](README.md).
