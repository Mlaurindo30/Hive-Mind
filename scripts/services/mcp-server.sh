#!/usr/bin/env bash
# =============================================================================
# Sinapse Agent — mcp-server.sh (Graphify MCP server)
# =============================================================================
# Inicia o servidor MCP do Graphify expondo o knowledge graph.
# Uso: ./scripts/mcp-server.sh [--port 8080]
#       Sem --port = modo stdio (para clientes MCP)
#       Com --port  = modo HTTP
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
GRAPH_JSON="$PROJECT_ROOT/cerebro/cortex/occipital/grafo/graph.json"

if [ ! -f "$GRAPH_JSON" ]; then
    echo "[sinapse] graph.json não encontrado. Execute ./scripts/graph/build-graph.sh primeiro."
    exit 1
fi

PORT_FLAG=""
for arg in "$@"; do
    case "$arg" in
        --port=*) PORT_FLAG="--port ${arg#*=}" ;;
        --port) shift; PORT_FLAG="--port $1" ;;
    esac
done

echo "[sinapse] Iniciando MCP server: $GRAPH_JSON"

if [ -n "$PORT_FLAG" ]; then
    echo "[sinapse] Modo HTTP não suportado pelo servidor unificado (use stdio)."
    exit 1
else
    echo "[sinapse] Modo stdio (para clientes MCP como Hermes, Claude, Cursor, etc.)"
fi

export SINAPSE_HOME="$PROJECT_ROOT"
exec "$PROJECT_ROOT/.venv/bin/python" "$SCRIPT_DIR/sinapse-mcp.py"
