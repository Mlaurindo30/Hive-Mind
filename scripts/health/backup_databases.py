#!/usr/bin/env python3
"""Compatibility shim — the backup engine lives in the package now (D008-R1B).

The implementation moved to :mod:`hive_mind.maintenance.backup`, which keeps
the behaviour that was already correct here (``sqlite3.Connection.backup()``
over a read-only source, so a live database is copied consistently) and adds
what this file lacked: a single-instance lock, atomic finalization, a content
manifest with SHA-256, verification before an artifact counts, and retention
that runs **only after** the new backup is verified — this version pruned
immediately after copying, so a corrupt new backup could evict a good old one.

    hive-mind backup run [--apply]
    hive-mind backup status
    hive-mind backup verify
    hive-mind backup restore --manifest <path> --into <dir>

This file holds no logic of its own. Removal: after the cutover (D010).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def main(argv: "list[str] | None" = None) -> int:
    from hive_mind.cli import main as cli_main

    argv = list(sys.argv[1:] if argv is None else argv)
    # The legacy entry point always wrote; the native command is dry-run by
    # default, so preserve the old contract for existing callers.
    args = ["backup", "run", "--apply"]
    if "--json" in argv:
        args.append("--json")
    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
