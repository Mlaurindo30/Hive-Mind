"""Testes do core/paths.py — constantes anatômicas e helpers de path."""
from datetime import date, datetime

from core import paths as P


def test_anatomia_top_level():
    assert P.CORTEX.name == "cortex"
    assert P.DIENCEFALO.name == "diencefalo"
    assert P.CEREBELO.name == "cerebelo"
    assert P.TRONCO.name == "tronco"
    assert P.CONSCIENCIA.name == "_Consciencia.md"


def test_lobos_do_cortex():
    assert P.TEMPORAL.parent == P.CORTEX and P.TEMPORAL.name == "temporal"
    assert P.FRONTAL.parent == P.CORTEX and P.FRONTAL.name == "frontal"
    assert P.PARIETAL.parent == P.CORTEX and P.PARIETAL.name == "parietal"
    assert P.OCCIPITAL.parent == P.CORTEX and P.OCCIPITAL.name == "occipital"
    assert P.INSULA.parent == P.CORTEX and P.INSULA.name == "insula"


def test_neuron_path_eixo_projeto():
    p = P.neuron_path("Hive-Mind", "infraestrutura", "7a3b2c1d4e5f6789")
    assert p == P.TEMPORAL / "Hive-Mind" / "infraestrutura" / "neuronio-7a3b2c1d4e5f6789.md"


def test_mocs():
    assert P.project_moc("Thoth") == P.TEMPORAL / "Thoth" / "_Thoth.md"
    assert P.topic_moc("Thoth", "seguranca") == P.TEMPORAL / "Thoth" / "seguranca" / "_seguranca.md"
    assert P.sector_moc("ai-infra") == P.SECTORS_ROOT / "_ai-infra.md"


def test_cadencia_paths():
    assert P.daily_path(date(2026, 6, 17)) == P.DAILY_ROOT / "2026" / "06" / "2026-06-17.md"
    sp = P.session_path(datetime(2026, 6, 17, 14, 22), "atlas-rename")
    assert sp == P.SESSIONS_ROOT / "2026" / "06" / "2026-06-17-1422-atlas-rename.md"
    assert P.weekly_path(2026, 25) == P.WEEKLY_ROOT / "2026-W25.md"


def test_cadencia_no_cerebelo():
    # cadências vivem no cerebelo (ritmo)
    assert P.DAILY_ROOT.parent == P.CEREBELO
    assert P.SESSIONS_ROOT.parent == P.CEREBELO
    assert P.WEEKLY_ROOT.parent == P.CEREBELO


def test_rel_to_vault():
    p = P.neuron_path("Hive-Mind", "infra", "abc123")
    assert P.rel_to_vault(p) == "cerebro/cortex/temporal/Hive-Mind/infra/neuronio-abc123.md"
