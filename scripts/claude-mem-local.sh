#!/usr/bin/env bash
# shim — moved to scripts/services/
exec "$(dirname "${BASH_SOURCE[0]}")/services/claude-mem-local.sh" "$@"
