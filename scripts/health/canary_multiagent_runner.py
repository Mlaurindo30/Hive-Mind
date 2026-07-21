#!/usr/bin/env python3
"""Compatibility shim — the canary lives in the native package now (D004-R1).

The product logic moved to ``hive_mind.validation``. This file exists only so
existing invocations keep working; it holds no behaviour of its own.

    hive-mind validate agents [--only PROVIDER] [--json]

The native canary reads real provider sources, runs the real parsers and
inspects the real delivery databases read-only. The previous implementation
here built a synthetic session, created mock schemas and monkeypatched the
bridge, so it could not fail while real capture was broken.

Removal: D009-R6 (once no caller references this path).
"""
from __future__ import annotations

import sys


def main() -> int:
    from hive_mind.cli import main as cli_main

    return cli_main(["validate", "agents", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
