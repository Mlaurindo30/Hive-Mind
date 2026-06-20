#!/usr/bin/env bash
# =============================================================================
# Sinapse Agent — sync-diario.sh
# =============================================================================
# Fallback: rebuild completo do knowledge graph (diário/semanal).
# Executado via cron. Uso: ./cron/sync-diario.sh
# =============================================================================

set -euo pipefail

SINAPSE_HOME="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
LOG_DIR="$PROJECT_ROOT/logs"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/sync-$(date +%Y%m%d-%H%M%S).log"

{
    echo "=== Sinapse Sync — $(date) ==="
    echo ""

    "$PROJECT_ROOT/scripts/graph/build-graph.sh" --force

    echo ""
    echo "=== Sync concluído — $(date) ==="
} >> "$LOG_FILE" 2>&1

# Manter apenas últimos 30 logs
ls -t "$LOG_DIR"/sync-*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true
