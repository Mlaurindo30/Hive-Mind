#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export CLAUDE_MEM_DATA_DIR="${CLAUDE_MEM_DATA_DIR:-$HOME/.claude-mem}"
export CLAUDE_MEM_WORKER_HOST="${CLAUDE_MEM_WORKER_HOST:-127.0.0.1}"
export CLAUDE_MEM_WORKER_PORT="${CLAUDE_MEM_WORKER_PORT:-37700}"
export CLAUDE_MEM_CHROMA_ENABLED=false
export CLAUDE_MEM_MANAGED=true
export FASTEMBED_CACHE_PATH="${FASTEMBED_CACHE_PATH:-$CLAUDE_MEM_DATA_DIR/models}"

mkdir -p "$CLAUDE_MEM_DATA_DIR" "$FASTEMBED_CACHE_PATH"

GLOBAL_PLUGIN=""
for candidate in \
    "$HOME/.codex/plugins/cache/claude-mem-local/claude-mem/"* \
    "$HOME/.codex/plugins/cache/thedotmack/claude-mem/"* \
    "$HOME/.claude/plugins/marketplaces/thedotmack/plugin" \
    "$HOME/.claude/plugins/cache/thedotmack/claude-mem/"*"/plugin"; do
    candidate="${candidate%/}"
    if [ -f "$candidate/plugin/scripts/worker-service.cjs" ]; then
        GLOBAL_PLUGIN="$candidate/plugin"
        break
    fi
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

case "${1:-}" in
    version-check)
        shift
        export CLAUDE_MEM_CODEX_HOOK=1
        exec node "$GLOBAL_PLUGIN/scripts/version-check.js" "$@"
        ;;
    ensure-worker)
        shift
        if command -v systemctl >/dev/null 2>&1 \
            && systemctl --user list-unit-files sinapse-claude-mem.service >/dev/null 2>&1; then
            systemctl --user start sinapse-claude-mem.service >/dev/null 2>&1 || true
            exit 0
        fi
        exec "$ROOT/scripts/claude-mem-local.sh" start "$@"
        ;;
    hook)
        shift
        exec node "$GLOBAL_PLUGIN/scripts/bun-runner.js" \
            "$GLOBAL_PLUGIN/scripts/worker-service.cjs" hook "$@"
        ;;
    *)
        echo "Usage: $0 {version-check|ensure-worker|hook ...}" >&2
        exit 2
        ;;
esac
