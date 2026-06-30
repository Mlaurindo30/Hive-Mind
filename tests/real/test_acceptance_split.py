"""Garante que a separação real × unit está respeitada.

Regra (docs/12 §K9, task 6): aceite da arquitetura de conhecimento só conta
teste real. O pytest.ini define marker `real`; este teste defende a
fronteira inspecionando:
- todo `tests/real/test_*.py` declara `@pytest.mark.real`;
- nenhum `tests/real/test_*.py` usa `MagicMock`/`@patch` (mocks = unit);
- o runner `./tests/run_real_knowledge.sh` filtra exatamente por `-m real`.

Falha o teste se a fronteira for violada, evitando regressão silenciosa da
"arquitetura de conhecimento" para um conjunto de mocks.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REAL_DIR = REPO / "tests" / "real"
RUNNER = REPO / "tests" / "run_real_knowledge.sh"

MOCK_RE = re.compile(r"\b(MagicMock|@patch\b|@mock\b|from unittest\.mock import.*Mock\b)")
MARK_REAL = re.compile(r"pytest\.mark\.real|@pytest\.mark\.real")


def _real_test_files() -> list[Path]:
    # O guard é ele mesmo o detector; não conta como ofensor.
    _GUARD = {REAL_DIR / "test_acceptance_split.py"}
    return sorted(p for p in REAL_DIR.glob("test_*.py") if p not in _GUARD)


@pytest.mark.real
def test_every_real_test_declares_marker_real():
    missing: list[str] = []
    for path in _real_test_files():
        if not MARK_REAL.search(path.read_text(encoding="utf-8")):
            missing.append(path.relative_to(REPO).as_posix())
    assert not missing, (
        "Arquivos em tests/real sem @pytest.mark.real: "
        f"{missing}. Aceite da arquitetura de conhecimento exige marker real."
    )


@pytest.mark.real
def test_real_tests_do_not_use_mocks():
    offenders: list[tuple[str, int, str]] = []
    for path in _real_test_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if MOCK_RE.search(line):
                offenders.append((path.relative_to(REPO).as_posix(), lineno, line.strip()))
    assert not offenders, (
        "Testes reais não podem usar mocks (docs/12 §K9 task 6). "
        "Mova para tests/unit/ ou substitua por backends reais:\n  "
        + "\n  ".join(f"{p}:{l} {snippet}" for p, l, snippet in offenders)
    )


@pytest.mark.real
def test_runner_filters_by_real_marker():
    assert RUNNER.exists(), f"Runner não encontrado: {RUNNER}"
    text = RUNNER.read_text(encoding="utf-8")
    assert "pytest" in text and "-m real" in text, (
        f"{RUNNER.relative_to(REPO)} deve invocar pytest com -m real para "
        "garantir que apenas o marcador real conta para o aceite."
    )


@pytest.mark.real
def test_real_layer_does_not_depend_on_unittest_mock():
    init = (REAL_DIR / "__init__.py").read_text(encoding="utf-8") if (REAL_DIR / "__init__.py").exists() else ""
    conftest = (REAL_DIR / "conftest.py").read_text(encoding="utf-8")
    for path in [REAL_DIR / "__init__.py", REAL_DIR / "conftest.py"]:
        if path.exists():
            assert "unittest.mock" not in path.read_text(encoding="utf-8"), (
                f"{path.relative_to(REPO)} não deve importar unittest.mock."
            )
    assert "unittest.mock" not in init
    assert "unittest.mock" not in conftest
