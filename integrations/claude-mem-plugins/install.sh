#!/usr/bin/env bash
# =============================================================================
# install.sh — Instala os plugins claude-mem nativos para cada ferramenta
#
# Uso:
#   ./integrations/claude-mem-plugins/install.sh             # instala todos
#   ./integrations/claude-mem-plugins/install.sh antigravity # instala só um
#
# O que faz:
#   1. Copia os arquivos de plugin (plugin.json + hooks.json) para o diretório
#      de plugins da ferramenta alvo
#   2. Idempotente: re-rodar sobrescreve sem quebrar nada
#   3. NÃO modifica os scripts do claude-mem — usa os que já estão instalados
#      em ~/.claude/plugins/marketplaces/thedotmack/plugin/scripts/
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Mapeamento: ferramenta → diretório de plugins da ferramenta
# ---------------------------------------------------------------------------
declare -A PLUGIN_DIRS=(
  ["antigravity"]="${HOME}/.gemini/antigravity-cli/plugins/claude-mem"
)

# ---------------------------------------------------------------------------
# Instala o plugin de uma ferramenta específica
# ---------------------------------------------------------------------------
install_plugin() {
  local tool="$1"
  local target_dir="${PLUGIN_DIRS[$tool]}"
  local source_dir="${SCRIPT_DIR}/${tool}"

  if [ ! -d "${source_dir}" ]; then
    echo "  ✗ ${tool}: diretório de plugin não encontrado em ${source_dir}"
    return 1
  fi

  echo "  → ${tool}: instalando em ${target_dir}"
  mkdir -p "${target_dir}"

  # Copia plugin.json
  cp "${source_dir}/plugin.json" "${target_dir}/plugin.json"
  echo "    ✓ plugin.json"

  # Copia hooks.json
  cp "${source_dir}/hooks.json" "${target_dir}/hooks.json"
  echo "    ✓ hooks.json"

  echo "  ✓ ${tool}: plugin instalado"
}

# ---------------------------------------------------------------------------
# Verifica pré-requisitos
# ---------------------------------------------------------------------------
check_claude_mem() {
  local worker="/home/michel/.claude/plugins/marketplaces/thedotmack/plugin/scripts/worker-service.cjs"
  if [ ! -f "${worker}" ]; then
    echo "⚠  claude-mem não encontrado em ~/.claude/plugins/"
    echo "   Instale o claude-mem no Claude Code antes de continuar."
    exit 1
  fi
  echo "✓ claude-mem encontrado"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "=== claude-mem native plugin installer ==="
check_claude_mem

if [ $# -gt 0 ]; then
  # Instala só a ferramenta especificada
  tool="$1"
  if [ -z "${PLUGIN_DIRS[$tool]+_}" ]; then
    echo "✗ Ferramenta desconhecida: ${tool}"
    echo "  Disponíveis: ${!PLUGIN_DIRS[*]}"
    exit 1
  fi
  install_plugin "${tool}"
else
  # Instala todas as ferramentas disponíveis
  for tool in "${!PLUGIN_DIRS[@]}"; do
    install_plugin "${tool}"
  done
fi

echo ""
echo "Feito. Reinicie a ferramenta para ativar os hooks."
