#!/usr/bin/env bash
# =============================================================================
# Hive-Mind — install-backup-cron.sh
# =============================================================================
# Instala/agrega jobs de backup audit (diário) e prune (semanal) no crontab.
# Preserva outras entradas existentes e atualiza somente entradas marcadas.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

AUDIT_SCHEDULE="${BACKUP_AUDIT_CRON_SCHEDULE:-20 2 * * *}"
PRUNE_SCHEDULE="${BACKUP_PRUNE_CRON_SCHEDULE:-35 2 * * 0}"

AUDIT_CMD="$PROJECT_ROOT/cron/backup-audit-daily.sh"
PRUNE_CMD="$PROJECT_ROOT/cron/backup-prune-weekly.sh"

TAG_AUDIT="# hive-mind-backup-audit"
TAG_PRUNE="# hive-mind-backup-prune"

if ! command -v crontab >/dev/null 2>&1; then
    echo "crontab não está disponível neste sistema." >&2
    exit 1
fi

EXISTING_CRON="$(crontab -l 2>/dev/null || true)"

NEW_CRON="$({
    printf '%s\n' "$EXISTING_CRON" | sed '/hive-mind-backup-audit/d;/hive-mind-backup-prune/d'
    echo "$AUDIT_SCHEDULE $AUDIT_CMD $TAG_AUDIT"
    echo "$PRUNE_SCHEDULE $PRUNE_CMD $TAG_PRUNE"
} | awk 'NF || NR==1')"

printf '%s\n' "$NEW_CRON" | crontab -

echo "Entradas instaladas/atualizadas:"
crontab -l | sed -n '/hive-mind-backup-audit/p;/hive-mind-backup-prune/p'
