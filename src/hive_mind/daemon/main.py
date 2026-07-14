"""Hive-Mind daemon entry point (F1 stub).

The F1 scope only registers ``hive-mindd --version``,
``hive-mindd --help``, and a ``hive-mindd run`` stub that prints
``not implemented in F1`` and exits 0. **No** processes are spawned;
**no** services are started; **no** manifest is parsed.

Real implementation lands in F3 (daemon) onwards.
"""
from __future__ import annotations

import argparse
import sys

__version__ = "0.0.0+f1"  # F1 stub; aligned with control plane, not project version


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hive-mindd",
        description="Hive-Mind control plane daemon (F1 stub).",
    )
    p.add_argument("--version", action="store_true", help="print the daemon version and exit")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("run", help="F1 stub: do nothing, print a message, exit 0")
    return p


def main(argv: "list[str] | None" = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"hive-mindd {__version__}")
        return 0
    if args.command == "run":
        print("not implemented in F1")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
