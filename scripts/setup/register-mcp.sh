#!/usr/bin/env bash
# =============================================================================
# register-mcp.sh — Registra o Hive-Mind MCP nos agentes de IA
#
# Uso:
#   ./scripts/setup/register-mcp.sh --only <agente>   # registra SÓ o agente indicado
#   ./scripts/setup/register-mcp.sh --only <agente> --check
#   ./scripts/setup/register-mcp.sh --list             # lista as chaves válidas
#   ./scripts/setup/register-mcp.sh                    # avançado: registra TODOS detectados
#
# Filosofia: cada agente deve registrar a SI MESMO com --only <agente>.
# O modo sem argumento (registra todos) é um atalho de administrador. O
# install.sh não chama esse modo; numa instalação normal use --only.
#
# Idempotente. Faz MERGE no JSON/TOML de cada agente — nunca remove MCP
# servers de terceiros já registrados.
#
# Chaves de agente válidas:
#   claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode openclaw
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(dirname "$(dirname "$SCRIPT_DIR")")}"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3 || command -v python)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

VALID_AGENTS="claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode openclaw swarmclaw"

CHECK_ONLY=false
ONLY=""          # vazio = todos os detectados

# Política de uso do agente (fonte única). É devolvida pelo sinapse-mcp.py como
# `instructions` no initialize E injetada nos arquivos de prompt aqui (híbrido).
PROMPT_SRC="$PROJECT_ROOT/config/sinapse-agent-prompt.md"
INJECT_PROMPT=true
[ -n "${HIVE_SKIP_PROMPT:-}" ] && INJECT_PROMPT=false

while [ $# -gt 0 ]; do
    case "$1" in
        --check) CHECK_ONLY=true ;;
        --no-instructions) INJECT_PROMPT=false ;;
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

# Merge seguro: adiciona/atualiza o servidor sinapse-memory gerenciado pelo
# Hive-Mind, preservando quaisquer outros MCP servers registrados pelo usuário.
# sinapse-memory federa NeuralMemory, claude-mem, Graphify, FalkorDB e UMC;
# os backends crus não são mais expostos como MCP separado ao agente.
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
# Apenas o orquestrador sinapse-memory é exposto ao agente. Ele federa
# por dentro NeuralMemory (.neuralmemory/), claude-mem (worker :37700),
# Graphify, FalkorDB/Graphiti, UMC SQL e filesystem. claude-mem segue
# capturando via hooks (.claude/settings.json), não precisa de MCP próprio.
entries = {
    "sinapse-memory": {
        "command": f"{project_root}/.venv/bin/python",
        "args": [f"{project_root}/scripts/services/sinapse-mcp.py"],
        "cwd": project_root,
        "env": {"PYTHONPATH": project_root},
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
# Colapsa o modelo legado (3 backends crus) para só sinapse-memory: remove os
# nomes que NÓS gerenciávamos antes, preservando MCP servers de terceiros.
for legacy in ("claude-mem-local", "neural-memory-local"):
    servers.pop(legacy, None)
for name, entry in entries.items():
    if root_key == "servers":
        entry["type"] = "stdio"
    servers[name] = entry
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PYEOF
}

# Verifica se um arquivo já tem o registro gerenciado pelo Hive-Mind.
has_registration() {
    local FILE="$1"
    local ROOT_KEY="${2:-mcpServers}"
    [ -f "$FILE" ] && "$PYTHON" -c "
import json, sys
try:
    cfg = json.load(open('$FILE'))
    expected = {'sinapse-memory'}
    sys.exit(0 if expected <= set(cfg.get('$ROOT_KEY', {})) else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null
}

register_codex() {
    if $CHECK_ONLY; then
        if codex mcp get sinapse-memory >/dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} Codex CLI — sinapse-memory registrado (~/.codex/config.toml)"
        else
            echo -e "  ${YELLOW}⊘${NC} Codex CLI — SEM registro (~/.codex/config.toml)"
        fi
    else
        # Remove servidores legados (modelo antigo de 3 backends crus) e os
        # re-registra apenas como o orquestrador sinapse-memory.
        for server in sinapse-memory claude-mem-local neural-memory-local; do
            codex mcp remove "$server" >/dev/null 2>&1 || true
        done
        codex mcp add sinapse-memory --env PYTHONPATH="$PROJECT_ROOT" -- \
            "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/services/sinapse-mcp.py"
        # Mantém o JSON compatível com clientes Codex anteriores.
        merge_mcp_server "$HOME/.codex/mcp.json"
        echo -e "  ${GREEN}✓${NC} Codex CLI → sinapse-memory"
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
# Claude Code NÃO lê ~/.claude/.mcp.json. As fontes válidas são o .mcp.json
# do projeto (escopo project) e ~/.claude.json (escopo user/local). Usamos o
# CLI oficial `claude mcp add -s project`, que grava em <PROJECT_ROOT>/.mcp.json.
# Fallback (sem CLI): escreve o .mcp.json do projeto via merge_mcp_server.
do_claude() {
    if ! command -v claude >/dev/null 2>&1; then
        register "Claude Code (project .mcp.json)" "$PROJECT_ROOT/.mcp.json"
        return
    fi
    if $CHECK_ONLY; then
        if ( cd "$PROJECT_ROOT" && claude mcp get sinapse-memory ) >/dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} Claude Code — sinapse-memory registrado (escopo project)"
        else
            echo -e "  ${YELLOW}⊘${NC} Claude Code — SEM registro (rode sem --check)"
        fi
    else
        ( cd "$PROJECT_ROOT" && {
            claude mcp remove sinapse-memory -s project >/dev/null 2>&1 || true
            claude mcp add sinapse-memory -s project \
                -e PYTHONPATH="$PROJECT_ROOT" \
                -- "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/services/sinapse-mcp.py"
        } )
        echo -e "  ${GREEN}✓${NC} Claude Code → sinapse-memory (.mcp.json do projeto)"
    fi
    ((++AGENTS_FOUND))
}
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

# SwarmClaw armazena MCPs em SQLite (~/.swarmclaw/data/swarmclaw.db, tabela mcp_servers).
# Se o servidor estiver rodando (porta 3456) usa a API REST; caso contrário faz upsert direto.
do_swarmclaw() {
    local SCLAW_DB="$HOME/.swarmclaw/data/swarmclaw.db"

    if $CHECK_ONLY; then
        local result
        result=$("$PYTHON" - << PYEOF
import json, sqlite3, sys
try:
    conn = sqlite3.connect('$SCLAW_DB')
    rows = conn.execute('SELECT data FROM mcp_servers').fetchall()
    names = {json.loads(r[0]).get('name') for r in rows}
    expected = {'sinapse-memory'}
    missing = expected - names
    conn.close()
    print('MISSING:' + ','.join(sorted(missing)) if missing else 'OK')
except Exception as e:
    print('ERROR:' + str(e))
PYEOF
)
        if [ "$result" = "OK" ]; then
            echo -e "  ${GREEN}✓${NC} SwarmClaw — sinapse-memory registrado ($SCLAW_DB)"
        else
            echo -e "  ${YELLOW}⊘${NC} SwarmClaw — detectado mas SEM registro completo ($result)"
        fi
        ((++AGENTS_FOUND))
        return
    fi

    MCP_PROJECT_ROOT="$PROJECT_ROOT" SCLAW_DB="$SCLAW_DB" "$PYTHON" - << 'PYEOF'
import json, os, sqlite3, time, uuid

project_root = os.environ['MCP_PROJECT_ROOT']
db_path      = os.environ['SCLAW_DB']

ENTRIES = [
    {
        'name': 'sinapse-memory',
        'transport': 'stdio',
        'command': f'{project_root}/.venv/bin/python',
        'args': [f'{project_root}/scripts/services/sinapse-mcp.py'],
        'cwd': project_root,
        'env': {'PYTHONPATH': project_root},
    },
]

conn = sqlite3.connect(db_path)
rows = conn.execute('SELECT id, data FROM mcp_servers').fetchall()
existing = {}
for row_id, row_data in rows:
    try:
        obj = json.loads(row_data)
        existing[obj.get('name')] = row_id
    except Exception:
        pass
now = int(time.time() * 1000)
for entry in ENTRIES:
    name = entry['name']
    sid = existing.get(name, uuid.uuid4().hex[:16])
    data = {
        'id': sid,
        'name': name,
        'transport': 'stdio',
        'command': entry['command'],
        'args': entry['args'],
        'cwd': entry['cwd'],
        'env': entry['env'],
        'createdAt': now,
        'updatedAt': now,
    }
    conn.execute(
        'INSERT OR REPLACE INTO mcp_servers (id, data) VALUES (?, ?)',
        (sid, json.dumps(data)),
    )
# Remove o modelo legado (backends crus) que NÓS gerenciávamos.
for legacy in ('claude-mem-local', 'neural-memory-local'):
    lid = existing.get(legacy)
    if lid is not None:
        conn.execute('DELETE FROM mcp_servers WHERE id = ?', (lid,))
conn.commit()
conn.close()
PYEOF

    echo -e "  ${GREEN}✓${NC} SwarmClaw → $SCLAW_DB"
    ((++AGENTS_FOUND))
}

# Arquivo de instruções (prompt) por agente — project-scoped, segue o repo.
prompt_target_for() {
    case "$1" in
        claude)   echo "$PROJECT_ROOT/CLAUDE.md" ;;
        gemini)   echo "$PROJECT_ROOT/GEMINI.md" ;;
        vscode)   echo "$PROJECT_ROOT/.github/copilot-instructions.md" ;;
        cursor)   echo "$PROJECT_ROOT/.cursor/rules/hive-mind.md" ;;
        codex|qwen|kimi|kiro|kilo|roo|opencode|openclaw) echo "$PROJECT_ROOT/AGENTS.md" ;;
        *)        echo "" ;;   # swarmclaw etc.: sem arquivo de prompt
    esac
}

# Upsert idempotente do bloco de instruções entre marcadores. Atualiza o bloco
# se já existir; nunca duplica; preserva o resto do arquivo do usuário.
inject_instructions() {
    local target="$1"
    if [ ! -f "$PROMPT_SRC" ]; then
        echo -e "    ${YELLOW}⊘${NC} prompt fonte ausente: $PROMPT_SRC"
        return 0
    fi
    mkdir -p "$(dirname "$target")"
    PROMPT_SRC="$PROMPT_SRC" TARGET="$target" "$PYTHON" - << 'PYEOF'
import os, re, pathlib
src = pathlib.Path(os.environ["PROMPT_SRC"]).read_text(encoding="utf-8").strip()
target = pathlib.Path(os.environ["TARGET"])
BEGIN = "<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.sh — do not edit) -->"
END = "<!-- END HIVE-MIND SINAPSE -->"
block = f"{BEGIN}\n{src}\n{END}\n"
existing = target.read_text(encoding="utf-8") if target.exists() else ""
pat = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
if pat.search(existing):
    new = pat.sub(block, existing)
else:
    prefix = existing.rstrip("\n")
    new = (prefix + "\n\n" if prefix else "") + block
target.write_text(new, encoding="utf-8")
PYEOF
    echo -e "    ${GREEN}↳${NC} prompt injetado em ${target#$PROJECT_ROOT/}"
}

# Registra o MCP do agente e injeta a política no prompt dele (a menos que
# --check ou --no-instructions). Fonte única: $PROMPT_SRC.
run_agent() {
    local key="$1"
    "do_$key"
    if ! $CHECK_ONLY && $INJECT_PROMPT; then
        local tgt; tgt="$(prompt_target_for "$key")"
        [ -n "$tgt" ] && inject_instructions "$tgt"
    fi
}

AGENTS_FOUND=0

echo "Hive-Mind — registro MCP (PROJECT_ROOT: $PROJECT_ROOT)"
echo ""

# --- Modo single-agent: registra SÓ o agente pedido, sem exigir detecção -----
if [ -n "$ONLY" ]; then
    echo "Modo single-agent: $ONLY"
    run_agent "$ONLY"
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
command -v claude  &>/dev/null && run_agent claude
command -v codex   &>/dev/null && run_agent codex
command -v gemini  &>/dev/null && run_agent gemini
{ command -v qwen &>/dev/null || [ -d "$HOME/.qwen" ]; } && run_agent qwen
{ command -v kimi &>/dev/null || [ -d "$HOME/.kimi" ]; } && run_agent kimi
{ command -v kiro &>/dev/null || [ -d "$HOME/.kiro" ]; } && run_agent kiro
if [ -d "$HOME/.config/Code/User/globalStorage/kilocode.kilo-code" ] || [ -d "$HOME/.kilocode" ]; then
    run_agent kilo
elif [ -f "$HOME/.kilo/config.json" ]; then
    register "Kilo (legado)" "$HOME/.kilo/config.json"
fi
[ -d "$HOME/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline" ] && run_agent roo
{ command -v code &>/dev/null || [ -d "$HOME/.config/Code/User/globalStorage/github.copilot-chat" ]; } && run_agent vscode
[ -d "$HOME/.cursor/" ] && run_agent cursor
command -v opencode &>/dev/null && run_agent opencode
command -v openclaw &>/dev/null && run_agent openclaw
{ command -v swarmclaw &>/dev/null || [ -d "$HOME/.swarmclaw" ]; } && run_agent swarmclaw

echo ""
if [ "$AGENTS_FOUND" -eq 0 ]; then
    echo -e "${YELLOW}⊘${NC} Nenhum agente detectado nesta máquina."
    echo "  Instale um agente (Claude Code, Codex, Gemini CLI, ...) e rode novamente,"
    echo "  ou registre um específico: ./scripts/setup/register-mcp.sh --only <agente>"
    exit 1
fi

if $CHECK_ONLY; then
    echo "$AGENTS_FOUND agente(s) detectado(s). Rode sem --check para registrar."
else
    echo "$AGENTS_FOUND agente(s) registrado(s). Reinicie cada agente para carregar os MCPs."
    echo "Teste em qualquer agente: peça \"use a tool sinapse_health\"."
fi
