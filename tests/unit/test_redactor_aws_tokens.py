"""R7.1 — Redactor covers AWS / OpenAI / Bearer / API key.

Spec: specs/post-audit-stabilization.md R7.1.

Each input below MUST be fully masked by `core.redactor.redact_for_export`.
"""

from __future__ import annotations

from core.redactor import redact_for_export


def test_aws_access_key_ak():
    out = redact_for_export("AKIA1234567890ABCDEF")
    assert "AKIA1234567890ABCDEF" not in out, f"AWS AKIA leaked: {out!r}"
    assert "[REDACTED" in out, f"AWS AKIA not redacted: {out!r}"


def test_aws_access_key_as():
    out = redact_for_export("ASIA1234567890ABCDEF")
    assert "ASIA1234567890ABCDEF" not in out


def test_aws_access_key_in_env():
    out = redact_for_export('aws_access_key_id=AKIAIOSFODNN7EXAMPLE')
    assert "AKIAIOSFODNN7EXAMPLE" not in out


def test_aws_secret_key_in_env():
    out = redact_for_export('aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY')
    assert "wJalrXUtnFEMI" not in out


def test_bearer_token():
    out = redact_for_export("Authorization: Bearer abc.def.ghi-token_value")
    assert "abc.def.ghi-token_value" not in out


def test_openai_key():
    out = redact_for_export("sk-proj-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890")
    assert "sk-proj-" not in out
    assert "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" not in out


def test_api_key_equals():
    out = redact_for_export("api_key=abcdefghij1234567890")
    assert "abcdefghij1234567890" not in out
