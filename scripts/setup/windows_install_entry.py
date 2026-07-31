#!/usr/bin/env python3
"""Compatibility entrypoint for Windows install wrappers.

Accepts the former PowerShell switch spelling and delegates all installation
behaviour to the canonical Python installer.
"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hive_mind.install.windows import main as native_main  # noqa: E402


_SWITCHES = {
    "-force": "--force",
    "-withtests": "--with-tests",
    "-withrealtests": "--with-real-tests",
    "-skipagents": "--skip-agents",
    "-skipservices": "--skip-services",
    "-noninteractive": "--non-interactive",
    "-skipprerequisites": "--skip-prerequisites",
    "-prerequisitesonly": "--prerequisites-only",
    "-installprerequisites": "--install-prerequisites",
    "-dryrun": "--dry-run",
    "-repair": "--repair",
    "-update": "--update",
    "-uninstall": "--uninstall",
    "-preservevault": "--preserve-vault",
    "-preservedatabase": "--preserve-database",
    "-systemservice": "--system-service",
}


def normalize(argv: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        lower = arg.lower()
        if lower == "-profile":
            if index + 1 >= len(argv):
                raise SystemExit("-Profile requires local-min or local-full")
            result.extend(("--profile", argv[index + 1]))
            index += 2
            continue
        result.append(_SWITCHES.get(lower, arg))
        index += 1
    return result


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--root" not in args:
        args = ["--root", str(ROOT), *args]
    return native_main(normalize(args))


if __name__ == "__main__":
    raise SystemExit(main())
