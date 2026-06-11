#!/usr/bin/env bash
# =============================================================================
# Sinapse Agent — Script de Instalação Universal
# =============================================================================
# Detecta quais agentes estão instalados e configura cada um automaticamente.
# Uso: ./install.sh [--force] [--skip-agent <nome>] [--with-tests]
#
# O que este script faz:
#   1. Verifica dependências (Python 3.10+, uv/pipx, Node 18+, Bun, Ollama opcional)
#   2. Instala dependências Python (requirements.txt: API, Core/UMC, Watcher, Multimodal)
#   3. Instala Graphify (graphifyy[all]) e indexa o vault cerebro/ (Gemini→Ollama→AST)
#   4. Registra skills nos agentes detectados (Hermes, Claude, Codex, etc.)
#   5. Configura claude-mem, instala dependências, inicia worker (systemd)
#   6. Instala NeuralMemory (nmem) — busca associativa com spreading activation
#   7. Compila RTK do source (Rust) e instala plugin no Hermes
#   8. Configura MCP servers (graphify + claude-mem) para Hermes
#   9. Instala cron job de sync periódico (rebuild do graph.json a cada 6h)
#  10. Instala/atualiza plugin sinapse-memory (multi-backend: nmem + claude-mem + graphify)
#  11. Configura inteligência do Ciclo de Sonho (dream cycle)
#  12. Configura agentes externos (MCP: Claude Code, Codex, Kilo Code, etc.)
#
# Flags:
#   --force          Reinstala componentes mesmo se já existirem
#   --skip-agent=X   Pula configuração de um agente específico
#   --with-tests     Executa testes unitários após instalação
# =============================================================================

set -euo pipefail

# ── Cores ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'
BOLD='\033[1m'; NC='\033[0m'

# ── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
VAULT_DIR="$PROJECT_ROOT/cerebro"
GRAPHIFY_OUT="$VAULT_DIR/graphify-out"

# ── Flags ───────────────────────────────────────────────────────────────────
FORCE=false
SKIP_AGENTS=()
WITH_TESTS=false
NON_INTERACTIVE=false
PROVIDER=""
MODEL=""

for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
        --skip-agent=*) SKIP_AGENTS+=("${arg#*=}") ;;
        --with-tests) WITH_TESTS=true ;;
        --non-interactive) NON_INTERACTIVE=true ;;
        --provider=*) PROVIDER="${arg#*=}" ;;
        --model=*) MODEL="${arg#*=}" ;;
        *) echo -e "${RED}Erro:${NC} argumento desconhecido: $arg"; exit 1 ;;
    esac
done

# ── Banner ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║          Hive-Mind — Instalação Universal        ║${NC}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# =============================================================================
# 1. VERIFICAÇÃO DE DEPENDÊNCIAS
# =============================================================================
echo -e "${BOLD}[1/12] Verificando dependências...${NC}"

# Python
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Erro:${NC} python3 não encontrado. Instale Python 3.10+."
    exit 1
fi
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "  ${GREEN}✓${NC} Python $PYTHON_VERSION"

# Validar versão mínima (3.10+)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    echo -e "  ${RED}Erro:${NC} Python $PYTHON_VERSION é muito antigo. Necessário Python 3.10+."
    exit 1
fi

# uv (preferred) ou pipx
INSTALL_METHOD=""
if command -v uv &>/dev/null; then
    INSTALL_METHOD="uv"
    echo -e "  ${GREEN}✓${NC} uv $(uv --version 2>/dev/null | awk '{print $2}')"
elif command -v pipx &>/dev/null; then
    INSTALL_METHOD="pipx"
    echo -e "  ${GREEN}✓${NC} pipx detectado"
else
    echo -e "  ${YELLOW}⚠${NC}  uv/pipx não encontrados. Instalando uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    INSTALL_METHOD="uv"
    echo -e "  ${GREEN}✓${NC} uv instalado"
fi

# Node (para claude-mem)
NODE_OK=false
if command -v node &>/dev/null; then
    NODE_VERSION=$(node --version | sed 's/v//')
    echo -e "  ${GREEN}✓${NC} Node $NODE_VERSION"
    NODE_OK=true
else
    echo -e "  ${YELLOW}⚠${NC}  Node não encontrado. claude-mem será pulado."
fi

# Bun (para claude-mem dependências)
BUN_OK=false
if command -v bun &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Bun $(bun --version 2>/dev/null)"
    BUN_OK=true
else
    echo -e "  ${YELLOW}⚠${NC}  Bun não encontrado. Alguns recursos do claude-mem podem falhar."
fi

# Ollama (opcional, para extração semântica local)
OLLAMA_OK=false
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    OLLAMA_MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "import json,sys; print(len(json.load(sys.stdin)['models']))" 2>/dev/null || echo "?")
    echo -e "  ${GREEN}✓${NC} Ollama detectado ($OLLAMA_MODELS modelos)"
    OLLAMA_OK=true
else
    echo -e "  ${YELLOW}⊘${NC}  Ollama não detectado (opcional para extração semântica local). Instale: curl -fsSL https://ollama.com/install.sh | sh"
fi

echo ""

# =============================================================================
# 2. DEPENDÊNCIAS PYTHON (requirements.txt)
# =============================================================================
echo -e "${BOLD}[2/12] Instalando dependências Python (requirements.txt)...${NC}"

# Cobre todos os componentes: API REST (fastapi/uvicorn/slowapi/cryptography),
# Core/UMC (pydantic/pyyaml/numpy/sqlite-vec/fastembed), Watcher (watchdog)
# e Multimodal Fase 10 (mss/PyMuPDF/python-docx).
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    if [ "$INSTALL_METHOD" = "uv" ]; then
        uv pip install -r "$PROJECT_ROOT/requirements.txt" --quiet 2>/dev/null || \
        pip install --user -r "$PROJECT_ROOT/requirements.txt" --quiet 2>/dev/null || \
        pip install --break-system-packages -r "$PROJECT_ROOT/requirements.txt" --quiet 2>/dev/null || \
        pip install -r "$PROJECT_ROOT/requirements.txt" --quiet 2>/dev/null || true
    else
        pip install --user -r "$PROJECT_ROOT/requirements.txt" --quiet 2>/dev/null || \
        pip install --break-system-packages -r "$PROJECT_ROOT/requirements.txt" --quiet 2>/dev/null || \
        pip install -r "$PROJECT_ROOT/requirements.txt" --quiet 2>/dev/null || true
    fi
    # Sanity check: módulos críticos para API e UMC
    if python3 -c "import fastapi, yaml, pydantic" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Dependências Python instaladas (requirements.txt)"
    else
        echo -e "  ${YELLOW}⚠${NC}  Algumas dependências Python podem não ter sido instaladas. Rode manualmente: pip install -r requirements.txt"
    fi
else
    echo -e "  ${YELLOW}⚠${NC}  requirements.txt não encontrado em $PROJECT_ROOT — pulando."
fi

echo ""

# =============================================================================
# 3. INSTALAÇÃO DO GRAPHIFY (do source clonado, NÃO do PyPI)
# =============================================================================
echo -e "${BOLD}[3/12] Instalando Graphify (source local)...${NC}"

GRAPHIFY_SRC="$PROJECT_ROOT/graphify"

if [ ! -f "$GRAPHIFY_SRC/pyproject.toml" ]; then
    echo -e "  Clonando Graphify de github.com/safishamsi/graphify..."
    git clone --depth 1 https://github.com/safishamsi/graphify.git "$GRAPHIFY_SRC" 2>&1 | tail -1
fi

# Instalar do source em modo editável (pip install -e)
if $FORCE || ! python3 -c "import graphify" 2>/dev/null; then
    if [ "$INSTALL_METHOD" = "uv" ]; then
        uv pip install -e "$GRAPHIFY_SRC[all]" 2>/dev/null || \
        pip install -e "$GRAPHIFY_SRC[all]"
    else
        pip install -e "$GRAPHIFY_SRC[all]"
    fi
    # Garantir pyyaml (usado pelo plugin sinapse-memory)
    if [ "$INSTALL_METHOD" = "uv" ]; then
        python3 -c "import yaml" 2>/dev/null || uv pip install pyyaml --quiet 2>/dev/null || pip3 install pyyaml --quiet 2>/dev/null || pip install pyyaml --quiet 2>/dev/null || true
    else
        python3 -c "import yaml" 2>/dev/null || pip3 install pyyaml --quiet 2>/dev/null || pip install pyyaml --quiet 2>/dev/null || true
    fi
    echo -e "  ${GREEN}✓${NC} graphify instalado do source ($GRAPHIFY_SRC)"
else
    echo -e "  ${GREEN}✓${NC} graphify já instalado"
fi

# Dependências Python (requirements.txt) já instaladas na etapa 2.

# Indexar o vault com extração semântica se API key disponível, senão AST-only
echo -e "  Indexando vault cerebro/..."
if [ -n "${GOOGLE_API_KEY:-}" ] || [ -n "${GEMINI_API_KEY:-}" ]; then
    echo -e "  Usando Gemini para extração semântica..."
    graphify "$VAULT_DIR" 2>&1 | tail -3
elif [ "${SINAPSE_OLLAMA:-0}" = "1" ] && curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e "  Ollama detectado. Usando qwen2.5-coder:3b para extração semântica..."
    OLLAMA_MODEL=qwen2.5-coder:3b graphify "$VAULT_DIR" --backend ollama 2>&1 | tail -3
else
    echo -e "  Usando AST-only rápido (tree-sitter + Leiden clustering)..."
    graphify update "$VAULT_DIR" 2>&1 | tail -3
fi

if [ -f "$GRAPHIFY_OUT/graph.json" ]; then
    NODE_COUNT=$(python3 -c "import json; g=json.load(open('$GRAPHIFY_OUT/graph.json')); print(len(g.get('nodes',[])))" 2>/dev/null || echo "?")
    echo -e "  ${GREEN}✓${NC} Knowledge graph gerado ($NODE_COUNT nodes)"
else
    echo -e "  ${RED}✗${NC} Falha ao gerar graph.json"
    exit 1
fi

echo ""

# =============================================================================
# 4. REGISTRO NOS AGENTES DETECTADOS
# =============================================================================
echo -e "${BOLD}[4/12] Registrando skills nos agentes...${NC}"

# Array associativo: comando de detecção → plataforma graphify
# Alguns agentes não têm CLI detectável (Cursor, Copilot) — usamos caminho de arquivo
declare -A AGENT_DETECTORS=(
    # Comandos CLI detectáveis
    ["hermes"]="hermes"
    ["claude"]="claude"
    ["codex"]="codex"
    ["opencode"]="opencode"
    ["gemini"]="gemini"
    ["aider"]="aider"
)

# Agentes por arquivo de configuração (sem CLI detectável)
declare -A AGENT_CONFIG_FILES=(
    ["copilot"]="$HOME/.github-copilot/hosts.json"
    ["cursor"]="$HOME/.cursor/rules/"
    ["openclaw"]="$HOME/.claw/config.yaml"
    ["trae"]="$HOME/.trae/config.json"
    ["kiro"]="$HOME/.kiro/config.json"
    ["antigravity"]="$HOME/.antigravity/config.json"
)

echo -e "  Detectando agentes..."

# ── Agentes CLI ───────────────────────────────────────────────────────
for agent in "${!AGENT_DETECTORS[@]}"; do
    if [[ " ${SKIP_AGENTS[*]:-} " == *" $agent "* ]]; then
        continue
    fi
    if command -v "$agent" &>/dev/null; then
        platform="${AGENT_DETECTORS[$agent]}"
        echo -e "  ${GREEN}✓${NC} $agent → registrando skill..."
        graphify install --platform "$platform" 2>&1 | tail -1
    fi
done

# ── Agentes por arquivo de config ──────────────────────────────────────
for agent in "${!AGENT_CONFIG_FILES[@]}"; do
    if [[ " ${SKIP_AGENTS[*]:-} " == *" $agent "* ]]; then
        continue
    fi
    config_path="${AGENT_CONFIG_FILES[$agent]}"
    if [ -e "$config_path" ]; then
        echo -e "  ${GREEN}✓${NC} $agent (detectado via config)"
        case "$agent" in
            copilot)
                graphify install --platform copilot 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registrada" || echo -e "    ${YELLOW}⊘${NC} falha ao registrar"
                ;;
            cursor)
                graphify cursor install 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registrada" || echo -e "    ${YELLOW}⊘${NC} falha ao registrar"
                ;;
            openclaw)
                graphify install --platform claw 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registrada" || echo -e "    ${YELLOW}⊘${NC} falha ao registrar"
                ;;
            trae)
                graphify install --platform trae 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registrada" || echo -e "    ${YELLOW}⊘${NC} falha ao registrar"
                ;;
            kiro)
                graphify kiro install 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registrada" || echo -e "    ${YELLOW}⊘${NC} falha ao registrar"
                ;;
            antigravity)
                graphify antigravity install 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registrada" || echo -e "    ${YELLOW}⊘${NC} falha ao registrar"
                ;;
        esac
    fi
done
echo ""

# ── Configuração específica do Hermes ──────────────────────────────────
if command -v hermes &>/dev/null; then
    echo -e "  ${BOLD}Configurando Hermes...${NC}"
    if [ -d "$HOME/.hermes/skills/" ]; then
        cp "$PROJECT_ROOT/skills/sinapse-consulta.md" "$HOME/.hermes/skills/sinapse-consulta.md" 2>/dev/null && \
            echo -e "    ${GREEN}✓${NC} skill sinapse-consulta"
    fi
    if [ -d "$HOME/.hermes/plugins/" ]; then
        mkdir -p "$HOME/.hermes/plugins/sinapse-memory/"
        cp "$PROJECT_ROOT/plugins/hermes/sinapse-memory.py" "$HOME/.hermes/plugins/sinapse-memory/__init__.py" 2>/dev/null && \
            echo -e "    ${GREEN}✓${NC} plugin sinapse-memory"
    fi
fi

echo ""

# =============================================================================
# 5. CONFIGURAÇÃO DO CLAUDE-MEM (do source clonado)
# =============================================================================
echo -e "${BOLD}[5/12] Configurando claude-mem (source local)...${NC}"

if $NODE_OK; then
    CLAUDE_MEM_DIR="$PROJECT_ROOT/claude-mem"

    if [ ! -f "$CLAUDE_MEM_DIR/package.json" ]; then
        echo -e "  Clonando claude-mem de github.com/thedotmack/claude-mem..."
        git clone --depth 1 https://github.com/thedotmack/claude-mem.git "$CLAUDE_MEM_DIR" 2>&1 | tail -1
    fi

    # Compilar do source local
    cd "$CLAUDE_MEM_DIR"
    if [ ! -d "node_modules" ] || $FORCE; then
        echo -e "  Instalando dependências..."
        npm install --silent 2>/dev/null || {
            echo -e "  ${YELLOW}⚠${NC}  npm install falhou. Tentando com Bun..."
            if $BUN_OK; then
                bun install 2>/dev/null || echo -e "  ${RED}✗${NC} Instalação do claude-mem falhou"
            fi
        }
    fi
    npm run build 2>&1 | tail -1
    cd "$PROJECT_ROOT"
    echo -e "  ${GREEN}✓${NC} claude-mem compilado do source"

    # Iniciar worker como systemd user service
    if command -v systemctl &>/dev/null; then
        SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
        mkdir -p "$SYSTEMD_USER_DIR"
        cat > "$SYSTEMD_USER_DIR/sinapse-claude-mem.service" << SERVICE_EOF
[Unit]
Description=Sinapse Agent — claude-mem Worker
After=network.target

[Service]
Type=simple
Environment=CLAUDE_MEM_DATA_DIR=$PROJECT_ROOT/claude-mem/data
ExecStart=$HOME/.bun/bin/bun $PROJECT_ROOT/claude-mem/plugin/scripts/worker-service.cjs
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
SERVICE_EOF
        systemctl --user daemon-reload 2>/dev/null || true
        systemctl --user enable sinapse-claude-mem.service 2>/dev/null || true
        systemctl --user start sinapse-claude-mem.service 2>/dev/null || true
        echo -e "  ${GREEN}✓${NC} claude-mem worker (systemd user service)"
    fi

    # Copiar config MCP
    if command -v hermes &>/dev/null; then
        cp "$PROJECT_ROOT/mcp/claude-mem.json" "$HOME/.hermes/mcp/claude-mem.json" 2>/dev/null || true
    fi
else
    echo -e "  ${YELLOW}⊘${NC}  claude-mem pulado (Node não encontrado)"
fi

echo ""

# =============================================================================
# 6. INSTALAÇÃO DO NEURAL MEMORY (spreading activation — associativo, do source)
# =============================================================================
echo -e "${BOLD}[6/12] Instalando NeuralMemory (spreading activation, source local)...${NC}"

NEURAL_MEMORY_SRC="$PROJECT_ROOT/neural-memory"

if [ ! -f "$NEURAL_MEMORY_SRC/pyproject.toml" ]; then
    echo -e "  Clonando NeuralMemory de github.com/nhadaututtheky/neural-memory..."
    git clone --depth 1 https://github.com/nhadaututtheky/neural-memory.git "$NEURAL_MEMORY_SRC" 2>&1 | tail -1
fi

# Instalar do source em modo editável
if $FORCE || ! python3 -c "import neural_memory" 2>/dev/null; then
    if [ "$INSTALL_METHOD" = "uv" ]; then
        uv pip install -e "$NEURAL_MEMORY_SRC" 2>/dev/null || \
        pip install -e "$NEURAL_MEMORY_SRC" --break-system-packages
    else
        pip install -e "$NEURAL_MEMORY_SRC" --break-system-packages
    fi
    echo -e "  ${GREEN}✓${NC} NeuralMemory instalado do source ($NEURAL_MEMORY_SRC)"
else
    echo -e "  ${GREEN}✓${NC} NeuralMemory já instalado"
fi

# Verificar se o CLI está disponível
if command -v nmem &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} nmem $(nmem --version 2>/dev/null || echo 'OK')"
else
    echo -e "  ${YELLOW}⊘${NC}  nmem CLI não encontrado. Verifique PATH: ~/.local/bin"
fi

echo ""

# =============================================================================
# 7. CONFIGURAÇÃO DO RTK (do source clonado — Rust)
# =============================================================================
echo -e "${BOLD}[7/12] Compilando RTK (source local)...${NC}"

RTK_SRC="$PROJECT_ROOT/rtk"

if [ ! -f "$RTK_SRC/Cargo.toml" ]; then
    echo -e "  Clonando RTK de github.com/rtk-ai/rtk..."
    git clone --depth 1 https://github.com/rtk-ai/rtk.git "$RTK_SRC" 2>&1 | tail -1
fi

# Verificar Rust
if ! command -v cargo &>/dev/null; then
    echo -e "  Instalando Rust (rustup)..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y 2>&1 | tail -1
    export PATH="$HOME/.cargo/bin:$PATH"
    echo -e "  ${GREEN}✓${NC} Rust instalado"
fi

# Compilar do source
cd "$RTK_SRC"
if $FORCE || [ ! -f "target/release/rtk" ]; then
    echo -e "  Compilando RTK (cargo build --release)..."
    cargo build --release 2>&1 | tail -1
    echo -e "  ${GREEN}✓${NC} RTK compilado"
else
    echo -e "  ${GREEN}✓${NC} RTK já compilado"
fi

# Instalar binário
mkdir -p "$HOME/.local/bin"
cp "$RTK_SRC/target/release/rtk" "$HOME/.local/bin/rtk" 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} RTK $(./target/release/rtk --version 2>/dev/null | awk '{print $2}') instalado"

# Plugin Hermes — hook nativo do RTK
if [ -d "$HOME/.hermes/plugins/" ]; then
    mkdir -p "$HOME/.hermes/plugins/rtk-rewrite/"
    cp "$RTK_SRC/hooks/hermes/rtk-rewrite/"* "$HOME/.hermes/plugins/rtk-rewrite/" 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} Plugin RTK (hook nativo) copiado para Hermes"
fi

cd "$PROJECT_ROOT"

echo ""

# =============================================================================
# 8. CONFIGURAÇÃO MCP (GRAPHIFY + CLAUDE-MEM)
# =============================================================================
echo -e "${BOLD}[8/12] Configurando servidores MCP...${NC}"

# Graphify MCP
if command -v hermes &>/dev/null; then
    MCP_DIR="$HOME/.hermes/mcp"
    mkdir -p "$MCP_DIR"

    # graphify MCP config
    cat > "$MCP_DIR/graphify.json" << 'MCPEOF'
{
    "mcpServers": {
        "graphify": {
            "command": "PROJECT_ROOT_PLACEHOLDER/scripts/serve-graph.sh",
            "cwd": "PROJECT_ROOT_PLACEHOLDER",
            "transport": "stdio",
            "enabled": true,
            "description": "Sinapse Agent — Knowledge Graph (Graphify)"
        }
    }
}
MCPEOF
    # Substituir placeholder pelo path real
    sed -i "s|PROJECT_ROOT_PLACEHOLDER|$PROJECT_ROOT|g" "$MCP_DIR/graphify.json"

    # claude-mem MCP config
    cat > "$MCP_DIR/claude-mem.json" << 'MCPEOF'
{
    "mcpServers": {
        "claude-mem": {
            "command": "PROJECT_ROOT_PLACEHOLDER/scripts/start-claude-mem.sh",
            "transport": "stdio",
            "enabled": true,
            "description": "Sinapse Agent — Event Tracking (claude-mem)"
        }
    }
}
MCPEOF
    sed -i "s|PROJECT_ROOT_PLACEHOLDER|$PROJECT_ROOT|g" "$MCP_DIR/claude-mem.json"

    echo -e "  ${GREEN}✓${NC} MCP configs gerados em $MCP_DIR"
else
    echo -e "  ${YELLOW}⊘${NC}  Hermes não detectado, MCP configs pulados"
fi

echo ""

# =============================================================================
# 9. CRON DE SYNC PERIÓDICO
# =============================================================================
echo -e "${BOLD}[9/12] Configurando cron de sync...${NC}"

CRON_JOB="0 */6 * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && ./scripts/build-graph.sh >> logs/sync.log 2>&1"

if command -v crontab &>/dev/null; then
    # Verificar se já existe
    if crontab -l 2>/dev/null | grep -q "sinapse_agent"; then
        echo -e "  ${GREEN}✓${NC} Cron já configurado"
    else
        (crontab -l 2>/dev/null || true; echo "# sinapse_agent — sync vault → graph a cada 6h"; echo "$CRON_JOB") | crontab -
        echo -e "  ${GREEN}✓${NC} Cron configurado (a cada 6h)"
    fi
else
    echo -e "  ${YELLOW}⊘${NC}  crontab não disponível. Use ./scripts/build-graph.sh manualmente."
fi

echo ""

# =============================================================================
# 10. PLUGIN SINAPSE-MEMORY (HERMES)
# =============================================================================
echo -e "${BOLD}[10/12] Instalando plugin sinapse-memory...${NC}"

if command -v hermes &>/dev/null && [ -d "$HOME/.hermes/plugins/" ]; then
    PLUGIN_DIR="$HOME/.hermes/plugins/sinapse-memory"
    mkdir -p "$PLUGIN_DIR"

    # Copia plugin do projeto
    if [ -f "$PROJECT_ROOT/plugins/hermes/sinapse-memory.py" ]; then
        cp "$PROJECT_ROOT/plugins/hermes/sinapse-memory.py" "$PLUGIN_DIR/__init__.py"
    fi

    # plugin.yaml
    cat > "$PLUGIN_DIR/plugin.yaml" << 'PLUGINEOF'
name: sinapse-memory
description: >
  Integração bidirecional Hermes ↔ Obsidian vault via Sinapse Agent.
  Busca multi-backend: claude-mem (semântica Chroma + FTS5) → Graphify (estrutural Leiden).
  Escrita de decisões e aprendizados no vault com frontmatter YAML + WikiLinks.
author: Sinapse Agent
hooks:
  - pre_gateway_dispatch
  - post_tool_call
  - on_session_end
provides_hooks:
  - pre_gateway_dispatch
  - post_tool_call
  - on_session_end
config:
  backends:
    claude_mem:
      enabled: true
      url: "http://127.0.0.1:37700"
      timeout: 3
    graphify:
      enabled: true
      graph_json: "$PROJECT_ROOT/cerebro/graphify-out/graph.json"
  limits:
    max_context_chars: 3000
    max_nodes: 5
    max_observations: 5
  vault:
    root: "$PROJECT_ROOT/cerebro"
    decisions: "work/active"
    learnings: "brain"
    memory: "brain"
    projects: "work/active"
PLUGINEOF

    echo -e "  ${GREEN}✓${NC} plugin sinapse-memory (multi-backend)"
else
    echo -e "  ${YELLOW}⊘${NC}  Hermes não detectado"
fi

echo ""

# ── CONFIGURAÇÃO DE INTELIGÊNCIA (Ciclo de Sonho) ───────────────────────────
echo -e "${BOLD}[11/12] Configurando inteligência do Ciclo de Sonho...${NC}"
if [ -n "$PROVIDER" ] && [ -n "$MODEL" ]; then
    echo -e "  Salvando provedor ($PROVIDER) e modelo ($MODEL) no .env..."
    # Garante que o .env existe
    [ -f "$PROJECT_ROOT/.env" ] || cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    # Salva no .env usando python
    python3 -c "import sys; sys.path.append('$PROJECT_ROOT'); from core.auth import save_env; save_env('HIVE_DREAMER_PROVIDER', '$PROVIDER'); save_env('HIVE_DREAMER_MODEL', '$MODEL')"
    echo -e "  ${GREEN}✓${NC} Provedor e modelo salvos."
else
    echo -e "  Nenhum provedor/modelo de IA fornecido via argumentos."
    echo -e "  A configuração poderá ser realizada ao final da instalação ou posteriormente."
fi
echo ""

# 12. CONFIGURAÇÃO DE AGENTES EXTERNOS (via MCP + templates)
# =============================================================================
echo -e "${BOLD}[12/12] Configurando agentes externos (MCP + CLI)...${NC}"

# Garantir permissões de execução em todos os scripts e hooks
chmod +x "$PROJECT_ROOT/scripts/"*.sh 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/"*.py 2>/dev/null || true
chmod +x "$PROJECT_ROOT/cerebro/.claude/scripts/"*.py 2>/dev/null || true

# Registro MCP delegado ao script standalone (idempotente, merge seguro).
# Pode ser re-executado a qualquer momento: ./scripts/register-mcp.sh
if ! PROJECT_ROOT="$PROJECT_ROOT" bash "$PROJECT_ROOT/scripts/register-mcp.sh"; then
    echo -e "  ${YELLOW}⊘${NC} Nenhum agente externo detectado. Use scripts/sinapse-write.py via CLI."
fi

# Template AGENTS.md no vault (Codex)
if command -v codex &>/dev/null && [ -f "$PROJECT_ROOT/cerebro/.codex/AGENTS.md" ]; then
    cp "$PROJECT_ROOT/cerebro/.codex/AGENTS.md" "$VAULT_DIR/.codex/AGENTS.md" 2>/dev/null || true
fi

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}Verificando integridade...${NC}"
if python3 "$PROJECT_ROOT/scripts/sinapse-write.py" health >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Health check: backends operacionais"
else
    echo -e "  ${YELLOW}⊘${NC}  Health check: alguns backends offline"
    echo -e "  Execute: python3 scripts/sinapse-write.py health"
fi
echo ""

if $WITH_TESTS; then
    echo -e "${BOLD}Executando testes da suíte completa...${NC}"
    if ./tests/run_all.sh; then
        echo -e "  ${GREEN}✓${NC} Todos os testes passaram com sucesso!"
    else
        echo -e "  ${RED}✗${NC} Alguns testes falharam!"
        exit 1
    fi
    echo ""
fi
echo -e "${BOLD}${GREEN}║       Sinapse Agent instalado com sucesso!          ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Vault Obsidian:  ${BOLD}$VAULT_DIR${NC}"
echo -e "  Knowledge Graph: ${BOLD}$GRAPHIFY_OUT/graph.json${NC}"
echo -e "  MCP Servers:     ${BOLD}$HOME/.hermes/mcp/${NC}"
echo ""
echo -e "  Abra a pasta ${BOLD}cerebro/${NC} no Obsidian como um vault."
echo -e "  Todo arquivo criado/editado será indexado automaticamente."
echo ""
echo -e "  ${YELLOW}Reinicie seus agentes para aplicar as mudanças.${NC}"
echo ""

# ── Notas pós-instalação ───────────────────────────────────────────────
echo -e "${BOLD}${BLUE}Notas pós-instalação:${NC}"
echo ""
echo -e "  ${BOLD}Obsidian:${NC} Abra a pasta cerebro/ como vault no Obsidian."
echo -e "         Flatpak: flatpak run md.obsidian.Obsidian --vault \"$VAULT_DIR\""
echo -e "         Em Configurações > Arquivos e links, ative 'Mostrar arquivos ocultos'."
echo ""
echo -e "  ${BOLD}Ollama (modelos recomendados):${NC}"
echo -e "         ollama pull qwen2.5-coder:3b    # Extração semântica local (rápido)"
echo -e "         ollama pull bge-m3               # Embeddings de alta qualidade"
echo -e "         ollama pull nomic-embed-text     # Embeddings leve"
echo ""
echo -e "  ${BOLD}Disaster Recovery:${NC}"
echo -e "         ${BOLD}./scripts/recover.sh${NC} — Verifica/Rebuilda graph.json, reinicia worker, health check"
echo ""
echo -e "  ${BOLD}API Keys (opcional):${NC}"
echo -e "         Copie .env.example para .env e configure GOOGLE_API_KEY."
echo -e "         Gemini é usado para extração semântica de alta qualidade."
echo ""
if $OLLAMA_OK; then
    echo -e "  ${BOLD}Modelos Ollama instalados:${NC}"
    curl -s http://localhost:11434/api/tags 2>/dev/null | python3 -c "
import json, sys
for m in json.load(sys.stdin)['models']:
    print(f'         {m[\"name\"]:35s} {m[\"size\"]/1e9:.1f}GB')
"
fi
echo ""

# ── Configuração Interativa Pós-Instalação (Opcional) ───────────────────────
HAS_DREAMER=false
if [ -f "$PROJECT_ROOT/.env" ]; then
    # Verifica se HIVE_DREAMER_PROVIDER está preenchido e não vazio
    if grep -q "^HIVE_DREAMER_PROVIDER=" "$PROJECT_ROOT/.env" && [ -n "$(grep "^HIVE_DREAMER_PROVIDER=" "$PROJECT_ROOT/.env" | cut -d= -f2-)" ]; then
        HAS_DREAMER=true
    fi
fi

if [ "$HAS_DREAMER" = "false" ] && [ "$NON_INTERACTIVE" = "false" ] && [ -t 0 ]; then
    echo -e "${BOLD}${YELLOW}Configuração do Dreamer (Inteligência do Ciclo de Sonho):${NC}"
    echo -e "  O Ciclo de Sonho consolida e destila seus aprendizados de forma autônoma."
    echo -e "  Para funcionar, ele precisa de um modelo de linguagem (Gemini, OpenAI, Ollama, etc.) configurado."
    echo ""
    read -p "  Deseja configurar o seu modelo e chaves de IA interativamente agora? [S/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[SsYy]$ ]] || [ -z "$REPLY" ]; then
        "$PROJECT_ROOT/scripts/setup-dreamer.sh"
    else
        echo -e "  Você pode realizar essa configuração mais tarde rodando: ${BOLD}./scripts/setup-dreamer.sh${NC}"
        echo ""
    fi
fi

