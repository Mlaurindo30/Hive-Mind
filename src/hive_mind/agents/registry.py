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
class ProviderSpec:
    id: str
    name: str
    commands: tuple[str, ...] = ()
    home_markers: tuple[str, ...] = ()
    appdata_markers: tuple[str, ...] = ()


_VSCODE_STORAGE = "Code/User/globalStorage"

PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec("claude", "Claude Code", commands=("claude",)),
    ProviderSpec("codex", "Codex", commands=("codex",)),
    ProviderSpec("gemini", "Gemini CLI", commands=("gemini",)),
    ProviderSpec("qwen", "Qwen Code", commands=("qwen",), home_markers=(".qwen",)),
    ProviderSpec("kimi", "Kimi Code", commands=("kimi",), home_markers=(".kimi",)),
    ProviderSpec("kiro", "Kiro", commands=("kiro",), home_markers=(".kiro",)),
    ProviderSpec(
        "kilo",
        "Kilo Code",
        home_markers=(".kilocode",),
        appdata_markers=(f"{_VSCODE_STORAGE}/kilocode.kilo-code",),
    ),
    ProviderSpec(
        "roo",
        "Roo Cline",
        appdata_markers=(f"{_VSCODE_STORAGE}/rooveterinaryinc.roo-cline",),
    ),
    ProviderSpec(
        "vscode",
        "VS Code (Copilot Chat)",
        commands=("code",),
        appdata_markers=(f"{_VSCODE_STORAGE}/github.copilot-chat",),
    ),
    ProviderSpec("cursor", "Cursor", home_markers=(".cursor",)),
    ProviderSpec("opencode", "OpenCode", commands=("opencode",)),
    ProviderSpec("openclaw", "OpenClaw", commands=("openclaw",)),
    ProviderSpec(
        "swarmclaw", "SwarmClaw", commands=("swarmclaw",), home_markers=(".swarmclaw",)
    ),
)


def provider_ids() -> list[str]:
    return [p.id for p in PROVIDERS]


def get_provider(provider_id: str) -> ProviderSpec:
    for spec in PROVIDERS:
        if spec.id == provider_id:
            return spec
    raise KeyError(provider_id)
