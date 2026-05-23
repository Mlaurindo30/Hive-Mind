#!/bin/bash
# Sinapse Agent — Smoke Tests
# Uso: bash tests/smoke/test_smoke.sh
# Deve passar em < 5 minutos

set -euo pipefail
PASS=0; FAIL=0

check() {
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  ✓ $desc"; ((PASS++))
    else
        echo "  ✗ $desc"; ((FAIL++))
    fi
}

echo "=== Sinapse Agent — Smoke Tests ==="
echo ""

# S0.1 — Binários no PATH
echo "[S0.1] Binários:"
check "python3" command -v python3
check "graphify" command -v graphify
check "nmem" command -v nmem
check "rtk" command -v rtk
check "bun" command -v bun
check "node" command -v node
check "sqlite3" command -v sqlite3

# S0.2 — graph.json existe e é válido
echo "[S0.2] Knowledge Graph:"
GRAPH="cerebro/graphify-out/graph.json"
[ -f "$GRAPH" ] && echo "  ✓ graph.json exists ($(du -h "$GRAPH" | cut -f1))" && ((PASS++)) || { echo "  ✗ graph.json missing"; ((FAIL++)); }
python3 -c "
import json
g = json.load(open('$GRAPH'))
assert 'nodes' in g and len(g['nodes']) > 100, 'Too few nodes'
assert 'links' in g, 'No links key'
" 2>/dev/null && echo "  ✓ graph.json valid ($(python3 -c "import json;g=json.load(open('$GRAPH'));print(f\"{len(g['nodes'])} nodes, {len(g['links'])} edges\")"))" && ((PASS++)) || { echo "  ✗ graph.json invalid"; ((FAIL++)); }

# S0.3 — Claude-mem worker
echo "[S0.3] Claude-mem Worker:"
HEALTH=$(curl -s --max-time 3 http://127.0.0.1:37700/health 2>/dev/null || echo '{"status":"down"}')
echo "$HEALTH" | python3 -c "import json,sys; assert json.load(sys.stdin).get('status')=='ok'" 2>/dev/null && echo "  ✓ worker healthy" && ((PASS++)) || { echo "  ✗ worker offline or unhealthy"; ((FAIL++)); }

# S0.4 — NeuralMemory
echo "[S0.4] NeuralMemory:"
nmem recall "test" >/dev/null 2>&1 && echo "  ✓ nmem functional" && ((PASS++)) || { echo "  ✗ nmem error"; ((FAIL++)); }

# S0.5 — RTK
echo "[S0.5] RTK:"
rtk --version >/dev/null 2>&1 && echo "  ✓ rtk functional" && ((PASS++)) || { echo "  ✗ rtk error"; ((FAIL++)); }

# S0.6 — Plugin sinapse-memory presente
echo "[S0.6] Plugin:"
[ -f "plugins/hermes/sinapse-memory.py" ] && echo "  ✓ plugin source exists" && ((PASS++)) || { echo "  ✗ plugin source missing"; ((FAIL++)); }
[ -f "$HOME/.hermes/plugins/sinapse-memory/__init__.py" ] && echo "  ✓ plugin installed in Hermes" && ((PASS++)) || { echo "  ⊘ plugin not installed in Hermes (optional)"; ((PASS++)); }

# S0.7 — Systemd service
echo "[S0.7] Systemd:"
systemctl --user is-active sinapse-claude-mem.service >/dev/null 2>&1 && echo "  ✓ service active" && ((PASS++)) || { echo "  ⊘ service not active (optional)"; ((PASS++)); }

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "SMOKE: PASS" || { echo "SMOKE: FAIL"; exit 1; }
