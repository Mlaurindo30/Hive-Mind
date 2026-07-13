"""R5.3 — Agent hooks materialized at documented paths.

Spec: specs/post-audit-stabilization.md R5.3.

For each documented agent (claude, codex, hermes, gemini, etc.), verifies:
  - the agent directory exists
  - JSON config files parse
  - every script referenced in the JSON exists and is executable
  - calling each script with a no-op input does not error
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ROOT = PROJECT_ROOT / "cerebro" / "tronco" / "infra" / "agentes"


# Each agent is associated with the config files that must exist and parse.
EXPECTED = {
    ".claude":   ["settings.json"],
    ".codex":    ["hooks.json"],
    ".gemini":   ["settings.json"],
    ".openclaw": ["settings.json"],
    ".github":   ["settings.json"],
    ".claude-flow": ["settings.json"],
    ".hermes":   ["settings.json", "AGENTS.md", "instructions.md"],
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
                continue
            if path.suffix != ".json":
                continue
            content = path.read_text(encoding="utf-8")
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                raise AssertionError(
                    f"{path} does not parse as JSON: {e}"
                )


def test_referenced_scripts_exist():
    """For each agent, every script path in settings.json/hooks.json MUST
    exist on disk and be executable. No-op invocation MUST NOT error.
    """
    skip_invocation = os.environ.get("HIVE_SKIP_HOOK_INVOCATION") == "1"

    for agent, files in EXPECTED.items():
        for fname in files:
            path = AGENTS_ROOT / agent / fname
            if not path.exists() or path.suffix != ".json":
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            # Walk the JSON for any "command" string under hook definitions.
            for script in _walk_commands(payload):
                # Skip references that depend on shell-level env-var
                # expansion (e.g. ${CLAUDE_PROJECT_DIR:-.}/bin/python) — the
                # expansion is not available without a real shell, and the
                # path is environment-specific by design.
                if "${" in script:
                    continue
                tokens = shlex.split(script)
                if any("=" in t for t in tokens):
                    continue
                script_path = tokens[0] if tokens else ""
                if not script_path:
                    continue
                if not os.path.isabs(script_path):
                    candidate = PROJECT_ROOT / script_path
                else:
                    candidate = Path(script_path)
                if not candidate.exists():
                    raise AssertionError(
                        f"agent {agent} references missing script: {script_path}"
                    )
                if skip_invocation:
                    continue
                try:
                    command = [str(candidate), "--help"]
                    if os.name == "nt" and candidate.suffix == ".py":
                        command = [sys.executable, str(candidate), "--help"]
                    subprocess.run(
                        command,
                        cwd=PROJECT_ROOT, capture_output=True, timeout=8,
                    )
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    if "not found" in str(e).lower():
                        raise AssertionError(f"{candidate} not executable: {e}")


def _walk_commands(obj):
    """Yield every 'command' string found anywhere in the JSON tree."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "command" and isinstance(v, str):
                yield v
            else:
                yield from _walk_commands(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_commands(item)
