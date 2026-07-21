"""D009 (fatia 2) — transactional MCP config registration.

Ports Merge-McpConfig from register-mcp.ps1 into native Python: insert the
sinapse-memory server entry under the config's root key, remove legacy
entries, preserve everything else. Writes are transactional (backup + atomic
replace + rollback) and support dry-run. Tested only against temp config
files — never a real provider config.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hive_mind.agents.mcp_config import (
    build_stdio_entry,
    is_registered,
    merge_mcp_config,
)

SERVER = "sinapse-memory"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_registers_into_empty_config(tmp_path):
    cfg = tmp_path / "mcp.json"
    entry = build_stdio_entry(python="py", server="s.py", root="R")
    result = merge_mcp_config(cfg, SERVER, entry)
    assert result.changed is True
    data = _read(cfg)
    assert data["mcpServers"][SERVER]["command"] == "py"
    assert data["mcpServers"][SERVER]["env"]["PYTHONPATH"] == "R"


def test_preserves_existing_servers(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8")
    merge_mcp_config(cfg, SERVER, build_stdio_entry("py", "s.py", "R"))
    data = _read(cfg)
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert SERVER in data["mcpServers"]


def test_custom_root_key_for_vscode(tmp_path):
    cfg = tmp_path / "settings.json"
    merge_mcp_config(cfg, SERVER, build_stdio_entry("py", "s.py", "R"), root_key="servers")
    data = _read(cfg)
    assert SERVER in data["servers"]
    assert "mcpServers" not in data


def test_removes_legacy_entries(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps({"mcpServers": {
            "claude-mem-local": {"command": "old"},
            "neural-memory-local": {"command": "old"},
            "keep": {"command": "x"},
        }}),
        encoding="utf-8",
    )
    merge_mcp_config(cfg, SERVER, build_stdio_entry("py", "s.py", "R"))
    servers = _read(cfg)["mcpServers"]
    assert "claude-mem-local" not in servers
    assert "neural-memory-local" not in servers
    assert "keep" in servers
    assert SERVER in servers


def test_dry_run_does_not_write(tmp_path):
    cfg = tmp_path / "mcp.json"
    result = merge_mcp_config(cfg, SERVER, build_stdio_entry("py", "s.py", "R"), dry_run=True)
    assert result.changed is True  # would change
    assert not cfg.exists()  # but nothing written


def test_idempotent_second_run_reports_no_change(tmp_path):
    cfg = tmp_path / "mcp.json"
    entry = build_stdio_entry("py", "s.py", "R")
    merge_mcp_config(cfg, SERVER, entry)
    second = merge_mcp_config(cfg, SERVER, entry)
    assert second.changed is False


def test_backup_is_created_when_overwriting(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"a": {"command": "x"}}}), encoding="utf-8")
    result = merge_mcp_config(cfg, SERVER, build_stdio_entry("py", "s.py", "R"))
    assert result.backup is not None
    assert Path(result.backup).exists()
    # The backup holds the pre-change content.
    assert "a" in json.loads(Path(result.backup).read_text(encoding="utf-8"))["mcpServers"]


def test_invalid_existing_json_is_refused_not_clobbered(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text("{ this is not valid json", encoding="utf-8")
    with pytest.raises(ValueError):
        merge_mcp_config(cfg, SERVER, build_stdio_entry("py", "s.py", "R"))
    # The original bytes are untouched.
    assert cfg.read_text(encoding="utf-8") == "{ this is not valid json"


def test_is_registered_reflects_state(tmp_path):
    cfg = tmp_path / "mcp.json"
    assert is_registered(cfg, SERVER) is False
    merge_mcp_config(cfg, SERVER, build_stdio_entry("py", "s.py", "R"))
    assert is_registered(cfg, SERVER) is True


def test_creates_parent_directories(tmp_path):
    cfg = tmp_path / "nested" / "deep" / "mcp.json"
    merge_mcp_config(cfg, SERVER, build_stdio_entry("py", "s.py", "R"))
    assert cfg.exists()
