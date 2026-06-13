#!/usr/bin/env bash
# =============================================================================
# Sinapse Agent — start-rtk.sh
# =============================================================================
# Ativa o plugin RTK no Hermes para otimização de comandos shell.
# Uso: ./scripts/start-rtk.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "[sinapse] Verificando RTK..."
export PATH="$PROJECT_ROOT/rtk/target/release:/usr/local/bin:/usr/bin:/bin"

if ! command -v rtk &>/dev/null; then
    echo "[sinapse] RTK local não compilado. Execute: cargo build --release --manifest-path rtk/Cargo.toml"
    exit 1
fi

RTK_VERSION=$(rtk --version 2>/dev/null || echo "desconhecida")
echo "[sinapse] RTK $RTK_VERSION detectado"

# Verificar plugin Hermes
HERMES_PLUGIN_DIR="$HOME/.hermes/plugins/rtk-rewrite"
if [ -d "$HERMES_PLUGIN_DIR" ]; then
    echo "[sinapse] ✓ Plugin RTK já configurado no Hermes"
else
    echo "[sinapse] Copiando plugin RTK para Hermes..."
    mkdir -p "$HERMES_PLUGIN_DIR"
    cp "$PROJECT_ROOT/rtk/hermes-plugin/"* "$HERMES_PLUGIN_DIR/" 2>/dev/null || {
        echo "[sinapse] ✗ Plugin RTK não encontrado no projeto."
        echo "[sinapse]   Compile o checkout local e valide rtk/target/release/rtk."
        exit 1
    }
    echo "[sinapse] ✓ Plugin copiado. Reinicie o Hermes para ativar."
fi

echo "[sinapse] RTK pronto. Comandos shell serão otimizados automaticamente."
