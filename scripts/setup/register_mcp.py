"""Portable Python entrypoint for Hive-Mind MCP registration."""
from __future__ import annotations

import sys

from hive_mind.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["agents", "register", *sys.argv[1:]]))
