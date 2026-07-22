"""D009-R5 — doctor, unregister and native instruction install.

Temp files only; no real agent config or instruction file is touched.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hive_mind.agents.doctor import diagnose, unregister_providers
from hive_mind.agents.instructions import (
    BEGIN_MARKER,
    END_MARKER,
    LEGACY_BEGIN_MARKER,
    has_managed_block,
    install_instructions,
    remove_instructions,
    render,
)
from hive_mind.agents.register import register_providers

PROMPT = "Follow the Hive-Mind protocol."


def _ctx(tmp_path: Path):
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    home.mkdir(parents=True, exist_ok=True)
    appdata.mkdir(parents=True, exist_ok=True)
    return {"home": home, "appdata": appdata, "project_root": tmp_path / "root"}


def _diag_ctx(tmp_path: Path, commands=()):
    """Diagnosis context with an isolated PATH, so the host does not leak in."""
    have = set(commands)
    return {**_ctx(tmp_path), "which": lambda cmd: cmd if cmd in have else None}


class TestInstructionRendering:
    def test_inserts_into_empty_content(self):
        out = render("", PROMPT)
        assert out.startswith(BEGIN_MARKER)
        assert PROMPT in out
        assert out.rstrip().endswith(END_MARKER)

    def test_preserves_user_content_above(self):
        out = render("# My notes\n\nkeep me\n", PROMPT)
        assert "# My notes" in out
        assert "keep me" in out
        assert BEGIN_MARKER in out

    def test_replaces_instead_of_appending(self):
        once = render("# notes\n", PROMPT)
        twice = render(once, PROMPT)
        assert twice.count(BEGIN_MARKER) == 1
        assert twice.count(END_MARKER) == 1

    def test_updates_the_block_content(self):
        first = render("", "old prompt")
        second = render(first, "new prompt")
        assert "new prompt" in second
        assert "old prompt" not in second

    def test_replaces_the_powershell_era_block(self):
        """A block written by register-mcp.ps1 must be replaced, not duplicated."""
        legacy = f"# notes\n\n{LEGACY_BEGIN_MARKER}\nold\n{END_MARKER}\n"
        out = render(legacy, PROMPT)
        assert out.count(END_MARKER) == 1
        assert "old" not in out
        assert "# notes" in out

    def test_is_idempotent(self):
        once = render("", PROMPT)
        assert render(once, PROMPT) == once


class TestInstructionInstall:
    def test_dry_run_writes_nothing(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        result = install_instructions("codex", target, PROMPT)
        assert result.changed is True
        assert not target.exists()

    def test_apply_creates_the_file(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        install_instructions("codex", target, PROMPT, dry_run=False)
        assert has_managed_block(target)
        assert PROMPT in target.read_text(encoding="utf-8")

    def test_backup_is_created_when_updating(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        target.write_text("# mine\n", encoding="utf-8")
        result = install_instructions("codex", target, PROMPT, dry_run=False)
        assert result.backup and Path(result.backup).is_file()
        assert "# mine" in Path(result.backup).read_text(encoding="utf-8")

    def test_second_apply_reports_no_change(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        install_instructions("codex", target, PROMPT, dry_run=False)
        assert install_instructions("codex", target, PROMPT, dry_run=False).changed is False

    def test_creates_nested_directories(self, tmp_path):
        target = tmp_path / ".cursor" / "rules" / "hive-mind.md"
        install_instructions("cursor", target, PROMPT, dry_run=False)
        assert target.is_file()

    def test_remove_leaves_user_content(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        target.write_text("# mine\n\nkeep\n", encoding="utf-8")
        install_instructions("codex", target, PROMPT, dry_run=False)
        remove_instructions("codex", target, dry_run=False)
        text = target.read_text(encoding="utf-8")
        assert "# mine" in text and "keep" in text
        assert BEGIN_MARKER not in text

    def test_remove_on_absent_file_is_noop(self, tmp_path):
        result = remove_instructions("codex", tmp_path / "nope.md", dry_run=False)
        assert result.changed is False


class TestDoctor:
    def test_reports_unregistered_provider(self, tmp_path):
        ctx = _ctx(tmp_path)
        report = {d.provider: d for d in diagnose(["qwen"], **_diag_ctx(tmp_path))}
        assert report["qwen"].fully_registered is False

    def test_reports_registered_after_apply(self, tmp_path):
        ctx = _ctx(tmp_path)
        register_providers(["qwen"], dry_run=False, python="py", server="s.py", **ctx)
        report = {d.provider: d for d in diagnose(["qwen"], **ctx)}
        assert report["qwen"].fully_registered is True

    def test_detects_installed_instructions(self, tmp_path):
        ctx = _ctx(tmp_path)
        target = ctx["project_root"] / "AGENTS.md"
        install_instructions("codex", target, PROMPT, dry_run=False)
        report = {d.provider: d for d in diagnose(["codex"], **ctx)}
        assert report["codex"].instructions_installed is True

    def test_an_absent_provider_is_not_unhealthy(self, tmp_path):
        """Nothing to configure for an agent that is not installed."""
        ctx = _ctx(tmp_path)
        diagnosis = diagnose(["qwen"], **_diag_ctx(tmp_path))[0]
        assert diagnosis.detected is False
        assert diagnosis.healthy is True

    def test_diagnose_covers_all_providers_by_default(self, tmp_path):
        from hive_mind.agents.registry import PROVIDERS

        report = diagnose(**_diag_ctx(tmp_path))
        assert {d.provider for d in report} == {p.id for p in PROVIDERS}


class TestUnregister:
    def test_dry_run_changes_nothing(self, tmp_path):
        ctx = _ctx(tmp_path)
        register_providers(["qwen"], dry_run=False, python="py", server="s.py", **ctx)
        target = ctx["home"] / ".qwen" / "settings.json"
        before = target.read_text(encoding="utf-8")
        results = unregister_providers(["qwen"], **ctx)
        assert any(r.changed for r in results)
        assert target.read_text(encoding="utf-8") == before

    def test_removes_only_the_hive_mind_entry(self, tmp_path):
        ctx = _ctx(tmp_path)
        target = ctx["home"] / ".qwen" / "settings.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"mcpServers": {"other": {"command": "keep"}}}),
                          encoding="utf-8")
        register_providers(["qwen"], dry_run=False, python="py", server="s.py", **ctx)
        unregister_providers(["qwen"], dry_run=False, **ctx)
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["mcpServers"] == {"other": {"command": "keep"}}

    def test_unregister_is_idempotent(self, tmp_path):
        ctx = _ctx(tmp_path)
        register_providers(["qwen"], dry_run=False, python="py", server="s.py", **ctx)
        unregister_providers(["qwen"], dry_run=False, **ctx)
        second = unregister_providers(["qwen"], dry_run=False, **ctx)
        assert all(r.changed is False for r in second)

    def test_removes_toml_entry_keeping_third_parties(self, tmp_path):
        import tomlkit

        ctx = _ctx(tmp_path)
        cfg = ctx["home"] / ".codex" / "config.toml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text('[mcp_servers.keep-me]\ncommand = "x"\n', encoding="utf-8")
        register_providers(["codex"], dry_run=False, python="py", server="s.py", **ctx)
        unregister_providers(["codex"], dry_run=False, **ctx)
        doc = tomlkit.parse(cfg.read_text(encoding="utf-8"))
        assert "keep-me" in doc["mcp_servers"]
        assert "sinapse-memory" not in doc["mcp_servers"]

    def test_can_also_remove_the_instruction_block(self, tmp_path):
        ctx = _ctx(tmp_path)
        target = ctx["project_root"] / "AGENTS.md"
        install_instructions("codex", target, PROMPT, dry_run=False)
        unregister_providers(
            ["codex"], dry_run=False, remove_instruction_block=True, **ctx
        )
        assert has_managed_block(target) is False
