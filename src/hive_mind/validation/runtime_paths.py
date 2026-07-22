"""Pure policy for canonical operational runtime paths."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable


_FORBIDDEN_FAMILIES = (
    ".codex/worktrees",
    ".worktrees",
    "backups/worktrees",
    "hive-mind-archive",
    "hive-mind-consolidation",
)


@dataclass(frozen=True)
class RuntimePathReference:
    """A named value taken from an operational runtime surface."""

    source: str
    value: str


@dataclass(frozen=True)
class RuntimePathFinding:
    """Evidence that an operational reference is not canonical."""

    source: str
    value: str
    normalized_value: str
    reason: str
    matched: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def normalize_runtime_value(value: str) -> str:
    """Normalize separators and case without interpreting command syntax."""

    normalized = value.strip().replace("\\", "/").casefold()
    if normalized.startswith("//"):
        return "//" + re.sub(r"/{2,}", "/", normalized[2:])
    return re.sub(r"/{2,}", "/", normalized)


def _contains_path_family(value: str, family: str) -> bool:
    return bool(
        re.search(
            rf"(?:^|/){re.escape(family)}(?=/|[\s\"']|$)",
            value,
        )
    )


def _hive_mind_roots(value: str) -> Iterable[str]:
    pattern = re.compile(
        r"(?P<root>(?:[a-z]:/|//[^/\s\"']+/[^/\s\"']+/|/)"
        r"(?:[^/\s\"']+/)*hive-mind)(?=/|[\s\"']|$)"
    )
    return (match.group("root").rstrip("/") for match in pattern.finditer(value))


def find_runtime_path_violations(
    references: Iterable[RuntimePathReference],
    canonical_root: str,
) -> list[RuntimePathFinding]:
    """Return explicit findings for noncanonical operational references."""

    canonical = normalize_runtime_value(canonical_root).rstrip("/")
    findings: list[RuntimePathFinding] = []
    for reference in references:
        normalized = normalize_runtime_value(reference.value)
        family = next(
            (
                candidate
                for candidate in _FORBIDDEN_FAMILIES
                if _contains_path_family(normalized, candidate)
            ),
            None,
        )
        if family is not None:
            findings.append(
                RuntimePathFinding(
                    source=reference.source,
                    value=reference.value,
                    normalized_value=normalized,
                    reason="forbidden_path_family",
                    matched=family,
                )
            )
            continue

        noncanonical_root = next(
            (root for root in _hive_mind_roots(normalized) if root != canonical),
            None,
        )
        if noncanonical_root is not None:
            findings.append(
                RuntimePathFinding(
                    source=reference.source,
                    value=reference.value,
                    normalized_value=normalized,
                    reason="noncanonical_hive_mind_root",
                    matched=noncanonical_root,
                )
            )
    return findings
