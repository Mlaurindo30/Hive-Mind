"""Read-only inventory of Hive-Mind topology on disk."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class TopologyEntry:
    path: str
    exists: bool
    registered_worktree: bool
    branch: str | None = None
    head: str | None = None
    dirty_lines: int | None = None
    classification: str = "UNKNOWN"
    disposition: str = "UNKNOWN"
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _norm(path: str | Path) -> str:
    return str(Path(path)).replace("\\", "/").casefold().rstrip("/")


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def _parse_worktree_porcelain(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if current:
                blocks.append(current)
                current = {}
            continue
        if " " in line:
            key, value = line.split(" ", 1)
        else:
            key, value = line, "true"
        current[key] = value
    if current:
        blocks.append(current)
    return blocks


def _git_summary(path: Path) -> tuple[str | None, str | None, int | None]:
    if not path.exists():
        return None, None, None
    branch_cp = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    head_cp = _run_git(["rev-parse", "HEAD"], cwd=path)
    status_cp = _run_git(["status", "--short"], cwd=path)
    branch = branch_cp.stdout.strip() if branch_cp.returncode == 0 else None
    head = head_cp.stdout.strip() if head_cp.returncode == 0 else None
    dirty = None
    if status_cp.returncode == 0:
        dirty = len([line for line in status_cp.stdout.splitlines() if line.strip()])
    return branch, head, dirty


def classify_topology_entry(path: Path, *, canonical_root: Path, registered_worktree: bool) -> tuple[str, str, str]:
    normalized = _norm(path)
    canonical = _norm(canonical_root)
    if normalized == canonical:
        return "CANONICAL_RUNTIME", "KEEP", "canonical operational root"
    if not path.exists():
        return "STALE_WORKTREE", "REMOVE_AFTER_APPROVAL", "registered path missing on disk"
    if "/.tmp/" in normalized or normalized.endswith("/.tmp"):
        return "STALE_WORKTREE", "REMOVE_AFTER_APPROVAL", "temporary path under canonical root"
    if "/backups/worktrees/" in normalized:
        return "DEVELOPMENT_WORKTREE", "ARCHIVE", "historical worktree under backups/worktrees"
    if "hive-mind-consolidation" in normalized or "hive-mind-dev" in normalized:
        return "BACKUP_SNAPSHOT", "ARCHIVE", "noncanonical sibling snapshot"
    if "hive-mind-archive" in normalized:
        return "ARCHIVE_ROOT", "KEEP", "archive root kept for historical evidence"
    if registered_worktree:
        return "EXTERNAL_WORKTREE", "ARCHIVE", "registered worktree outside canonical root"
    return "UNTRACKED_COPY", "UNKNOWN", "path exists outside canonical root but is not a registered worktree"


def inventory_topology(root: Path) -> list[TopologyEntry]:
    root = Path(root).resolve()
    entries: dict[str, TopologyEntry] = {}

    branch, head, dirty = _git_summary(root)
    cls, disp, reason = classify_topology_entry(root, canonical_root=root, registered_worktree=True)
    entries[_norm(root)] = TopologyEntry(
        path=str(root),
        exists=root.exists(),
        registered_worktree=True,
        branch=branch,
        head=head,
        dirty_lines=dirty,
        classification=cls,
        disposition=disp,
        reason=reason,
    )

    wt_cp = _run_git(["worktree", "list", "--porcelain"], cwd=root)
    if wt_cp.returncode == 0:
        for block in _parse_worktree_porcelain(wt_cp.stdout):
            wt_path = Path(block["worktree"])
            branch, head, dirty = _git_summary(wt_path)
            cls, disp, reason = classify_topology_entry(
                wt_path, canonical_root=root, registered_worktree=True
            )
            entries[_norm(wt_path)] = TopologyEntry(
                path=str(wt_path),
                exists=wt_path.exists(),
                registered_worktree=True,
                branch=branch if "detached" not in block else "detached",
                head=block.get("HEAD", head),
                dirty_lines=dirty,
                classification=cls,
                disposition=disp,
                reason=reason,
            )

    for candidate in (
        root.parent / "Hive-Mind-Dev",
        root.parent / "Hive-Mind-Consolidation",
        root.parent / "Hive-Mind-Archive",
        root / ".tmp",
    ):
        key = _norm(candidate)
        if key in entries or not candidate.exists():
            continue
        cls, disp, reason = classify_topology_entry(
            candidate, canonical_root=root, registered_worktree=False
        )
        entries[key] = TopologyEntry(
            path=str(candidate),
            exists=True,
            registered_worktree=False,
            classification=cls,
            disposition=disp,
            reason=reason,
        )

    return sorted(entries.values(), key=lambda item: item.path.casefold())
