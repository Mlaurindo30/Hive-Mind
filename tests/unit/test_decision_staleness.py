"""F3.2 decision_staleness — relatório read-only de decisões estagnadas (doc 08 §11).

Vault temporário, now fixo (R1/R5). Garante: filtra só decisions > limiar, ordena por
idade, render markdown coerente, e NÃO escreve nada (read-only).
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts import decision_staleness as ds

NOW = datetime(2026, 6, 18, 12, 0, 0)


def _write(path: Path, *, ntype: str, last_updated: str, **extra) -> None:
    fm = {"type": ntype, "last_updated": last_updated, **extra}
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "# Minha Decisão\n\nCorpo.\n"
    path.write_text("---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False)
                    + "---\n" + body, encoding="utf-8")


@pytest.fixture()
def vault(tmp_path):
    t = tmp_path / "temporal"
    p = t / "Hive-Mind" / "atlas"
    _write(p / "neuronio-olddec.md", ntype="decision", last_updated="2025-10-01 10:00")   # ~260d
    _write(p / "neuronio-olderdec.md", ntype="decision", last_updated="2025-06-01 10:00")  # ~382d
    _write(p / "neuronio-newdec.md", ntype="decision", last_updated="2026-06-01 10:00")    # ~17d
    _write(p / "neuronio-oldfact.md", ntype="fact", last_updated="2025-01-01 10:00")       # fact: ignora
    return t


def test_filtra_e_ordena_por_idade(vault):
    items = ds.stale_decisions(vault, days=180, now=NOW)
    names = [Path(i["source_file"]).name for i in items]
    assert names == ["neuronio-olderdec.md", "neuronio-olddec.md"]  # mais velha primeiro
    assert all(i["project"] == "Hive-Mind" for i in items)


def test_ignora_facts_e_recentes(vault):
    items = ds.stale_decisions(vault, days=180, now=NOW)
    nomes = {Path(i["source_file"]).name for i in items}
    assert "neuronio-newdec.md" not in nomes   # recente
    assert "neuronio-oldfact.md" not in nomes   # não é decision


def test_render_markdown_vazio():
    assert "Nenhuma decisão" in ds.render_markdown([])


def test_render_markdown_tabela(vault):
    items = ds.stale_decisions(vault, days=180, now=NOW)
    md = ds.render_markdown(items)
    assert md.startswith("| Decisão | Projeto |")
    assert "Hive-Mind" in md
    assert "Minha Decisão" in md


def test_read_only_nao_altera_arquivos(vault):
    before = {p: p.read_text() for p in vault.rglob("*.md")}
    ds.stale_decisions(vault, days=180, now=NOW)
    after = {p: p.read_text() for p in vault.rglob("*.md")}
    assert before == after   # nenhum arquivo tocado
