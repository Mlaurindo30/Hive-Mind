"""Fail-closed import of signed neurons from trusted Hive-Mind peers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from cryptography.hazmat.primitives.serialization import load_pem_public_key

from core.signing import fingerprint, verify_neuron


IMPORT_COLUMNS = {
    "label",
    "type",
    "source_file",
    "content",
    "hash",
    "metadata",
    "community",
    "visibility",
}


def trusted_key_dir(root: Path) -> Path:
    return root / "config" / "keys" / "trusted"


def trust_public_key(root: Path, pem: bytes) -> str:
    pubkey = load_pem_public_key(pem)
    key_fingerprint = fingerprint(pubkey)
    destination = trusted_key_dir(root) / f"{key_fingerprint}.pem"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(pem)
    destination.chmod(0o600)
    return key_fingerprint


def load_trusted_key(root: Path, key_fingerprint: str):
    if not key_fingerprint or any(c not in "0123456789abcdef" for c in key_fingerprint):
        raise ValueError("invalid public-key fingerprint")
    path = trusted_key_dir(root) / f"{key_fingerprint}.pem"
    if not path.is_file():
        raise PermissionError(f"untrusted federation key: {key_fingerprint}")
    pubkey = load_pem_public_key(path.read_bytes())
    if fingerprint(pubkey) != key_fingerprint:
        raise ValueError("trusted key fingerprint mismatch")
    return pubkey


def import_signed_neurons(
    conn,
    neurons: Iterable[dict],
    key_fingerprint: str,
    project_root: Path,
    *,
    commit: bool = True,
) -> list[str]:
    pubkey = load_trusted_key(project_root, key_fingerprint)
    verified = []
    for neuron in neurons:
        if neuron.get("visibility") not in {"shared", "public"}:
            raise ValueError("federation import accepts only shared/public neurons")
        if neuron.get("_pubkey_fingerprint") != key_fingerprint:
            raise ValueError("neuron fingerprint does not match declared source")
        if not verify_neuron(neuron, pubkey):
            raise ValueError(f"invalid signature for neuron {neuron.get('id')!r}")
        verified.append(dict(neuron))

    imported_ids = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        for neuron in verified:
            source_id = str(neuron["id"])
            imported_id = f"federated:{key_fingerprint[:16]}:{source_id}"
            values = {key: neuron.get(key) for key in IMPORT_COLUMNS}
            metadata = values.get("metadata")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    metadata = {"source_metadata": metadata}
            metadata = metadata if isinstance(metadata, dict) else {}
            metadata.update(
                {
                    "federated": True,
                    "source_neuron_id": source_id,
                    "source_fingerprint": key_fingerprint,
                }
            )
            values["metadata"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)

            conn.execute(
                """
                INSERT INTO neurons (
                    id, label, type, source_file, content, hash, metadata,
                    community, visibility
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    label=excluded.label,
                    type=excluded.type,
                    source_file=excluded.source_file,
                    content=excluded.content,
                    hash=excluded.hash,
                    metadata=excluded.metadata,
                    community=excluded.community,
                    visibility=excluded.visibility,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    imported_id,
                    values["label"],
                    values["type"],
                    values["source_file"],
                    values["content"],
                    values["hash"],
                    values["metadata"],
                    values["community"],
                    values["visibility"],
                ),
            )
            imported_ids.append(imported_id)
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return imported_ids
