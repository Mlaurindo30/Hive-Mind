#!/usr/bin/env python3
"""Audita a fronteira real × unit × integration (docs/12 §K9 task 6).

Regra: aceite da arquitetura de conhecimento = teste real. Mock-heavy fica
em `tests/unit/`. Integração usa serviços externos e exige `requires_service`.

Saída:
- exit 0 + relatório vazio = fronteira limpa.
- exit 0 + relatório com ofensores = informativo (não bloqueia CI).
- exit 1 = uso errado do script (ver --help).

Por padrão, escreve um relatório versionado em
`docs/reports/k9/test-layering-audit.md` e imprime um resumo no stdout.
Use `--strict` para falhar quando:
  - `tests/real/` usar MagicMock/@patch; ou
  - `tests/unit/` usar `@pytest.mark.real` (vazou para o lado errado).
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "docs" / "reports" / "k9"

MOCK_RE = re.compile(r"\b(MagicMock|@patch\b|@mock\b|from unittest\.mock import.*Mock\b)")
MARK_REAL = re.compile(r"pytest\.mark\.real")
MARK_REQUIRES = re.compile(r"pytest\.mark\.requires_service")


@dataclass
class Offense:
    path: str
    line: int
    rule: str
    snippet: str


def _scan(path: Path, regex: re.Pattern[str], rule: str) -> list[Offense]:
    out: list[Offense] = []
    if not path.exists() or not path.is_file():
        return out
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if regex.search(line):
            out.append(Offense(path.relative_to(ROOT).as_posix(), lineno, rule, line.strip()))
    return out


def audit() -> tuple[list[Offense], dict[str, int]]:
    offenses: list[Offense] = []
    real_dir = ROOT / "tests" / "real"
    unit_dir = ROOT / "tests" / "unit"
    integration_dir = ROOT / "tests" / "integration"

    _GUARD_FILES = {"test_acceptance_split.py"}
    real_files = sorted([p for p in real_dir.glob("test_*.py") if p.name not in _GUARD_FILES]) if real_dir.exists() else []
    unit_files = sorted(unit_dir.glob("test_*.py")) if unit_dir.exists() else []
    integration_files = sorted(integration_dir.glob("test_*.py")) if integration_dir.exists() else []

    real_with_real = [p for p in real_files if MARK_REAL.search(p.read_text(encoding="utf-8"))]
    real_with_mocks: list[Offense] = []
    for p in real_files:
        real_with_mocks.extend(_scan(p, MOCK_RE, "real_com_mock"))

    unit_with_real: list[Offense] = []
    for p in unit_files:
        unit_with_real.extend(_scan(p, MARK_REAL, "unit_com_marker_real"))

    integration_with_real: list[Offense] = []
    for p in integration_files:
        integration_with_real.extend(_scan(p, MARK_REAL, "integration_com_marker_real"))

    offenses.extend(real_with_mocks)
    offenses.extend(unit_with_real)
    offenses.extend(integration_with_real)

    counts = {
        "real_files": len(real_files),
        "real_with_real_marker": len(real_with_real),
        "real_with_mocks": len(real_with_mocks),
        "unit_files": len(unit_files),
        "unit_with_real_marker": len(unit_with_real),
        "integration_files": len(integration_files),
        "integration_with_real_marker": len(integration_with_real),
    }
    return offenses, counts


def render_markdown(offenses: list[Offense], counts: dict[str, int]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        "# Test Layering Audit",
        "",
        f"_Generated_: `{stamp}`",
        "_Source_: `scripts/setup/audit_test_layering.py`",
        "_Spec_: `docs/12-knowledge-implementation-plan.md` §K9 task 6",
        "",
        "## Counts",
        "",
        "| Camada | Arquivos | Com marker real | Com mock |",
        "|---|---:|---:|---:|",
        f"| tests/real | {counts['real_files']} | {counts['real_with_real_marker']} | {counts['real_with_mocks']} |",
        f"| tests/unit | {counts['unit_files']} | {counts['unit_with_real_marker']} | — |",
        f"| tests/integration | {counts['integration_files']} | {counts['integration_with_real_marker']} | — |",
        "",
    ]
    if offenses:
        lines.append("## Offensores")
        lines.append("")
        for o in offenses:
            lines.append(f"- `{o.path}:{o.line}` — **{o.rule}** — `{o.snippet}`")
        lines.append("")
    else:
        lines.append("## Resultado")
        lines.append("")
        lines.append("- Fronteira limpa: nenhum teste real usa mocks; nenhum teste unit marca `real`.")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true", help="Falha (exit 1) quando houver ofensores graves.")
    parser.add_argument("--report", type=Path, default=None, help="Caminho do relatório Markdown.")
    args = parser.parse_args()

    offenses, counts = audit()
    report_path = args.report or (REPORTS / "test-layering-audit.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(offenses, counts), encoding="utf-8")

    print(f"[audit] testes real: {counts['real_files']} (marker real: {counts['real_with_real_marker']}; com mock: {counts['real_with_mocks']})")
    print(f"[audit] testes unit: {counts['unit_files']} (marker real: {counts['unit_with_real_marker']})")
    print(f"[audit] testes integration: {counts['integration_files']} (marker real: {counts['integration_with_real_marker']})")
    print(f"[audit] relatório: {report_path.relative_to(ROOT) if report_path.is_absolute() else report_path}")
    if offenses:
        print(f"[audit] {len(offenses)} ofensor(es) listado(s) no relatório.")
        if args.strict:
            for o in offenses:
                if o.rule in {"real_com_mock", "unit_com_marker_real"}:
                    print(f"  - {o.path}:{o.line} {o.rule}: {o.snippet}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
