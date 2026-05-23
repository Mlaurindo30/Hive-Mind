#!/bin/bash
# Sinapse Agent — claude-mem MCP launcher (self-contained)
# Data directory: sinapse_agent/claude-mem/data/
export CLAUDE_MEM_DATA_DIR="/home/michel/Documentos/Projects/sinapse_agent/claude-mem/data"
exec /home/michel/.bun/bin/bun /home/michel/Documentos/Projects/sinapse_agent/claude-mem/plugin/scripts/mcp-server.cjs "$@"
