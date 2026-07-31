from __future__ import annotations

from pathlib import Path

from hive_mind.maintenance.topology_archive import archive_topology, cleanup_topology_stale


def test_archive_topology_dry_run_collapses_nested_archive_targets(tmp_path, monkeypatch):
    root = tmp_path / "Hive-Mind"
    root.mkdir()
    dev_root = tmp_path / "Hive-Mind-Dev"
    (dev_root / "runtime-consolidation-final").mkdir(parents=True)
    backups_worktree = root / "backups" / "worktrees" / "hive-mind-windows-zero-install"
    backups_worktree.mkdir(parents=True)
    archive_root = tmp_path / "Hive-Mind-Archive"
    archive_root.mkdir()

    def fake_inventory(_root: Path):
        from hive_mind.validation.topology import TopologyEntry

        return [
            TopologyEntry(path=str(root), exists=True, registered_worktree=True,
                          classification="CANONICAL_RUNTIME", disposition="KEEP"),
            TopologyEntry(path=str(dev_root), exists=True, registered_worktree=False,
                          classification="BACKUP_SNAPSHOT", disposition="ARCHIVE"),
            TopologyEntry(path=str(dev_root / "runtime-consolidation-final"), exists=True, registered_worktree=True,
                          classification="BACKUP_SNAPSHOT", disposition="ARCHIVE"),
            TopologyEntry(path=str(backups_worktree), exists=True, registered_worktree=True,
                          classification="DEVELOPMENT_WORKTREE", disposition="ARCHIVE"),
        ]

    monkeypatch.setattr("hive_mind.maintenance.topology_archive.inventory_topology", fake_inventory)

    report = archive_topology(project_root=root, archive_root=archive_root, apply=False, stamp="20260727-210000")

    assert report.eligible == 2
    assert {Path(entry.source_path).name for entry in report.entries} == {
        "Hive-Mind-Dev",
        "hive-mind-windows-zero-install",
    }
    assert all(entry.status == "DRY_RUN" for entry in report.entries)


def test_archive_topology_apply_copies_and_removes_sources(tmp_path, monkeypatch):
    root = tmp_path / "Hive-Mind"
    root.mkdir()
    dev_root = tmp_path / "Hive-Mind-Dev"
    payload = dev_root / "runtime-consolidation-final"
    payload.mkdir(parents=True)
    (payload / "note.txt").write_text("legacy\n", encoding="utf-8")
    archive_root = tmp_path / "Hive-Mind-Archive"
    archive_root.mkdir()

    def fake_inventory(_root: Path):
        from hive_mind.validation.topology import TopologyEntry

        return [
            TopologyEntry(path=str(root), exists=True, registered_worktree=True,
                          classification="CANONICAL_RUNTIME", disposition="KEEP"),
            TopologyEntry(path=str(dev_root), exists=True, registered_worktree=False,
                          classification="BACKUP_SNAPSHOT", disposition="ARCHIVE"),
        ]

    monkeypatch.setattr("hive_mind.maintenance.topology_archive.inventory_topology", fake_inventory)

    report = archive_topology(project_root=root, archive_root=archive_root, apply=True, stamp="20260727-210100")

    assert report.archived == 1
    assert report.removed == 1
    assert not dev_root.exists()
    copied = Path(report.entries[0].destination_path) / "runtime-consolidation-final" / "note.txt"
    assert copied.read_text(encoding="utf-8") == "legacy\n"


def test_cleanup_topology_stale_dry_run_covers_tmp_root_and_missing_worktree(tmp_path, monkeypatch):
    root = tmp_path / "Hive-Mind"
    root.mkdir()
    tmp_root = root / ".tmp"
    tmp_root.mkdir()
    (tmp_root / "capture-3way-test").mkdir()
    missing = tmp_path / "ghost-worktree"
    archive_root = tmp_path / "Hive-Mind-Archive"
    archive_root.mkdir()

    def fake_inventory(_root: Path):
        from hive_mind.validation.topology import TopologyEntry

        return [
            TopologyEntry(path=str(root), exists=True, registered_worktree=True,
                          classification="CANONICAL_RUNTIME", disposition="KEEP"),
            TopologyEntry(path=str(tmp_root), exists=True, registered_worktree=False,
                          classification="STALE_WORKTREE", disposition="REMOVE_AFTER_APPROVAL"),
            TopologyEntry(path=str(tmp_root / "capture-3way-test"), exists=True, registered_worktree=True,
                          classification="STALE_WORKTREE", disposition="REMOVE_AFTER_APPROVAL"),
            TopologyEntry(path=str(missing), exists=False, registered_worktree=True,
                          classification="STALE_WORKTREE", disposition="REMOVE_AFTER_APPROVAL"),
        ]

    monkeypatch.setattr("hive_mind.maintenance.topology_archive.inventory_topology", fake_inventory)

    report = cleanup_topology_stale(project_root=root, archive_root=archive_root, apply=False, stamp="20260727-211000")

    assert report.eligible == 2
    assert {Path(entry.source_path).name for entry in report.entries} == {".tmp", "ghost-worktree"}
    by_name = {Path(entry.source_path).name: entry for entry in report.entries}
    assert by_name[".tmp"].action == "ARCHIVE_THEN_REMOVE"
    assert by_name["ghost-worktree"].action == "PRUNE_STALE_REGISTRATION"


def test_cleanup_topology_stale_apply_archives_tmp_and_prunes_missing_registration(tmp_path, monkeypatch):
    root = tmp_path / "Hive-Mind"
    root.mkdir()
    tmp_root = root / ".tmp"
    nested = tmp_root / "capture-3way-test"
    nested.mkdir(parents=True)
    (tmp_root / "note.txt").write_text("tmp\n", encoding="utf-8")
    missing = tmp_path / "ghost-worktree"
    archive_root = tmp_path / "Hive-Mind-Archive"
    archive_root.mkdir()
    calls: list[str] = []

    def fake_inventory(_root: Path):
        from hive_mind.validation.topology import TopologyEntry

        return [
            TopologyEntry(path=str(root), exists=True, registered_worktree=True,
                          classification="CANONICAL_RUNTIME", disposition="KEEP"),
            TopologyEntry(path=str(tmp_root), exists=True, registered_worktree=False,
                          classification="STALE_WORKTREE", disposition="REMOVE_AFTER_APPROVAL"),
            TopologyEntry(path=str(nested), exists=True, registered_worktree=True,
                          classification="STALE_WORKTREE", disposition="REMOVE_AFTER_APPROVAL"),
            TopologyEntry(path=str(missing), exists=False, registered_worktree=True,
                          classification="STALE_WORKTREE", disposition="REMOVE_AFTER_APPROVAL"),
        ]

    monkeypatch.setattr("hive_mind.maintenance.topology_archive.inventory_topology", fake_inventory)
    monkeypatch.setattr(
        "hive_mind.maintenance.topology_archive._remove_worktree",
        lambda project_root, target: (calls.append(str(target)) or True, "git worktree remove --force"),
    )
    monkeypatch.setattr(
        "hive_mind.maintenance.topology_archive._remove_or_prune_missing_worktree",
        lambda project_root, target: (calls.append(f"prune:{target}") or True, "git worktree prune --expire now"),
    )

    report = cleanup_topology_stale(project_root=root, archive_root=archive_root, apply=True, stamp="20260727-211100")

    assert report.archived == 1
    assert report.removed == 2
    assert not tmp_root.exists()
    copied = Path(report.entries[0].destination_path) / "note.txt"
    assert copied.read_text(encoding="utf-8") == "tmp\n"
    assert any("capture-3way-test" in call for call in calls)
    assert any(call.startswith("prune:") for call in calls)
