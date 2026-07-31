"""Protected pre-install snapshot owned by the native Python installer."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


_SOURCES = ("cerebro", "hive_mind.db", ".env", ".mcp.json", "config/mcp")


@dataclass(frozen=True)
class InstallSnapshot:
    snapshot_path: Path
    manifest_path: Path
    database_backup_path: Path | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        integrity = destination_connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError("SQLite backup integrity check failed")
    finally:
        destination_connection.close()
        source_connection.close()


def create_install_snapshot(root: Path, output_root: Path) -> InstallSnapshot:
    root = root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_root / f"install-{datetime.now():%Y%m%d-%H%M%S}"
    snapshot_path.mkdir()
    hashes: dict[str, str] = {}
    database_backup_path: Path | None = None

    for relative in _SOURCES:
        source = root / relative
        if not source.exists():
            continue
        destination = snapshot_path / relative
        if source.is_dir():
            shutil.copytree(source, destination)
            for item in source.rglob("*"):
                if item.is_file():
                    hashes[str(item.relative_to(root)).replace("\\", "/")] = _sha256(item)
            continue
        if relative == "hive_mind.db":
            _copy_sqlite(source, destination)
            database_backup_path = destination
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        hashes[relative] = _sha256(source)

    manifest_path = snapshot_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source_root": str(root),
                "database_backup_path": str(database_backup_path) if database_backup_path else None,
                "hashes": hashes,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return InstallSnapshot(snapshot_path, manifest_path, database_backup_path)
