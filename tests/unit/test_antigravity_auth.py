"""Autenticacao do provider Antigravity (`agy`)."""
from __future__ import annotations

from pathlib import Path

from core import auth


def test_antigravity_auth_file_prefers_native_agy_token(monkeypatch, tmp_path):
    home = tmp_path / "home"
    token = home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    token.parent.mkdir(parents=True)
    token.write_text("token", encoding="utf-8")

    monkeypatch.setattr(auth, "ANTIGRAVITY_CLI_AUTH_FILES", (token,))
    monkeypatch.setattr(auth, "GEMINI_CLI_OAUTH_FILES", ())

    assert auth.antigravity_cli_auth_file() == token


def test_discover_antigravity_models_uses_native_agy_auth(monkeypatch, tmp_path):
    token = tmp_path / "antigravity-oauth-token"
    token.write_text("token", encoding="utf-8")
    agy = tmp_path / "agy"
    agy.write_text("#!/bin/sh\n", encoding="utf-8")
    agy.chmod(0o755)

    monkeypatch.setenv("AGY_BIN", str(agy))
    monkeypatch.setattr(auth, "antigravity_cli_auth_file", lambda: token)
    monkeypatch.setattr(auth, "gemini_cli_oauth_file", lambda: None)

    models = auth.discover_models_realtime("antigravity")

    assert models
    assert {m["provider"] for m in models} == {"antigravity"}
    assert {m["source"] for m in models} == {"antigravity_cli_models_hint"}
