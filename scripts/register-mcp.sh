#!/usr/bin/env bash
# =============================================================================
# register-mcp.sh — Registra o Hive-Mind MCP nos agentes de IA
#
# Uso:
#   ./scripts/register-mcp.sh --only <agente>   # registra SÓ o agente indicado
#   ./scripts/register-mcp.sh                    # (avançado) registra TODOS detectados
#   ./scripts/register-mcp.sh --check            # só mostra status, sem modificar
#   ./scripts/register-mcp.sh --list             # lista as chaves de agente válidas
#
# Filosofia: cada agente deve registrar a SI MESMO com --only <agente>.
# O modo sem argumento (registra todos) é um atalho de administrador, usado
# também pelo install.sh (etapa 12) numa instalação do zero.
#
# Idempotente. Faz MERGE no JSON/TOML de cada agente — nunca remove MCP
# servers de terceiros já registrados.
#
# Chaves de agente válidas:
#   claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode openclaw
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(dirname "$SCRIPT_DIR")}"
PYTHON="$PROJECT_ROOT/.venv/bin/python"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

VALID_AGENTS="claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode openclaw"

CHECK_ONLY=false
ONLY=""          # vazio = todos os detectados

while [ $# -gt 0 ]; do
    case "$1" in
        --check) CHECK_ONLY=true ;;
        --only|--self|--agent)
            shift
            ONLY="${1:-}"
            ;;
        --only=*|--self=*|--agent=*) ONLY="${1#*=}" ;;
        --list)
            echo "Agentes válidos: $VALID_AGENTS"
            exit 0
            ;;
        -h|--help)
            sed -n '2,27p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            # aceita nome de agente posicional (ex: register-mcp.sh claude)
            if [ -z "$ONLY" ]; then ONLY="$1"; else
                echo -e "${RED}✗${NC} argumento desconhecido: $1" >&2; exit 2
            fi
            ;;
    esac
    shift
done

if [ -n "$ONLY" ]; then
    case " $VALID_AGENTS " in
        *" $ONLY "*) : ;;
        *)
            echo -e "${RED}✗${NC} agente inválido: '$ONLY'"
            echo "  Válidos: $VALID_AGENTS"
            exit 2
            ;;
    esac
fi

# Merge seguro: adiciona/atualiza os três servidores project-local do
# Hive-Mind, preservando quaisquer outros MCP servers registrados pelo usuário.
# Uso: merge_mcp_server <arquivo> [chave_raiz]
#   chave_raiz padrão: mcpServers — VS Code (.vscode/mcp.json) usa "servers"
merge_mcp_server() {
    local FILE="$1"
    local ROOT_KEY="${2:-mcpServers}"
    mkdir -p "$(dirname "$FILE")"
    MCP_TARGET_FILE="$FILE" MCP_ROOT_KEY="$ROOT_KEY" MCP_PROJECT_ROOT="$PROJECT_ROOT" "$PYTHON" - << 'PYEOF'
import json, os
path = os.environ["MCP_TARGET_FILE"]
root_key = os.environ["MCP_ROOT_KEY"]
project_root = os.environ["MCP_PROJECT_ROOT"]
entries = {
    "sinapse-memory": {
        "command": f"{project_root}/.venv/bin/python",
        "args": [f"{project_root}/scripts/sinapse-mcp.py"],
        "cwd": project_root,
    },
    "claude-mem-local": {
        "command": "npx",
        "args": ["-y", "claude-mem@13.6", "mcp-server"],
        "cwd": project_root,
    },
    "neural-memory-local": {
        "command": f"{project_root}/scripts/neural-memory-local.sh",
        "args": [],
        "cwd": project_root,
    },
}
cfg = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
if not isinstance(cfg, dict):
    cfg = {}
servers = cfg.setdefault(root_key, {})
for name, entry in entries.items():
    if root_key == "servers":
        entry["type"] = "stdio"
    servers[name] = entry
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PYEOF
}

# Verifica se um arquivo já tem os três registros project-local.
has_registration() {
    local FILE="$1"
    local ROOT_KEY="${2:-mcpServers}"
    [ -f "$FILE" ] && "$PYTHON" -c "
import json, sys
try:
    cfg = json.load(open('$FILE'))
    expected = {'sinapse-memory', 'claude-mem-local', 'neural-memory-local'}
    sys.exit(0 if expected <= set(cfg.get('$ROOT_KEY', {})) else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null
}

register_codex() {
    if $CHECK_ONLY; then
        local missing=0
        for server in sinapse-memory claude-mem-local neural-memory-local; do
            codex mcp get "$server" >/dev/null 2>&1 || missing=1
        done
        if [ "$missing" -eq 0 ]; then
            echo -e "  ${GREEN}✓${NC} Codex CLI — 3 servidores registrados (~/.codex/config.toml)"
        else
            echo -e "  ${YELLOW}⊘${NC} Codex CLI — registro incompleto (~/.codex/config.toml)"
        fi
    else
        for server in sinapse-memory claude-mem-local neural-memory-local; do
            codex mcp remove "$server" >/dev/null 2>&1 || true
        done
        codex mcp add sinapse-memory -- \
            "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/sinapse-mcp.py"
        codex mcp add claude-mem-local -- \
            npx -y claude-mem@13.6 mcp-server
        codex mcp add neural-memory-local -- \
            "$PROJECT_ROOT/scripts/neural-memory-local.sh"
        # Mantém o JSON compatível com clientes Codex anteriores.
        merge_mcp_server "$HOME/.codex/mcp.json"
        echo -e "  ${GREEN}✓${NC} Codex CLI → 3 servidores project-local"
    fi
    ((++AGENTS_FOUND))
}

# register <nome> <arquivo> [chave_raiz]
register() {
    local NAME="$1" FILE="$2" ROOT_KEY="${3:-mcpServers}"
    if $CHECK_ONLY; then
        if has_registration "$FILE" "$ROOT_KEY"; then
            echo -e "  ${GREEN}✓${NC} $NAME — registrado ($FILE)"
        else
            echo -e "  ${YELLOW}⊘${NC} $NAME — detectado mas SEM registro ($FILE)"
        fi
    else
        merge_mcp_server "$FILE" "$ROOT_KEY"
        echo -e "  ${GREEN}✓${NC} $NAME → $FILE"
    fi
    ((++AGENTS_FOUND))
}

# -- Registradores por agente (cada um sabe o caminho de config do seu agente) --
do_claude()   { register "Claude Code" "$HOME/.claude/.mcp.json"; }
do_codex()    { register_codex; }
do_gemini()   { register "Gemini CLI" "$HOME/.gemini/settings.json"; }
do_qwen()     { register "Qwen Code" "$HOME/.qwen/settings.json"; }
do_kimi()     { register "Kimi Code" "$HOME/.kimi/mcp.json"; }
do_kiro()     { register "Kiro" "$HOME/.kiro/settings/mcp.json"; }
do_kilo()     { register "Kilo Code" "$HOME/.config/Code/User/globalStorage/kilocode.kilo-code/settings/mcp_settings.json"; }
do_roo()      { register "Roo Code" "$HOME/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json"; }
do_vscode()   { register "VS Code/Copilot" "$PROJECT_ROOT/.vscode/mcp.json" "servers"; }
do_cursor()   { register "Cursor" "$HOME/.cursor/mcp.json"; }
do_opencode() { register "OpenCode" "$HOME/.opencode/mcp.json"; }
do_openclaw() { register "OpenClaw" "$HOME/.openclaw/openclaw.json"; }

AGENTS_FOUND=0

echo "Hive-Mind — registro MCP (PROJECT_ROOT: $PROJECT_ROOT)"
echo ""

# --- Modo single-agent: registra SÓ o agente pedido, sem exigir detecção -----
if [ -n "$ONLY" ]; then
    echo "Modo single-agent: $ONLY"
    "do_$ONLY"
    echo ""
    if $CHECK_ONLY; then
        echo "Verificação concluída para: $ONLY"
    else
        echo "Registrado: $ONLY. Reinicie esse agente para carregar os MCPs."
        echo "Teste: peça \"use a tool sinapse_health\"."
    fi
    exit 0
fi

# --- Modo "todos" (admin / install.sh): detecta e registra cada um ------------
command -v claude  &>/dev/null && do_claude
command -v codex   &>/dev/null && do_codex
command -v gemini  &>/dev/null && do_gemini
{ command -v qwen &>/dev/null || [ -d "$HOME/.qwen" ]; } && do_qwen
{ command -v kimi &>/dev/null || [ -d "$HOME/.kimi" ]; } && do_kimi
{ command -v kiro &>/dev/null || [ -d "$HOME/.kiro" ]; } && do_kiro
if [ -d "$HOME/.config/Code/User/globalStorage/kilocode.kilo-code" ] || [ -d "$HOME/.kilocode" ]; then
    do_kilo
elif [ -f "$HOME/.kilo/config.json" ]; then
    register "Kilo (legado)" "$HOME/.kilo/config.json"
fi
[ -d "$HOME/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline" ] && do_roo
{ command -v code &>/dev/null || [ -d "$HOME/.config/Code/User/globalStorage/github.copilot-chat" ]; } && do_vscode
[ -d "$HOME/.cursor/" ] && do_cursor
command -v opencode &>/dev/null && do_opencode
command -v openclaw &>/dev/null && do_openclaw

echo ""
if [ "$AGENTS_FOUND" -eq 0 ]; then
    echo -e "${YELLOW}⊘${NC} Nenhum agente detectado nesta máquina."
    echo "  Instale um agente (Claude Code, Codex, Gemini CLI, ...) e rode novamente,"
    echo "  ou registre um específico: ./scripts/register-mcp.sh --only <agente>"
    exit 1
fi

if $CHECK_ONLY; then
    echo "$AGENTS_FOUND agente(s) detectado(s). Rode sem --check para registrar."
else
    echo "$AGENTS_FOUND agente(s) registrado(s). Reinicie cada agente para carregar os MCPs."
    echo "Teste em qualquer agente: peça \"use a tool sinapse_health\"."
fi
