#!/bin/bash
# Sinapse Agent — Disaster Recovery
# Uso: bash scripts/recover.sh

set -euo pipefail
SINAPSE_HOME="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
echo "=== Sinapse Agent — Disaster Recovery ==="

# 1. Verificar graph.json
if [ ! -f "$SINAPSE_HOME/cerebro/graphify-out/graph.json" ]; then
    echo "[1/5] graph.json ausente — rebuild..."
    cd "$SINAPSE_HOME" && graphify update cerebro/ 2>&1
fi

# 2. Verificar backup
if [ -f "$SINAPSE_HOME/cerebro/graphify-out/graph.json.bak" ]; then
    echo "[2/5] Backup encontrado — verificando integridade..."
    python3 -c "import json; json.load(open('$SINAPSE_HOME/cerebro/graphify-out/graph.json.bak'))" 2>/dev/null && \
        echo "  backup válido" || echo "  backup corrompido"
fi

# 3. Reiniciar worker claude-mem
echo "[3/5] Reiniciando worker..."
systemctl --user restart sinapse-claude-mem.service 2>/dev/null || \
    echo "  systemd indisponível — inicie manualmente"

# 4. Health check
echo "[4/5] Health check..."
sleep 2
if curl -s --max-time 3 http://127.0.0.1:37700/health | grep -q '"status":"ok"'; then
    echo "  ✓ worker healthy"
else
    echo "  ✗ worker não respondeu"
fi

# 5. Verificar plugin
echo "[5/5] Verificando plugin..."
python3 -c "
import sys; sys.path.insert(0, '$SINAPSE_HOME/plugins/hermes')
from importlib import import_module
m = import_module('sinapse-memory')
status = m.health_check()
print(f'  Backends: {status[\"backends\"]}')
print(f'  Graph nodes: {status[\"vault\"][\"graph_nodes\"]}')
" 2>/dev/null || echo "  ✗ Plugin não carregou"

echo ""
echo "Recovery concluído."
