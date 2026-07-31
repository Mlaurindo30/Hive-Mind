"""Controlled repair of missing project_id in legacy temporal neurons."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from core.memory.writers import atomic_write, read_vault_text
from hive_mind.validation.vault import _is_temporal_neuron, _split_frontmatter


@dataclass(frozen=True)
class ProjectIdRepairEntry:
    path: str
    status: str
    reason: str
    project_id: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectIdRepairReport:
    vault_root: str
    apply: bool
    scanned: int
    candidates: int
    repaired: int
    unchanged: int
    failed: int
    entries: tuple[ProjectIdRepairEntry, ...]

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


def _derive_project_id(path: Path, frontmatter: dict[str, object], *, vault_root: Path) -> tuple[str | None, str]:
    if not _is_temporal_neuron(path, vault_root=vault_root):
        return None, "not_temporal_neuron"
    current = frontmatter.get("project_id")
    if isinstance(current, str) and current.strip():
        return None, "already_has_project_id"
    project = frontmatter.get("project")
    if isinstance(project, str) and project.strip():
        return project.strip(), "from_frontmatter_project"
    rel = path.relative_to(vault_root)
    if len(rel.parts) >= 4 and rel.parts[2].strip():
        return rel.parts[2].strip(), "from_temporal_project_folder"
    return None, "cannot_derive_project_id"


def _inject_project_id(text: str, project_id: str) -> str:
    frontmatter, body, had_frontmatter = _split_frontmatter(text)
    if not had_frontmatter:
        raise ValueError("missing_frontmatter")
    frontmatter = dict(frontmatter)
    frontmatter["project_id"] = project_id
    rendered = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    return f"---\n{rendered}\n---\n{body}"


def repair_missing_project_id(*, vault_root: str | Path, apply: bool = False) -> ProjectIdRepairReport:
    root = Path(vault_root).resolve()
    entries: list[ProjectIdRepairEntry] = []
    scanned = 0
    candidates = 0
    repaired = 0
    unchanged = 0
    failed = 0

    for path in sorted(root.rglob("*.md")):
        text = read_vault_text(str(path))
        frontmatter, body, had_frontmatter = _split_frontmatter(text)
        if not _is_temporal_neuron(path, vault_root=root):
            continue
        scanned += 1
        project_id, reason = _derive_project_id(path, frontmatter, vault_root=root)
        if project_id is None:
            unchanged += 1
            if reason == "cannot_derive_project_id":
                failed += 1
                unchanged -= 1
                entries.append(ProjectIdRepairEntry(str(path), "failed", reason, None))
            continue
        candidates += 1
        if not apply:
            entries.append(ProjectIdRepairEntry(str(path), "candidate", reason, project_id))
            continue
        try:
            updated = _inject_project_id(text, project_id)
        except Exception as exc:
            failed += 1
            entries.append(
                ProjectIdRepairEntry(
                    str(path),
                    "failed",
                    f"inject_failed:{type(exc).__name__}:{exc}",
                    project_id,
                )
            )
            continue
        if atomic_write(str(path), updated):
            repaired += 1
            entries.append(ProjectIdRepairEntry(str(path), "repaired", reason, project_id))
        else:
            failed += 1
            entries.append(ProjectIdRepairEntry(str(path), "failed", "atomic_write_failed", project_id))

    return ProjectIdRepairReport(
        vault_root=str(root),
        apply=apply,
        scanned=scanned,
        candidates=candidates,
        repaired=repaired,
        unchanged=unchanged,
        failed=failed,
        entries=tuple(entries),
    )
