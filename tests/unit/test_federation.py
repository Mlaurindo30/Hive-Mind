import sqlite3

import pytest
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.federation import import_signed_neurons, trust_public_key
from core.signing import generate_keypair, load_private_key, sign_neuron


def _db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE neurons (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            type TEXT NOT NULL,
            source_file TEXT,
            content TEXT,
            hash TEXT,
            metadata TEXT,
            community INTEGER,
            visibility TEXT DEFAULT 'private',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    return conn


def _signed(root, monkeypatch, neuron):
    monkeypatch.setenv("SINAPSE_HOME", str(root))
    import core.signing as signing

    monkeypatch.setattr(signing, "SINAPSE_HOME", str(root))
    generate_keypair("default")
    private_key = load_private_key("default")
    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    fingerprint = trust_public_key(root, public_pem)
    return sign_neuron(neuron, "default"), fingerprint


def test_bidirectional_import_between_two_instances(tmp_path, monkeypatch):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    neuron_a = {
        "id": "a1",
        "label": "From A",
        "type": "fact",
        "content": "shared by A",
        "visibility": "shared",
    }
    signed_a, fingerprint_a = _signed(root_a, monkeypatch, neuron_a)
    public_a = (
        root_a / "config" / "keys" / "default_pubkey.pem"
    ).read_bytes()
    trust_public_key(root_b, public_a)

    db_b = _db()
    imported_b = import_signed_neurons(db_b, [signed_a], fingerprint_a, root_b)
    assert imported_b == [f"federated:{fingerprint_a[:16]}:a1"]

    neuron_b = {
        "id": "b1",
        "label": "From B",
        "type": "fact",
        "content": "shared by B",
        "visibility": "public",
    }
    signed_b, fingerprint_b = _signed(root_b, monkeypatch, neuron_b)
    public_b = (
        root_b / "config" / "keys" / "default_pubkey.pem"
    ).read_bytes()
    trust_public_key(root_a, public_b)

    db_a = _db()
    imported_a = import_signed_neurons(db_a, [signed_b], fingerprint_b, root_a)
    assert imported_a == [f"federated:{fingerprint_b[:16]}:b1"]


def test_import_rejects_tampered_neuron(tmp_path, monkeypatch):
    root = tmp_path / "source"
    target = tmp_path / "target"
    signed, key_fingerprint = _signed(
        root,
        monkeypatch,
        {
            "id": "n1",
            "label": "Original",
            "type": "fact",
            "content": "trusted",
            "visibility": "shared",
        },
    )
    trust_public_key(
        target,
        (root / "config" / "keys" / "default_pubkey.pem").read_bytes(),
    )
    signed["content"] = "tampered"

    with pytest.raises(ValueError, match="invalid signature"):
        import_signed_neurons(_db(), [signed], key_fingerprint, target)
