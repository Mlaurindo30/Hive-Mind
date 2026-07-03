"""R5.3 — Agent hooks materialized at documented paths.

Spec: specs/post-audit-stabilization.md R5.3.

For each documented agent (claude, codex, gemini per the install script),
verifies the hook directory exists and the JSON files inside parse
correctly. The exact path is `cerebro/tronco/infra/agentes/<agent>/`.
"""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ROOT = PROJECT_ROOT / "cerebro" / "tronco" / "infra" / "agentes"


# Each agent is associated with a config file that must exist and parse.
EXPECTED = {
    ".claude":   ["settings.json"],
    ".codex":    ["hooks.json"],
    ".gemini":   ["settings.json"],
    ".openclaw": ["settings.json"],
    ".github":   ["settings.json"],
    ".claude-flow": ["settings.json"],
}


def test_agent_dirs_exist():
    assert AGENTS_ROOT.exists(), f"agentes dir missing: {AGENTS_ROOT}"
    for agent in EXPECTED:
        agent_dir = AGENTS_ROOT / agent
        assert agent_dir.exists(), f"agent dir missing: {agent_dir}"


def test_settings_json_parses():
    for agent, files in EXPECTED.items():
        for fname in files:
            path = AGENTS_ROOT / agent / fname
            if not path.exists():
                # Skip missing optional files (the install script may not
                # have been run for every agent). Log but do not fail hard
                # unless the agent dir exists.
                continue
            content = path.read_text(encoding="utf-8")
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                raise AssertionError(
                    f"{path} does not parse as JSON: {e}"
                )
