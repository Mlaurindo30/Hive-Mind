#!/usr/bin/env bash
# =============================================================================
# register-mcp.sh — Registra o Hive-Mind MCP nos agentes de IA
#
# Uso:
#   ./scripts/setup/register-mcp.sh --only <agent>      # registers ONLY the named agent
#   ./scripts/setup/register-mcp.sh --only <agente> --check
#   ./scripts/setup/register-mcp.sh --list             # lista as chaves válidas
#   ./scripts/setup/register-mcp.sh                    # advanced: registers ALL detected agents
#
# Philosophy: each agent should register ITSELF with --only <agent>.
# The no-argument mode (register all) is an admin shortcut. The
# install.sh does not call this mode; in a normal installation use --only.
#
# Idempotent. MERGEs into each agent's JSON/TOML — never removes third-party
# MCP servers already registered.
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
ONLY=""          # empty = all detected agents

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

# Safe merge: adds/updates the sinapse-memory server managed by
# Hive-Mind, preserving any other MCP servers registered by the user.
# sinapse-memory federates NeuralMemory, claude-mem, Graphify, FalkorDB and UMC;
# raw backends are no longer exposed as separate MCPs to the agent.
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
# Internally federates NeuralMemory (.neuralmemory/), claude-mem (worker :37700),
# Graphify, FalkorDB/Graphiti, UMC SQL e filesystem. claude-mem segue
# capturing via hooks (.claude/settings.json), no dedicated MCP needed.
# Collapses the legacy model (3 raw backends) into only sinapse-memory: removes the
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
# names WE managed before, preserving third-party MCP servers.
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
            echo -e "  ${GREEN}✓${NC} Codex CLI — sinapse-memory registered (~/.codex/config.toml)"
        else
            echo -e "  ${YELLOW}⊘${NC} Codex CLI — SEM registro (~/.codex/config.toml)"
        fi
    else
        # Remove servidores legados (modelo antigo de 3 backends crus) e os
        # re-registers only as the sinapse-memory orchestrator.
        for server in sinapse-memory claude-mem-local neural-memory-local; do
            codex mcp remove "$server" >/dev/null 2>&1 || true
        done
        codex mcp add sinapse-memory --env PYTHONPATH="$PROJECT_ROOT" -- \
            "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/services/sinapse-mcp.py"
        # Keeps the JSON compatible with older Codex clients.
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
            echo -e "  ${GREEN}✓${NC} $NAME — registered ($FILE)"
        else
            echo -e "  ${YELLOW}⊘${NC} $NAME — detected but NOT registered ($FILE)"
        fi
    else
        merge_mcp_server "$FILE" "$ROOT_KEY"
        echo -e "  ${GREEN}✓${NC} $NAME → $FILE"
    fi
    ((++AGENTS_FOUND))
}

# -- Per-agent registrars (each one knows its own agent config path) --
# Claude Code does NOT read ~/.claude/.mcp.json. The valid sources are the .mcp.json
# do projeto (escopo project) e ~/.claude.json (escopo user/local). Usamos o
# at <PROJECT_ROOT>/.mcp.json.
# Fallback (sem CLI): escreve o .mcp.json do projeto via merge_mcp_server.
do_claude() {
    if ! command -v claude >/dev/null 2>&1; then
        register "Claude Code (project .mcp.json)" "$PROJECT_ROOT/.mcp.json"
        return
    fi
    if $CHECK_ONLY; then
        if ( cd "$PROJECT_ROOT" && claude mcp get sinapse-memory ) >/dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} Claude Code — sinapse-memory registered (project scope)"
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
            echo -e "  ${GREEN}✓${NC} SwarmClaw — sinapse-memory registered ($SCLAW_DB)"
        else
            echo -e "  ${YELLOW}⊘${NC} SwarmClaw — detected but NOT fully registered ($result)"
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
# Removes the legacy model (raw backends) that WE managed.
# Prompt instruction file (prompt) per agent — project-scoped, follows the repo.
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

# Prompt file (prompt) per agent — project-scoped, follows the repo.
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

# Registers the agent's MCP and injects the policy into its prompt (unless
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

# --- single-agent mode: registers ONLY the requested agent, no detection needed -----
if [ -n "$ONLY" ]; then
    echo "Modo single-agent: $ONLY"
    run_agent "$ONLY"
    echo ""
    if $CHECK_ONLY; then
        echo "Verification completed for: $ONLY"
    else
        echo "Registered: $ONLY. Restart that agent to load the MCPs."
        echo "Test: ask it \"use the sinapse_health tool\"."
    fi
    exit 0
fi

# --- "all" mode (admin / install.sh): detects and registers each one ------------
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
    echo -e "${YELLOW}⊘${NC} No agent detected on this machine."
    echo "  Install an agent (Claude Code, Codex, Gemini CLI, ...) and run again,"
    echo "  or register a specific one: ./scripts/setup/register-mcp.sh --only <agent>"
    exit 1
fi

if $CHECK_ONLY; then
    echo "$AGENTS_FOUND agent(s) detected. Run without --check to register."
else
    echo "$AGENTS_FOUND agent(s) registered. Restart each agent to load the MCPs."
    echo "Test on any agent: ask \"use the sinapse_health tool\"."
fi
