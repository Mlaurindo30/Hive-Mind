from __future__ import annotations

from pathlib import Path

import yaml

from hive_mind.maintenance.vault_frontmatter import repair_invalid_frontmatter


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repair_invalid_frontmatter_reports_candidate_in_dry_run(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "cortex" / "frontal" / "trabalho" / "ativo" / "bad.md"
    _write(
        note,
        "---\n"
        "tags: [decision]\n"
        "evidence: \"D:\\Bad\\Path\\file.md\"\n"
        "---\n\n# Title\n",
    )

    report = repair_invalid_frontmatter(vault_root=vault, apply=False)

    assert report.candidates == 1
    assert report.repaired == 0
    assert report.entries[0].status == "candidate"


def test_repair_invalid_frontmatter_applies_yaml_safe_evidence(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "cortex" / "frontal" / "trabalho" / "ativo" / "bad.md"
    evidence = r"D:\IQ Option\iq-agent-desk\docs\reports\VALIDATION_ACCEPTANCE_MATRIX_2026-07-18.md"
    _write(
        note,
        "---\n"
        "tags: [decision]\n"
        f"evidence: \"{evidence}\"\n"
        "---\n\n# Title\n",
    )

    report = repair_invalid_frontmatter(vault_root=vault, apply=True)

    assert report.candidates == 1
    assert report.repaired == 1
    frontmatter = note.read_text(encoding="utf-8").split("---", 2)[1]
    parsed = yaml.safe_load(frontmatter)
    assert parsed["evidence"] == evidence


def test_repair_invalid_frontmatter_leaves_valid_note_unchanged(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "ok.md"
    _write(note, "---\ntags: [decision]\nstatus: active\n---\n\n# Ok\n")

    report = repair_invalid_frontmatter(vault_root=vault, apply=True)

    assert report.candidates == 0
    assert report.repaired == 0
    assert report.failed == 0
