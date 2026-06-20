"""F4.2 project_synthesizer — status agregado por projeto (doc 08 §11/Fase 4)."""
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts.knowledge import project_synthesizer as ps


def _write(path: Path, *, ntype: str, last_updated: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.dump({"type": ntype, "last_updated": last_updated})
                    + "---\n# T\n\nx\n", encoding="utf-8")


@pytest.fixture()
def vault(tmp_path):
    t = tmp_path / "temporal"
    _write(t / "ComfyUI" / "nodes" / "neuronio-a.md", ntype="decision", last_updated="2026-06-10 10:00")
    _write(t / "ComfyUI" / "nodes" / "neuronio-b.md", ntype="fact", last_updated="2026-06-12 10:00")
    _write(t / "Thoth" / "auth" / "neuronio-c.md", ntype="fact", last_updated="2026-06-11 10:00")
    return t


def test_stats_agrega_por_projeto(vault):
    st = ps.project_stats(vault)
    assert st["ComfyUI"]["neurons"] == 2
    assert st["ComfyUI"]["decisions"] == 1 and st["ComfyUI"]["facts"] == 1
    assert st["ComfyUI"]["latest"] == "2026-06-12 10:00"
    assert st["Thoth"]["topics"] == ["auth"]


def test_dry_run_nao_escreve(vault, tmp_path):
    proj_root = tmp_path / "projetos"
    ps.write_all(temporal_root=vault, projects_root=proj_root, apply=False)
    assert not proj_root.exists()


def test_apply_escreve_por_projeto(vault, tmp_path):
    proj_root = tmp_path / "projetos"
    ps.write_all(temporal_root=vault, projects_root=proj_root, apply=True)
    txt = (proj_root / "ComfyUI.md").read_text()
    assert "type: project-status" in txt
    assert ps.AUTO_START in txt and ps.AUTO_END in txt
    assert "| Decisões | 1 |" in txt


def test_idempotente_preserva_edicao_manual(vault, tmp_path):
    proj_root = tmp_path / "projetos"
    ps.write_all(temporal_root=vault, projects_root=proj_root, apply=True)
    f = proj_root / "ComfyUI.md"
    # usuário adiciona nota fora do bloco auto
    f.write_text(f.read_text() + "\nNOTA MANUAL IMPORTANTE\n")
    ps.write_all(temporal_root=vault, projects_root=proj_root, apply=True)
    txt = f.read_text()
    assert "NOTA MANUAL IMPORTANTE" in txt          # preservada
    assert txt.count(ps.AUTO_START) == 1            # bloco auto não duplicou
