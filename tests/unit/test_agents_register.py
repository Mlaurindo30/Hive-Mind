"""D009 (fatia 3) — `agents register`: provider -> config target -> merge.

Maps each detected provider to its real config file(s), ported from the
per-provider registrars in register-mcp.ps1, and applies the transactional
merge. Defaults to dry-run so inspection never mutates anything. Tested with
an injected HOME/APPDATA — never a real provider config.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hive_mind.agents.register import register_providers
from hive_mind.agents.registry import config_targets, get_provider

SERVER = "sinapse-memory"


def _ctx(tmp_path: Path):
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    home.mkdir(parents=True, exist_ok=True)
    appdata.mkdir(parents=True, exist_ok=True)
    return {
        "home": home,
        "appdata": appdata,
        "project_root": tmp_path / "root",
        "python": "py",
        "server": "s.py",
    }


def test_known_providers_declare_config_targets():
    for provider_id in ("claude", "qwen", "kimi", "cursor", "vscode"):
        assert config_targets(get_provider(provider_id)), provider_id


def test_dry_run_writes_nothing(tmp_path):
    ctx = _ctx(tmp_path)
    results = register_providers(["qwen"], dry_run=True, **ctx)
    assert results
    for r in results:
        assert not Path(r.path).exists()


def test_apply_writes_the_config(tmp_path):
    ctx = _ctx(tmp_path)
    results = register_providers(["qwen"], dry_run=False, **ctx)
    target = ctx["home"] / ".qwen" / "settings.json"
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert SERVER in data["mcpServers"]
    assert any(r.changed for r in results)


def test_vscode_uses_servers_root_key_and_stdio_type(tmp_path):
    ctx = _ctx(tmp_path)
    register_providers(["vscode"], dry_run=False, **ctx)
    target = ctx["project_root"] / ".vscode" / "mcp.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    assert SERVER in data["servers"]
    assert data["servers"][SERVER]["type"] == "stdio"


def test_claude_writes_both_user_and_project_configs(tmp_path):
    ctx = _ctx(tmp_path)
    register_providers(["claude"], dry_run=False, **ctx)
    assert (ctx["home"] / ".claude.json").exists()
    assert (ctx["project_root"] / ".mcp.json").exists()


def test_registering_twice_is_idempotent(tmp_path):
    ctx = _ctx(tmp_path)
    register_providers(["qwen"], dry_run=False, **ctx)
    second = register_providers(["qwen"], dry_run=False, **ctx)
    assert all(r.changed is False for r in second)


def test_unknown_provider_raises(tmp_path):
    with pytest.raises(KeyError):
        register_providers(["nope"], dry_run=True, **_ctx(tmp_path))


def test_existing_third_party_servers_survive(tmp_path):
    ctx = _ctx(tmp_path)
    target = ctx["home"] / ".qwen" / "settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"mcpServers": {"other": {"command": "keep"}}}), encoding="utf-8"
    )
    register_providers(["qwen"], dry_run=False, **ctx)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["mcpServers"]["other"] == {"command": "keep"}
    assert SERVER in data["mcpServers"]


def test_toml_target_is_reported_not_silently_skipped(tmp_path):
    """Codex's config.toml needs a TOML writer; it must be visible, not silent."""
    ctx = _ctx(tmp_path)
    results = register_providers(["codex"], dry_run=True, **ctx)
    kinds = {r.kind for r in results}
    assert "toml" in kinds
    toml_result = next(r for r in results if r.kind == "toml")
    assert toml_result.supported is False
    assert toml_result.note
