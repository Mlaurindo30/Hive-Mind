#!/usr/bin/env bash
# =============================================================================
# Hive-Mind — Real-time Watcher Service
# =============================================================================
# Monitora o vault Obsidian e sincroniza com o UMC instantaneamente.
# =============================================================================

PROJECT_ROOT="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python3"
VAULT_DIR="$PROJECT_ROOT/cerebro"

export SINAPSE_HOME="$PROJECT_ROOT"
echo "[hive-mind] Iniciando Real-time Watcher..."
echo "[hive-mind] Monitorando: $VAULT_DIR"

# Executa o watch em background
# --debounce 2.0 para reações mais rápidas que o padrão de 3.0
exec "$VENV_PYTHON" -m graphify watch "$VAULT_DIR" --debounce 2.0
