"""F4.3 pattern_distiller — memória procedural (doc 08 §11/Fase 4).

Mocka o LLM (distill) e valida gather/write/slug contra arquivos reais (R5).
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts import pattern_distiller as pd
from core.schemas.pattern_models import Pattern, PatternOutput

NOW = datetime(2026, 6, 18, 12, 0, 0)


def test_gather_signals_le_sessoes_recentes(tmp_path):
    sroot = tmp_path / "sessoes"
    sroot.mkdir()
    (sroot / "s1.md").write_text("# Sessão\n## Próximos Passos\n- fazer X\n")
    sig = pd.gather_signals(sroot, since_days=30, now=NOW)
    assert "fazer X" in sig


def test_gather_signals_vazio_quando_sem_dir(tmp_path):
    assert pd.gather_signals(tmp_path / "nope") == ""


def test_distill_vazio_sem_sinais_nao_chama_llm():
    # signals vazio → PatternOutput vazio, sem tocar na rede
    assert pd.distill_patterns("").patterns == []


def test_slug_estavel():
    p = Pattern(title="Validar Contra DB Real!", slug="", context="c")
    assert pd._slug(p) == "validar-contra-db-real"
    p2 = Pattern(title="x", slug="meu-slug", context="c")
    assert pd._slug(p2) == "meu-slug"


def test_write_pattern_apply(tmp_path):
    root = tmp_path / "padroes"
    p = Pattern(title="Validar contra DB real", slug="validar-db-real",
                context="antes do commit", steps=["rodar contra DB", "checar schema"],
                when_to_use="sempre", confidence=0.9)
    dest = pd.write_pattern(p, root, dry_run=False)
    assert dest.name == "validar-db-real.md"
    txt = dest.read_text()
    assert "type: pattern" in txt and "1. rodar contra DB" in txt and "## Quando usar" in txt


def test_run_apply_mockando_llm(tmp_path, monkeypatch):
    sroot = tmp_path / "sessoes"; sroot.mkdir()
    (sroot / "s.md").write_text("conteúdo de sessão")
    proot = tmp_path / "padroes"
    monkeypatch.setattr(pd, "distill_patterns",
                        lambda sig: PatternOutput(patterns=[
                            Pattern(title="P1", slug="p1", context="c", steps=["a"])]))
    stats = pd.run(sessions_root=sroot, padroes_root=proot, apply=True)
    assert stats["patterns"] == 1
    assert (proot / "p1.md").exists()
