"""Read-only vault Markdown audit for G11."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

import yaml

from core.memory.writers import read_vault_text


WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


@dataclass(frozen=True)
class BrokenLink:
    source: str
    target: str
    exists: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class VaultMetrics:
    total_md: int
    empty_md: int
    invalid_frontmatter: int
    missing_project_id: int
    mojibake_files: int
    broken_wikilinks: int
    orphan_notes: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class VaultAuditReport:
    vault_root: str
    metrics: VaultMetrics
    broken_links: list[BrokenLink]
    orphan_paths: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "vault_root": self.vault_root,
            "metrics": self.metrics.to_dict(),
            "broken_links": [item.to_dict() for item in self.broken_links],
            "orphan_paths": list(self.orphan_paths),
        }


def _strip_nonsemantic_code(text: str) -> str:
    text = FENCED_CODE_RE.sub("", text)
    text = INLINE_CODE_RE.sub("", text)
    return text


def _split_frontmatter(text: str) -> tuple[dict, str, bool]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text, False
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
        if not isinstance(frontmatter, dict):
            return {}, text[match.end():], True
        return frontmatter, text[match.end():], True
    except Exception:
        return {}, text[match.end():], True


def _wikilink_targets(text: str) -> list[str]:
    cleaned = _strip_nonsemantic_code(text)
    targets: list[str] = []
    for raw in WIKILINK_RE.findall(cleaned):
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            targets.append(target)
    return targets


def _is_temporal_neuron(path: Path, *, vault_root: Path) -> bool:
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return False
    return (
        len(rel.parts) >= 4
        and rel.parts[0:2] == ("cortex", "temporal")
        and path.name.startswith("neuronio-")
    )


def _is_operational_link_scope(path: Path, *, vault_root: Path) -> bool:
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return False
    parts = rel.parts
    if not parts:
        return False
    if parts[0] == "90-intake":
        return False
    if path.name in {"Home.md", "Consciencia.md"}:
        return False
    if path.name in {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}:
        return False
    if len(parts) >= 4 and parts[0:4] == ("cortex", "occipital", "grafo", "GRAPH_REPORT.md"):
        return False
    if len(parts) >= 2 and parts[0:2] == ("tronco", "modelos"):
        return False
    if len(parts) >= 2 and parts[0:2] == ("tronco", "meta"):
        return False
    if len(parts) >= 3 and parts[0:3] == ("tronco", "infra", "agentes"):
        return False
    return True


def _is_orphan_gate_scope(path: Path, *, vault_root: Path) -> bool:
    if not _is_operational_link_scope(path, vault_root=vault_root):
        return False
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return False
    parts = rel.parts
    if rel == Path("Hive-Mind Dashboard.md"):
        return False
    if rel == Path("cortex") / "frontal" / "brain" / "Current State.md":
        return False
    if len(parts) >= 3 and parts[0:3] == ("cortex", "parietal", "inbox"):
        return False
    if len(parts) >= 4 and parts[0:4] == ("cortex", "frontal", "trabalho", "ativo"):
        return False
    return True


def _is_structural_taxonomy_link(source: Path, target: str, *, vault_root: Path) -> bool:
    if target in {"cortex", "cortex-temporal"}:
        return True
    if not _is_temporal_neuron(source, vault_root=vault_root):
        return False
    rel = source.relative_to(vault_root)
    if len(rel.parts) < 5:
        return False
    project_name = rel.parts[2]
    topic_name = rel.parts[3]
    return target in {project_name, topic_name}


def audit_vault_markdown(vault_root: Path) -> VaultAuditReport:
    vault_root = Path(vault_root).resolve()
    md_files = sorted(vault_root.rglob("*.md"))
    note_index = {path.stem for path in md_files}
    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, int] = {}
    broken_links: list[BrokenLink] = []
    empty_md = 0
    invalid_frontmatter = 0
    missing_project_id = 0
    mojibake_files = 0

    for path in md_files:
        events: list[tuple[str, str, dict]] = []
        text = read_vault_text(str(path), lambda level, event, **kw: events.append((level, event, kw)))
        if any(event == "vault_legacy_encoding" for _, event, _ in events):
            mojibake_files += 1
        if not text.strip():
            empty_md += 1
        frontmatter, body, had_frontmatter = _split_frontmatter(text)
        if had_frontmatter and not frontmatter:
            invalid_frontmatter += 1
        if _is_temporal_neuron(path, vault_root=vault_root) and not frontmatter.get("project_id"):
            missing_project_id += 1

        source_key = str(path)
        outgoing[source_key] = set()
        if not _is_operational_link_scope(path, vault_root=vault_root):
            continue
        targets = _wikilink_targets(body)
        for target in targets:
            if _is_structural_taxonomy_link(path, target, vault_root=vault_root):
                continue
            exists = target in note_index
            outgoing[source_key].add(target)
            if exists:
                incoming[target] = incoming.get(target, 0) + 1
            else:
                broken_links.append(BrokenLink(source=source_key, target=target, exists=False))

    orphan_paths: list[str] = []
    for path in md_files:
        if not _is_orphan_gate_scope(path, vault_root=vault_root):
            continue
        source_key = str(path)
        has_outgoing = bool(outgoing.get(source_key))
        has_incoming = incoming.get(path.stem, 0) > 0
        if not has_outgoing and not has_incoming:
            orphan_paths.append(source_key)

    metrics = VaultMetrics(
        total_md=len(md_files),
        empty_md=empty_md,
        invalid_frontmatter=invalid_frontmatter,
        missing_project_id=missing_project_id,
        mojibake_files=mojibake_files,
        broken_wikilinks=len(broken_links),
        orphan_notes=len(orphan_paths),
    )
    return VaultAuditReport(
        vault_root=str(vault_root),
        metrics=metrics,
        broken_links=broken_links,
        orphan_paths=orphan_paths,
    )
