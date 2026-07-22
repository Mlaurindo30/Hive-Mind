"""D009-R4 — native Codex TOML writer, temp files only.

Mirrors the JSON path's safety contract, plus what TOML adds: a user's
comments and key order must survive, and an existing entry's nested
subtables (.env, .tools.*) must be replaced whole rather than merged into.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from hive_mind.agents.toml_config import (
    build_codex_entry,
    is_registered,
    merge_codex_config,
)

SERVER = "sinapse-memory"

REAL_SHAPE = """\
# Codex configuration — hand written, keep my comments
model_reasoning_effort = "medium"
sandbox_mode = "danger-full-access"

[windows]
sandbox = "elevated"

[projects.'d:\\\\hive-mind']
trust_level = "trusted"

[mcp_servers.iq-agent-desk]
command = "node"
args = ["desk.js"]

[mcp_servers.iq-agent-desk.env]
TOKEN = "keep-me"
"""


def _entry() -> dict:
    return build_codex_entry("py.exe", "sinapse_mcp.py", "D:/Hive-Mind")


class TestWrite:
    def test_registers_into_empty_file(self, tmp_path):
        cfg = tmp_path / "config.toml"
        result = merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        assert result.changed and result.created
        doc = tomlkit.parse(cfg.read_text(encoding="utf-8"))
        assert doc["mcp_servers"][SERVER]["command"] == "py.exe"
        assert doc["mcp_servers"][SERVER]["env"]["SINAPSE_HOME"] == "D:/Hive-Mind"

    def test_dry_run_is_the_default_and_writes_nothing(self, tmp_path):
        cfg = tmp_path / "config.toml"
        result = merge_codex_config(cfg, SERVER, _entry())
        assert result.changed is True
        assert not cfg.exists()

    def test_preserves_comments_and_third_party_servers(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text(REAL_SHAPE, encoding="utf-8")
        merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        text = cfg.read_text(encoding="utf-8")

        assert "# Codex configuration — hand written, keep my comments" in text
        doc = tomlkit.parse(text)
        assert doc["model_reasoning_effort"] == "medium"
        assert doc["windows"]["sandbox"] == "elevated"
        # The project key is a TOML literal string holding a Windows path;
        # assert the entry survived without re-deriving its exact escaping.
        assert len(doc["projects"]) == 1
        assert next(iter(doc["projects"].values()))["trust_level"] == "trusted"
        assert doc["mcp_servers"]["iq-agent-desk"]["env"]["TOKEN"] == "keep-me"
        assert SERVER in doc["mcp_servers"]

    def test_replaces_nested_subtables_wholesale(self, tmp_path):
        """A stale .tools subtable must not survive re-registration."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            "[mcp_servers.sinapse-memory]\n"
            'command = "old"\n'
            "\n[mcp_servers.sinapse-memory.env]\n"
            'STALE = "yes"\n'
            "\n[mcp_servers.sinapse-memory.tools.old_tool]\n"
            "enabled = true\n",
            encoding="utf-8",
        )
        merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        doc = tomlkit.parse(cfg.read_text(encoding="utf-8"))
        entry = doc["mcp_servers"][SERVER]
        assert entry["command"] == "py.exe"
        assert "tools" not in entry
        assert "STALE" not in entry["env"]

    def test_removes_legacy_entries(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[mcp_servers.claude-mem-local]\ncommand = "old"\n'
            '\n[mcp_servers.keep-me]\ncommand = "x"\n',
            encoding="utf-8",
        )
        result = merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        doc = tomlkit.parse(cfg.read_text(encoding="utf-8"))
        assert "claude-mem-local" not in doc["mcp_servers"]
        assert "keep-me" in doc["mcp_servers"]
        assert result.removed_legacy == ("claude-mem-local",)

    def test_second_run_reports_no_change(self, tmp_path):
        cfg = tmp_path / "config.toml"
        merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        assert merge_codex_config(cfg, SERVER, _entry(), dry_run=False).changed is False

    def test_backup_is_created(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text(REAL_SHAPE, encoding="utf-8")
        result = merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        assert result.backup and Path(result.backup).is_file()
        assert "iq-agent-desk" in Path(result.backup).read_text(encoding="utf-8")


class TestSafety:
    def test_invalid_toml_is_refused_without_clobbering(self, tmp_path):
        cfg = tmp_path / "config.toml"
        broken = "[mcp_servers\nthis is not toml"
        cfg.write_text(broken, encoding="utf-8")
        with pytest.raises(ValueError):
            merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        assert cfg.read_text(encoding="utf-8") == broken

    def test_no_temp_file_survives(self, tmp_path):
        cfg = tmp_path / "config.toml"
        merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        assert list(tmp_path.glob("*.hive-tmp")) == []

    def test_result_reparses_cleanly(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text(REAL_SHAPE, encoding="utf-8")
        merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        tomlkit.parse(cfg.read_text(encoding="utf-8"))  # must not raise

    def test_is_registered_never_raises_on_broken_toml(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("[[[nope", encoding="utf-8")
        assert is_registered(cfg, SERVER) is False

    def test_is_registered_tracks_state(self, tmp_path):
        cfg = tmp_path / "config.toml"
        assert is_registered(cfg, SERVER) is False
        merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        assert is_registered(cfg, SERVER) is True

    def test_creates_parent_directories(self, tmp_path):
        cfg = tmp_path / "deep" / "nested" / "config.toml"
        merge_codex_config(cfg, SERVER, _entry(), dry_run=False)
        assert cfg.is_file()
