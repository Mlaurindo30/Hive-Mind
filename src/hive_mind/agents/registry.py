"""Declarative provider registry (ADR-013).

One row per supported agent, describing how it is detected. Ported faithfully
from register-mcp.ps1's detection block: a provider is present when any of its
commands is on PATH, or any of its marker directories exists.

Marker paths are templates rooted at HOME (``~``) or APPDATA (``%APPDATA%``),
so detection is cross-platform and testable with injected roots.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConfigTarget:
    """Where a provider's MCP configuration lives.

    ``base`` selects the root the relative path hangs off: ``home``,
    ``appdata`` or ``project`` (the Hive-Mind project root).
    ``kind`` is ``json`` or ``toml``; ``root_key`` is the JSON object the
    server entry goes under.
    """

    base: str
    path: str
    kind: str = "json"
    root_key: str = "mcpServers"
    stdio_type: bool = False


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    commands: tuple[str, ...] = ()
    home_markers: tuple[str, ...] = ()
    appdata_markers: tuple[str, ...] = ()
    configs: tuple[ConfigTarget, ...] = ()
    # Instruction file this agent reads, relative to the project root.
    # Ported from Get-PromptTarget in register-mcp.ps1.
    prompt_target: str | None = None


_VSCODE_STORAGE = "Code/User/globalStorage"

PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        "claude", "Claude Code", commands=("claude",),
        prompt_target="CLAUDE.md",
        configs=(
            ConfigTarget("home", ".claude.json"),
            ConfigTarget("project", ".mcp.json"),
        ),
    ),
    ProviderSpec(
        "codex", "Codex", commands=("codex",),
        prompt_target="AGENTS.md",
        configs=(
            ConfigTarget("home", ".codex/config.toml", kind="toml"),
            ConfigTarget("home", ".codex/mcp.json"),
        ),
    ),
    ProviderSpec(
        "gemini", "Gemini CLI", commands=("gemini",),
        prompt_target="GEMINI.md",
        configs=(ConfigTarget("home", ".gemini/settings.json"),),
    ),
    ProviderSpec(
        "qwen", "Qwen Code", commands=("qwen",), home_markers=(".qwen",),
        prompt_target="AGENTS.md",
        configs=(ConfigTarget("home", ".qwen/settings.json"),),
    ),
    ProviderSpec(
        "kimi", "Kimi Code", commands=("kimi",), home_markers=(".kimi",),
        prompt_target="AGENTS.md",
        configs=(ConfigTarget("home", ".kimi/mcp.json"),),
    ),
    ProviderSpec(
        "kiro", "Kiro", commands=("kiro",), home_markers=(".kiro",),
        prompt_target="AGENTS.md",
        configs=(ConfigTarget("home", ".kiro/settings/mcp.json"),),
    ),
    ProviderSpec(
        "kilo",
        "Kilo Code",
        prompt_target="AGENTS.md",
        home_markers=(".kilocode",),
        appdata_markers=(f"{_VSCODE_STORAGE}/kilocode.kilo-code",),
        configs=(
            ConfigTarget(
                "appdata",
                f"{_VSCODE_STORAGE}/kilocode.kilo-code/settings/mcp_settings.json",
            ),
        ),
    ),
    ProviderSpec(
        "roo",
        "Roo Cline",
        prompt_target="AGENTS.md",
        appdata_markers=(f"{_VSCODE_STORAGE}/rooveterinaryinc.roo-cline",),
        configs=(
            ConfigTarget(
                "appdata",
                f"{_VSCODE_STORAGE}/rooveterinaryinc.roo-cline/settings/mcp_settings.json",
            ),
        ),
    ),
    ProviderSpec(
        "vscode",
        "VS Code (Copilot Chat)",
        prompt_target=".github/copilot-instructions.md",
        commands=("code",),
        appdata_markers=(f"{_VSCODE_STORAGE}/github.copilot-chat",),
        configs=(
            ConfigTarget(
                "project", ".vscode/mcp.json", root_key="servers", stdio_type=True
            ),
        ),
    ),
    ProviderSpec(
        "cursor", "Cursor", home_markers=(".cursor",),
        prompt_target=".cursor/rules/hive-mind.md",
        configs=(ConfigTarget("home", ".cursor/mcp.json"),),
    ),
    ProviderSpec(
        "opencode", "OpenCode", commands=("opencode",),
        prompt_target="AGENTS.md",
        configs=(ConfigTarget("home", ".opencode/mcp.json"),),
    ),
    ProviderSpec(
        "openclaw", "OpenClaw", commands=("openclaw",),
        prompt_target="AGENTS.md",
        configs=(ConfigTarget("home", ".openclaw/openclaw.json"),),
    ),
    # SwarmClaw stores its config in a SQLite database, not a JSON/TOML file;
    # it has no declarative config target here.
    ProviderSpec(
        "swarmclaw", "SwarmClaw", commands=("swarmclaw",), home_markers=(".swarmclaw",)
    ),
)


def config_targets(spec: ProviderSpec) -> tuple[ConfigTarget, ...]:
    return spec.configs


def provider_ids() -> list[str]:
    return [p.id for p in PROVIDERS]


def get_provider(provider_id: str) -> ProviderSpec:
    for spec in PROVIDERS:
        if spec.id == provider_id:
            return spec
    raise KeyError(provider_id)
