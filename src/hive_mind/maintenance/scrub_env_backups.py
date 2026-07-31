from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from hive_mind.maintenance.lock import MaintenanceLock

_SECRET_NAME = re.compile(r"(API_KEY|TOKEN|PASSWORD|SECRET)$")


@dataclass(frozen=True)
class EnvBackupScrubEntry:
    path: str
    changed: bool
    redacted_keys: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnvBackupScrubReport:
    apply: bool
    scanned: int
    changed: int
    entries: tuple[EnvBackupScrubEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "apply": self.apply,
            "scanned": self.scanned,
            "changed": self.changed,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def default_env_backup_targets(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.glob("backups/**/.env")
        if path.is_file()
    )


def _scrub_env_text(text: str) -> tuple[str, tuple[str, ...]]:
    lines: list[str] = []
    redacted: list[str] = []
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        newline = raw[len(line):]
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            lines.append(raw)
            continue
        key, value = line.split("=", 1)
        env_key = key.strip()
        if _SECRET_NAME.search(env_key) and value.strip().strip('"').strip("'"):
            lines.append(f"{key}=[REDACTED:env-backup-secret]{newline}")
            redacted.append(env_key)
            continue
        lines.append(raw)
    return "".join(lines), tuple(sorted(set(redacted)))


def scrub_env_backups(
    *,
    project_root: str | Path,
    apply: bool = False,
    targets: list[str | Path] | None = None,
) -> EnvBackupScrubReport:
    root = Path(project_root)
    candidates = [Path(p) for p in (targets or default_env_backup_targets(root))]
    entries: list[EnvBackupScrubEntry] = []

    for path in candidates:
        if not path.is_file():
            continue
        before = path.read_text(encoding="utf-8", errors="ignore")
        after, redacted_keys = _scrub_env_text(before)
        changed = before != after
        entries.append(
            EnvBackupScrubEntry(
                path=str(path),
                changed=changed,
                redacted_keys=redacted_keys,
            )
        )
        if apply and changed:
            lock_path = path.with_suffix(path.suffix + ".env-scrub.lock")
            with MaintenanceLock(lock_path):
                path.write_text(after, encoding="utf-8")

    return EnvBackupScrubReport(
        apply=apply,
        scanned=len(entries),
        changed=sum(1 for entry in entries if entry.changed),
        entries=tuple(entries),
    )
