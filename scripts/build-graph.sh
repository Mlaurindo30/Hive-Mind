#!/bin/bash
# Sinapse Agent — Rebuild graph.json from vault (cron-safe)
# Chamado pelo cron a cada 6h. Sem LLM, apenas tree-sitter + Leiden clustering.
# Atomic write via temp file + rename (Fase 1.2).
set -euo pipefail

SINAPSE_HOME="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
VAULT_DIR="$SINAPSE_HOME/cerebro"
GRAPH_OUT="$VAULT_DIR/graphify-out"

cd "$SINAPSE_HOME" || exit 1

# Backup do graph atual
if [ -f "$GRAPH_OUT/graph.json" ]; then
    cp "$GRAPH_OUT/graph.json" "$GRAPH_OUT/graph.json.bak"
fi

# Reindexa sem LLM (tree-sitter + regex + Leiden clustering)
graphify update "$VAULT_DIR" 2>&1

# Verificar se o novo graph.json é válido
if python3 -c "import json; json.load(open('$GRAPH_OUT/graph.json'))" 2>/dev/null; then
    NODES=$(python3 -c "import json;g=json.load(open('$GRAPH_OUT/graph.json'));print(len(g.get('nodes',[])))")
    echo "graph.json valid — $NODES nodes — build completo"
else
    echo "ERRO: graph.json inválido, restaurando backup" >&2
    if [ -f "$GRAPH_OUT/graph.json.bak" ]; then
        mv "$GRAPH_OUT/graph.json.bak" "$GRAPH_OUT/graph.json"
        echo "Backup restaurado" >&2
    fi
    exit 1
fi
