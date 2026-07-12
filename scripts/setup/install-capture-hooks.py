#!/usr/bin/env python3
"""Idempotent installer for Hive-Mind provider capture hooks.

Merges Hive-Mind-owned hook records into each detected provider's hook
surface (Claude Code ``~/.claude/settings.json``, Codex ``~/.codex/hooks.json``).
Foreign hooks are never removed, owned records are never duplicated and
whole settings files are never replaced. Providers without a supported
hook/configuration surface are reported as unsupported and left untouched.

Usage:
    python install-capture-hooks.py --check
    python install-capture-hooks.py --install
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

HOOK_SCRIPT_NAME = "capture-hook.py"

# Hook events installed per provider, mapped to the settings surface key.
EVENT_SURFACE = {
    "session_start": "SessionStart",
    "prompt": "UserPromptSubmit",
    "tool_use": "PreToolUse",
    "tool_result": "PostToolUse",
    "assistant": "Stop",
    "session_end": "SessionEnd",
}

# Events we actually wire for every supported provider. PreToolUse is left
# out on purpose: capture never sits in front of a tool call.
INSTALLED_EVENTS = (
    "session_start",
    "prompt",
    "tool_result",
    "assistant",
    "session_end",
)

# Providers with a real, file-based hook surface.
SUPPORTED = {
    "claude": {
        "detect_dir": ".claude",
        "settings": Path(".claude") / "settings.json",
    },
    "codex": {
        "detect_dir": ".codex",
        "settings": Path(".codex") / "hooks.json",
    },
}

# Known providers without a hook surface (closed providers and file-only
# sources are handled by the watchdog capture service, not by hooks).
UNSUPPORTED = {
    "gemini": ".gemini",
    "qwen": ".qwen",
    "kimi": ".kimi",
    "kiro": ".kiro",
    "cursor": ".cursor",
    "opencode": ".opencode",
    "openclaw": ".openclaw",
    "swarmclaw": ".swarmclaw",
}

_EVENT_TYPE_PATTERN = re.compile(r"--event-type[=\s]+([A-Za-z_]+)")


def project_python(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def hook_command(root: Path, provider: str, event_type: str) -> str:
    python = project_python(root)
    hook = root / "scripts" / "capture" / HOOK_SCRIPT_NAME
    return (
        f'"{python}" "{hook}" --provider {provider} --event-type {event_type}'
    )


def _event_type_from_command(command: str) -> str | None:
    match = _EVENT_TYPE_PATTERN.search(command)
    return match.group(1) if match else None


def _is_owned(command: str, provider: str, event_type: str) -> bool:
    return (
        HOOK_SCRIPT_NAME in command
        and f"--provider {provider}" in command
        and _event_type_from_command(command) == event_type
    )


def merge_hooks(settings: dict, provider: str, command: str) -> dict:
    """Merge one Hive-Mind-owned hook command into a settings dict.

    Deterministic and idempotent: an existing owned record for the same
    provider and event type is updated in place, otherwise one new record
    is appended. Foreign hooks and unrelated settings keys are preserved.
    """
    event_type = _event_type_from_command(command)
    if event_type is None or event_type not in EVENT_SURFACE:
        raise ValueError(f"command has no recognizable --event-type: {command!r}")

    merged = copy.deepcopy(settings) if isinstance(settings, dict) else {}
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("settings['hooks'] must be an object")
    groups = hooks.setdefault(EVENT_SURFACE[event_type], [])
    if not isinstance(groups, list):
        raise ValueError(f"settings['hooks'][{EVENT_SURFACE[event_type]!r}] must be a list")

    for group in groups:
        if not isinstance(group, dict):
            continue
        for record in group.get("hooks", []):
            if not isinstance(record, dict):
                continue
            existing = record.get("command", "")
            if isinstance(existing, str) and _is_owned(existing, provider, event_type):
                record["command"] = command
                record.setdefault("type", "command")
                record.setdefault("timeout", 10)
                return merged

    groups.append(
        {
            "hooks": [
                {"type": "command", "command": command, "timeout": 10}
            ]
        }
    )
    return merged


def _load_settings(path: Path) -> dict | None:
    """Load a settings file; return None when it exists but cannot be parsed."""
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _owned_commands(settings: dict, provider: str) -> set[str]:
    found: set[str] = set()
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return found
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for record in group.get("hooks", []):
                if not isinstance(record, dict):
                    continue
                command = record.get("command", "")
                if (
                    isinstance(command, str)
                    and HOOK_SCRIPT_NAME in command
                    and f"--provider {provider}" in command
                ):
                    event_type = _event_type_from_command(command)
                    if event_type:
                        found.add(event_type)
    return found


def _provider_status(provider: str, home: Path, root: Path) -> str:
    spec = SUPPORTED[provider]
    if not (home / spec["detect_dir"]).is_dir():
        return "not-detected"
    settings = _load_settings(home / spec["settings"])
    if settings is None:
        return "unreadable"
    if set(INSTALLED_EVENTS) <= _owned_commands(settings, provider):
        return "installed"
    return "missing"


def check_providers(home: Path | None = None, root: Path | None = None) -> dict[str, str]:
    """Return installed/missing/unsupported/not-detected status per provider."""
    home = home or Path.home()
    root = root or ROOT
    statuses: dict[str, str] = {}
    for provider in SUPPORTED:
        statuses[provider] = _provider_status(provider, home, root)
    for provider, detect_dir in UNSUPPORTED.items():
        statuses[provider] = (
            "unsupported" if (home / detect_dir).is_dir() else "not-detected"
        )
    return statuses


def install_providers(home: Path | None = None, root: Path | None = None) -> dict[str, str]:
    """Merge owned hook records into every detected supported provider."""
    home = home or Path.home()
    root = root or ROOT
    results: dict[str, str] = {}
    for provider, spec in SUPPORTED.items():
        if not (home / spec["detect_dir"]).is_dir():
            results[provider] = "not-detected"
            continue
        path = home / spec["settings"]
        settings = _load_settings(path)
        if settings is None:
            results[provider] = "unreadable"
            continue
        merged = settings
        for event_type in INSTALLED_EVENTS:
            merged = merge_hooks(merged, provider, hook_command(root, provider, event_type))
        if merged != settings or not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            results[provider] = "installed"
        else:
            results[provider] = "unchanged"
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report hook status per provider")
    mode.add_argument("--install", action="store_true", help="merge owned hooks into detected providers")
    args = parser.parse_args(argv)

    if args.check:
        statuses = check_providers()
        failed = False
        for provider, status in sorted(statuses.items()):
            print(f"{status:>12}  {provider}")
            failed = failed or status in ("missing", "unreadable")
        return 1 if failed else 0

    results = install_providers()
    for provider, status in sorted(results.items()):
        print(f"{status:>12}  {provider}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001 — installer must not break callers
        print(f"install-capture-hooks: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
