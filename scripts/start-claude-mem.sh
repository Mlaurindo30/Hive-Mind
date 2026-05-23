#!/bin/bash
# Sinapse Agent — claude-mem MCP launcher (self-contained)
# Data directory: sinapse_agent/claude-mem/data/
SINAPSE_HOME="${SINAPSE_HOME:-$HOME/Documentos/Projects/sinapse_agent}"
export CLAUDE_MEM_DATA_DIR="$SINAPSE_HOME/claude-mem/data"
exec "$HOME/.bun/bin/bun" "$SINAPSE_HOME/claude-mem/plugin/scripts/mcp-server.cjs" "$@"
