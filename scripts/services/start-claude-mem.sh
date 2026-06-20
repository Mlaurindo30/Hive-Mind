#!/bin/bash
# Hive-Mind — Legacy claude-mem shim (Legacy)
# Este script agora redireciona para o MCP unificado do Hive-Mind.
echo "[hive-mind] claude-mem nativo está obsoleto. Iniciando Hive-Mind MCP Unificado..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/mcp-server.sh" "$@"
