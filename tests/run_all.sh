#!/bin/bash
# Sinapse Agent — Full Test Suite Runner
# Uso: ./tests/run_all.sh
set -euo pipefail

SINAPSE_HOME="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export SINAPSE_HOME
cd "$SINAPSE_HOME"

PYTHON="${SINAPSE_PYTHON:-$SINAPSE_HOME/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
    echo "Local Python environment missing: $PYTHON" >&2
    exit 2
fi

PASS=0; FAIL=0
run_suite() {
    local name="$1"; shift
    echo ""
    echo "════════════════════════════════════════════════════"
    echo "  SUITE: $name"
    echo "════════════════════════════════════════════════════"
    if "$@"; then
        echo "  ✓ $name PASSED"
        ((++PASS))
    else
        echo "  ✗ $name FAILED"
        ((++FAIL))
    fi
}

run_suite "S0 — Smoke" env SINAPSE_PYTHON="$PYTHON" bash tests/smoke/test_smoke.sh
run_suite "U — Unit" "$PYTHON" -m pytest tests/unit/ -v --tb=short
run_suite "I — Integration" env HIVE_RUN_INTEGRATION=1 "$PYTHON" -m pytest tests/integration/ -v --tb=short
run_suite "E — End-to-End" "$PYTHON" -m pytest tests/e2e/ -v --tb=short

echo ""
echo "════════════════════════════════════════════════════"
echo "  RESULTS: $PASS suites passed, $FAIL suites failed"
echo "════════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ] || exit 1
