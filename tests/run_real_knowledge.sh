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
    REPORT_PATH="$REPORT" "$PY" - <<'PYREPORT'
import os
import pathlib
import xml.etree.ElementTree as ET

report_path = os.environ["REPORT_PATH"]
root = ET.parse(f"{report_path}.junit.xml").getroot()
totals = {"tests": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0}
skipped = []
for tc in root.iter("testcase"):
    totals["tests"] += 1
    for child in tc:
        if child.tag in ("failure", "error"):
            totals["failed" if child.tag == "failure" else "errors"] += 1
        elif child.tag == "skipped":
            totals["skipped"] += 1
            skipped.append({
                "name": f"{tc.attrib.get('classname', '')}.{tc.attrib.get('name', '')}".strip("."),
                "reason": child.attrib.get("message", "").strip(),
            })
totals["passed"] = totals["tests"] - totals["failed"] - totals["errors"] - totals["skipped"]
status = "pass" if totals["failed"] == totals["errors"] == totals["skipped"] == 0 else (
    "degraded" if totals["failed"] == totals["errors"] == 0 else "fail"
)
lines = [
    "# K9 — Relatorio da suite real de conhecimento",
    "",
    "- Fonte: tests/run_real_knowledge.sh",
    "- Spec: docs/12-knowledge-implementation-plan.md §K9",
    f"- Status: **{status}**",
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
if skipped:
    lines.extend([
        "## Testes skipped",
        "",
        "| Teste | Motivo |",
        "|---|---|",
    ])
    for item in skipped:
        reason = item["reason"].replace("|", "&#124;") or "sem motivo no JUnit"
        lines.append(f"| `{item['name']}` | {reason} |")
    lines.append("")
pathlib.Path(report_path).write_text("\n".join(lines), encoding="utf-8")
print(f"relatorio: {report_path}")
PYREPORT
else
    exec "$PY" -m pytest tests/real -m real -q --no-header "$@"
fi
