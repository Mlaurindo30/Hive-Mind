"""Verified SQLite backup engine (D008-R1B).

Ported from `scripts/health/backup_databases.py`, preserving the behaviour
that was already correct — `sqlite3.Connection.backup()` over a read-only
source, so a live database is copied consistently — and adding the
guarantees it lacked.

What the legacy engine did not do, and this one does:

  - a single-instance lock, so two runs cannot interleave on one destination;
  - writes to a `.partial` file and finalizes with `os.replace` (atomic);
  - verifies every artifact (`PRAGMA integrity_check` + SHA-256) *before*
    it counts as a backup;
  - **prunes only after the new backup is verified** — the legacy code
    pruned immediately after copying, so a corrupt new backup could evict a
    good old one;
  - writes a content manifest (artifacts, hashes, sizes, coverage);
  - cleans up temporaries on failure;
  - supports dry-run.

Coverage is honest: only SQLite is backed up here. Docker-hosted services
need their own snapshot and are declared as such rather than pretended.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from hive_mind.maintenance.lock import MaintenanceLock, MaintenanceLockError

MANIFEST_VERSION = 1
MANIFEST_PREFIX = "backup-manifest"
PARTIAL_SUFFIX = ".partial"
_HASH_CHUNK = 1 << 20


class Coverage:
    """Honest statement of what a backup does and does not include."""

    BACKED_UP = "BACKED_UP"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    REQUIRES_SERVICE_SNAPSHOT = "REQUIRES_SERVICE_SNAPSHOT"
    EXTERNALLY_MANAGED = "EXTERNALLY_MANAGED"


COMPONENT_COVERAGE: dict[str, str] = {
    "sqlite": Coverage.BACKED_UP,
    "cerebro-markdown": Coverage.NOT_SUPPORTED,
    "dotenv-secrets": Coverage.NOT_SUPPORTED,
    "milvus": Coverage.REQUIRES_SERVICE_SNAPSHOT,
    "falkordb": Coverage.REQUIRES_SERVICE_SNAPSHOT,
    "ragflow": Coverage.REQUIRES_SERVICE_SNAPSHOT,
    "lightrag": Coverage.EXTERNALLY_MANAGED,
}


@dataclass
class BackupTarget:
    name: str
    src: Path
    dest_dir: Path
    keep_last: int = 7
    enabled: bool = True


@dataclass
class Artifact:
    name: str
    path: str
    sha256: str
    size_bytes: int
    source_size_bytes: int
    elapsed_seconds: float


@dataclass
class TargetResult:
    name: str
    status: str  # OK | SKIP | FAIL
    detail: str
    artifact: Optional[Artifact] = None
    pruned: list[str] = field(default_factory=list)


@dataclass
class BackupReport:
    timestamp: str
    dry_run: bool
    results: list[TargetResult] = field(default_factory=list)
    manifest_path: Optional[str] = None
    coverage: dict[str, str] = field(default_factory=lambda: dict(COMPONENT_COVERAGE))

    @property
    def failures(self) -> list[TargetResult]:
        return [r for r in self.results if r.status == "FAIL"]

    @property
    def healthy(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "dry_run": self.dry_run,
            "healthy": self.healthy,
            "manifest": self.manifest_path,
            "coverage": self.coverage,
            "results": [
                {
                    **{k: v for k, v in asdict(r).items() if k != "artifact"},
                    "artifact": asdict(r.artifact) if r.artifact else None,
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Target discovery (ported: same sources, same destinations, same retention)
# ---------------------------------------------------------------------------
def default_targets(
    *, home: Optional[Path] = None, root: Optional[Path] = None, env: Optional[dict] = None
) -> list[BackupTarget]:
    env = env if env is not None else os.environ
    home = Path(home) if home is not None else Path.home()
    if root is None:
        from hive_mind.project import resolve_project_root

        root = resolve_project_root()
    root = Path(root)
    return [
        BackupTarget("claude-mem", home / ".claude-mem" / "claude-mem.db",
                     home / ".claude-mem" / "backups", keep_last=7),
        BackupTarget("hive_mind", root / "hive_mind.db", root / "backups", keep_last=7),
        BackupTarget("swarmclaw", home / ".swarmclaw" / "data" / "swarmclaw.db",
                     home / ".swarmclaw" / "backups", keep_last=7),
        # Hermes is large; opt in, matching the legacy behaviour.
        BackupTarget("hermes", home / ".hermes" / "state.db", home / ".hermes" / "backups",
                     keep_last=3, enabled=bool(env.get("SINAPSE_BACKUP_HERMES"))),
    ]


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_is_intact(path: Path) -> tuple[bool, str]:
    """Run integrity_check and foreign_key_check on a backup artifact."""
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10)
    except sqlite3.Error as exc:
        return False, f"cannot open: {exc}"
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            return False, f"integrity_check: {integrity[0] if integrity else 'no result'}"
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            return False, f"foreign_key_check: {len(violations)} violation(s)"
        return True, "ok"
    except sqlite3.DatabaseError as exc:
        return False, f"not a valid database: {exc}"
    finally:
        conn.close()


def _hot_backup(src: Path, dest: Path) -> float:
    """Consistent copy of a live database (ported verbatim in behaviour)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    src_con = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True, timeout=10)
    dst_con = sqlite3.connect(str(dest))
    try:
        src_con.backup(dst_con, pages=512)
    finally:
        dst_con.close()
        src_con.close()
    return time.monotonic() - started


def _prune(dest_dir: Path, name: str, keep_last: int) -> list[Path]:
    if keep_last <= 0:
        return []
    existing = sorted(dest_dir.glob(f"{name}.20*.db"), key=lambda p: p.name)
    removed = existing[:-keep_last]
    for path in removed:
        path.unlink(missing_ok=True)
    return removed


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
def _backup_one(target: BackupTarget, stamp: str, *, dry_run: bool) -> TargetResult:
    if not target.enabled:
        return TargetResult(target.name, "SKIP", "disabled")
    if not target.src.exists():
        return TargetResult(target.name, "SKIP", "source not found")

    dest = target.dest_dir / f"{target.name}.{stamp}.db"
    if dest.exists():
        return TargetResult(target.name, "OK", f"already present for {stamp}: {dest}")
    if dry_run:
        return TargetResult(target.name, "OK", f"would write {dest}")

    partial = dest.with_name(dest.name + PARTIAL_SUFFIX)
    try:
        elapsed = _hot_backup(target.src, partial)
    except Exception as exc:  # noqa: BLE001 - a copy failure is a reported result
        partial.unlink(missing_ok=True)
        return TargetResult(target.name, "FAIL", f"copy failed: {exc}")

    intact, reason = sqlite_is_intact(partial)
    if not intact:
        partial.unlink(missing_ok=True)
        return TargetResult(target.name, "FAIL", f"verification failed: {reason}")

    digest = sha256_file(partial)
    size = partial.stat().st_size
    os.replace(partial, dest)  # atomic: a reader never sees a half file

    return TargetResult(
        target.name,
        "OK",
        f"{dest} ({size} bytes, {elapsed:.1f}s)",
        artifact=Artifact(
            name=target.name, path=str(dest), sha256=digest, size_bytes=size,
            source_size_bytes=target.src.stat().st_size, elapsed_seconds=round(elapsed, 3),
        ),
    )


def run(
    targets: Optional[Iterable[BackupTarget]] = None,
    *,
    dry_run: bool = False,
    lock_dir: Optional[Path] = None,
    stamp: Optional[str] = None,
) -> BackupReport:
    """Back up every target, verify, then prune. Prune never precedes verify."""
    targets = list(targets) if targets is not None else default_targets()
    stamp = stamp or time.strftime("%Y-%m-%d")
    report = BackupReport(timestamp=stamp, dry_run=dry_run)

    lock_path = Path(lock_dir or Path.home() / ".hive-mind") / "backup.lock"
    lock = MaintenanceLock(lock_path)
    lock.acquire()  # raises MaintenanceLockError if another run holds it
    try:
        for target in targets:
            report.results.append(_backup_one(target, stamp, dry_run=dry_run))

        # Retention runs only when every target succeeded and was verified.
        # A failed run must never evict a known-good older backup.
        if report.healthy and not dry_run:
            by_name = {t.name: t for t in targets}
            for result in report.results:
                if result.status != "OK" or result.artifact is None:
                    continue
                target = by_name[result.name]
                result.pruned = [
                    str(p) for p in _prune(target.dest_dir, target.name, target.keep_last)
                ]

        if not dry_run:
            report.manifest_path = _write_manifest(report, targets, stamp)
    finally:
        lock.release()
    return report


def _write_manifest(report: BackupReport, targets: list[BackupTarget], stamp: str) -> Optional[str]:
    artifacts = [r.artifact for r in report.results if r.artifact]
    if not artifacts:
        return None
    # The manifest lives beside the first destination so verify can find it.
    dest_dir = Path(artifacts[0].path).parent
    manifest_path = dest_dir / f"{MANIFEST_PREFIX}-{stamp}.json"
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "timestamp": stamp,
        "coverage": report.coverage,
        "artifacts": [asdict(a) for a in artifacts],
    }
    tmp = manifest_path.with_name(manifest_path.name + PARTIAL_SUFFIX)
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, manifest_path)
    return str(manifest_path)


# ---------------------------------------------------------------------------
# Verify / status / restore
# ---------------------------------------------------------------------------
def verify(manifest_path: Path | str) -> dict:
    """Re-check every artifact a manifest claims: hash and SQLite integrity."""
    manifest_path = Path(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks = []
    for entry in payload.get("artifacts", []):
        path = Path(entry["path"])
        if not path.is_file():
            checks.append({"name": entry["name"], "ok": False, "reason": "missing"})
            continue
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            checks.append({"name": entry["name"], "ok": False, "reason": "sha256 mismatch"})
            continue
        intact, reason = sqlite_is_intact(path)
        checks.append({"name": entry["name"], "ok": intact, "reason": reason})
    return {
        "manifest": str(manifest_path),
        "ok": all(c["ok"] for c in checks) and bool(checks),
        "checks": checks,
    }


def latest_manifest(dest_dir: Path | str) -> Optional[Path]:
    found = sorted(Path(dest_dir).glob(f"{MANIFEST_PREFIX}-*.json"))
    return found[-1] if found else None


def status(targets: Optional[Iterable[BackupTarget]] = None) -> dict:
    """What exists on disk right now, per target. Read-only."""
    targets = list(targets) if targets is not None else default_targets()
    entries = []
    for target in targets:
        backups = sorted(target.dest_dir.glob(f"{target.name}.20*.db"))
        newest = backups[-1] if backups else None
        entries.append({
            "name": target.name,
            "enabled": target.enabled,
            "source_present": target.src.exists(),
            "backups": len(backups),
            "newest": str(newest) if newest else None,
            "keep_last": target.keep_last,
        })
    return {"targets": entries, "coverage": dict(COMPONENT_COVERAGE)}


class RestoreRefused(RuntimeError):
    """Raised when a restore would overwrite live data without consent."""


def restore(
    manifest_path: Path | str,
    target_dir: Path | str,
    *,
    allow_overwrite_live: bool = False,
) -> dict:
    """Restore artifacts into `target_dir`.

    Restoring **into an alternate directory is the default**. Writing over a
    live database requires `allow_overwrite_live=True`, which callers must set
    deliberately.
    """
    manifest_path = Path(manifest_path)
    target_dir = Path(target_dir)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    restored = []
    target_dir.mkdir(parents=True, exist_ok=True)
    for entry in payload.get("artifacts", []):
        source = Path(entry["path"])
        destination = target_dir / f"{entry['name']}.db"
        if destination.exists() and not allow_overwrite_live:
            raise RestoreRefused(
                f"{destination} exists; pass allow_overwrite_live to replace it"
            )
        if not source.is_file():
            raise FileNotFoundError(f"artifact missing: {source}")
        if sha256_file(source) != entry["sha256"]:
            raise ValueError(f"artifact {entry['name']} fails its recorded sha256")
        partial = destination.with_name(destination.name + PARTIAL_SUFFIX)
        partial.write_bytes(source.read_bytes())
        intact, reason = sqlite_is_intact(partial)
        if not intact:
            partial.unlink(missing_ok=True)
            raise ValueError(f"restored {entry['name']} is not intact: {reason}")
        os.replace(partial, destination)
        restored.append({"name": entry["name"], "path": str(destination)})
    return {"manifest": str(manifest_path), "restored": restored, "ok": bool(restored)}
