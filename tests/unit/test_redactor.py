"""
Unit tests for core/redactor.py

Covers each redaction rule plus edge cases for neuron dict handling.
"""

import copy
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.redactor import redact_for_export, redact_neuron


# ---------------------------------------------------------------------------
# redact_for_export — individual rules
# ---------------------------------------------------------------------------

def test_redact_api_token():
    text = "Use key sk-proj-abcdefghijklmnopqrstuvwxyz to authenticate"
    result = redact_for_export(text)
    assert "[REDACTED:token]" in result
    assert "sk-proj-" not in result


def test_redact_jwt():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    result = redact_for_export(f"Authorization header: {jwt}")
    assert "[REDACTED:token]" in result
    assert "eyJ" not in result


def test_redact_email():
    text = "Send invoices to billing@acme-corp.io for payment"
    result = redact_for_export(text)
    assert "[REDACTED:email]" in result
    assert "billing@acme-corp.io" not in result


def test_redact_ipv4():
    text = "Server running at 192.168.1.100 on port 8080"
    result = redact_for_export(text)
    assert "[REDACTED:ip]" in result
    assert "192.168.1.100" not in result


def test_redact_absolute_path():
    text = "Config loaded from /home/michel/secrets.txt successfully"
    result = redact_for_export(text)
    assert "[REDACTED:path]" in result
    assert "/home/michel/secrets.txt" not in result


def test_no_redaction_on_clean_text():
    text = "The sky is blue and the ocean is wide"
    result = redact_for_export(text)
    assert result == text


def test_redact_cpf():
    text = "CPF do usuário: 123.456.789-09"
    result = redact_for_export(text)
    assert "[REDACTED:cpf]" in result
    assert "123.456.789-09" not in result


def test_redact_multiple_patterns_in_one_text():
    text = "Contact admin@example.com from server 10.0.0.5 immediately"
    result = redact_for_export(text)
    assert "[REDACTED:email]" in result
    assert "[REDACTED:ip]" in result
    assert "admin@example.com" not in result
    assert "10.0.0.5" not in result


# ---------------------------------------------------------------------------
# redact_neuron — dict handling
# ---------------------------------------------------------------------------

def test_redact_neuron_only_content_label():
    neuron = {
        "id": "abc-123",
        "type": "observation",
        "visibility": "private",
        "content": "token sk-proj-secretvalue12345678901234 found",
        "label": "secret doc at /home/user/private.key",
    }
    result = redact_neuron(neuron)

    # id, type, visibility must be untouched
    assert result["id"] == "abc-123"
    assert result["type"] == "observation"
    assert result["visibility"] == "private"

    # content and label must be redacted
    assert "sk-proj-" not in result["content"]
    assert "[REDACTED:token]" in result["content"]
    assert "/home/user/private.key" not in result["label"]
    assert "[REDACTED:path]" in result["label"]


def test_redact_neuron_does_not_mutate_original():
    original = {
        "id": "xyz-999",
        "content": "email: ops@internal.org and ip 172.16.0.1",
        "label": None,
    }
    original_copy = copy.deepcopy(original)
    _ = redact_neuron(original)

    # original must be identical to what it was before the call
    assert original == original_copy
