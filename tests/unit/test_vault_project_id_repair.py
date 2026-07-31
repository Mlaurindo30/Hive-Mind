from __future__ import annotations

from pathlib import Path

import yaml

from hive_mind.maintenance.vault_project_id import repair_missing_project_id


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repair_missing_project_id_reports_temporal_candidate_in_dry_run(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "cortex" / "temporal" / "Hive-Mind" / "codex" / "neuronio-a.md"
    _write(
        note,
        "---\n"
        "type: fact\n"
        "project: Hive-Mind\n"
        "topic: codex\n"
        "---\n\n# Title\n",
    )

    report = repair_missing_project_id(vault_root=vault, apply=False)

    assert report.scanned == 1
    assert report.candidates == 1
    assert report.repaired == 0
    assert report.entries[0].status == "candidate"
    assert report.entries[0].project_id == "Hive-Mind"


def test_repair_missing_project_id_applies_frontmatter_project_value(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "cortex" / "temporal" / "ComfyUI" / "comfyui" / "neuronio-b.md"
    _write(
        note,
        "---\n"
        "type: fact\n"
        "project: ComfyUI\n"
        "topic: comfyui\n"
        "---\n\n# Title\n",
    )

    report = repair_missing_project_id(vault_root=vault, apply=True)

    assert report.candidates == 1
    assert report.repaired == 1
    frontmatter = note.read_text(encoding="utf-8").split("---", 2)[1]
    parsed = yaml.safe_load(frontmatter)
    assert parsed["project_id"] == "ComfyUI"
    assert parsed["project"] == "ComfyUI"


def test_repair_missing_project_id_falls_back_to_temporal_folder(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "cortex" / "temporal" / "app" / "codex" / "neuronio-c.md"
    _write(
        note,
        "---\n"
        "type: fact\n"
        "topic: codex\n"
        "---\n\n# Title\n",
    )

    report = repair_missing_project_id(vault_root=vault, apply=True)

    assert report.candidates == 1
    assert report.repaired == 1
    frontmatter = note.read_text(encoding="utf-8").split("---", 2)[1]
    parsed = yaml.safe_load(frontmatter)
    assert parsed["project_id"] == "app"


def test_repair_missing_project_id_ignores_non_temporal_notes(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "cortex" / "frontal" / "trabalho" / "ativo" / "decision.md"
    _write(note, "---\ntype: decision\nproject: Hive-Mind\n---\n\n# Title\n")

    report = repair_missing_project_id(vault_root=vault, apply=True)

    assert report.scanned == 0
    assert report.candidates == 0
    assert report.repaired == 0
