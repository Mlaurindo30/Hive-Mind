"""
Ed25519 signing and verification for Hive-Mind neuron export.
Keys stored in config/keys/ (must be gitignored).
"""

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)

# Fields excluded from canonical payload (volatile metadata)
_EXCLUDE_FIELDS = {"created_at", "updated_at", "indexed_at"}
# Fields added by signing (must be stripped before verification)
_SIGNATURE_FIELDS = {"_signature", "_pubkey_fingerprint"}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_PROJECT_ROOT))


def get_key_dir() -> Path:
    """Return the directory where key PEM files are stored, creating it if needed."""
    key_dir = Path(SINAPSE_HOME) / "config" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    return key_dir


def fingerprint(pubkey) -> str:
    """Return the SHA-256 hex digest of the DER-encoded public key."""
    der = pubkey.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def generate_keypair(name: str = "default") -> dict:
    """
    Generate an Ed25519 key pair and persist both keys as PEM files.

    Returns a dict with keys: name, fingerprint (first 16 hex chars), pubkey_path.
    Private key file is created with mode 0o600.
    """
    key_dir = get_key_dir()
    priv_path = key_dir / f"{name}_privkey.pem"
    pub_path = key_dir / f"{name}_pubkey.pem"

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    pub_pem = public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)

    # Write private key and restrict permissions immediately
    priv_path.write_bytes(priv_pem)
    priv_path.chmod(0o600)

    pub_path.write_bytes(pub_pem)

    fp = fingerprint(public_key)
    return {
        "name": name,
        "fingerprint": fp[:16],
        "pubkey_path": str(pub_path),
    }


def load_private_key(name: str = "default"):
    """Load and return the Ed25519 private key from the PEM file for *name*."""
    key_dir = get_key_dir()
    priv_path = key_dir / f"{name}_privkey.pem"
    if not priv_path.exists():
        raise FileNotFoundError(
            f"Private key '{name}' not found at {priv_path}. "
            "Run generate_keypair() first."
        )
    pem_data = priv_path.read_bytes()
    return load_pem_private_key(pem_data, password=None)


def load_public_key(name: str = "default"):
    """Load and return the Ed25519 public key from the PEM file for *name*."""
    key_dir = get_key_dir()
    pub_path = key_dir / f"{name}_pubkey.pem"
    if not pub_path.exists():
        raise FileNotFoundError(
            f"Public key '{name}' not found at {pub_path}. "
            "Run generate_keypair() first."
        )
    pem_data = pub_path.read_bytes()
    return load_pem_public_key(pem_data)


def _canonical_bytes(neuron: dict) -> bytes:
    """
    Build canonical JSON bytes from a neuron dict.

    Excludes volatile timestamp fields and signature fields so that the payload
    is deterministic across nodes.
    """
    excluded = _EXCLUDE_FIELDS | _SIGNATURE_FIELDS
    canonical = {k: v for k, v in neuron.items() if k not in excluded}
    return json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sign_neuron(neuron: dict, key_name: str = "default") -> dict:
    """
    Sign *neuron* with the private key identified by *key_name*.

    Returns a copy of the neuron dict augmented with:
      _signature          — base64-encoded Ed25519 signature
      _pubkey_fingerprint — full SHA-256 hex of the DER-encoded public key
    """
    private_key = load_private_key(key_name)
    public_key = private_key.public_key()

    payload = _canonical_bytes(neuron)
    raw_sig = private_key.sign(payload)

    signed = dict(neuron)
    signed["_signature"] = base64.b64encode(raw_sig).decode("ascii")
    signed["_pubkey_fingerprint"] = fingerprint(public_key)
    return signed


def verify_neuron(neuron: dict, pubkey) -> bool:
    """
    Verify the Ed25519 signature embedded in *neuron* against *pubkey*.

    Returns True when the signature is valid, False otherwise.
    Never raises on an invalid or missing signature — only on genuinely bad
    input format (e.g. non-dict).
    """
    raw_sig_b64 = neuron.get("_signature")
    if not raw_sig_b64:
        return False

    try:
        raw_sig = base64.b64decode(raw_sig_b64)
    except Exception:
        return False

    payload = _canonical_bytes(neuron)

    try:
        pubkey.verify(raw_sig, payload)
        return True
    except Exception:
        return False
