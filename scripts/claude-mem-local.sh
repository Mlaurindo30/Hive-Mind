#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUN="${BUN_BIN:-$ROOT/.tools/bin/bun}"
if [[ ! -x "$BUN" ]]; then
    echo "Project-local Bun is missing: $BUN. Run ./install.sh." >&2
    exit 2
fi

export CLAUDE_MEM_DATA_DIR="$ROOT/claude-mem/data"
export CLAUDE_MEM_WORKER_HOST="${CLAUDE_MEM_WORKER_HOST:-127.0.0.1}"
export CLAUDE_MEM_WORKER_PORT="${CLAUDE_MEM_WORKER_PORT:-37700}"
export CLAUDE_MEM_CHROMA_ENABLED=false
export CLAUDE_MEM_MANAGED=true

if [[ "${1:-}" == "mcp-server" ]]; then
    shift
    exec "$BUN" "$ROOT/claude-mem/plugin/scripts/mcp-server.cjs" "$@"
fi

exec "$BUN" "$ROOT/claude-mem/plugin/scripts/worker-service.cjs" "$@"
