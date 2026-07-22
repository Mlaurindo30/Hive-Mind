"""Transactional TOML config registration for Codex (D009-R4).

Codex keeps its MCP servers in `~/.codex/config.toml` under
`[mcp_servers.<name>]`, with nested subtables (`.env`, `.tools.*`). The
legacy `register-mcp.ps1` edited it by regex block replacement; this is the
native writer.

`tomlkit` is used deliberately: it round-trips a document preserving
comments, key order and formatting, so a user's hand-written config is not
reformatted just because one server entry changed. A plain parse-and-dump
writer would silently destroy that.

Safety follows the JSON path (`mcp_config.py`):

  1. refuse invalid TOML before writing anything;
  2. back the original up;
  3. write to a temp file on the same volume, flush + fsync;
  4. `os.replace` it into place (atomic);
  5. re-parse the result and roll back if it does not read cleanly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

MCP_TABLE = "mcp_servers"
LEGACY_ENTRIES = ("claude-mem-local", "neural-memory-local")
DEFAULT_STARTUP_TIMEOUT = 30


@dataclass(frozen=True)
class TomlMergeResult:
    path: str
    changed: bool
    created: bool
    backup: Optional[str] = None
    removed_legacy: tuple[str, ...] = ()


def build_codex_entry(
    python: str, server: str, root: str, *, startup_timeout_sec: int = DEFAULT_STARTUP_TIMEOUT
) -> dict[str, Any]:
    """The Codex MCP entry, mirroring what register-mcp.ps1 wrote."""
    return {
        "command": python,
        "args": [server],
        "startup_timeout_sec": startup_timeout_sec,
        "env": {"PYTHONPATH": root, "SINAPSE_HOME": root},
    }


def _load(path: Path):
    import tomlkit

    if not path.exists():
        return tomlkit.document()
    raw = path.read_text(encoding="utf-8-sig")
    if not raw.strip():
        return tomlkit.document()
    try:
        return tomlkit.parse(raw)
    except Exception as exc:  # noqa: BLE001 - tomlkit raises several parse errors
        raise ValueError(f"invalid TOML in {path}: {exc}") from exc


def is_registered(path: Path | str, server_name: str) -> bool:
    """True when the server is present. Never raises on malformed TOML."""
    try:
        document = _load(Path(path))
    except ValueError:
        return False
    servers = document.get(MCP_TABLE)
    return bool(servers) and server_name in servers


def merge_codex_config(
    path: Path | str,
    server_name: str,
    entry: dict[str, Any],
    *,
    dry_run: bool = True,
) -> TomlMergeResult:
    """Register `entry` under `[mcp_servers.<server_name>]`, transactionally."""
    import tomlkit

    path = Path(path)
    created = not path.exists()
    document = _load(path)  # raises ValueError before any write

    servers = document.get(MCP_TABLE)
    if servers is None:
        servers = tomlkit.table(is_super_table=True)
        document[MCP_TABLE] = servers

    removed = tuple(name for name in LEGACY_ENTRIES if name in servers)
    already_current = _entry_matches(servers.get(server_name), entry)
    changed = bool(removed) or not already_current

    if dry_run or not changed:
        return TomlMergeResult(str(path), changed, created, None, removed)

    for name in removed:
        del servers[name]
    # Replacing the whole subtree matters: the existing entry can carry
    # nested tables (.env, .tools.*) that a shallow update would leave behind.
    if server_name in servers:
        del servers[server_name]
    servers[server_name] = _as_table(entry)

    backup = _write_atomic(path, tomlkit.dumps(document), created)
    return TomlMergeResult(str(path), True, created, backup, removed)


def _as_table(value: dict[str, Any]):
    import tomlkit

    table = tomlkit.table()
    for key, item in value.items():
        table[key] = _as_table(item) if isinstance(item, dict) else item
    return table


def _entry_matches(existing: Any, wanted: dict[str, Any]) -> bool:
    if existing is None:
        return False
    try:
        return {k: _plain(v) for k, v in dict(existing).items()} == {
            k: _plain(v) for k, v in wanted.items()
        }
    except (TypeError, ValueError):
        return False


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _write_atomic(path: Path, text: str, created: bool) -> Optional[str]:
    import shutil

    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Optional[Path] = None
    if not created:
        backup = path.with_suffix(path.suffix + ".hive-bak")
        shutil.copy2(path, backup)

    # Same directory keeps the temp file on the same volume, so os.replace
    # is a real atomic rename rather than a cross-device copy.
    tmp = path.with_suffix(path.suffix + ".hive-tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _load(path)  # parse-after-write: a corrupt result must not survive
    except Exception:
        if backup is not None and backup.exists():
            shutil.copy2(backup, path)
        tmp.unlink(missing_ok=True)
        raise
    return str(backup) if backup is not None else None


def remove_from_codex_config(
    path: Path | str, server_name: str, *, dry_run: bool = True
) -> TomlMergeResult:
    """Remove `[mcp_servers.<server_name>]` and its subtables, keeping the rest."""
    import tomlkit

    path = Path(path)
    if not path.exists():
        return TomlMergeResult(str(path), False, False, None, ())
    document = _load(path)  # raises ValueError on invalid TOML, before any write

    servers = document.get(MCP_TABLE)
    if not servers or server_name not in servers:
        return TomlMergeResult(str(path), False, False, None, ())
    if dry_run:
        return TomlMergeResult(str(path), True, False, None, ())

    del servers[server_name]
    backup = _write_atomic(path, tomlkit.dumps(document), created=False)
    return TomlMergeResult(str(path), True, False, backup, ())
