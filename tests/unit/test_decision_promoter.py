"""F4.1 decision_promoter — promove decisões ao frontal (doc 08 §11/Fase 4).

Vault temporário (R1/R5): só promove type=decision, gera registro com seções §5.2 +
wikilink à origem, idempotente, log-only por default.
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts import decision_promoter as dp

NOW = datetime(2026, 6, 18, 12, 0, 0)


def _write(path: Path, *, ntype: str, ihash: str, body: str, **fm) -> None:
    data = {"type": ntype, "integrity_hash": ihash, **fm}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.dump(data, allow_unicode=True, sort_keys=False)
                    + "---\n" + body, encoding="utf-8")


@pytest.fixture()
def vault(tmp_path):
    t = tmp_path / "temporal"
    p = t / "Hive-Mind" / "atlas"
    _write(p / "neuronio-dec1.md", ntype="decision", ihash="dec1",
           body="# Migrar para Postgres\n\nUsar Postgres pela robustez.\n\n## Alternativas\nSQLite, Mongo.\n")
    _write(p / "neuronio-fact1.md", ntype="fact", ihash="f1", body="# Um fato\n\nx\n")
    return t


def test_so_promove_decisions(vault):
    items = dp.promotable_decisions(vault)
    assert len(items) == 1 and items[0]["type"] == "decision"


def test_dry_run_nao_escreve(vault, tmp_path):
    dec_root = tmp_path / "decisoes"
    stats = dp.run(temporal_root=vault, decisions_root=dec_root, apply=False)
    assert stats["decisions"] == 1
    assert not dec_root.exists()


def test_apply_materializa_registro(vault, tmp_path):
    dec_root = tmp_path / "decisoes"
    dp.run(temporal_root=vault, decisions_root=dec_root, apply=True)
    rec = dec_root / "Hive-Mind" / "dec-dec1.md"
    assert rec.exists()
    txt = rec.read_text()
    assert "type: decision-record" in txt
    assert "[[neuronio-dec1]]" in txt              # wikilink à origem
    assert "## Decisão" in txt and "## Alternativas Consideradas" in txt
    assert "Postgres" in txt
    assert "SQLite, Mongo." in txt                 # seção Alternativas extraída do neurônio


def test_idempotente(vault, tmp_path):
    dec_root = tmp_path / "decisoes"
    dp.run(temporal_root=vault, decisions_root=dec_root, apply=True)
    first = (dec_root / "Hive-Mind" / "dec-dec1.md").read_text()
    dp.run(temporal_root=vault, decisions_root=dec_root, apply=True)
    assert (dec_root / "Hive-Mind" / "dec-dec1.md").read_text() == first
    assert len(list((dec_root / "Hive-Mind").glob("*.md"))) == 1
