"""Smoke tests do topic_consolidator — garante import + parsing de args sem crash.

O gemini entregou este script SEM teste, e ele tinha um SyntaxError (global após
uso). Este teste mínimo cobre essa classe de defeito (import/compile + CLI)."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    spec = importlib.util.spec_from_file_location(
        "topic_consolidator", SCRIPTS / "knowledge" / "topic_consolidator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_importa_sem_syntaxerror():
    """Compila e importa — pega SyntaxError (ex.: global após uso)."""
    mod = _load()
    assert hasattr(mod, "main")


def test_help_nao_crasha(monkeypatch, capsys):
    """`--help` deve sair via SystemExit (argparse), não crashar."""
    mod = _load()
    monkeypatch.setattr(sys, "argv", ["topic_consolidator.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()
