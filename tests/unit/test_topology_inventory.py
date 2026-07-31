from __future__ import annotations

from pathlib import Path

from hive_mind.validation.topology import (
    classify_topology_entry,
    inventory_topology,
    _parse_worktree_porcelain,
)


def test_parse_worktree_porcelain_reads_multiple_blocks():
    blocks = _parse_worktree_porcelain(
        "worktree D:/Hive-Mind\nHEAD abc\nbranch refs/heads/main\n\n"
        "worktree D:/Hive-Mind/.tmp/capture-3way-test\nHEAD def\ndetached\n\n"
    )

    assert blocks == [
        {"worktree": "D:/Hive-Mind", "HEAD": "abc", "branch": "refs/heads/main"},
        {"worktree": "D:/Hive-Mind/.tmp/capture-3way-test", "HEAD": "def", "detached": "true"},
    ]


def test_classify_topology_entry_marks_expected_dispositions(tmp_path):
    root = tmp_path / "Hive-Mind"
    root.mkdir()
    tmp_tree = root / ".tmp" / "capture-3way-test"
    tmp_tree.mkdir(parents=True)
    backup_tree = root / "backups" / "worktrees" / "x"
    backup_tree.mkdir(parents=True)
    archive = tmp_path / "Hive-Mind-Archive"
    archive.mkdir()

    assert classify_topology_entry(root, canonical_root=root, registered_worktree=True) == (
        "CANONICAL_RUNTIME", "KEEP", "canonical operational root"
    )
    assert classify_topology_entry(tmp_tree, canonical_root=root, registered_worktree=True)[0:2] == (
        "STALE_WORKTREE", "REMOVE_AFTER_APPROVAL"
    )
    assert classify_topology_entry(backup_tree, canonical_root=root, registered_worktree=True)[0:2] == (
        "DEVELOPMENT_WORKTREE", "ARCHIVE"
    )
    assert classify_topology_entry(archive, canonical_root=root, registered_worktree=False)[0:2] == (
        "ARCHIVE_ROOT", "KEEP"
    )


def test_inventory_topology_includes_known_sibling_roots(tmp_path, monkeypatch):
    root = tmp_path / "Hive-Mind"
    root.mkdir()
    (tmp_path / "Hive-Mind-Dev").mkdir()
    (tmp_path / "Hive-Mind-Consolidation").mkdir()
    (tmp_path / "Hive-Mind-Archive").mkdir()
    (root / ".tmp").mkdir()

    def fake_git(args: list[str], *, cwd: Path):
        class CP:
            def __init__(self, returncode: int, stdout: str):
                self.returncode = returncode
                self.stdout = stdout
        if args == ["worktree", "list", "--porcelain"]:
            return CP(0, f"worktree {root}\nHEAD abc\nbranch refs/heads/main\n\n")
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return CP(0, "main\n")
        if args == ["rev-parse", "HEAD"]:
            return CP(0, "abc\n")
        if args == ["status", "--short"]:
            return CP(0, "")
        return CP(1, "")

    monkeypatch.setattr("hive_mind.validation.topology._run_git", fake_git)

    entries = inventory_topology(root)
    by_path = {Path(entry.path).name: entry for entry in entries}

    assert by_path["Hive-Mind"].classification == "CANONICAL_RUNTIME"
    assert by_path["Hive-Mind-Dev"].classification == "BACKUP_SNAPSHOT"
    assert by_path["Hive-Mind-Consolidation"].classification == "BACKUP_SNAPSHOT"
    assert by_path["Hive-Mind-Archive"].classification == "ARCHIVE_ROOT"
    assert by_path[".tmp"].classification == "STALE_WORKTREE"
