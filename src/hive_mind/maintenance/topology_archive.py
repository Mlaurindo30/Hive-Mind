"""Controlled archival of legacy topology paths classified as ARCHIVE."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
import stat
import shutil
import subprocess
import time

from hive_mind.maintenance.lock import MaintenanceLock
from hive_mind.validation.topology import TopologyEntry, inventory_topology


@dataclass(frozen=True)
class TopologyArchiveEntry:
    source_path: str
    destination_path: str | None
    classification: str
    disposition: str
    registered_worktree: bool
    dirty_lines: int | None
    action: str
    status: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TopologyArchiveReport:
    project_root: str
    archive_root: str
    apply: bool
    batch_dir: str
    scanned: int
    eligible: int
    archived: int
    removed: int
    preserved: int
    skipped: int
    entries: tuple[TopologyArchiveEntry, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "project_root": self.project_root,
            "archive_root": self.archive_root,
            "apply": self.apply,
            "batch_dir": self.batch_dir,
            "scanned": self.scanned,
            "eligible": self.eligible,
            "archived": self.archived,
            "removed": self.removed,
            "preserved": self.preserved,
            "skipped": self.skipped,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _norm(path: Path) -> str:
    return str(path).replace("\\", "/").casefold().rstrip("/")


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _batch_dir(archive_root: Path, stamp: str) -> Path:
    return archive_root / "topology-cleanup" / stamp


def _destination_for(source: Path, *, archive_root: Path, stamp: str) -> Path:
    drive = source.drive.rstrip(":") or "drive"
    rel = [part for part in source.parts[1:] if part not in ("\\", "/")]
    return _batch_dir(archive_root, stamp) / drive / Path(*rel)


def _collapse_archive_targets(entries: list[TopologyEntry]) -> list[TopologyEntry]:
    eligible = [
        entry for entry in entries
        if entry.disposition == "ARCHIVE" and entry.exists
    ]
    eligible_sorted = sorted(eligible, key=lambda item: (len(Path(item.path).parts), item.path.casefold()))
    selected: list[TopologyEntry] = []
    for entry in eligible_sorted:
        path = Path(entry.path)
        if any(path.is_relative_to(Path(chosen.path)) for chosen in selected):
            continue
        selected.append(entry)
    return selected


def _collapse_targets(entries: list[TopologyEntry], *, disposition: str) -> list[TopologyEntry]:
    eligible = [entry for entry in entries if entry.disposition == disposition]
    eligible_sorted = sorted(
        eligible,
        key=lambda item: (
            0 if Path(item.path).exists() else 1,
            len(Path(item.path).parts),
            item.path.casefold(),
        ),
    )
    selected: list[TopologyEntry] = []
    for entry in eligible_sorted:
        path = Path(entry.path)
        if any(path == Path(chosen.path) or path.is_relative_to(Path(chosen.path)) for chosen in selected if Path(chosen.path).exists()):
            continue
        selected.append(entry)
    return selected


def _remove_worktree(project_root: Path, target: Path) -> tuple[bool, str]:
    cp = _run_git(["worktree", "remove", "--force", str(target)], cwd=project_root)
    if cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or "git worktree remove failed").strip()
        return False, detail
    return True, "git worktree remove --force"


def _prune_worktrees(project_root: Path) -> tuple[bool, str]:
    cp = _run_git(["worktree", "prune", "--expire", "now", "--verbose"], cwd=project_root)
    if cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or "git worktree prune failed").strip()
        return False, detail
    detail = (cp.stdout or cp.stderr or "git worktree prune --expire now").strip()
    return True, detail


def _remove_or_prune_missing_worktree(project_root: Path, target: Path) -> tuple[bool, str]:
    ok, detail = _remove_worktree(project_root, target)
    if ok:
        return True, detail
    prune_ok, prune_detail = _prune_worktrees(project_root)
    if not prune_ok:
        return False, f"{detail}; {prune_detail}"
    return True, f"{detail}; {prune_detail}"


def _remove_nested_worktrees(project_root: Path, source: Path, inventory: list[TopologyEntry]) -> tuple[bool, str]:
    nested = [
        Path(entry.path)
        for entry in inventory
        if entry.registered_worktree and Path(entry.path) != source and Path(entry.path).is_relative_to(source)
    ]
    removed = 0
    for path in nested:
        ok, detail = _remove_worktree(project_root, path)
        if not ok:
            return False, detail
        removed += 1
    return True, f"removed {removed} nested worktree registration(s)"


def _remove_directory(path: Path) -> tuple[bool, str]:
    def _onerror(func, target, exc_info):
        target_path = Path(target)
        try:
            os.chmod(target_path, stat.S_IWRITE | stat.S_IREAD)
            func(target)
        except Exception:
            raise exc_info[1]

    try:
        shutil.rmtree(path, onerror=_onerror)
    except FileNotFoundError:
        return True, "already absent after archival"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    return True, "directory removed after archival"


def archive_topology(
    *,
    project_root: str | Path,
    archive_root: str | Path | None = None,
    apply: bool = False,
    stamp: str | None = None,
) -> TopologyArchiveReport:
    project_root = Path(project_root).resolve()
    archive_root = Path(archive_root).resolve() if archive_root else project_root.parent / "Hive-Mind-Archive"
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    batch_dir = _batch_dir(archive_root, stamp)

    inventory = inventory_topology(project_root)
    selected = _collapse_archive_targets(inventory)
    entries: list[TopologyArchiveEntry] = []
    archived = 0
    removed = 0
    preserved = 0
    skipped = 0

    if not apply:
        for item in selected:
            source = Path(item.path)
            destination = _destination_for(source, archive_root=archive_root, stamp=stamp)
            entries.append(
                TopologyArchiveEntry(
                    source_path=str(source),
                    destination_path=str(destination),
                    classification=item.classification,
                    disposition=item.disposition,
                    registered_worktree=item.registered_worktree,
                    dirty_lines=item.dirty_lines,
                    action="ARCHIVE_ONLY",
                    status="DRY_RUN",
                    reason="eligible archive target",
                )
            )
        return TopologyArchiveReport(
            project_root=str(project_root),
            archive_root=str(archive_root),
            apply=False,
            batch_dir=str(batch_dir),
            scanned=len(inventory),
            eligible=len(selected),
            archived=0,
            removed=0,
            preserved=0,
            skipped=0,
            entries=tuple(entries),
        )

    lock_path = archive_root / ".topology-archive.lock"
    with MaintenanceLock(lock_path):
        batch_dir.mkdir(parents=True, exist_ok=True)
        for item in selected:
            source = Path(item.path)
            destination = _destination_for(source, archive_root=archive_root, stamp=stamp)
            if destination.exists():
                skipped += 1
                entries.append(
                    TopologyArchiveEntry(
                        source_path=str(source),
                        destination_path=str(destination),
                        classification=item.classification,
                        disposition=item.disposition,
                        registered_worktree=item.registered_worktree,
                        dirty_lines=item.dirty_lines,
                        action="SKIP",
                        status="SKIPPED",
                        reason="destination already exists",
                    )
                )
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
            archived += 1

            if item.registered_worktree:
                ok, detail = _remove_worktree(project_root, source)
                if ok:
                    removed += 1
                    action = "ARCHIVE_AND_REMOVE_WORKTREE"
                    status = "ARCHIVED_REMOVED"
                    reason = detail
                else:
                    preserved += 1
                    action = "ARCHIVE_PRESERVE_SOURCE"
                    status = "ARCHIVED_PRESERVED"
                    reason = detail
            else:
                nested_ok, nested_detail = _remove_nested_worktrees(project_root, source, inventory)
                if not nested_ok:
                    preserved += 1
                    entries.append(
                        TopologyArchiveEntry(
                            source_path=str(source),
                            destination_path=str(destination),
                            classification=item.classification,
                            disposition=item.disposition,
                            registered_worktree=item.registered_worktree,
                            dirty_lines=item.dirty_lines,
                            action="ARCHIVE_PRESERVE_SOURCE",
                            status="ARCHIVED_PRESERVED",
                            reason=nested_detail,
                        )
                    )
                    continue
                ok, detail = _remove_directory(source)
                if ok:
                    removed += 1
                    action = "ARCHIVE_AND_REMOVE_DIRECTORY"
                    status = "ARCHIVED_REMOVED"
                    reason = f"{nested_detail}; {detail}"
                else:
                    preserved += 1
                    action = "ARCHIVE_PRESERVE_SOURCE"
                    status = "ARCHIVED_PRESERVED"
                    reason = detail

            entries.append(
                TopologyArchiveEntry(
                    source_path=str(source),
                    destination_path=str(destination),
                    classification=item.classification,
                    disposition=item.disposition,
                    registered_worktree=item.registered_worktree,
                    dirty_lines=item.dirty_lines,
                    action=action,
                    status=status,
                    reason=reason,
                )
            )

        for parent in (project_root.parent / "Hive-Mind-Dev", project_root.parent / "Hive-Mind-Consolidation"):
            try:
                if parent.exists() and not any(parent.iterdir()):
                    os.rmdir(parent)
            except OSError:
                pass

    return TopologyArchiveReport(
        project_root=str(project_root),
        archive_root=str(archive_root),
        apply=True,
        batch_dir=str(batch_dir),
        scanned=len(inventory),
        eligible=len(selected),
        archived=archived,
        removed=removed,
        preserved=preserved,
        skipped=skipped,
        entries=tuple(entries),
    )


def cleanup_topology_stale(
    *,
    project_root: str | Path,
    archive_root: str | Path | None = None,
    apply: bool = False,
    stamp: str | None = None,
) -> TopologyArchiveReport:
    project_root = Path(project_root).resolve()
    archive_root = Path(archive_root).resolve() if archive_root else project_root.parent / "Hive-Mind-Archive"
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    batch_dir = _batch_dir(archive_root, stamp)

    inventory = inventory_topology(project_root)
    selected = _collapse_targets(inventory, disposition="REMOVE_AFTER_APPROVAL")
    entries: list[TopologyArchiveEntry] = []
    archived = 0
    removed = 0
    preserved = 0
    skipped = 0

    if not apply:
        for item in selected:
            source = Path(item.path)
            destination = str(_destination_for(source, archive_root=archive_root, stamp=stamp)) if source.exists() else None
            action = "ARCHIVE_THEN_REMOVE" if source.exists() else "PRUNE_STALE_REGISTRATION"
            reason = "stale topology target pending controlled cleanup"
            entries.append(
                TopologyArchiveEntry(
                    source_path=str(source),
                    destination_path=destination,
                    classification=item.classification,
                    disposition=item.disposition,
                    registered_worktree=item.registered_worktree,
                    dirty_lines=item.dirty_lines,
                    action=action,
                    status="DRY_RUN",
                    reason=reason,
                )
            )
        return TopologyArchiveReport(
            project_root=str(project_root),
            archive_root=str(archive_root),
            apply=False,
            batch_dir=str(batch_dir),
            scanned=len(inventory),
            eligible=len(selected),
            archived=0,
            removed=0,
            preserved=0,
            skipped=0,
            entries=tuple(entries),
        )

    lock_path = archive_root / ".topology-cleanup.lock"
    with MaintenanceLock(lock_path):
        batch_dir.mkdir(parents=True, exist_ok=True)
        for item in selected:
            source = Path(item.path)
            destination = _destination_for(source, archive_root=archive_root, stamp=stamp) if source.exists() else None
            if not source.exists():
                ok, detail = _remove_or_prune_missing_worktree(project_root, source)
                if ok:
                    removed += 1
                    action = "PRUNE_STALE_REGISTRATION"
                    status = "REMOVED"
                    reason = detail
                else:
                    preserved += 1
                    action = "PRESERVE_STALE_REGISTRATION"
                    status = "PRESERVED"
                    reason = detail
                entries.append(
                    TopologyArchiveEntry(
                        source_path=str(source),
                        destination_path=None,
                        classification=item.classification,
                        disposition=item.disposition,
                        registered_worktree=item.registered_worktree,
                        dirty_lines=item.dirty_lines,
                        action=action,
                        status=status,
                        reason=reason,
                    )
                )
                continue

            assert destination is not None
            if destination.exists():
                copied_now = False
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination)
                archived += 1
                copied_now = True

            nested_ok, nested_detail = _remove_nested_worktrees(project_root, source, inventory)
            if not nested_ok:
                preserved += 1
                entries.append(
                    TopologyArchiveEntry(
                        source_path=str(source),
                        destination_path=str(destination),
                        classification=item.classification,
                        disposition=item.disposition,
                        registered_worktree=item.registered_worktree,
                        dirty_lines=item.dirty_lines,
                        action="ARCHIVE_PRESERVE_SOURCE",
                        status="ARCHIVED_PRESERVED",
                        reason=nested_detail,
                    )
                )
                continue

            ok, detail = _remove_directory(source)
            if ok:
                removed += 1
                action = "ARCHIVE_AND_REMOVE_DIRECTORY" if copied_now else "REMOVE_AFTER_ARCHIVE_RESUME"
                status = "ARCHIVED_REMOVED"
                resume_reason = "resumed removal using existing archived copy" if not copied_now else None
                reason = f"{nested_detail}; {detail}" if not resume_reason else f"{resume_reason}; {nested_detail}; {detail}"
            else:
                preserved += 1
                action = "ARCHIVE_PRESERVE_SOURCE"
                status = "ARCHIVED_PRESERVED"
                reason = detail
            entries.append(
                TopologyArchiveEntry(
                    source_path=str(source),
                    destination_path=str(destination),
                    classification=item.classification,
                    disposition=item.disposition,
                    registered_worktree=item.registered_worktree,
                    dirty_lines=item.dirty_lines,
                    action=action,
                    status=status,
                    reason=reason,
                )
            )

    return TopologyArchiveReport(
        project_root=str(project_root),
        archive_root=str(archive_root),
        apply=True,
        batch_dir=str(batch_dir),
        scanned=len(inventory),
        eligible=len(selected),
        archived=archived,
        removed=removed,
        preserved=preserved,
        skipped=skipped,
        entries=tuple(entries),
    )
