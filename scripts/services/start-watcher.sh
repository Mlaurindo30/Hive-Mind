#!/usr/bin/env bash
# =============================================================================
# Hive-Mind — Real-time Watcher Service
# =============================================================================
# Monitora o vault Obsidian e sincroniza com o UMC instantaneamente.
# =============================================================================

PROJECT_ROOT="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python3"
VAULT_DIR="$PROJECT_ROOT/cerebro"

export SINAPSE_HOME="$PROJECT_ROOT"
echo "[hive-mind] Iniciando Real-time Watcher..."
echo "[hive-mind] Monitorando: $VAULT_DIR"

# Executa o watch em background
# Debounce conservador: rebuild estrutural pode levar dezenas de segundos.
DEBOUNCE="${GRAPHIFY_WATCH_DEBOUNCE:-30.0}"
echo "[hive-mind] Debounce estrutural: ${DEBOUNCE}s"
exec "$VENV_PYTHON" -m graphify watch "$VAULT_DIR" --debounce "$DEBOUNCE"
