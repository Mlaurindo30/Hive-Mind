#!/usr/bin/env python3
"""Install Codex hooks that force claude-mem to use Hive-Mind local data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
HOOK = ROOT / "scripts" / "claude-mem-hook.sh"


def cmd(*args: str) -> str:
    return " ".join([str(HOOK), *args])


def hook(command: str, timeout: int, status_message: str | None = None) -> dict:
    data = {"type": "command", "command": command, "timeout": timeout}
    if status_message:
        data["statusMessage"] = status_message
    return data


def build_hooks() -> dict:
    return {
        "description": "Hive-Mind project-local claude-mem Codex hook integration",
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume",
                    "hooks": [
                        hook(cmd("version-check"), 5),
                        hook(cmd("ensure-worker"), 60),
                        hook(
                            cmd("hook", "codex", "context"),
                            60,
                            "Loading claude-mem context",
                        ),
                    ],
                }
            ],
            "UserPromptSubmit": [
                {"hooks": [hook(cmd("hook", "codex", "session-init"), 60)]}
            ],
            "PreToolUse": [
                {
                    "matcher": "^Bash$|^mcp__.+__(read|view|cat)(_file|_files)?$",
                    "hooks": [hook(cmd("hook", "codex", "file-context"), 30)],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": ".*",
                    "hooks": [hook(cmd("hook", "codex", "observation"), 120)],
                }
            ],
            "Stop": [
                {"hooks": [hook(cmd("hook", "codex", "summarize"), 60)]}
            ],
        },
    }


def install(paths: list[Path], *, check: bool = False) -> int:
    payload = build_hooks()
    expected = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    failed = False
    for path in paths:
        if check:
            ok = path.is_file() and path.read_text() == expected
            print(f"{'ok' if ok else 'drift'} {path}")
            failed = failed or not ok
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected)
        path.chmod(0o600)
        print(f"wrote {path}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--global-only",
        action="store_true",
        help="Only update ~/.codex/hooks.json.",
    )
    args = parser.parse_args()
    paths = [Path.home() / ".codex" / "hooks.json"]
    if not args.global_only:
        paths.insert(0, ROOT / ".codex" / "hooks.json")
    return install(paths, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
