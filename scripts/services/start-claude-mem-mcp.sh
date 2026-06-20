#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export CLAUDE_MEM_DATA_DIR="${CLAUDE_MEM_DATA_DIR:-$ROOT/claude-mem/data}"
export CLAUDE_MEM_WORKER_HOST="${CLAUDE_MEM_WORKER_HOST:-127.0.0.1}"
export CLAUDE_MEM_WORKER_PORT="${CLAUDE_MEM_WORKER_PORT:-37700}"
export CLAUDE_MEM_CHROMA_ENABLED=false
export CLAUDE_MEM_MANAGED=true
export FASTEMBED_CACHE_PATH="${FASTEMBED_CACHE_PATH:-$CLAUDE_MEM_DATA_DIR/models}"

mkdir -p "$CLAUDE_MEM_DATA_DIR" "$FASTEMBED_CACHE_PATH"

exec "$ROOT/scripts/claude-mem-local.sh" mcp-server "$@"
