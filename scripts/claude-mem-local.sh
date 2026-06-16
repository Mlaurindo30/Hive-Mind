#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Global claude-mem: data lives in ~/.claude-mem, worker + mcp-server from the
# global plugin installation (~/.claude/plugins/marketplaces/thedotmack).
# The systemd unit (install_services.py) sets PATH so bun/npx are reachable.

export CLAUDE_MEM_WORKER_HOST="${CLAUDE_MEM_WORKER_HOST:-127.0.0.1}"
export CLAUDE_MEM_WORKER_PORT="${CLAUDE_MEM_WORKER_PORT:-37700}"
export CLAUDE_MEM_CHROMA_ENABLED=false
export CLAUDE_MEM_MANAGED=true

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
    echo "claude-mem global plugin not found. Run: npx claude-mem@13.6 install" >&2
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
Uses the global plugin installation; data lives in ~/.claude-mem.
EOF
    exit 0
fi

if [[ "${1:-}" == "mcp-server" ]]; then
    shift
    exec "$BUN" "$GLOBAL_PLUGIN/scripts/mcp-server.cjs" "$@"
fi

# Foreground worker (no --daemon) for systemd Type=simple.
exec "$BUN" "$GLOBAL_PLUGIN/scripts/worker-service.cjs" "$@"
