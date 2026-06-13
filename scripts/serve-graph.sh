#!/bin/bash
# Sinapse Agent — Graphify MCP server launcher (self-contained)
# Serve o knowledge graph queryable via MCP
SINAPSE_HOME="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
GRAPH_PATH="$SINAPSE_HOME/cerebro/graphify-out/graph.json"

if [ ! -f "$GRAPH_PATH" ]; then
    echo "graph.json não encontrado em $GRAPH_PATH. Execute: graphify update cerebro/" >&2
    exit 1
fi

exec "$SINAPSE_HOME/.venv/bin/python" -m graphify.serve "$GRAPH_PATH" "$@"
