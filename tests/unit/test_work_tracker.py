"""F4.5 work_tracker — trabalho ativo dos 'Próximos Passos' (doc 08 §11/Fase 4)."""
import sys
from datetime import datetime
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts import work_tracker as wt

NOW = datetime(2026, 6, 18, 12, 0, 0)


@pytest.fixture()
def sessions(tmp_path):
    s = tmp_path / "sessoes" / "2026" / "06"
    s.mkdir(parents=True)
    (s / "sessao-1.md").write_text(
        "# Sessão\n## Resumo\nx\n## Próximos Passos\n- implementar F4.5\n- [x] já feito\n- revisar docs\n")
    (s / "sessao-2.md").write_text("# Sessão 2\n## Próximos Passos\n- implementar F4.5\n")  # dup
    return tmp_path / "sessoes"


def test_extrai_proximos_passos(sessions):
    items = wt.extract_next_steps(sessions, now=NOW)
    texts = [i["item"] for i in items]
    assert "implementar F4.5" in texts
    assert "revisar docs" in texts
    assert "[x] já feito" not in texts          # itens feitos ignorados
    assert texts.count("implementar F4.5") == 1  # dedupe entre sessões


def test_dry_run_nao_escreve(sessions, tmp_path):
    wa = tmp_path / "ativo"
    wt.run(sessions_root=sessions, work_active=wa, apply=False, now=NOW)
    assert not wa.exists()


def test_apply_escreve_quadro(sessions, tmp_path):
    wa = tmp_path / "ativo"
    stats = wt.run(sessions_root=sessions, work_active=wa, apply=True, now=NOW)
    assert stats["items"] == 2
    txt = (wa / "_ativo.md").read_text()
    assert "type: work-active" in txt and "- [ ] implementar F4.5" in txt


def test_vazio_quando_sem_sessoes(tmp_path):
    items = wt.extract_next_steps(tmp_path / "nope", now=NOW)
    assert items == []
    assert "nenhum item ativo" in wt.render([])
