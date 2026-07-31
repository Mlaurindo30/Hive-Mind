from __future__ import annotations

from pathlib import Path

from core.memory.writers import read_vault_text
from hive_mind.maintenance.vault_encoding import repair_legacy_encoding


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_repair_legacy_encoding_reports_candidate_in_dry_run(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "cortex" / "parietal" / "inbox" / "x.md"
    _write_bytes(note, b"# Sess\xe3o\n")

    report = repair_legacy_encoding(vault_root=vault, apply=False)

    assert report.candidates == 1
    assert report.repaired == 0
    assert report.entries[0].status == "candidate"
    assert report.entries[0].reason.startswith("cp1252_surrogates_normalized:")


def test_repair_legacy_encoding_applies_cp1252_normalization(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "cortex" / "parietal" / "inbox" / "x.md"
    _write_bytes(note, b"# Sess\xe3o Epis\xf3dica\n")

    report = repair_legacy_encoding(vault_root=vault, apply=True)

    assert report.candidates == 1
    assert report.repaired == 1
    assert note.read_text(encoding="utf-8") == "# Sessão Episódica\n"
    assert "Sessão" in read_vault_text(str(note))


def test_repair_legacy_encoding_repairs_mixed_utf8_and_single_cp1252_bytes(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "cerebelo" / "padroes" / "Patterns.md"
    _write_bytes(
        note,
        (
            b"> confidence: hypothesis \xc2\xb7 next_review: 2026-10-07\n"
            b"> confidence: hypothesis \xb7 next_review: 2026-10-11\n"
        ),
    )

    report = repair_legacy_encoding(vault_root=vault, apply=True)

    assert report.candidates == 1
    assert report.repaired == 1
    content = note.read_text(encoding="utf-8")
    assert content.count("·") == 2
    assert "\\udc" not in ascii(content)


def test_repair_legacy_encoding_ignores_utf8_clean_files(tmp_path):
    vault = tmp_path / "cerebro"
    note = vault / "ok.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("# título · ok\n", encoding="utf-8")

    report = repair_legacy_encoding(vault_root=vault, apply=True)

    assert report.candidates == 0
    assert report.repaired == 0
    assert report.failed == 0
