import json
import os
import time

from scripts.backup_audit import apply_prune, parse_args, run_audit


def test_run_audit_detects_non_empty_secret_and_stale_candidates(tmp_path, monkeypatch):
    backups = tmp_path / "backups"
    backups.mkdir(parents=True)

    (backups / "hive_mind.20200101T000000Z.db").write_bytes(b"old")
    (backups / "hive_mind.20200101T000000Z.manifest.json").write_text("{}")
    (backups / "hive_mind.20200102T000000Z.db").write_bytes(b"new")

    leak_dir = backups / "sample"
    leak_dir.mkdir()
    (leak_dir / "settings.json").write_text(
        json.dumps({"CLAUDE_MEM_GEMINI_API_KEY": "leaked-value"})
    )

    monkeypatch.setattr(
        "sys.argv",
        ["backup_audit.py", "--root", str(tmp_path), "--keep-umc", "1"],
    )
    args = parse_args()
    report = run_audit(tmp_path, args)

    assert len(report["secret_hits"]) == 1
    assert report["secret_hits"][0]["key"] == "CLAUDE_MEM_GEMINI_API_KEY"
    assert len(report["stale_candidates"]["umc_backups"]) == 1


def test_apply_prune_removes_stale_and_manifest(tmp_path, monkeypatch):
    backups = tmp_path / "backups"
    backups.mkdir(parents=True)

    stale_db = backups / "hive_mind.20200101T000000Z.db"
    stale_manifest = backups / "hive_mind.20200101T000000Z.manifest.json"
    stale_db.write_bytes(b"stale")
    stale_manifest.write_text("{}")
    (backups / "hive_mind.20200102T000000Z.db").write_bytes(b"keep")

    monkeypatch.setattr(
        "sys.argv",
        ["backup_audit.py", "--root", str(tmp_path), "--keep-umc", "1"],
    )
    args = parse_args()
    report = run_audit(tmp_path, args)

    removed = apply_prune(report)

    assert str(stale_db) in removed
    assert not stale_db.exists()
    assert not stale_manifest.exists()


def test_legacy_snapshot_dir_policy_by_family_and_age(tmp_path, monkeypatch):
    backups = tmp_path / "backups"
    backups.mkdir(parents=True)

    old_dir = backups / "claude-mem-reinstall-20200101-000000"
    keep_dir = backups / "claude-mem-reinstall-20260101-000000"
    old_dir.mkdir()
    keep_dir.mkdir()
    (old_dir / "payload.bin").write_bytes(b"x")
    (keep_dir / "payload.bin").write_bytes(b"x")

    ten_days_ago = time.time() - (10 * 86400)
    os.utime(old_dir, (ten_days_ago, ten_days_ago))

    monkeypatch.setattr(
        "sys.argv",
        [
            "backup_audit.py",
            "--root",
            str(tmp_path),
            "--keep-legacy-per-family",
            "1",
            "--legacy-max-age-days",
            "7",
        ],
    )
    args = parse_args()
    report = run_audit(tmp_path, args)

    stale_legacy = report["stale_candidates"]["legacy_snapshot_dirs"]
    assert str(old_dir) in stale_legacy
    assert str(keep_dir) not in stale_legacy


def test_apply_prune_removes_legacy_directories(tmp_path, monkeypatch):
    backups = tmp_path / "backups"
    backups.mkdir(parents=True)
    stale = backups / "cleanup-20200101-000000"
    fresh = backups / "cleanup-20260101-000000"
    stale.mkdir()
    fresh.mkdir()
    (stale / "artifact.txt").write_text("stale")
    (fresh / "artifact.txt").write_text("fresh")

    monkeypatch.setattr(
        "sys.argv",
        [
            "backup_audit.py",
            "--root",
            str(tmp_path),
            "--keep-legacy-per-family",
            "1",
            "--legacy-max-age-days",
            "0",
        ],
    )
    args = parse_args()
    report = run_audit(tmp_path, args)
    removed = apply_prune(report)

    assert str(stale) in removed
    assert not stale.exists()
    assert fresh.exists()
