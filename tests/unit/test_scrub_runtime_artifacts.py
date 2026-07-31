from pathlib import Path

from hive_mind.maintenance.scrub_runtime_artifacts import scrub_runtime_artifacts


def test_scrub_runtime_artifacts_dry_run_detects_secret_shaped_content(tmp_path):
    target = tmp_path / "logs" / "audit" / "sample.patch"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        'Authorization: Bearer abc.def.ghi\n'
        'OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890\n'
        'google=AIzaSyABCDEFGHIJKLMNOPQRSTUVWXY123456789\n',
        encoding="utf-8",
    )

    report = scrub_runtime_artifacts(
        project_root=tmp_path,
        apply=False,
        targets=[target],
    )
    assert report.scanned == 1
    assert report.changed == 1
    assert report.entries[0].changed is True


def test_scrub_runtime_artifacts_apply_rewrites_file(tmp_path):
    target = tmp_path / "logs" / "audit" / "sample.patch"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        'Authorization: Bearer abc.def.ghi\n'
        'ANTHROPIC_API_KEY=sk-ant-abcdefghijklmnopqrstuvwxyz1234567890\n'
        'HIVE_MIND_API_KEY=keep-this-secret\n'
        'google=AIzaSyABCDEFGHIJKLMNOPQRSTUVWXY123456789\n',
        encoding="utf-8",
    )

    report = scrub_runtime_artifacts(
        project_root=tmp_path,
        apply=True,
        targets=[target],
    )
    assert report.changed == 1

    text = target.read_text(encoding="utf-8")
    assert "Bearer abc.def.ghi" not in text
    assert "sk-ant-" not in text
    assert "HIVE_MIND_API_KEY=keep-this-secret" not in text
    assert "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXY123456789" not in text
