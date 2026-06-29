"""Tests for the Antigravity (`agy`) provider wrapper."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core import agy_client


def test_run_agy_uses_real_home_by_default(monkeypatch, tmp_path):
    fake_agy = tmp_path / "agy"
    fake_agy.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_agy.chmod(0o755)
    captured = {}

    def fake_run(cmd, cwd, env, capture_output, text, timeout):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["home"] = env["HOME"]
        return subprocess.CompletedProcess(cmd, 0, stdout="OK", stderr="")

    monkeypatch.setattr(agy_client, "AGY_BIN", str(fake_agy))
    monkeypatch.setenv("HOME", str(tmp_path / "real-home"))
    monkeypatch.delenv("AGY_USE_ISOLATED_HOME", raising=False)
    monkeypatch.setattr(agy_client.subprocess, "run", fake_run)

    assert agy_client._run_agy("ping", "gemini-3.5-flash", timeout=1) == "OK"
    assert captured["home"] == str(Path.home())
    assert captured["cwd"] == "/tmp"
    assert "--new-project" in captured["cmd"]


def test_run_agy_can_opt_into_isolated_home(monkeypatch, tmp_path):
    fake_agy = tmp_path / "agy"
    fake_agy.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_agy.chmod(0o755)
    real_gemini = tmp_path / "real-gemini"
    real_gemini.mkdir()
    (real_gemini / "oauth_creds.json").write_text("{}", encoding="utf-8")
    agy_token = real_gemini / "antigravity-cli" / "antigravity-oauth-token"
    agy_token.parent.mkdir()
    agy_token.write_text("agy-token", encoding="utf-8")
    isolated = tmp_path / "isolated"
    captured = {}

    def fake_run(cmd, cwd, env, capture_output, text, timeout):
        captured["home"] = env["HOME"]
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(cmd, 0, stdout="OK", stderr="")

    monkeypatch.setattr(agy_client, "AGY_BIN", str(fake_agy))
    monkeypatch.setattr(agy_client, "_REAL_GEMINI_DIR", real_gemini)
    monkeypatch.setattr(agy_client, "_ISOLATED_HOME", isolated)
    monkeypatch.setenv("AGY_USE_ISOLATED_HOME", "1")
    monkeypatch.setattr(agy_client.subprocess, "run", fake_run)

    assert agy_client._run_agy("ping", "gemini-3.5-flash", timeout=1) == "OK"
    assert captured["home"] == str(isolated)
    assert captured["cwd"] == str(isolated)
    assert (isolated / ".gemini" / "oauth_creds.json").is_symlink()
    assert (isolated / ".gemini" / "antigravity-cli" / "antigravity-oauth-token").is_symlink()
