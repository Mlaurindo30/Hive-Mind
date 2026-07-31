"""Controlled repair of legacy invalid YAML frontmatter in vault notes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

import yaml

from core.memory.writers import atomic_write, read_vault_text, yaml_scalar_line


FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)
EVIDENCE_LINE_RE = re.compile(r'(?m)^evidence:\s*"(?P<value>.*)"\s*$')


@dataclass(frozen=True)
class FrontmatterRepairEntry:
    path: str
    status: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FrontmatterRepairReport:
    vault_root: str
    apply: bool
    scanned: int
    candidates: int
    repaired: int
    unchanged: int
    failed: int
    entries: tuple[FrontmatterRepairEntry, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "vault_root": self.vault_root,
            "apply": self.apply,
            "scanned": self.scanned,
            "candidates": self.candidates,
            "repaired": self.repaired,
            "unchanged": self.unchanged,
            "failed": self.failed,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _repair_frontmatter_block(block: str) -> tuple[str | None, str]:
    try:
        loaded = yaml.safe_load(block) or {}
        if isinstance(loaded, dict):
            return None, "already_valid"
        return None, f"unsupported_frontmatter_type={type(loaded).__name__}"
    except Exception:
        pass

    match = EVIDENCE_LINE_RE.search(block)
    if match is None:
        return None, "no_quoted_evidence_line"
    repaired = (
        block[:match.start()]
        + yaml_scalar_line("evidence", match.group("value")).rstrip("\n")
        + block[match.end():]
    )
    try:
        loaded = yaml.safe_load(repaired) or {}
        if not isinstance(loaded, dict):
            return None, f"repaired_type={type(loaded).__name__}"
    except Exception as exc:
        return None, f"repair_failed:{type(exc).__name__}:{exc}"
    return repaired, "repaired_evidence_yaml"


def repair_invalid_frontmatter(*, vault_root: str | Path, apply: bool = False) -> FrontmatterRepairReport:
    root = Path(vault_root).resolve()
    entries: list[FrontmatterRepairEntry] = []
    scanned = 0
    candidates = 0
    repaired_count = 0
    unchanged = 0
    failed = 0

    for path in sorted(root.rglob("*.md")):
        text = read_vault_text(str(path))
        match = FRONTMATTER_RE.match(text)
        if match is None:
            continue
        scanned += 1
        repaired_block, reason = _repair_frontmatter_block(match.group(2))
        if repaired_block is None:
            if reason == "already_valid":
                unchanged += 1
            elif reason.startswith("unsupported_frontmatter_type") or reason == "no_quoted_evidence_line":
                unchanged += 1
            else:
                failed += 1
                entries.append(FrontmatterRepairEntry(str(path), "failed", reason))
            continue

        candidates += 1
        if not apply:
            entries.append(FrontmatterRepairEntry(str(path), "candidate", reason))
            continue

        updated = text[:match.start(2)] + repaired_block + text[match.end(2):]
        if atomic_write(str(path), updated):
            repaired_count += 1
            entries.append(FrontmatterRepairEntry(str(path), "repaired", reason))
        else:
            failed += 1
            entries.append(FrontmatterRepairEntry(str(path), "failed", "atomic_write_failed"))

    return FrontmatterRepairReport(
        vault_root=str(root),
        apply=apply,
        scanned=scanned,
        candidates=candidates,
        repaired=repaired_count,
        unchanged=unchanged,
        failed=failed,
        entries=tuple(entries),
    )
