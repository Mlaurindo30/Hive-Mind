#!/usr/bin/env bash
# =============================================================================
# Sinapse Agent — Script de Instalação Universal
# =============================================================================
# Detecta quais agentes estão instalados e configura cada um automaticamente.
# Uso: ./install.sh [--force] [--skip-agent <nome>]
#
# O que este script faz:
#   1. Verifica dependências (Python 3.10+, uv/pipx, Node 18+, Bun, Ollama opcional)
#   2. Instala Graphify (graphifyy[all]) e indexa o vault cerebro/ (Gemini→Ollama→AST)
#   3. Configura claude-mem, instala dependências, inicia worker (systemd)
#   4. Instala NeuralMemory (nmem) — busca associativa com spreading activation
#   5. Configura RTK plugin no Hermes (se detectado)
#   6. Registra skills em cada agente detectado (Hermes, Claude, Codex, etc.)
#   7. Configura MCP servers (graphify + claude-mem)
#   8. Instala cron job de sync periódico
#   9. Instala/atualiza plugin sinapse-memory (multi-backend: nmem + claude-mem + graphify)
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

for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
        --skip-agent=*) SKIP_AGENTS+=("${arg#*=}") ;;
        *) echo -e "${RED}Erro:${NC} argumento desconhecido: $arg"; exit 1 ;;
    esac
done

# ── Banner ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║          Sinapse Agent — Instalação Universal        ║${NC}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# =============================================================================
# 1. VERIFICAÇÃO DE DEPENDÊNCIAS
# =============================================================================
echo -e "${BOLD}[1/9] Verificando dependências...${NC}"

# Python
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Erro:${NC} python3 não encontrado. Instale Python 3.10+."
    exit 1
fi
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "  ${GREEN}✓${NC} Python $PYTHON_VERSION"

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
# 2. INSTALAÇÃO DO GRAPHIFY (do source clonado, NÃO do PyPI)
# =============================================================================
echo -e "${BOLD}[2/9] Instalando Graphify (source local)...${NC}"

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
    echo -e "  ${GREEN}✓${NC} graphify instalado do source ($GRAPHIFY_SRC)"
else
    echo -e "  ${GREEN}✓${NC} graphify já instalado"
fi

# Indexar o vault com extração semântica se API key disponível, senão AST-only
echo -e "  Indexando vault cerebro/..."
if [ -n "${GOOGLE_API_KEY:-}" ] || [ -n "${GEMINI_API_KEY:-}" ]; then
    echo -e "  Usando Gemini para extração semântica..."
    graphify "$VAULT_DIR" 2>&1 | tail -3
elif curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e "  Ollama detectado. Usando qwen2.5-coder:3b para extração semântica..."
    OLLAMA_MODEL=qwen2.5-coder:3b graphify "$VAULT_DIR" --backend ollama 2>&1 | tail -3
else
    echo -e "  Sem API key ou Ollama. Usando AST-only (tree-sitter + Leiden clustering)..."
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
# 3. REGISTRO NOS AGENTES DETECTADOS
# =============================================================================
echo -e "${BOLD}[3/9] Registrando skills nos agentes...${NC}"

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
# 4. CONFIGURAÇÃO DO CLAUDE-MEM (do source clonado)
# =============================================================================
echo -e "${BOLD}[4/9] Configurando claude-mem (source local)...${NC}"

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
# 5. INSTALAÇÃO DO NEURALMEMORY (spreading activation — associativo)
# =============================================================================
echo -e "${BOLD}[5/9] Instalando NeuralMemory (spreading activation)...${NC}"

if command -v pipx &>/dev/null; then
    if ! command -v nmem &>/dev/null || $FORCE; then
        echo -e "  Instalando neural-memory via pipx..."
        pipx install neural-memory 2>&1 | tail -1
    fi
    echo -e "  ${GREEN}✓${NC} NeuralMemory $(nmem --version 2>/dev/null || echo 'OK')"
else
    echo -e "  ${YELLOW}⊘${NC}  pipx não encontrado. Instale: sudo apt install pipx && pipx ensurepath"
fi

echo ""

# =============================================================================
# 6. CONFIGURAÇÃO DO RTK (do source clonado — Rust)
# =============================================================================
echo -e "${BOLD}[6/9] Compilando RTK (source local)...${NC}"

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
# 6. CONFIGURAÇÃO MCP (GRAPHIFY + CLAUDE-MEM)
# =============================================================================
echo -e "${BOLD}[7/9] Configurando servidores MCP...${NC}"

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
# 7. CRON DE SYNC PERIÓDICO
# =============================================================================
echo -e "${BOLD}[8/9] Configurando cron de sync...${NC}"

CRON_JOB="0 */6 * * * cd $PROJECT_ROOT && ./scripts/build-graph.sh >> logs/sync.log 2>&1"

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
# 8. PLUGIN SINAPSE-MEMORY (HERMES)
# =============================================================================
echo -e "${BOLD}[9/9] Instalando plugin sinapse-memory...${NC}"

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
version: "2.0.0"
description: >
  Integração bidirecional Hermes ↔ Obsidian vault via Sinapse Agent.
  Busca multi-backend: claude-mem (semântica Chroma + FTS5) → Graphify (estrutural Leiden).
  Escrita de decisões e aprendizados no vault com frontmatter YAML + WikiLinks.
author: Sinapse Agent
hooks:
  - pre_prompt_build
  - post_tool_use
  - post_session_end
provides_hooks:
  - pre_prompt_build
  - post_tool_use
  - post_session_end
config:
  backends:
    claude_mem:
      enabled: true
      url: "http://127.0.0.1:37700"
      timeout: 3
    graphify:
      enabled: true
      graph_json: "~/Documentos/Projects/sinapse_agent/cerebro/graphify-out/graph.json"
  limits:
    max_context_chars: 3000
    max_nodes: 5
    max_observations: 5
  vault:
    root: "~/Documentos/Projects/sinapse_agent/cerebro"
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
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
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
