#!/usr/bin/env bash
# =============================================================================
# integrations-update.sh — Atualiza integrações + dependências (lock-based)
#
# Substitui o antigo `git pull --rebase` cru pela delegação ao
# scripts/setup/components.py, que é:
#   • patch-safe       — remove o patch, faz o fetch/checkout e reaplica
#   • lock-consistente — bumpa config/components.lock.json (com backup)
#   • reversível       — components.py rollback <backup> em caso de regressão
#
# O que atualiza:
#   1. Componentes git (config/components.lock.json):
#        graphify, neural-memory, rtk
#        → components.py bootstrap/update
#   2. Dependências Python (.venv via uv):
#        uv lock --upgrade && uv sync  (inclui graphiti-core, falkordb,
#        ragflow-sdk, pymilvus, llama-index, opentelemetry-* e os componentes
#        editáveis acima)
#   3. claude-mem (plugin global de marketplace):
#        claude plugins update claude-mem@thedotmack
#
# NÃO mexe em (por design — não são repos git):
#   • integrations/graphiti/   (pacote pip graphiti-core)
#   • integrations/langfuse/   (serviço Docker + OTLP; sem código no repo)
#   • integrations/crsqlite/, integrations/claude-mem-plugins/, .../patches/
#   • vault cerebro/           (só leitura)
#
# Uso:
#   ./scripts/maintenance/integrations-update.sh            # tudo
#   ./scripts/maintenance/integrations-update.sh --verbose
#   ./scripts/maintenance/integrations-update.sh --no-components  # pula git/lock
#   ./scripts/maintenance/integrations-update.sh --no-pip   # pula uv upgrade
#   ./scripts/maintenance/integrations-update.sh --no-plugins
#   ./scripts/maintenance/integrations-update.sh --wrappers-only  # deps/wrappers, sem git/lock/plugins
#
# Instalação do cron (2x/semana):
#   crontab -l | cat - scripts/maintenance/integrations-update.crontab | crontab -
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERBOSE=false
DO_COMPONENTS=true
DO_PIP=true
DO_PLUGINS=true

for arg in "$@"; do
    case "$arg" in
        --verbose|-v)       VERBOSE=true ;;
        --no-components)    DO_COMPONENTS=false ;;
        --no-pip)           DO_PIP=false ;;
        --no-plugins)       DO_PLUGINS=false ;;
        --wrappers-only)    DO_COMPONENTS=false; DO_PLUGINS=false ;;
        *) echo "Argumento desconhecido: $arg (use --verbose|--no-components|--no-pip|--no-plugins|--wrappers-only)"; exit 1 ;;
    esac
done

log()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
ok()   { echo -e "\033[0;32m[OK]\033[0m    $*"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
err()  { echo -e "\033[0;31m[ERR]\033[0m   $*"; }

cd "$PROJECT_ROOT"

PYTHON="$PROJECT_ROOT/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

echo ""
echo -e "\033[1;34m╔══════════════════════════════════════════════════════╗\033[0m"
echo -e "\033[1;34m║   Hive-Mind — Atualização de Integrações (lock-based) ║\033[0m"
echo -e "\033[1;34m╚══════════════════════════════════════════════════════╝\033[0m"
echo ""

# =============================================================================
# 1. Componentes git pinados — via components.py (patch-safe + lock + rollback)
# =============================================================================
if [ "$DO_COMPONENTS" = true ]; then
    log "Componentes git: verificando estado do lock..."
    "$PYTHON" scripts/setup/components.py bootstrap
    "$PYTHON" scripts/setup/components.py verify || warn "verify reportou drift (será reconciliado pelo update)"
    echo ""

    # Limpa __pycache__ dos checkouts: o components.py aborta com 'dirty checkout
    # beyond the pinned patch' se houver qualquer untracked além do patch.
    find integrations/graphify integrations/neural-memory integrations/rtk \
        -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

    log "Componentes git: atualizando para origin/HEAD e re-pinando o lock..."
    if "$PYTHON" scripts/setup/components.py update --component all; then
        ok "Componentes git atualizados (lock bumpado; backup em config/component-lock-backups/)"
    else
        err "components.py update falhou — lock preservado, checkouts revertidos ao commit pinado."
        err "Inspecione o erro acima; rollback manual: $PYTHON scripts/setup/components.py rollback <backup>"
    fi
    echo ""
else
    warn "Componentes git: pulando bootstrap/update (--no-components/--wrappers-only)"
    echo ""
fi

# =============================================================================
# 2. Dependências Python (.venv via uv)
# =============================================================================
if [ "$DO_PIP" = true ]; then
    if command -v uv &>/dev/null; then
        log "Python deps: uv lock --upgrade && uv sync (graphiti, falkordb, ragflow-sdk, pymilvus, llama-index, otel, editáveis)..."
        if [ "$VERBOSE" = true ]; then
            uv lock --upgrade && uv sync --all-groups
        else
            uv lock --upgrade --quiet && uv sync --all-groups --quiet
        fi
        ok "Dependências Python sincronizadas no .venv"
    else
        warn "uv não encontrado — pulando atualização de pacotes Python"
    fi
    echo ""
fi

# =============================================================================
# 2.5. Wrappers Docker/SDK — valida compose + imagem pinada por digest
# =============================================================================
log "Wrappers K1: validando compose e digests pinados (Milvus/RAGFlow)..."
"$PYTHON" scripts/setup/verify_wrappers.py
ok "Wrappers K1 validados"
echo ""

# =============================================================================
# 3. claude-mem (plugin global de marketplace — instalado via npx/marketplace)
# =============================================================================
if [ "$DO_PLUGINS" = true ]; then
    log "claude-mem: verificando plugin de marketplace..."
    if command -v claude &>/dev/null; then
        if [ "$VERBOSE" = true ]; then
            claude plugins update claude-mem@thedotmack 2>&1 | tail -10
        else
            claude plugins update claude-mem@thedotmack 2>&1 | tail -3
        fi
        ok "claude-mem: verificação concluída"
    else
        warn "comando 'claude' não encontrado — pulando atualização do claude-mem"
    fi
    echo ""
fi

# =============================================================================
# Resumo
# =============================================================================
log "Estado final do lock:"
if [ "$DO_COMPONENTS" = true ]; then
    "$PYTHON" scripts/setup/components.py verify || true
else
    warn "verify do components.lock pulado porque componentes git não foram tocados"
fi
echo ""
warn "Antes de aceitar a atualização: rode tests/run_all.sh para validar."
echo ""
