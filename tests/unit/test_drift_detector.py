"""F3.1 drift_detector — envelhecimento de memória (doc 08 §11/Fase 3).

Testa contra ARQUIVOS REAIS num vault temporário (R1/R5): classificação por idade
via frontmatter (`last_updated`), idempotência, e o efeito de --apply (move cold p/
arquivo/ + visibility:cold; flag stale decisions). Sem DB, sem LLM.
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts import drift_detector as dd

NOW = datetime(2026, 6, 18, 12, 0, 0)


def _write(path: Path, *, ntype: str, last_updated: str, **extra) -> None:
    fm = {"type": ntype, "last_updated": last_updated, **extra}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False)
                    + "---\n# Neurônio\n\nCorpo.\n", encoding="utf-8")


@pytest.fixture()
def vault(tmp_path):
    temporal = tmp_path / "temporal"
    arquivo = temporal / "arquivo"
    proj = temporal / "Hive-Mind" / "atlas"
    _write(proj / "neuronio-oldfact.md", ntype="fact", last_updated="2026-01-01 10:00")     # ~168d
    _write(proj / "neuronio-newfact.md", ntype="fact", last_updated="2026-06-10 10:00")     # ~8d
    _write(proj / "neuronio-olddec.md", ntype="decision", last_updated="2025-10-01 10:00")  # ~260d
    _write(proj / "neuronio-newdec.md", ntype="decision", last_updated="2026-06-01 10:00")  # ~17d
    _write(proj / "neuronio-coldalready.md", ntype="fact", last_updated="2026-01-01 10:00",
           visibility="cold")
    return temporal, arquivo


def test_classify_separa_cold_e_stale(vault):
    temporal, _ = vault
    neurons = dd.scan_neuronios(temporal, now=NOW)
    cold, stale = dd.classify(neurons, days_cold=90, days_stale=180)
    cold_names = {n["path"].name for n in cold}
    stale_names = {n["path"].name for n in stale}
    assert cold_names == {"neuronio-oldfact.md"}           # newfact recente; coldalready já frio
    assert stale_names == {"neuronio-olddec.md"}           # newdec recente


def test_dry_run_nao_escreve(vault):
    temporal, arquivo = vault
    stats = dd.run_drift(temporal_root=temporal, arquivo_root=arquivo,
                         apply=False, now=NOW)
    assert stats["cold"] == 1 and stats["stale"] == 1
    assert not arquivo.exists()                            # nada movido
    txt = (temporal / "Hive-Mind" / "atlas" / "neuronio-olddec.md").read_text()
    assert "staleness" not in txt                          # nada flagueado


def test_apply_move_cold_e_flag_stale(vault):
    temporal, arquivo = vault
    stats = dd.run_drift(temporal_root=temporal, arquivo_root=arquivo,
                         apply=True, now=NOW)
    assert stats["cold"] == 1 and stats["stale"] == 1
    # cold: movido p/ arquivo/{proj}/{topic}/ com visibility: cold
    moved = arquivo / "Hive-Mind" / "atlas" / "neuronio-oldfact.md"
    assert moved.exists()
    assert not (temporal / "Hive-Mind" / "atlas" / "neuronio-oldfact.md").exists()
    fm = yaml.safe_load(moved.read_text().split("---")[1])
    assert fm["visibility"] == "cold"
    # stale: decision flagueada, NÃO movida
    dec = temporal / "Hive-Mind" / "atlas" / "neuronio-olddec.md"
    assert dec.exists()
    assert yaml.safe_load(dec.read_text().split("---")[1])["staleness"] == "flagged"


def test_idempotente(vault):
    temporal, arquivo = vault
    dd.run_drift(temporal_root=temporal, arquivo_root=arquivo, apply=True, now=NOW)
    stats2 = dd.run_drift(temporal_root=temporal, arquivo_root=arquivo, apply=True, now=NOW)
    assert stats2["cold"] == 0 and stats2["stale"] == 0    # 2ª passada = no-op


def test_boundedness_respeita_limit(vault):
    temporal, arquivo = vault
    stats = dd.run_drift(temporal_root=temporal, arquivo_root=arquivo,
                         apply=False, limit=0, now=NOW)
    assert stats["cold"] == 0 and stats["stale"] == 0      # teto 0 = não processa nada
