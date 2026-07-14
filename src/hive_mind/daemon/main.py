"""Hive-Mind daemon entry point (F1 stub).

The F1 scope only registers ``hive-mindd --version``,
``hive-mindd --help``, and ``hive-mindd run`` (which **fails** with
``EX_UNAVAILABLE=69`` because the daemon is not implemented in F1).
**No** processes are spawned; **no** services are started; **no**
manifest is parsed.

Real implementation lands in F3 (daemon) onwards.
"""
from __future__ import annotations

import argparse
import sys

EX_UNAVAILABLE = 69  # sysexits.h


def _get_version() -> str:
    """Return the installed package version.

    The single source of truth is ``pyproject.toml::project.version``,
    read at runtime via importlib.metadata.
    """
    try:
        from importlib.metadata import version
        return version("hive-mind")
    except Exception:
        import re
        from pathlib import Path
        for candidate in (Path.cwd(), Path(__file__).resolve().parents[3]):
            pyproject = candidate / "pyproject.toml"
            if pyproject.is_file():
                m = re.search(
                    r"^version\s*=\s*\"([^\"]+)\"",
                    pyproject.read_text(encoding="utf-8"),
                    re.M,
                )
                if m:
                    return m.group(1)
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hive-mindd",
        description="Hive-Mind control plane daemon (F1 stub).",
    )
    p.add_argument("--version", action="store_true", help="print the daemon version and exit")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("run", help="not implemented in F1: returns EX_UNAVAILABLE (69)")
    return p


def main(argv: "list[str] | None" = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"hive-mindd {_get_version()}")
        return 0
    if args.command == "run":
        print("hive-mindd run is not implemented in F1", file=sys.stderr)
        return EX_UNAVAILABLE
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
