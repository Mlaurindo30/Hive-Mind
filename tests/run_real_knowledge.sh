#!/usr/bin/env bash
# Suíte de aceite da frente de conhecimento (docs/12 §K9) — backends reais, sem mock.
# Testes cujo serviço nomeado está offline PULAM (requires_service).
#
# Aceita --report <path> para gravar um resumo Markdown com totais.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x "$PY" ] || PY="$(command -v python3)"

REPORT=""
while [ $# -gt 0 ]; do
    case "$1" in
        --report=*) REPORT="${1#*=}" ;;
        --report) REPORT="$2"; shift ;;
        *) ;;
    esac
    shift || true
done

if [ -n "$REPORT" ]; then
    mkdir -p "$(dirname "$REPORT")"
    "$PY" -m pytest tests/real -m real -v --no-header --color=no \
        --junitxml="$REPORT.junit.xml" 2>&1 | tee "$REPORT.log"
    echo ""
    "$PY" - <<PYREPORT
import pathlib, xml.etree.ElementTree as ET
root = ET.parse("$REPORT.junit.xml").getroot()
totals = {"tests": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0}
for tc in root.iter("testcase"):
    totals["tests"] += 1
    for child in tc:
        if child.tag in ("failure", "error"):
            totals["failed" if child.tag == "failure" else "errors"] += 1
        elif child.tag == "skipped":
            totals["skipped"] += 1
totals["passed"] = totals["tests"] - totals["failed"] - totals["errors"] - totals["skipped"]
lines = [
    "# K9 — Relatorio da suite real de conhecimento",
    "",
    "- Fonte: tests/run_real_knowledge.sh",
    "- Spec: docs/12-knowledge-implementation-plan.md §K9",
    "",
    "| Metrica | Valor |",
    "|---|---:|",
    f"| total | {totals['tests']} |",
    f"| passed | {totals['passed']} |",
    f"| failed | {totals['failed']} |",
    f"| errors | {totals['errors']} |",
    f"| skipped | {totals['skipped']} |",
    "",
    "_Skips = servicos nomeados em " + chr(96) + "requires_service" + chr(96) + " que estao offline (intencional)._",
    "",
]
pathlib.Path("$REPORT").write_text("\\n".join(lines), encoding="utf-8")
print(f"relatorio: $REPORT")
PYREPORT
else
    exec "$PY" -m pytest tests/real -m real -q --no-header "$@"
fi
