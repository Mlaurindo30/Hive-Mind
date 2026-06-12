#!/usr/bin/env bash
# =============================================================================
# register-mcp.sh — Registra o Hive-Mind MCP em todos os agentes detectados
#
# Uso:
#   ./scripts/register-mcp.sh           # detecta e registra
#   ./scripts/register-mcp.sh --check   # só mostra o status, sem modificar nada
#
# Pode ser executado a qualquer momento (idempotente). Faz MERGE no JSON de
# cada agente — nunca sobrescreve outros MCP servers já registrados.
# Também é chamado pelo install.sh (etapa 12).
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(dirname "$SCRIPT_DIR")}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

CHECK_ONLY=false
[ "${1:-}" = "--check" ] && CHECK_ONLY=true

# Merge seguro: adiciona/atualiza apenas a chave sinapse-memory no JSON do
# agente, preservando quaisquer outros MCP servers registrados pelo usuário.
# Uso: merge_mcp_server <arquivo> [chave_raiz]
#   chave_raiz padrão: mcpServers — VS Code (.vscode/mcp.json) usa "servers"
merge_mcp_server() {
    local FILE="$1"
    local ROOT_KEY="${2:-mcpServers}"
    mkdir -p "$(dirname "$FILE")"
    MCP_TARGET_FILE="$FILE" MCP_ROOT_KEY="$ROOT_KEY" MCP_PROJECT_ROOT="$PROJECT_ROOT" python3 - << 'PYEOF'
import json, os
path = os.environ["MCP_TARGET_FILE"]
root_key = os.environ["MCP_ROOT_KEY"]
project_root = os.environ["MCP_PROJECT_ROOT"]
entry = {
    "command": "python3",
    "args": [f"{project_root}/scripts/sinapse-mcp.py"],
    "cwd": project_root,
}
if root_key == "servers":
    entry["type"] = "stdio"
cfg = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
if not isinstance(cfg, dict):
    cfg = {}
cfg.setdefault(root_key, {})["sinapse-memory"] = entry
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PYEOF
}

# Verifica se um arquivo já tem o registro sinapse-memory
has_registration() {
    local FILE="$1"
    local ROOT_KEY="${2:-mcpServers}"
    [ -f "$FILE" ] && python3 -c "
import json, sys
try:
    cfg = json.load(open('$FILE'))
    sys.exit(0 if 'sinapse-memory' in cfg.get('$ROOT_KEY', {}) else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null
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

AGENTS_FOUND=0

echo "Hive-Mind — registro MCP (PROJECT_ROOT: $PROJECT_ROOT)"
echo ""

# Claude Code
if command -v claude &>/dev/null; then
    register "Claude Code" "$HOME/.claude/.mcp.json"
fi

# Codex CLI
if command -v codex &>/dev/null; then
    register "Codex CLI" "$HOME/.codex/mcp.json"
fi

# Gemini CLI
if command -v gemini &>/dev/null; then
    register "Gemini CLI" "$HOME/.gemini/settings.json"
fi

# Qwen Code (mesmo formato do Gemini CLI)
if command -v qwen &>/dev/null || [ -d "$HOME/.qwen" ]; then
    register "Qwen Code" "$HOME/.qwen/settings.json"
fi

# Kimi Code CLI (formato compatível com Claude Desktop)
if command -v kimi &>/dev/null || [ -d "$HOME/.kimi" ]; then
    register "Kimi Code" "$HOME/.kimi/mcp.json"
fi

# Kiro (AWS) — config global
if command -v kiro &>/dev/null || [ -d "$HOME/.kiro" ]; then
    register "Kiro" "$HOME/.kiro/settings/mcp.json"
fi

# Kilo Code (extensão VS Code — globalStorage; ~/.kilo é legado)
if [ -d "$HOME/.config/Code/User/globalStorage/kilocode.kilo-code" ] || [ -d "$HOME/.kilocode" ]; then
    register "Kilo Code" "$HOME/.config/Code/User/globalStorage/kilocode.kilo-code/settings/mcp_settings.json"
elif [ -f "$HOME/.kilo/config.json" ]; then
    register "Kilo (legado)" "$HOME/.kilo/config.json"
fi

# Roo Code (extensão VS Code)
if [ -d "$HOME/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline" ]; then
    register "Roo Code" "$HOME/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json"
fi

# VS Code / GitHub Copilot (Agent Mode) — .vscode/mcp.json NO PROJETO,
# chave raiz "servers" (formato próprio do VS Code, não "mcpServers")
if command -v code &>/dev/null || [ -d "$HOME/.config/Code/User/globalStorage/github.copilot-chat" ]; then
    register "VS Code/Copilot" "$PROJECT_ROOT/.vscode/mcp.json" "servers"
fi

# Cursor
if [ -d "$HOME/.cursor/" ]; then
    register "Cursor" "$HOME/.cursor/mcp.json"
fi

# OpenCode
if command -v opencode &>/dev/null; then
    register "OpenCode" "$HOME/.opencode/mcp.json"
fi

# OpenClaw
if command -v openclaw &>/dev/null; then
    register "OpenClaw" "$HOME/.openclaw/openclaw.json"
fi

echo ""
if [ "$AGENTS_FOUND" -eq 0 ]; then
    echo -e "${YELLOW}⊘${NC} Nenhum agente detectado nesta máquina."
    echo "  Instale um agente (Claude Code, Codex, Gemini CLI, ...) e rode novamente."
    exit 1
fi

if $CHECK_ONLY; then
    echo "$AGENTS_FOUND agente(s) detectado(s). Rode sem --check para registrar."
else
    echo "$AGENTS_FOUND agente(s) registrado(s). Reinicie cada agente para carregar as 9 tools."
    echo "Teste em qualquer agente: peça \"use a tool sinapse_health\"."
fi
