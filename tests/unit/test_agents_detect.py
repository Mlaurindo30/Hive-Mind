"""D009 (fatia 1) — native provider detection under hive_mind.agents.

Ports the detection contract from register-mcp.ps1: a provider is present when
its command is on PATH OR one of its marker directories exists. Detection is
injectable (home/appdata/command lookup) so it is deterministic and
cross-platform in tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hive_mind.agents.detect import detect_providers
from hive_mind.agents.registry import PROVIDERS, provider_ids


def _env(tmp_path: Path, *, home_subdirs=(), appdata_subdirs=(), commands=()):
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    for sub in home_subdirs:
        (home / sub).mkdir(parents=True, exist_ok=True)
    for sub in appdata_subdirs:
        (appdata / sub).mkdir(parents=True, exist_ok=True)
    have = set(commands)
    return {
        "home": home,
        "appdata": appdata,
        "which": lambda cmd: cmd if cmd in have else None,
    }


def test_registry_covers_the_ported_providers():
    ids = provider_ids()
    for expected in (
        "claude", "codex", "gemini", "qwen", "kimi", "kiro", "kilo",
        "roo", "vscode", "cursor", "opencode", "openclaw", "swarmclaw",
    ):
        assert expected in ids, f"missing provider {expected} in registry"


def test_detects_by_command_on_path(tmp_path):
    ctx = _env(tmp_path, commands=["codex"])
    found = {p.id for p in detect_providers(**ctx) if p.detected}
    assert "codex" in found


def test_detects_by_home_marker(tmp_path):
    ctx = _env(tmp_path, home_subdirs=[".qwen"])
    found = {p.id for p in detect_providers(**ctx) if p.detected}
    assert "qwen" in found


def test_qwen_detected_by_command_without_marker(tmp_path):
    ctx = _env(tmp_path, commands=["qwen"])
    found = {p.id for p in detect_providers(**ctx) if p.detected}
    assert "qwen" in found


def test_detects_by_appdata_marker(tmp_path):
    ctx = _env(
        tmp_path,
        appdata_subdirs=["Code/User/globalStorage/kilocode.kilo-code"],
    )
    found = {p.id for p in detect_providers(**ctx) if p.detected}
    assert "kilo" in found


def test_nothing_detected_on_empty_environment(tmp_path):
    ctx = _env(tmp_path)
    found = {p.id for p in detect_providers(**ctx) if p.detected}
    assert found == set()


def test_result_lists_every_provider_with_detected_flag(tmp_path):
    ctx = _env(tmp_path, commands=["claude"])
    results = detect_providers(**ctx)
    assert {p.id for p in results} == set(provider_ids())
    by_id = {p.id: p for p in results}
    assert by_id["claude"].detected is True
    assert by_id["codex"].detected is False


def test_detection_reports_the_evidence(tmp_path):
    ctx = _env(tmp_path, home_subdirs=[".cursor"])
    cursor = next(p for p in detect_providers(**ctx) if p.id == "cursor")
    assert cursor.detected is True
    assert cursor.evidence  # a human-readable reason (path or command)


def test_vscode_detected_by_copilot_marker(tmp_path):
    ctx = _env(
        tmp_path,
        appdata_subdirs=["Code/User/globalStorage/github.copilot-chat"],
    )
    found = {p.id for p in detect_providers(**ctx) if p.detected}
    assert "vscode" in found
