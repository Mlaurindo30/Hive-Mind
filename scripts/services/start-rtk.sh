#!/usr/bin/env bash
# =============================================================================
# Hive-Mind — start-rtk.sh
# =============================================================================
# Configura o RTK como otimizador de comandos shell para agentes/CLIs.
# O RTK nao e memoria e nao participa do sinapse_query; ele atua antes da
# execucao de comandos, via hooks/plugins/instrucoes instalados por agente.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

export PATH="$PROJECT_ROOT/integrations/rtk/target/release:/usr/local/bin:/usr/bin:/bin"

AGENTS=()
DRY_RUN=0
SHOW=0
VERBOSE=0

usage() {
    cat <<'EOF'
Uso:
  ./scripts/services/start-rtk.sh --only <agente> [--dry-run]
  ./scripts/services/start-rtk.sh --all [--dry-run]
  ./scripts/services/start-rtk.sh --check
  ./scripts/services/start-rtk.sh --list

Agentes suportados:
  claude, codex, gemini, cursor, windsurf, copilot, opencode, pi,
  hermes, cline, roo, kilocode, kilo, antigravity

Exemplos:
  ./scripts/services/start-rtk.sh --only codex
  ./scripts/services/start-rtk.sh --only gemini --dry-run
  ./scripts/services/start-rtk.sh --all

Notas:
  - claude/codex/gemini/cursor/windsurf/copilot/opencode/pi usam instalacao global.
  - hermes/cline/roo/kilocode/kilo/antigravity usam instalacao no projeto atual.
  - O script delega para 'rtk init', preservando o comportamento oficial do RTK.
EOF
}

list_agents() {
    printf '%s\n' \
        claude codex gemini cursor windsurf copilot opencode pi \
        hermes cline roo kilocode kilo antigravity
}

require_rtk() {
    echo "[sinapse] Verificando RTK..."
    if ! command -v rtk &>/dev/null; then
        echo "[sinapse] RTK local nao compilado."
        echo "[sinapse] Execute: cargo build --release --manifest-path integrations/rtk/Cargo.toml"
        exit 1
    fi

    local version
    version="$(rtk --version 2>/dev/null || echo "desconhecida")"
    echo "[sinapse] $version detectado"
}

normalize_agent() {
    case "$1" in
        claude|claude-code) echo "claude" ;;
        codex|codex-cli) echo "codex" ;;
        gemini|gemini-cli) echo "gemini" ;;
        cursor) echo "cursor" ;;
        windsurf) echo "windsurf" ;;
        copilot|github-copilot) echo "copilot" ;;
        opencode|open-code) echo "opencode" ;;
        pi) echo "pi" ;;
        hermes) echo "hermes" ;;
        cline|roo|roo-code) echo "cline" ;;
        kilocode|kilo|kilo-code) echo "kilocode" ;;
        antigravity|google-antigravity) echo "antigravity" ;;
        *)
            echo "[sinapse] Agente RTK desconhecido: $1" >&2
            echo "[sinapse] Use --list para ver os alvos suportados." >&2
            exit 1
            ;;
    esac
}

run_rtk_init() {
    local agent="$1"
    local -a cmd

    case "$agent" in
        claude) cmd=(rtk init --global --agent claude --auto-patch) ;;
        codex) cmd=(rtk init --global --codex) ;;
        gemini) cmd=(rtk init --global --gemini) ;;
        cursor) cmd=(rtk init --global --agent cursor --auto-patch) ;;
        windsurf) cmd=(rtk init --global --agent windsurf) ;;
        copilot) cmd=(rtk init --global --copilot) ;;
        opencode) cmd=(rtk init --global --opencode) ;;
        pi) cmd=(rtk init --global --agent pi) ;;
        hermes) cmd=(rtk init --agent hermes) ;;
        cline) cmd=(rtk init --agent cline) ;;
        kilocode) cmd=(rtk init --agent kilocode) ;;
        antigravity) cmd=(rtk init --agent antigravity) ;;
        *)
            echo "[sinapse] Agente normalizado invalido: $agent" >&2
            exit 1
            ;;
    esac

    if [ "$DRY_RUN" -eq 1 ]; then
        cmd+=(--dry-run)
    fi
    if [ "$VERBOSE" -eq 1 ]; then
        cmd+=(-v)
    fi

    echo "[sinapse] Configurando RTK para $agent: ${cmd[*]}"
    "${cmd[@]}"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --only)
            shift
            [ "$#" -gt 0 ] || { echo "[sinapse] --only requer um agente." >&2; exit 1; }
            AGENTS+=("$(normalize_agent "$1")")
            ;;
        --all)
            AGENTS=(claude codex gemini cursor windsurf copilot opencode pi hermes cline kilocode antigravity)
            ;;
        --check|--show)
            SHOW=1
            ;;
        --list)
            list_agents
            exit 0
            ;;
        --dry-run)
            DRY_RUN=1
            ;;
        -v|--verbose)
            VERBOSE=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            AGENTS+=("$(normalize_agent "$1")")
            ;;
    esac
    shift
done

require_rtk

if [ "$SHOW" -eq 1 ]; then
    rtk init --show
    exit 0
fi

if [ "${#AGENTS[@]}" -eq 0 ]; then
    usage
    exit 0
fi

for agent in "${AGENTS[@]}"; do
    run_rtk_init "$agent"
done

echo "[sinapse] RTK configurado. Reinicie os agentes/CLIs alterados para carregar os hooks/instrucoes."
