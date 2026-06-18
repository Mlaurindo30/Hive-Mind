"""F4.4 conflict_detector — contradições entre neurônios (doc 08 §11/Fase 4).

embed_fn e llm_fn injetados (sem fastembed/rede). Valida pares por similaridade,
julgamento, report e read-only.
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts import conflict_detector as cd
from core.schemas.conflict_models import ConflictJudgement

NOW = datetime(2026, 6, 18, 12, 0, 0)


def _write(path: Path, *, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.dump({"type": "fact"}) + "---\n" + body, encoding="utf-8")


@pytest.fixture()
def vault(tmp_path):
    t = tmp_path / "temporal"
    _write(t / "P" / "topic" / "neuronio-a.md", body="# A\nPostgres é a melhor escolha.\n")
    _write(t / "P" / "topic" / "neuronio-b.md", body="# B\nNão use Postgres, prefira Mongo.\n")
    _write(t / "P" / "topic" / "neuronio-c.md", body="# C\nReceita de bolo de cenoura.\n")
    return t


# embed determinístico: vetor 2D; a/b muito próximos, c ortogonal
def _fake_embed(texts):
    out = []
    for t in texts:
        if "Postgres" in t or "Mongo" in t:
            out.append([1.0, 0.0])
        else:
            out.append([0.0, 1.0])
    return out


def test_candidate_pairs_por_similaridade(vault):
    neurons = cd.scan_neuronios(vault)
    pairs = cd.find_candidate_pairs(neurons, threshold=0.9, cap=50, embed_fn=_fake_embed)
    # a e b (ambos [1,0]) são par; c ([0,1]) não casa com ninguém
    names = {(neurons[i]["path"].stem, neurons[j]["path"].stem) for i, j, _ in pairs}
    flat = {n for pair in names for n in pair}
    assert "neuronio-c" not in flat
    assert ("neuronio-a", "neuronio-b") in names or ("neuronio-b", "neuronio-a") in names


def test_judge_filtra_nao_conflito(vault):
    neurons = cd.scan_neuronios(vault)
    a, b = neurons[0], neurons[1]
    assert cd.judge_conflict(a, b, llm_fn=lambda x, y: ConflictJudgement(is_conflict=False)) is None
    c = cd.judge_conflict(a, b, llm_fn=lambda x, y: ConflictJudgement(is_conflict=True, explanation="x"))
    assert c and c["explanation"] == "x"


def test_run_apply_gera_report(vault, tmp_path):
    croot = tmp_path / "conflitos"
    stats = cd.run(temporal_root=vault, conflicts_root=croot, apply=True, threshold=0.9,
                   embed_fn=_fake_embed,
                   llm_fn=lambda a, b: ConflictJudgement(is_conflict=True, explanation="contradição"))
    assert stats["conflicts"] >= 1
    report = croot / "2026-06-18.md" if (croot / "2026-06-18.md").exists() else next(croot.glob("*.md"))
    txt = report.read_text()
    assert "type: conflict-report" in txt and "⚔️" in txt


def test_read_only_nao_altera_neuronios(vault, tmp_path):
    before = {p: p.read_text() for p in vault.rglob("*.md")}
    cd.run(temporal_root=vault, conflicts_root=tmp_path / "c", apply=True, threshold=0.9,
           embed_fn=_fake_embed, llm_fn=lambda a, b: ConflictJudgement(is_conflict=False))
    after = {p: p.read_text() for p in vault.rglob("*.md")}
    assert before == after


def test_report_vazio_quando_sem_conflito(vault, tmp_path):
    croot = tmp_path / "c"
    stats = cd.run(temporal_root=vault, conflicts_root=croot, apply=True, threshold=0.9,
                   embed_fn=_fake_embed, llm_fn=lambda a, b: ConflictJudgement(is_conflict=False))
    assert stats["conflicts"] == 0
    assert "Nenhum conflito" in next(croot.glob("*.md")).read_text()
