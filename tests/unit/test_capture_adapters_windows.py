"""Testes do registro de adapters em Windows e POSIX.

Garante que o antigravity observa TANTO o layout Desktop (~/.gemini/antigravity)
quanto o CLI (~/.gemini/antigravity-cli), e que o storage do VS Code resolve
via %APPDATA%\\Code\\User no Windows mantendo ~/.config/Code/User no POSIX.
"""
from __future__ import annotations

import importlib.util
import itertools
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "capture"

_MODULE_COUNTER = itertools.count()


def reload_capture_adapters():
    """Executa capture_adapters.py do zero para honrar monkeypatches de ambiente."""
    for entry in (str(ROOT), str(CAPTURE)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    name = f"capture_adapters_under_test_{next(_MODULE_COUNTER)}"
    spec = importlib.util.spec_from_file_location(name, CAPTURE / "capture_adapters.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _posix(paths: list[str]) -> list[str]:
    return [p.replace("\\", "/") for p in paths]


def test_registry_includes_antigravity_desktop_home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    module = reload_capture_adapters()

    assert any(
        ".gemini/antigravity/brain" in p.replace("\\", "/")
        for p in module.ADAPTERS["antigravity"]["sources"]
    )
    assert any(
        ".gemini/antigravity/conversations/*.db" in p.replace("\\", "/")
        for p in module.ADAPTERS["antigravity"]["sources"]
    )


def test_registry_includes_antigravity_ide_windows_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    module = reload_capture_adapters()
    sources = _posix(module.ADAPTERS["antigravity"]["sources"])
    watch = _posix(module.ADAPTERS["antigravity"]["watch"])

    assert any(".gemini/antigravity-ide/brain" in path for path in sources)
    assert any(".gemini/antigravity-ide/conversations/*.db" in path for path in sources)
    assert any(".gemini/antigravity-ide/brain" in path for path in watch)
    assert any(".gemini/antigravity-ide/conversations" in path for path in watch)

def test_registry_keeps_antigravity_cli_home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    module = reload_capture_adapters()
    sources = _posix(module.ADAPTERS["antigravity"]["sources"])
    watch = _posix(module.ADAPTERS["antigravity"]["watch"])

    assert any(".gemini/antigravity-cli/brain" in p for p in sources)
    assert any(".gemini/antigravity-cli/conversations/*.db" in p for p in sources)
    assert any(".gemini/antigravity/brain" in p for p in watch)
    assert any(".gemini/antigravity-cli/brain" in p for p in watch)
    home = tmp_path.as_posix()
    assert all(p.startswith(home) for p in sources)


def test_vscode_storage_resolves_appdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(os, "name", "nt")
    appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))

    module = reload_capture_adapters()
    expected = (appdata / "Code" / "User").as_posix()

    for provider in ("copilot", "roo"):
        sources = _posix(module.ADAPTERS[provider]["sources"])
        assert sources, provider
        assert any(expected in p for p in sources), (provider, sources)
        assert all(".config/Code/User" not in p for p in sources), (provider, sources)


def test_copilot_windows_includes_cli_and_ide_session_databases(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(os, "name", "nt")
    appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))

    module = reload_capture_adapters()
    sources = _posix(module.ADAPTERS["copilot"]["sources"])
    watch = _posix(module.ADAPTERS["copilot"]["watch"])

    cli_db = (tmp_path / ".copilot" / "session-store.db").as_posix()
    ide_db = (
        appdata / "Code" / "User" / "globalStorage"
        / "github.copilot-chat" / "session-store.db"
    ).as_posix()
    assert cli_db in sources
    assert ide_db in sources
    assert (tmp_path / ".copilot").as_posix() in watch
    assert (
        appdata / "Code" / "User" / "globalStorage" / "github.copilot-chat"
    ).as_posix() in watch
    assert any("workspaceStorage/*/chatSessions/*.jsonl" in source for source in sources)


def test_vscode_storage_falls_back_to_roaming_without_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.delenv("APPDATA", raising=False)

    module = reload_capture_adapters()
    expected = (tmp_path / "AppData" / "Roaming" / "Code" / "User").as_posix()

    sources = _posix(module.ADAPTERS["copilot"]["sources"])
    assert any(expected in p for p in sources), sources


def test_vscode_storage_keeps_posix_paths_elsewhere(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.delenv("APPDATA", raising=False)

    module = reload_capture_adapters()
    expected = (tmp_path / ".config" / "Code" / "User").as_posix()

    for provider in ("copilot", "roo"):
        sources = _posix(module.ADAPTERS[provider]["sources"])
        assert sources, provider
        assert any(expected in p for p in sources), (provider, sources)


def test_kimi_code_includes_current_wire_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    module = reload_capture_adapters()
    sources = _posix(module.ADAPTERS["kimi"]["sources"])
    watch = _posix(module.ADAPTERS["kimi"]["watch"])

    assert any(".kimi-code/sessions/**/agents/main/wire.jsonl" in path for path in sources)
    assert any(".kimi-code/sessions" in path for path in watch)

def test_hermes_uses_localappdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(os, "name", "nt")
    local = tmp_path / "AppData" / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    module = reload_capture_adapters()
    sources = _posix(module.ADAPTERS["hermes"]["sources"])
    assert sources == [(local / "hermes" / "state.db").as_posix()]


def test_kilo_windows_searches_vscode_global_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(os, "name", "nt")
    appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))

    module = reload_capture_adapters()
    sources = _posix(module.ADAPTERS["kilo"]["sources"])
    expected = (appdata / "Code" / "User" / "globalStorage" / "kilocode.kilo-code").as_posix()
    assert any(expected in source and source.endswith("/**/kilo.db") for source in sources)
    canonical_cli_db = (tmp_path / ".local" / "share" / "kilo" / "kilo.db").as_posix()
    assert canonical_cli_db in sources

def test_qwen_includes_current_project_chats(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    module = reload_capture_adapters()
    sources = _posix(module.ADAPTERS["qwen"]["sources"])
    watch = _posix(module.ADAPTERS["qwen"]["watch"])

    assert any(".qwen/projects/**/chats/*.jsonl" in path for path in sources)
    assert any(".qwen/projects" in path for path in watch)


def test_codex_keeps_incremental_rollout_capture(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    module = reload_capture_adapters()

    assert module.ADAPTERS["codex"]["mode"] == "tail"
