"""Transactional MCP config registration (ADR-013).

Ports ``Merge-McpConfig`` from register-mcp.ps1: insert the sinapse-memory
server entry under the config's root key, drop legacy entries, and preserve
everything else the user has configured.

Every write is transactional:

  1. refuse to touch a config whose existing JSON is invalid (never clobber);
  2. back the original up next to it;
  3. write to a temp file and ``os.replace`` it into place (atomic);
  4. on failure, restore from the backup.

``dry_run`` reports what *would* change without writing anything.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

DEFAULT_ROOT_KEY = "mcpServers"
LEGACY_ENTRIES = ("claude-mem-local", "neural-memory-local")


@dataclass(frozen=True)
class MergeResult:
    path: str
    changed: bool
    created: bool
    backup: Optional[str] = None
    removed_legacy: tuple[str, ...] = ()


def build_stdio_entry(python: str, server: str, root: str, *, with_cwd: bool = True) -> dict:
    """The stdio MCP entry, matching Get-StdioEntry in register-mcp.ps1."""
    entry: dict[str, Any] = {
        "command": python,
        "args": [server],
        "env": {"PYTHONPATH": root, "SINAPSE_HOME": root},
    }
    if with_cwd:
        entry["cwd"] = root
    return entry


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8-sig")
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"unexpected top-level JSON in {path}: expected an object")
    return data


def is_registered(path: Path | str, server_name: str, root_key: str = DEFAULT_ROOT_KEY) -> bool:
    """True when the server is already present. Never raises on bad JSON."""
    try:
        data = _load(Path(path))
    except ValueError:
        return False
    return server_name in (data.get(root_key) or {})


def merge_mcp_config(
    path: Path | str,
    server_name: str,
    entry: dict,
    root_key: str = DEFAULT_ROOT_KEY,
    *,
    dry_run: bool = False,
) -> MergeResult:
    """Register `entry` under `root_key`, transactionally."""
    path = Path(path)
    created = not path.exists()
    data = _load(path)  # raises ValueError on invalid JSON, before any write

    servers = dict(data.get(root_key) or {})
    removed = tuple(name for name in LEGACY_ENTRIES if name in servers)
    for name in removed:
        servers.pop(name, None)

    already_current = servers.get(server_name) == entry
    servers[server_name] = entry
    changed = bool(removed) or not already_current

    if dry_run or not changed:
        return MergeResult(str(path), changed, created, None, removed)

    data[root_key] = servers
    backup = _write_atomic(path, data, created)
    return MergeResult(str(path), True, created, backup, removed)


def _write_atomic(path: Path, data: dict, created: bool) -> Optional[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Optional[Path] = None
    if not created:
        backup = path.with_suffix(path.suffix + ".hive-bak")
        shutil.copy2(path, backup)

    tmp = path.with_suffix(path.suffix + ".hive-tmp")
    try:
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(tmp, path)
    except Exception:
        # Restore the original before surfacing the failure.
        if backup is not None and backup.exists():
            shutil.copy2(backup, path)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return str(backup) if backup is not None else None


def remove_mcp_config(
    path: Path | str,
    server_name: str,
    root_key: str = DEFAULT_ROOT_KEY,
    *,
    dry_run: bool = True,
) -> MergeResult:
    """Remove the server entry, leaving every other server untouched."""
    path = Path(path)
    if not path.exists():
        return MergeResult(str(path), False, False, None, ())
    data = _load(path)  # raises ValueError on invalid JSON, before any write

    servers = dict(data.get(root_key) or {})
    if server_name not in servers:
        return MergeResult(str(path), False, False, None, ())
    if dry_run:
        return MergeResult(str(path), True, False, None, ())

    servers.pop(server_name)
    data[root_key] = servers
    backup = _write_atomic(path, data, created=False)
    return MergeResult(str(path), True, False, backup, ())
