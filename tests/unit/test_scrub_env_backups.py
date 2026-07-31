from pathlib import Path

from hive_mind.maintenance.scrub_env_backups import scrub_env_backups


def test_scrub_env_backups_dry_run_detects_backup_env_secret_values(tmp_path):
    target = tmp_path / "backups" / "install-20260712-200339" / ".env"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "SAFE_FLAG=1\n"
        "HIVE_MIND_API_KEY=super-secret\n"
        "OLLAMA_API_KEY=another-secret\n",
        encoding="utf-8",
    )

    report = scrub_env_backups(project_root=tmp_path, apply=False)

    assert report.scanned == 1
    assert report.changed == 1
    assert report.entries[0].redacted_keys == ("HIVE_MIND_API_KEY", "OLLAMA_API_KEY")


def test_scrub_env_backups_apply_redacts_only_sensitive_values(tmp_path):
    target = tmp_path / "backups" / "install-20260712-200339" / ".env"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# comment\n"
        "SAFE_FLAG=1\n"
        "HIVE_MIND_API_KEY=super-secret\n"
        "NVIDIA_API_KEY=third-secret\n",
        encoding="utf-8",
    )

    report = scrub_env_backups(project_root=tmp_path, apply=True)

    assert report.changed == 1
    text = target.read_text(encoding="utf-8")
    assert "SAFE_FLAG=1" in text
    assert "super-secret" not in text
    assert "third-secret" not in text
    assert "HIVE_MIND_API_KEY=[REDACTED:env-backup-secret]" in text
    assert "NVIDIA_API_KEY=[REDACTED:env-backup-secret]" in text
