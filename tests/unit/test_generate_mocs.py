"""Testes da camada de navegação (MOCs) — generate_mocs.build_mocs."""
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core import paths as cp  # noqa: E402

spec = importlib.util.spec_from_file_location("generate_mocs", SCRIPTS / "generate_mocs.py")
gm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gm)


def _neuron(temporal: Path, project: str, topic: str, name: str, title: str, sectors="") -> None:
    d = temporal / project / topic
    d.mkdir(parents=True, exist_ok=True)
    fm = f"sectors: {sectors}\n" if sectors else ""
    (d / f"{name}.md").write_text(f"---\ntype: fact\n{fm}---\n# {title}\n\nconteúdo\n")


def test_build_mocs_gera_hierarquia(monkeypatch, tmp_path):
    temporal = tmp_path / "cortex" / "temporal"
    monkeypatch.setattr(cp, "TEMPORAL", temporal)
    monkeypatch.setattr(cp, "SECTORS_ROOT", tmp_path / "diencefalo" / "setores")
    monkeypatch.setattr(cp, "CONSCIENCIA", tmp_path / "_Consciencia.md")

    _neuron(temporal, "Hive-Mind", "seguranca", "neuronio-a", "Auditoria real", sectors="[ai-infra]")
    _neuron(temporal, "Hive-Mind", "seguranca", "neuronio-b", "Outro fato")
    _neuron(temporal, "Thoth", "tts", "neuronio-c", "TTS pipeline")

    stats = gm.build_mocs(verbose=False)
    assert stats == {"neurons": 3, "projects": 2, "topics": 2, "sectors": 1}

    # Consciência (Home) lista os projetos
    home = (tmp_path / "_Consciencia.md").read_text()
    assert "[[_Hive-Mind|Hive-Mind]]" in home and "[[_Thoth|Thoth]]" in home

    # MOC de projeto lista o tópico
    proj = cp.project_moc("Hive-Mind").read_text()
    assert "[[_seguranca|seguranca]]" in proj

    # MOC de tópico lista os neurônios pelo título
    top = cp.topic_moc("Hive-Mind", "seguranca").read_text()
    assert "[[neuronio-a|Auditoria real]]" in top and "[[neuronio-b|Outro fato]]" in top

    # MOC de setor cruza projetos
    sec = cp.sector_moc("ai-infra").read_text()
    assert "[[neuronio-a|Auditoria real]]" in sec


def test_mocs_idempotentes(monkeypatch, tmp_path):
    temporal = tmp_path / "cortex" / "temporal"
    monkeypatch.setattr(cp, "TEMPORAL", temporal)
    monkeypatch.setattr(cp, "SECTORS_ROOT", tmp_path / "diencefalo" / "setores")
    monkeypatch.setattr(cp, "CONSCIENCIA", tmp_path / "_Consciencia.md")
    _neuron(temporal, "P", "t", "neuronio-x", "X")
    a = gm.build_mocs(verbose=False)
    b = gm.build_mocs(verbose=False)
    assert a == b  # re-rodar não muda os contadores
