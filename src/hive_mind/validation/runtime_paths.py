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

# Directories that are legitimate on disk but must never host a runtime target.
# Unlike the families above they are only forbidden *inside the canonical root*:
# `D:\Hive-Mind\.tmp` is a violation, an unrelated `D:\data\backups` from a
# third-party provider is not. Matched as whole segments, so `logs/backup` and
# `config/component-lock-backups` are untouched.
_FORBIDDEN_CANONICAL_SUBDIRS = (
    ".tmp",
    "backups",
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
    """Normalize separators and case without interpreting command syntax.

    A doubled separator is kept only where it carries meaning: a UNC host
    (`//server/share`) or a URL authority (`https://host`). After a drive
    letter it carries none — `D:\\\\Hive-Mind` is `D:\\Hive-Mind`, and a
    command line quoted through another shell routinely doubles the
    backslash. Keeping it there produced `d://hive-mind`, which no longer
    matched the canonical root, so canonical services were reported as
    running outside it.
    """

    normalized = value.strip().replace("\\", "/").casefold()

    def normalize_separator(match: re.Match[str]) -> str:
        if len(match.group()) < 2:
            return "/"
        start = match.start()
        preceding = normalized[start - 1] if start else ""
        if not preceding or preceding in "= \t\"'":
            return "//"
        if preceding == ":":
            # A single trailing letter is a drive (`d:`); two or more are a
            # URL scheme (`https:`). Only the scheme takes an authority.
            scheme = re.search(r"[a-z]+$", normalized[: start - 1])
            if scheme is not None and len(scheme.group()) >= 2:
                return "//"
        return "/"

    return re.sub(r"/+", normalize_separator, normalized)


def _contains_path_family(value: str, family: str) -> bool:
    return bool(
        re.search(
            rf"(?:^|/){re.escape(family)}(?=/|[\s\"']|$)",
            value,
        )
    )


def _contains_absolute_family(value: str, family: str) -> bool:
    """Like :func:`_contains_path_family` but for an absolute-path family.

    A canonical subdir (`d:/hive-mind/.tmp`) can appear as a second token on a
    command line, preceded by a space or quote rather than a `/`, so the leading
    boundary is widened to any path/whitespace/quote start.
    """
    return bool(
        re.search(
            rf"(?:^|[/\s\"']){re.escape(family)}(?=/|[\s\"']|$)",
            value,
        )
    )


def _hive_mind_roots(value: str) -> Iterable[str]:
    pattern = re.compile(
        r"(?P<root>(?:[a-z]:/|//[^/\s\"']+/[^/\s\"']+/|/)"
        r"(?:[^/\s\"']+/)*hive-mind)(?=/|[\s\"']|$)"
    )
    return (match.group("root").rstrip("/") for match in pattern.finditer(value))


def _without_canonical_root(value: str, canonical_root: str) -> str:
    pattern = re.compile(
        rf"(?<![a-z0-9_.-]){re.escape(canonical_root)}(?=/|[\s\"']|$)"
    )
    return pattern.sub("<canonical-root>", value)


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

        canonical_subdir = next(
            (
                f"{canonical}/{subdir}"
                for subdir in _FORBIDDEN_CANONICAL_SUBDIRS
                if _contains_absolute_family(normalized, f"{canonical}/{subdir}")
            ),
            None,
        )
        if canonical_subdir is not None:
            findings.append(
                RuntimePathFinding(
                    source=reference.source,
                    value=reference.value,
                    normalized_value=normalized,
                    reason="forbidden_path_family",
                    matched=canonical_subdir,
                )
            )
            continue

        remaining = _without_canonical_root(normalized, canonical)
        noncanonical_root = next(iter(_hive_mind_roots(remaining)), None)
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
