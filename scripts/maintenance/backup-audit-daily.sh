#!/usr/bin/env bash
# =============================================================================
# Hive-Mind — backup-audit-daily.sh
# =============================================================================
# Auditoria diária de backups (dry-run), com saída JSON para logs.
# Uso: ./cron/backup-audit-daily.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs/backup-audit"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/audit-$(date +%Y%m%d-%H%M%S).json"

PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="python3"
fi

KEEP_UMC="${BACKUP_AUDIT_KEEP_UMC:-10}"
KEEP_COMPONENT_LOCK="${BACKUP_AUDIT_KEEP_COMPONENT_LOCK:-20}"
KEEP_SESSION_LOGS="${BACKUP_AUDIT_KEEP_SESSION_LOGS:-10}"
KEEP_FK_REPAIR="${BACKUP_AUDIT_KEEP_FK_REPAIR:-5}"
KEEP_LEGACY_PER_FAMILY="${BACKUP_AUDIT_KEEP_LEGACY_PER_FAMILY:-1}"
LEGACY_MAX_AGE_DAYS="${BACKUP_AUDIT_LEGACY_MAX_AGE_DAYS:-30}"

cd "$PROJECT_ROOT"
"$PYTHON_BIN" scripts/backup_audit.py \
    --root . \
    --keep-umc "$KEEP_UMC" \
    --keep-component-lock "$KEEP_COMPONENT_LOCK" \
    --keep-session-logs "$KEEP_SESSION_LOGS" \
    --keep-fk-repair "$KEEP_FK_REPAIR" \
    --keep-legacy-per-family "$KEEP_LEGACY_PER_FAMILY" \
    --legacy-max-age-days "$LEGACY_MAX_AGE_DAYS" \
    --json > "$LOG_FILE"

# Mantém os 60 logs mais recentes.
ls -t "$LOG_DIR"/audit-*.json 2>/dev/null | tail -n +61 | xargs rm -f 2>/dev/null || true
