#!/usr/bin/env bash
# =============================================================================
# Hive-Mind — Real-time Watcher Service
# =============================================================================
# Monitora o vault Obsidian e sincroniza com o UMC instantaneamente.
# =============================================================================

PROJECT_ROOT="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python3"
VAULT_DIR="$PROJECT_ROOT/cerebro"
GRAPHIFY_OUT="$VAULT_DIR/cortex/occipital/grafo"

export SINAPSE_HOME="$PROJECT_ROOT"
export GRAPHIFY_OUT
echo "[hive-mind] Iniciando Real-time Watcher..."
echo "[hive-mind] Monitorando: $VAULT_DIR"
echo "[hive-mind] Graphify output: $GRAPHIFY_OUT"

# Debounce: tempo de espera após a última edição antes de disparar o rebuild.
# 10s é o equilíbrio entre edições rápidas consecutivas (sem rebuilds sobrepostos)
# e feedback razoável durante o uso. Para rebuilds pesados use GRAPHIFY_WATCH_DEBOUNCE=30.
DEBOUNCE="${GRAPHIFY_WATCH_DEBOUNCE:-10.0}"
echo "[hive-mind] Debounce: ${DEBOUNCE}s (ajuste via GRAPHIFY_WATCH_DEBOUNCE)"
exec "$VENV_PYTHON" -m graphify watch "$VAULT_DIR" --debounce "$DEBOUNCE"
