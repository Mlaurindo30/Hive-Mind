#!/bin/bash
# Hive-Mind disaster recovery with consistent SQLite backup/restore.

set -euo pipefail
SINAPSE_HOME="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON="$SINAPSE_HOME/.venv/bin/python"
RECOVERY="$SINAPSE_HOME/scripts/recovery.py"
export PATH="$SINAPSE_HOME/.venv/bin:$SINAPSE_HOME/rtk/target/release:/usr/local/bin:/usr/bin:/bin"

case "${1:-verify}" in
    backup)
        exec "$PYTHON" "$RECOVERY" backup "${@:2}"
        ;;
    verify)
        exec "$PYTHON" "$RECOVERY" verify "${@:2}"
        ;;
    rebuild-indexes)
        exec "$PYTHON" "$RECOVERY" rebuild-indexes "${@:2}"
        ;;
    restore)
        if [[ $# -lt 2 ]]; then
            echo "Uso: $0 restore BACKUP_DB [--rebuild-indexes]" >&2
            exit 2
        fi
        backup="$2"
        shift 2
        systemctl --user stop sinapse-graphify-watch.service sinapse-api.service 2>/dev/null || true
        trap 'systemctl --user start sinapse-graphify-watch.service sinapse-api.service 2>/dev/null || true' EXIT
        "$PYTHON" "$RECOVERY" restore "$backup" "$@"
        systemctl --user start sinapse-graphify-watch.service sinapse-api.service 2>/dev/null || true
        trap - EXIT
        ;;
    *)
        echo "Uso: $0 {backup|verify|rebuild-indexes|restore BACKUP_DB}" >&2
        exit 2
        ;;
esac
