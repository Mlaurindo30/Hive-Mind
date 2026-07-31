"""Read-only inventory of legacy project labels.

The auditor proposes classifications; it never migrates, rewrites, or normalizes
source data. SQLite sources are opened with ``mode=ro`` and ``query_only``.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote

import yaml

from hive_mind.projects.identity import (
    DEFAULT_REGISTRY_PATH,
    ProjectAliasRegistry,
)


class AuditClassification(str, Enum):
    CANONICAL = "CANONICAL"
    ALIAS = "ALIAS"
    SURFACE = "SURFACE"
    PROFILE = "PROFILE"
    UNCLASSIFIED = "UNCLASSIFIED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class ProjectAuditRow:
    legacy_label: str
    proposed_project_id: str | None
    sessions: int
    observations: int
    vectors: int
    markdown: int
    confidence: float
    classification: AuditClassification
    reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["classification"] = self.classification.value
        return payload


MINIMUM_LABELS = (
    "Hive-Mind",
    "hive-mind-windows-zero-install",
    "Hive-Mind/hive-mind-windows-zero-install",
    "Microsoft Visual Studio Code",
    "Microsoft VS Code",
    "miche",
    "Qwen",
    "hermes",
    "app",
)

_SURFACE_KINDS = {
    "qwen": "tool",
    "hermes": "tool",
    "microsoft visual studio code": "application",
    "microsoft vs code": "application",
    "app": "application",
}
_PROFILE_LABELS = {"miche"}
_PROJECT_COLUMNS = ("project", "project_name", "workspace_id", "project_id")
_METADATA_COLUMNS = ("metadata", "metadata_json", "data")


@dataclass(slots=True)
class _Counts:
    sessions: int = 0
    observations: int = 0
    vectors: int = 0
    markdown: int = 0


class _Inventory:
    def __init__(self) -> None:
        self.counts: dict[str, _Counts] = defaultdict(_Counts)
        self.candidates: dict[str, set[str]] = defaultdict(set)
        self.display: dict[str, str] = {}

    def add(
        self,
        label: str,
        kind: str,
        *,
        candidate: str | None = None,
    ) -> None:
        clean = str(label).strip()
        if not clean:
            return
        key = clean.casefold()
        self.display.setdefault(key, clean)
        target = self.counts[key]
        setattr(target, kind, getattr(target, kind) + 1)
        if candidate:
            self.candidates[key].add(candidate.strip())

    def ensure(self, label: str) -> None:
        clean = label.strip()
        key = clean.casefold()
        self.display.setdefault(key, clean)
        self.counts[key]


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9._-]+", "-", value.strip().casefold())
    return clean.strip("-._") or "unknown"


def _open_readonly(path: Path) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    resolved = path.resolve(strict=True).as_posix()
    uri = f"file:{quote(resolved, safe='/:')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type IN ('table', 'view')"
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    escaped = table.replace('"', '""')
    try:
        return {row[1] for row in connection.execute(f'PRAGMA table_info("{escaped}")')}
    except sqlite3.OperationalError:
        return set()


def _decode_json(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, Mapping) else {}


def _identity_candidate(payload: Mapping[str, Any]) -> str | None:
    identity = payload.get("project_identity")
    if not isinstance(identity, Mapping):
        return None
    value = identity.get("project_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _row_evidence(row: sqlite3.Row, columns: set[str]) -> tuple[str | None, str | None]:
    metadata: Mapping[str, Any] = {}
    for column in _METADATA_COLUMNS:
        if column in columns:
            decoded = _decode_json(row[column])
            if decoded:
                metadata = decoded
                break
    candidate = _identity_candidate(metadata)
    for column in _PROJECT_COLUMNS:
        if column in columns:
            value = row[column]
            if isinstance(value, str) and value.strip():
                return value.strip(), candidate
    identity = metadata.get("project_identity")
    if isinstance(identity, Mapping):
        for key in ("project_name", "project_id"):
            value = identity.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), candidate
    return None, candidate


def _scan_entity_table(
    connection: sqlite3.Connection,
    table: str,
    kind: str,
    inventory: _Inventory,
) -> dict[str, tuple[str, ...]]:
    columns = _columns(connection, table)
    selected = [
        column
        for column in (*_PROJECT_COLUMNS, *_METADATA_COLUMNS, "id", "rowid")
        if column in columns
    ]
    if not selected:
        return {}
    quoted = ", ".join(f'"{column}"' for column in dict.fromkeys(selected))
    by_id: dict[str, tuple[str, ...]] = {}
    for row in connection.execute(f'SELECT {quoted} FROM "{table}"'):
        label, candidate = _row_evidence(row, columns)
        if label:
            inventory.add(label, kind, candidate=candidate)
        identifiers: list[str] = []
        for column in ("id", "rowid"):
            if column in columns and row[column] is not None:
                identifiers.append(str(row[column]))
        if label:
            for identifier in identifiers:
                by_id[identifier] = (label,)
    return by_id


def _scan_vector_metadata(connection: sqlite3.Connection, inventory: _Inventory) -> None:
    columns = _columns(connection, "vector_metadata")
    project_column = next((name for name in _PROJECT_COLUMNS if name in columns), None)
    if project_column is None:
        return
    for row in connection.execute(
        f'SELECT "{project_column}" FROM "vector_metadata"'
    ):
        if isinstance(row[0], str) and row[0].strip():
            inventory.add(row[0], "vectors")


def _scan_observation_vectors(
    connection: sqlite3.Connection,
    observation_labels: Mapping[str, tuple[str, ...]],
    inventory: _Inventory,
) -> None:
    try:
        columns = _columns(connection, "vec_observations")
    except sqlite3.OperationalError:
        return
    identifier = "id" if "id" in columns else "rowid"
    try:
        rows = connection.execute(f'SELECT "{identifier}" FROM "vec_observations"')
    except sqlite3.OperationalError:
        return
    for row in rows:
        for label in observation_labels.get(str(row[0]), ()):
            inventory.add(label, "vectors")


def _scan_database(path: Path, inventory: _Inventory) -> None:
    connection = _open_readonly(path)
    if connection is None:
        return
    try:
        tables = _tables(connection)
        if "sessions" in tables:
            _scan_entity_table(connection, "sessions", "sessions", inventory)
        observations: dict[str, tuple[str, ...]] = {}
        if "observations" in tables:
            observations = _scan_entity_table(
                connection, "observations", "observations", inventory
            )
        if "vector_metadata" in tables:
            _scan_vector_metadata(connection, inventory)
        if "vec_observations" in tables:
            _scan_observation_vectors(connection, observations, inventory)
    finally:
        connection.close()


def _frontmatter(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            if handle.readline().strip() != "---":
                return {}
            lines: list[str] = []
            for line in handle:
                if line.strip() == "---":
                    break
                lines.append(line)
            else:
                return {}
    except OSError:
        return {}
    try:
        payload = yaml.safe_load("".join(lines)) or {}
    except yaml.YAMLError:
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _scan_markdown(vault_root: Path, inventory: _Inventory) -> None:
    if not vault_root.is_dir():
        return
    for path in vault_root.rglob("*.md"):
        payload = _frontmatter(path)
        candidate = _identity_candidate(payload)
        label = next(
            (
                payload.get(column).strip()
                for column in _PROJECT_COLUMNS
                if isinstance(payload.get(column), str) and payload.get(column).strip()
            ),
            None,
        )
        if label:
            inventory.add(label, "markdown", candidate=candidate)


def _classify(
    label: str,
    candidates: set[str],
    registry: ProjectAliasRegistry,
) -> tuple[AuditClassification, str | None, float, str]:
    if len(candidates) > 1:
        values = ", ".join(sorted(candidates))
        return (
            AuditClassification.AMBIGUOUS,
            None,
            0.0,
            f"validated identity evidence conflicts: {values}",
        )

    entry = registry.by_alias(label)
    if entry is not None:
        canonical_names = {entry.project_id.casefold(), entry.project_name.casefold()}
        if label.casefold() in canonical_names:
            return (
                AuditClassification.CANONICAL,
                entry.project_id,
                1.0,
                "canonical project label from validated registry",
            )
        return (
            AuditClassification.ALIAS,
            entry.project_id,
            0.99,
            "validated alias from canonical project registry",
        )

    if candidates:
        candidate = next(iter(candidates))
        return (
            AuditClassification.ALIAS,
            candidate,
            0.95,
            "legacy label linked by versioned project_identity evidence",
        )

    key = label.casefold()
    if key in _PROFILE_LABELS:
        return (
            AuditClassification.PROFILE,
            f"unclassified/profile/{_slug(label)}",
            0.95,
            "profile label; no validated project evidence",
        )
    surface_kind = _SURFACE_KINDS.get(key)
    if surface_kind is not None:
        return (
            AuditClassification.SURFACE,
            f"unclassified/{_slug(label)}",
            0.95,
            f"{surface_kind} surface; no validated project evidence",
        )
    return (
        AuditClassification.UNCLASSIFIED,
        f"unclassified/{_slug(label)}",
        0.0,
        "no registry match or validated project identity evidence",
    )


def audit_projects(
    *,
    claude_mem_db: str | os.PathLike[str] | None = None,
    hive_db: str | os.PathLike[str] | None = None,
    vault_root: str | os.PathLike[str] | None = None,
    registry_path: str | os.PathLike[str] = DEFAULT_REGISTRY_PATH,
    include_minimum_labels: bool = True,
) -> list[ProjectAuditRow]:
    """Inventory project labels without modifying any source."""
    home = Path.home()
    root = Path(os.environ.get("SINAPSE_HOME", Path.cwd()))
    claude_path = Path(claude_mem_db) if claude_mem_db else home / ".claude-mem" / "claude-mem.db"
    hive_path = Path(hive_db) if hive_db else root / "hive_mind.db"
    vault_path = Path(vault_root) if vault_root else root / "cerebro"
    registry = ProjectAliasRegistry.load(registry_path)

    inventory = _Inventory()
    if include_minimum_labels:
        for label in MINIMUM_LABELS:
            inventory.ensure(label)
    _scan_database(claude_path, inventory)
    if hive_path.resolve(strict=False) != claude_path.resolve(strict=False):
        _scan_database(hive_path, inventory)
    _scan_markdown(vault_path, inventory)

    rows: list[ProjectAuditRow] = []
    for key in sorted(inventory.counts, key=lambda item: inventory.display[item].casefold()):
        label = inventory.display[key]
        counts = inventory.counts[key]
        classification, project_id, confidence, reason = _classify(
            label, inventory.candidates[key], registry
        )
        rows.append(
            ProjectAuditRow(
                legacy_label=label,
                proposed_project_id=project_id,
                sessions=counts.sessions,
                observations=counts.observations,
                vectors=counts.vectors,
                markdown=counts.markdown,
                confidence=confidence,
                classification=classification,
                reason=reason,
            )
        )
    return rows


def render_audit_table(rows: Iterable[ProjectAuditRow]) -> str:
    rows = list(rows)
    headers = (
        "Label antiga",
        "project_id proposto",
        "Sessões",
        "Observações",
        "Vetores",
        "Markdown",
        "Confiança",
        "Classificação",
    )
    data = [
        (
            row.legacy_label,
            row.proposed_project_id or "-",
            str(row.sessions),
            str(row.observations),
            str(row.vectors),
            str(row.markdown),
            f"{row.confidence:.2f}",
            row.classification.value,
        )
        for row in rows
    ]
    widths = [
        max([len(headers[index]), *(len(row[index]) for row in data)])
        for index in range(len(headers))
    ]
    line = " | ".join(headers[index].ljust(widths[index]) for index in range(len(headers)))
    separator = "-+-".join("-" * width for width in widths)
    body = [" | ".join(row[index].ljust(widths[index]) for index in range(len(headers))) for row in data]
    reasons = [f"- {row.legacy_label}: {row.reason}" for row in rows]
    return "\n".join((line, separator, *body, "", "Razões:", *reasons))
