from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.redactor import redact_for_export
from hive_mind.maintenance.lock import MaintenanceLock
from scripts.utils.sanitizer import sanitize

_LEGACY_AUDIT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"HIVE_MIND_API_KEY\s*=\s*[^\s\\\"']*", re.IGNORECASE),
        "HIVE_MIND_API_KEY [REDACTED:token]",
    ),
    (
        re.compile(r"ANTHROPIC_API_KEY\s*=\s*[^\s\\\"']*", re.IGNORECASE),
        "ANTHROPIC_API_KEY [REDACTED:token]",
    ),
    (
        re.compile(r"OPENAI_API_KEY\s*=\s*[^\s\\\"']*", re.IGNORECASE),
        "OPENAI_API_KEY [REDACTED:token]",
    ),
    (
        re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/=]{6,}", re.IGNORECASE),
        "AUTHORIZATION [REDACTED:token]",
    ),
    (
        re.compile(r"AIza[0-9A-Za-z_\-]{0,80}"),
        "[REDACTED:google-key]",
    ),
    (
        re.compile(r"xoxb-[A-Za-z0-9\-]{6,}"),
        "[REDACTED:slack-token]",
    ),
    (
        re.compile(r"sk-[A-Za-z0-9_\-]{8,80}"),
        "[REDACTED:token]",
    ),
]


@dataclass(frozen=True)
class ArtifactScrubEntry:
    path: str
    changed: bool
    before_bytes: int
    after_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactScrubReport:
    apply: bool
    scanned: int
    changed: int
    entries: tuple[ArtifactScrubEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "apply": self.apply,
            "scanned": self.scanned,
            "changed": self.changed,
            "entries": [e.to_dict() for e in self.entries],
        }


def default_runtime_artifact_targets(root: Path) -> list[Path]:
    return [
        root / "logs" / "audit" / "windows-compatibility-matrix.json",
        root / "logs" / "audit" / "m0-tracked.patch",
        root / "logs" / "audit" / "m1-tracked.patch",
        root / "logs" / "audit" / "m1-staged-review.patch",
        root / "logs" / "audit" / "m1-staged-review-v2.patch",
        root / "logs" / "audit" / "pre-implementation-tracked.patch",
        root / "logs" / "graph_push_backlog.jsonl",
    ]


def _scrub_text(text: str) -> str:
    result = redact_for_export(sanitize(text))
    for pattern, replacement in _LEGACY_AUDIT_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def scrub_runtime_artifacts(
    *,
    project_root: str | Path,
    apply: bool = False,
    targets: list[str | Path] | None = None,
) -> ArtifactScrubReport:
    root = Path(project_root)
    candidates = [Path(p) for p in (targets or default_runtime_artifact_targets(root))]
    entries: list[ArtifactScrubEntry] = []

    for path in candidates:
        if not path.is_file():
            continue
        before = path.read_text(encoding="utf-8", errors="replace")
        after = _scrub_text(before)
        changed = before != after
        entries.append(
            ArtifactScrubEntry(
                path=str(path),
                changed=changed,
                before_bytes=len(before.encode("utf-8", errors="replace")),
                after_bytes=len(after.encode("utf-8", errors="replace")),
            )
        )
        if apply and changed:
            lock_path = path.with_suffix(path.suffix + ".secret-scrub.lock")
            with MaintenanceLock(lock_path):
                path.write_text(after, encoding="utf-8")

    return ArtifactScrubReport(
        apply=apply,
        scanned=len(entries),
        changed=sum(1 for e in entries if e.changed),
        entries=tuple(entries),
    )
