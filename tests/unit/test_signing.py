"""
Unit tests for core/signing.py

All tests use tmp_path and monkeypatch get_key_dir so that no real
config/keys/ directory is touched during the test run.
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import core.signing as signing


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_key_dir(tmp_path, monkeypatch):
    """Redirect get_key_dir() to a temp directory for every test."""
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    monkeypatch.setattr(signing, "get_key_dir", lambda: key_dir)
    return key_dir


@pytest.fixture()
def sample_neuron():
    return {
        "id": "neuron-001",
        "content": "Federated swarm node handshake",
        "tags": ["hive-mind", "ed25519"],
        "created_at": "2026-06-13T00:00:00Z",
        "updated_at": "2026-06-13T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_generate_keypair_creates_files(isolated_key_dir):
    """Both PEM files must exist after generate_keypair()."""
    signing.generate_keypair("test")

    assert (isolated_key_dir / "test_privkey.pem").exists()
    assert (isolated_key_dir / "test_pubkey.pem").exists()


def test_generate_keypair_returns_fingerprint(isolated_key_dir):
    """Returned fingerprint must be a non-empty hex string (first 16 chars)."""
    result = signing.generate_keypair("fp_test")

    fp = result["fingerprint"]
    assert isinstance(fp, str)
    assert len(fp) > 0
    # Must be hex-only characters
    int(fp, 16)


def test_sign_neuron_adds_signature_field(sample_neuron, isolated_key_dir):
    """sign_neuron() must add a _signature field to the returned dict."""
    signing.generate_keypair("default")
    signed = signing.sign_neuron(sample_neuron)

    assert "_signature" in signed
    assert isinstance(signed["_signature"], str)
    assert len(signed["_signature"]) > 0


def test_verify_neuron_valid_signature(sample_neuron, isolated_key_dir):
    """A freshly signed neuron must verify successfully."""
    signing.generate_keypair("default")
    signed = signing.sign_neuron(sample_neuron)

    pubkey = signing.load_public_key("default")
    assert signing.verify_neuron(signed, pubkey) is True


def test_verify_neuron_tampered_content_fails(sample_neuron, isolated_key_dir):
    """Mutating the content field after signing must cause verification to fail."""
    signing.generate_keypair("default")
    signed = signing.sign_neuron(sample_neuron)

    tampered = dict(signed)
    tampered["content"] = "INJECTED malicious payload"

    pubkey = signing.load_public_key("default")
    assert signing.verify_neuron(tampered, pubkey) is False


def test_verify_neuron_missing_signature_fails(sample_neuron, isolated_key_dir):
    """verify_neuron() must return False (not raise) when _signature is absent."""
    signing.generate_keypair("default")
    pubkey = signing.load_public_key("default")

    # Neuron without any signature fields
    result = signing.verify_neuron(sample_neuron, pubkey)
    assert result is False
