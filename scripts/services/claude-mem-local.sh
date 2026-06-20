#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export CLAUDE_MEM_DATA_DIR="${CLAUDE_MEM_DATA_DIR:-$HOME/.claude-mem}"
export CLAUDE_MEM_WORKER_HOST="${CLAUDE_MEM_WORKER_HOST:-127.0.0.1}"
export CLAUDE_MEM_WORKER_PORT="${CLAUDE_MEM_WORKER_PORT:-37700}"
export CLAUDE_MEM_CHROMA_ENABLED=false
export CLAUDE_MEM_MANAGED=true
export FASTEMBED_CACHE_PATH="${FASTEMBED_CACHE_PATH:-$CLAUDE_MEM_DATA_DIR/models}"

mkdir -p "$CLAUDE_MEM_DATA_DIR" "$FASTEMBED_CACHE_PATH"

# Resolve the global plugin directory (version-independent).
GLOBAL_PLUGIN=""
for candidate in \
    "$HOME/.claude/plugins/marketplaces/thedotmack/plugin" \
    "$HOME/.claude/plugins/cache/thedotmack/claude-mem/"*"/plugin"; do
    if [ -f "$candidate/scripts/worker-service.cjs" ]; then
        GLOBAL_PLUGIN="$candidate"
        break
    fi
done

if [ -z "$GLOBAL_PLUGIN" ]; then
    echo "claude-mem plugin not found. Run: npx claude-mem@13.6 install" >&2
    exit 2
fi

BUN="${BUN_BIN:-$ROOT/.tools/bin/bun}"
if [ ! -x "$BUN" ]; then
    BUN="$(command -v bun 2>/dev/null || true)"
fi
if [ -z "$BUN" ] || [ ! -x "$BUN" ]; then
    echo "Bun not found. Install bun or run ./install.sh." >&2
    exit 2
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    cat <<EOF
Usage: $0 [mcp-server|start|stop|restart|status|hook ...]

Without arguments this runs the claude-mem worker in the foreground for systemd.
Uses the native claude-mem plugin/runtime; data lives in:
  $CLAUDE_MEM_DATA_DIR
EOF
    exit 0
fi

if [[ "${1:-}" == "mcp-server" ]]; then
    shift
    exec "$BUN" "$GLOBAL_PLUGIN/scripts/mcp-server.cjs" "$@"
fi

if [[ "$#" -eq 0 ]]; then
    if [ ! -f "$GLOBAL_PLUGIN/scripts/worker-wrapper.cjs" ]; then
        echo "claude-mem worker-wrapper.cjs not found in $GLOBAL_PLUGIN" >&2
        exit 2
    fi
    # Foreground supervisor for systemd Type=simple. It owns the child worker
    # and exits if the worker dies instead of daemonizing behind systemd.
    exec "$BUN" "$GLOBAL_PLUGIN/scripts/worker-wrapper.cjs"
fi

exec "$BUN" "$GLOBAL_PLUGIN/scripts/worker-service.cjs" "$@"
