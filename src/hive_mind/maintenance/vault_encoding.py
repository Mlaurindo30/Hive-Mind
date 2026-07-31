"""Controlled repair of legacy cp1252 bytes preserved via surrogateescape."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from core.memory.writers import atomic_write, read_vault_text


@dataclass(frozen=True)
class EncodingRepairEntry:
    path: str
    status: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EncodingRepairReport:
    vault_root: str
    apply: bool
    scanned: int
    candidates: int
    repaired: int
    unchanged: int
    failed: int
    entries: tuple[EncodingRepairEntry, ...]

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


def _has_legacy_surrogates(text: str) -> bool:
    return any(0xDC80 <= ord(ch) <= 0xDCFF for ch in text)


def _repair_legacy_surrogates(text: str) -> tuple[str | None, str]:
    if not _has_legacy_surrogates(text):
        return None, "already_utf8_clean"
    out: list[str] = []
    repaired = 0
    for ch in text:
        code = ord(ch)
        if 0xDC80 <= code <= 0xDCFF:
            raw = bytes([code - 0xDC00])
            out.append(raw.decode("cp1252"))
            repaired += 1
        else:
            out.append(ch)
    normalized = "".join(out)
    if _has_legacy_surrogates(normalized):
        return None, "surrogates_remain_after_repair"
    return normalized, f"cp1252_surrogates_normalized:{repaired}"


def repair_legacy_encoding(*, vault_root: str | Path, apply: bool = False) -> EncodingRepairReport:
    root = Path(vault_root).resolve()
    entries: list[EncodingRepairEntry] = []
    scanned = 0
    candidates = 0
    repaired = 0
    unchanged = 0
    failed = 0

    for path in sorted(root.rglob("*.md")):
        scanned += 1
        text = read_vault_text(str(path))
        normalized, reason = _repair_legacy_surrogates(text)
        if normalized is None:
            unchanged += 1
            if reason != "already_utf8_clean":
                unchanged -= 1
                failed += 1
                entries.append(EncodingRepairEntry(str(path), "failed", reason))
            continue
        candidates += 1
        if not apply:
            entries.append(EncodingRepairEntry(str(path), "candidate", reason))
            continue
        if atomic_write(str(path), normalized):
            repaired += 1
            entries.append(EncodingRepairEntry(str(path), "repaired", reason))
        else:
            failed += 1
            entries.append(EncodingRepairEntry(str(path), "failed", "atomic_write_failed"))

    return EncodingRepairReport(
        vault_root=str(root),
        apply=apply,
        scanned=scanned,
        candidates=candidates,
        repaired=repaired,
        unchanged=unchanged,
        failed=failed,
        entries=tuple(entries),
    )
