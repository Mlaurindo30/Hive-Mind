"""Task 7 — idempotent managed hook installer for provider surfaces.

``install-capture-hooks.py`` must merge only Hive-Mind-owned hook records,
never duplicate them, never remove foreign hooks and never replace whole
settings files.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "setup" / "install-capture-hooks.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "install_capture_hooks", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load_module()
merge_hooks = module.merge_hooks


def _commands(settings: dict, event: str) -> list[str]:
    return [
        hook["command"]
        for group in settings["hooks"][event]
        for hook in group["hooks"]
    ]


def test_installer_preserves_unrelated_hooks(tmp_path):
    settings = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "foreign-hook"}]}
            ]
        }
    }
    merged = merge_hooks(settings, "codex", "python capture-hook.py --provider codex --event-type prompt")
    commands = [
        hook["command"]
        for group in merged["hooks"]["UserPromptSubmit"]
        for hook in group["hooks"]
    ]
    assert "foreign-hook" in commands
    assert commands.count("python capture-hook.py --provider codex --event-type prompt") == 1


def test_merge_hooks_is_idempotent():
    command = "python capture-hook.py --provider claude --event-type prompt"
    merged = merge_hooks({}, "claude", command)
    merged_again = merge_hooks(merged, "claude", command)
    assert merged_again == merged
    assert _commands(merged_again, "UserPromptSubmit").count(command) == 1


def test_merge_hooks_updates_owned_command_without_duplicating():
    stale = "/old/python /old/capture-hook.py --provider claude --event-type prompt"
    fresh = "/new/python /new/capture-hook.py --provider claude --event-type prompt"
    settings = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "foreign-hook"}]},
                {"hooks": [{"type": "command", "command": stale}]},
            ]
        }
    }
    merged = merge_hooks(settings, "claude", fresh)
    commands = _commands(merged, "UserPromptSubmit")
    assert "foreign-hook" in commands
    assert fresh in commands
    assert stale not in commands
    assert len(commands) == 2


def test_merge_hooks_does_not_mutate_the_input(tmp_path):
    settings = {"hooks": {"UserPromptSubmit": []}}
    merge_hooks(settings, "codex", "python capture-hook.py --provider codex --event-type prompt")
    assert settings == {"hooks": {"UserPromptSubmit": []}}


def test_check_reports_installed_missing_and_unsupported(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".gemini").mkdir()

    statuses = module.check_providers(home=tmp_path, root=ROOT)

    assert statuses["claude"] == "missing"
    assert statuses["gemini"] == "unsupported"
    assert statuses["codex"] == "not-detected"


def test_install_merges_into_existing_settings_without_replacing(tmp_path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "model": "opus",
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": "foreign-hook"}]}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    module.install_providers(home=tmp_path, root=ROOT)

    written = json.loads(settings_path.read_text(encoding="utf-8"))
    assert written["model"] == "opus"
    commands = _commands(written, "UserPromptSubmit")
    assert "foreign-hook" in commands
    assert any("capture-hook.py" in command for command in commands)

    before = settings_path.read_text(encoding="utf-8")
    module.install_providers(home=tmp_path, root=ROOT)
    assert settings_path.read_text(encoding="utf-8") == before

    statuses = module.check_providers(home=tmp_path, root=ROOT)
    assert statuses["claude"] == "installed"


def test_install_covers_codex_hooks_surface(tmp_path):
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()

    module.install_providers(home=tmp_path, root=ROOT)

    hooks_path = codex_dir / "hooks.json"
    assert hooks_path.is_file()
    written = json.loads(hooks_path.read_text(encoding="utf-8"))
    commands = _commands(written, "UserPromptSubmit")
    assert any(
        "capture-hook.py" in command and "--provider codex" in command
        for command in commands
    )
