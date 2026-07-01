#!/usr/bin/env python3
"""Compatibility entrypoint for the K4 Claude-Mem bridge.

Implementation lives in ``core.knowledge.claude_mem_bridge`` so CLI, tests and
MCP can share one contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.knowledge import claude_mem_bridge as _core_bridge  # noqa: E402
from core.knowledge.claude_mem_bridge import (  # noqa: E402,F401
    BRIDGE_SOURCE,
    CLAUDE_MEM_DB,
    DEFAULT_LIMIT,
    existing_bridged_ids,
    fetch_source_records,
    main,
)

get_connection = _core_bridge.get_connection
ensure_migrations = _core_bridge.ensure_migrations
open_claude_mem = _core_bridge.open_claude_mem


def _sync_core_hooks() -> None:
    _core_bridge.get_connection = get_connection
    _core_bridge.ensure_migrations = ensure_migrations
    _core_bridge.open_claude_mem = open_claude_mem


def bridge(*args, **kwargs):
    _sync_core_hooks()
    return _core_bridge.bridge(*args, **kwargs)


def quarantine_legacy(*args, **kwargs):
    _sync_core_hooks()
    return _core_bridge.quarantine_legacy(*args, **kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
