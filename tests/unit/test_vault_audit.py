from __future__ import annotations

from pathlib import Path

from hive_mind.validation.vault import audit_vault_markdown


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_audit_vault_ignores_wikilink_examples_inside_code(tmp_path):
    vault = tmp_path / "cerebro"
    _write(
        vault / "AGENTS.md",
        b"# Docs\n\nUse `[[Note Title]]` and:\n```md\n[[wikilinks]]\n```\n",
    )
    _write(
        vault / "cortex" / "temporal" / "proj" / "topic" / "neuronio-a.md",
        (
            "---\nproject_id: proj\n---\n\n# A\n\n"
            "[[neuronio-b]]\n"
        ).encode("utf-8"),
    )
    _write(
        vault / "cortex" / "temporal" / "proj" / "topic" / "neuronio-b.md",
        (
            "---\nproject_id: proj\n---\n\n# B\n"
        ).encode("utf-8"),
    )

    report = audit_vault_markdown(vault)

    assert report.metrics.broken_wikilinks == 0
    assert report.metrics.missing_project_id == 0


def test_audit_vault_excludes_templates_and_agent_instructions_from_link_gate(tmp_path):
    vault = tmp_path / "cerebro"
    _write(
        vault / "tronco" / "modelos" / "Work Note.md",
        b"# Template\n\n[[fake-template-link]]\n",
    )
    _write(
        vault / "tronco" / "infra" / "agentes" / ".codex" / "AGENTS.md",
        b"# Agent docs\n\n[[fake-agent-link]]\n",
    )
    _write(
        vault / "cortex" / "temporal" / "proj" / "topic" / "neuronio-a.md",
        b"---\nproject_id: proj\n---\n\n# A\n",
    )

    report = audit_vault_markdown(vault)

    assert report.metrics.broken_wikilinks == 0
    assert report.metrics.orphan_notes == 1


def test_audit_vault_excludes_legacy_root_navigation_from_link_gate(tmp_path):
    vault = tmp_path / "cerebro"
    _write(vault / "Home.md", b"# Home\n\n[[North Star]]\n")
    _write(vault / "Consciencia.md", b"# Consciencia\n\n[[Hive-Mind]]\n")
    _write(
        vault / "cortex" / "temporal" / "proj" / "topic" / "neuronio-a.md",
        b"---\nproject_id: proj\n---\n\n# A\n",
    )

    report = audit_vault_markdown(vault)

    assert report.metrics.broken_wikilinks == 0
    assert report.metrics.orphan_notes == 1


def test_audit_vault_counts_missing_project_id_and_orphans(tmp_path):
    vault = tmp_path / "cerebro"
    _write(
        vault / "cortex" / "temporal" / "proj" / "topic" / "neuronio-a.md",
        b"---\nproject_id: proj\n---\n\n# A\n\n[[neuronio-b]]\n",
    )
    _write(
        vault / "cortex" / "temporal" / "proj" / "topic" / "neuronio-b.md",
        b"---\nkind: fact\n---\n\n# B\n",
    )
    _write(vault / "cortex" / "frontal" / "solta.md", b"# Solta\n")

    report = audit_vault_markdown(vault)

    assert report.metrics.missing_project_id == 1
    assert report.metrics.orphan_notes == 1
    assert str(vault / "cortex" / "frontal" / "solta.md") in report.orphan_paths


def test_audit_vault_excludes_operational_standalone_notes_from_orphan_gate(tmp_path):
    vault = tmp_path / "cerebro"
    _write(vault / "Hive-Mind Dashboard.md", b"# Dashboard\n")
    _write(vault / "cortex" / "frontal" / "brain" / "Current State.md", b"# State\n")
    _write(
        vault / "cortex" / "parietal" / "inbox" / "2026" / "07" / "27" / "0200-session.md",
        b"# Session\n",
    )
    _write(
        vault / "cortex" / "frontal" / "trabalho" / "ativo" / "goal-abc123.md",
        b"# Goal\n",
    )
    _write(vault / "cortex" / "frontal" / "solta.md", b"# Solta\n")

    report = audit_vault_markdown(vault)

    assert report.metrics.orphan_notes == 1
    assert report.orphan_paths == [str(vault / "cortex" / "frontal" / "solta.md")]


def test_audit_vault_counts_legacy_encoding_as_mojibake_signal(tmp_path):
    vault = tmp_path / "cerebro"
    _write(
        vault / "cortex" / "temporal" / "proj" / "topic" / "neuronio-a.md",
        b"---\nproject_id: proj\n---\n\n# A\n\nok \xb7 legado\n",
    )

    report = audit_vault_markdown(vault)

    assert report.metrics.mojibake_files == 1
    assert report.metrics.total_md == 1


def test_audit_vault_ignores_structural_taxonomy_links_from_temporal_neurons(tmp_path):
    vault = tmp_path / "cerebro"
    _write(
        vault / "cortex" / "temporal" / "app" / "codex" / "neuronio-a.md",
        (
            "---\nproject_id: app\n---\n\n# A\n\n"
            "## Sinapses\n"
            "- projeto:: [[app]]\n"
            "- tópico:: [[codex]]\n"
            "- lobo:: [[cortex-temporal]]\n"
            "- córtex:: [[cortex]]\n"
        ).encode("utf-8"),
    )

    report = audit_vault_markdown(vault)

    assert report.metrics.broken_wikilinks == 0
