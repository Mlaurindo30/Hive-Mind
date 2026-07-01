#!/usr/bin/env bash
# =============================================================================
# Sinapse Agent — Script de Instalação Universal
# =============================================================================
# Detecta quais agentes estão instalados e configura cada um automaticamente.
# Uso: ./install.sh [--force] [--skip-agent <nome>] [--with-tests]
#
# O que este script faz:
#   1. Verifica dependências (uv, Node 18+, Bun, Ollama opcional)
#   2. Sincroniza o ambiente Python local e reproduzível (.venv + uv.lock)
#   3. Instala Graphify (graphifyy[all]) e indexa o vault cerebro/ (Gemini→Ollama→AST)
#   4. Registra skills nos agentes detectados (Hermes, Claude, Codex, etc.)
#   5. Instala claude-mem via npx nativo, com dados globais em ~/.claude-mem
#   6. Instala NeuralMemory (nmem) — busca associativa com spreading activation
#   7. Compila RTK do source (Rust) e instala plugin no Hermes
#   8. Configura MCP servers (graphify + claude-mem) para Hermes
#   9. Instala cron job de sync periódico (rebuild do graph.json a cada 6h)
#  10. Instala/atualiza plugin sinapse-memory (multi-backend: nmem + claude-mem + graphify)
#  11. Configura inteligência do Ciclo de Sonho (dream cycle)
#  12. Configura agentes externos (MCP: Claude Code, Codex, Kilo Code, etc.)
#
# Flags:
#   --force              Reinstala componentes mesmo se ja existirem
#   --skip-agent=X       Pula configuracao de um agente especifico
#   --with-tests         Executa testes unitarios apos instalacao
#   --with-real-tests    Encadeia a suite real de conhecimento (K9) no fim
#   --profile=<perfil>   Perfil de servicos: local-min (padrao) ou local-full
#   --provider=X         Provider do Dreamer (gemini|openai|ollama|...)
#   --model=X            Modelo do Dreamer
#   --non-interactive    Pula prompts interativos (CI/maquina zerada)
# =============================================================================

set -euo pipefail

# ── Cores ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'
BOLD='\033[1m'; NC='\033[0m'

# ── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
VAULT_DIR="$PROJECT_ROOT/cerebro"
GRAPHIFY_OUT="$VAULT_DIR/cortex/occipital/grafo"
TOOLS_DIR="$PROJECT_ROOT/.tools/bin"
export SINAPSE_HOME="$PROJECT_ROOT"
export GRAPHIFY_OUT

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
        --profile=*) INSTALL_PROFILE="${arg#*=}" ;;
        --with-real-tests) WITH_REAL_TESTS=true ;;
        *) echo -e "${RED}Erro:${NC} argumento desconhecido: $arg"; exit 1 ;;
    esac
done

# Defaults de K10 (docs/12 §K10). --profile escolhe até onde o instalador
# vai em "maquina zerada"; --with-real-tests encadeia a suite real no fim.
INSTALL_PROFILE="${INSTALL_PROFILE:-local-min}"
WITH_REAL_TESTS="${WITH_REAL_TESTS:-false}"
case "$INSTALL_PROFILE" in
    local-min|local-full) ;;
    *) echo -e "${RED}Erro:${NC} --profile invalido: $INSTALL_PROFILE (use local-min|local-full)"; exit 1 ;;
esac

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

# uv é a única ferramenta de instalação Python aceita. O Python do sistema
# não participa do runtime e nenhum fallback global é permitido.
if command -v uv &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} uv $(uv --version 2>/dev/null | awk '{print $2}')"
else
    echo -e "${RED}Erro:${NC} uv não encontrado. Instale uv antes de executar este instalador."
    exit 1
fi
uv python install 3.12
BOOTSTRAP_PYTHON="$(uv python find 3.12)"

# Produção exige .env local e HIVE_MIND_API_KEY para a REST API fail-closed.
# O instalador cria um token local se o operador ainda não preencheu, sem
# commitar segredo e sem sobrescrever valor existente.
if [ -f "$PROJECT_ROOT/.env.example" ]; then
    [ -f "$PROJECT_ROOT/.env" ] || cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    "$BOOTSTRAP_PYTHON" - "$PROJECT_ROOT/.env" <<'PY'
import secrets
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
lines = env_path.read_text(encoding="utf-8").splitlines()
found = False
changed = False
for idx, line in enumerate(lines):
    if line.startswith("HIVE_MIND_API_KEY="):
        found = True
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
        if not key:
            lines[idx] = "HIVE_MIND_API_KEY=" + secrets.token_urlsafe(32)
            changed = True
        break
if not found:
    lines.append("HIVE_MIND_API_KEY=" + secrets.token_urlsafe(32))
    changed = True
if changed:
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  OK: HIVE_MIND_API_KEY gerado em .env local")
else:
    print("  OK: HIVE_MIND_API_KEY ja existe em .env local")
PY
fi

# Node 18+ é requisito do runtime completo e dos smoke tests.
if command -v node &>/dev/null; then
    NODE_VERSION=$(node --version | sed 's/v//')
    NODE_MAJOR="${NODE_VERSION%%.*}"
    if [ "$NODE_MAJOR" -lt 18 ]; then
        echo -e "${RED}Erro:${NC} Node 18+ é obrigatório (encontrado: $NODE_VERSION)."
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Node $NODE_VERSION"
else
    echo -e "${RED}Erro:${NC} Node 18+ é obrigatório para o claude-mem."
    exit 1
fi

# Bun é copiado para .tools/bin (runtime gerenciado pelo projeto, scripts auxiliares).
if command -v bun &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Bun $(bun --version 2>/dev/null)"
    mkdir -p "$TOOLS_DIR"
    BUN_SOURCE="$(command -v bun)"
    if [ "$BUN_SOURCE" != "$TOOLS_DIR/bun" ]; then
        BUN_TMP="$TOOLS_DIR/bun.$$"
        cp "$BUN_SOURCE" "$BUN_TMP"
        chmod 0755 "$BUN_TMP"
        mv -f "$BUN_TMP" "$TOOLS_DIR/bun"
    fi
    BUN_BIN="$TOOLS_DIR/bun"
else
    echo -e "${RED}Erro:${NC} Bun é obrigatório para o runtime gerenciado do claude-mem."
    exit 1
fi

# Ollama (opcional, para extração semântica local)
OLLAMA_OK=false
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    OLLAMA_MODELS=$(curl -s http://localhost:11434/api/tags | "$BOOTSTRAP_PYTHON" -c "import json,sys; print(len(json.load(sys.stdin)['models']))" 2>/dev/null || echo "?")
    OLLAMA_VERSION=$(curl -s http://localhost:11434/api/version | "$BOOTSTRAP_PYTHON" -c "import json,sys; print(json.load(sys.stdin).get('version','0.0.0'))" 2>/dev/null || echo "0.0.0")
    echo -e "  ${GREEN}✓${NC} Ollama detectado ($OLLAMA_MODELS modelos, v$OLLAMA_VERSION)"
    OLLAMA_OK=true
else
    echo -e "  ${YELLOW}⊘${NC}  Ollama não detectado (opcional para extração semântica local). Instale: curl -fsSL https://ollama.com/install.sh | sh"
fi

# Baixa os modelos locais que o Hive-Mind precisa (idempotente: pula os já presentes).
# - snowflake-arctic-embed2 embeddings 1024d (core/database.py, LightRAG, Graphiti)
# - qwen2.5:3b        extração de entidades Graphiti + LightRAG (default novo)
# - qwen2.5-coder:3b      extração semântica do Graphify
# - minicpm-v4.6:latest   visão local compacta para Deep Portal e testes vision
# Opcional (gate SINAPSE_PULL_QWEN7B=1): qwen2.5:7b para o Graphiti local de
# alta qualidade (HIVE_GRAPHITI_MODEL=qwen2.5:7b). ~4.7GB, exige folga de VRAM.
# Opcional (local-full): gemma3:4b como fallback de visão/raciocínio visual.
# Opcional (SINAPSE_PULL_DEEPSEEK_OCR=1 ou HIVE_OCR_MODEL=deepseek-ocr:latest):
# deepseek-ocr:latest para OCR dedicado.
# Nota: MiniCPM-V 4.6 exige Ollama >= 0.30; em versões anteriores o instalador
# baixa gemma3:4b como fallback funcional para não deixar o papel vision quebrado.
if $OLLAMA_OK; then
    version_ge() {
        [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
    }

    ollama_pull_if_missing() {
        local model="$1"; local note="$2"
        if curl -s http://localhost:11434/api/tags 2>/dev/null | grep -q "\"$model\""; then
            echo -e "  ${GREEN}✓${NC} $model já presente ${note:+($note)}"
            return 0
        else
            echo -e "  ${BLUE}↓${NC} baixando $model ${note:+($note)}..."
            if ollama pull "$model" 2>&1 | tail -1; then
                return 0
            fi
            echo -e "  ${YELLOW}⊘${NC} falha ao baixar $model (siga manualmente: ollama pull $model)"
            return 1
        fi
    }
    echo -e "  ${BOLD}Modelos locais do Hive-Mind:${NC}"
    ollama_pull_if_missing "snowflake-arctic-embed2" "embeddings 1024d" || true
    ollama_pull_if_missing "qwen2.5:3b"       "extração Graphiti/LightRAG" || true
    ollama_pull_if_missing "qwen2.5-coder:3b" "extração Graphify" || true
    if version_ge "$OLLAMA_VERSION" "0.30.0"; then
        VISION_PRIMARY="minicpm-v4.6:latest"
    else
        VISION_PRIMARY="gemma3:4b"
        echo -e "  ${YELLOW}⊘${NC}  minicpm-v4.6 exige Ollama >=0.30 (atual: $OLLAMA_VERSION); usando gemma3:4b como visão local"
    fi
    if ! ollama_pull_if_missing "$VISION_PRIMARY" "visão local"; then
        echo -e "  ${YELLOW}⊘${NC}  $VISION_PRIMARY indisponível; baixando gemma3:4b como fallback funcional"
        ollama_pull_if_missing "gemma3:4b" "fallback visão/raciocínio visual" || true
    fi
    if [ "$INSTALL_PROFILE" = "local-full" ]; then
        ollama_pull_if_missing "gemma3:4b" "fallback visão/raciocínio visual" || true
    else
        echo -e "  ${YELLOW}⊘${NC}  gemma3:4b pulado (local-full). Para fallback de visão: ./install.sh --profile=local-full"
    fi
    if [ "${SINAPSE_PULL_DEEPSEEK_OCR:-0}" = "1" ] || [ "${HIVE_OCR_MODEL:-}" = "deepseek-ocr:latest" ]; then
        ollama_pull_if_missing "deepseek-ocr:latest" "OCR dedicado opcional" || true
    else
        echo -e "  ${YELLOW}⊘${NC}  deepseek-ocr:latest pulado (opcional). Para OCR dedicado: SINAPSE_PULL_DEEPSEEK_OCR=1 ./install.sh"
    fi
    if [ "${SINAPSE_PULL_QWEN7B:-0}" = "1" ] || [ "${HIVE_GRAPHITI_MODEL:-}" = "qwen2.5:7b" ]; then
        ollama_pull_if_missing "qwen2.5:7b"   "Graphiti local alta qualidade" || true
    else
        echo -e "  ${YELLOW}⊘${NC}  qwen2.5:7b pulado (opcional). Para o Graphiti local de alta qualidade: SINAPSE_PULL_QWEN7B=1 ./install.sh"
    fi
fi

echo ""

# Os componentes editáveis precisam existir antes do uv sync. O manifesto fixa
# commits exatos e preserva checkouts locais já modificados.
"$BOOTSTRAP_PYTHON" "$PROJECT_ROOT/scripts/setup/components.py" bootstrap

# =============================================================================
# 2. AMBIENTE PYTHON LOCAL
# =============================================================================
echo -e "${BOLD}[2/12] Sincronizando ambiente Python local (.venv)...${NC}"
uv sync --frozen --all-groups
PYTHON="$PROJECT_ROOT/.venv/bin/python"
GRAPHIFY="$PROJECT_ROOT/.venv/bin/graphify"
NMEM="$PROJECT_ROOT/.venv/bin/nmem"
export PATH="$PROJECT_ROOT/.venv/bin:$PROJECT_ROOT/integrations/rtk/target/release:$PATH"
"$PYTHON" -c "import fastapi, yaml, pydantic, graphify, neural_memory, sqlite_vec, pymilvus, llama_index, ragflow_sdk"
"$PYTHON" "$PROJECT_ROOT/scripts/setup/verify_wrappers.py"
mkdir -p "$PROJECT_ROOT/integrations/neural-memory/data"
"$PYTHON" "$PROJECT_ROOT/scripts/setup/setup_umc.py" >/dev/null
echo -e "  ${GREEN}✓${NC} Python $("$PYTHON" -c 'import sys; print(sys.version.split()[0])') em $PROJECT_ROOT/.venv"

echo ""

# =============================================================================
# 3. INSTALAÇÃO DO GRAPHIFY (do source clonado, NÃO do PyPI)
# =============================================================================
echo -e "${BOLD}[3/12] Instalando Graphify (source local)...${NC}"

GRAPHIFY_SRC="$PROJECT_ROOT/integrations/graphify"

echo -e "  ${GREEN}✓${NC} graphify resolvido do source local ($GRAPHIFY_SRC)"

# Dependências Python (requirements.txt) já instaladas na etapa 2.

# Indexar o vault com extração semântica se API key disponível, senão AST-only
echo -e "  Indexando vault cerebro/..."
if [ -n "${GOOGLE_API_KEY:-}" ] || [ -n "${GEMINI_API_KEY:-}" ]; then
    echo -e "  Usando Gemini para extração semântica..."
    "$GRAPHIFY" "$VAULT_DIR" 2>&1 | tail -3
elif [ "${SINAPSE_OLLAMA:-0}" = "1" ] && curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e "  Ollama detectado. Usando qwen2.5-coder:3b para extração semântica..."
    OLLAMA_MODEL=qwen2.5-coder:3b "$GRAPHIFY" "$VAULT_DIR" --backend ollama 2>&1 | tail -3
else
    echo -e "  Usando AST-only rápido (tree-sitter + Leiden clustering)..."
    "$GRAPHIFY" update "$VAULT_DIR" 2>&1 | tail -3
fi

if [ -f "$GRAPHIFY_OUT/graph.json" ]; then
    NODE_COUNT=$("$PYTHON" -c "import json; g=json.load(open('$GRAPHIFY_OUT/graph.json')); print(len(g.get('nodes',[])))" 2>/dev/null || echo "?")
    echo -e "  ${GREEN}✓${NC} Knowledge graph gerado ($NODE_COUNT nodes)"
else
    echo -e "  ${RED}✗${NC} Falha ao gerar graph.json"
    exit 1
fi
"$PYTHON" "$PROJECT_ROOT/scripts/graph/build_hnsw.py"

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
        cp "$PROJECT_ROOT/docs/skills/sinapse-consulta.md" "$HOME/.hermes/skills/sinapse-consulta.md" 2>/dev/null && \
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
# 5. INSTALAÇÃO DO CLAUDE-MEM (npx nativo, dados globais)
# =============================================================================
echo -e "${BOLD}[5/12] Instalando claude-mem (npx nativo, dados globais)...${NC}"

# O claude-mem usa a instalação nativa (npx/marketplace) para manter hooks e
# worker compatíveis com upstream. O runtime temporal oficial é global e
# multi-projeto, com dados em ~/.claude-mem.

CLAUDE_MEM_VERSION="13.6"
CLAUDE_MEM_NPX="npx -y claude-mem@${CLAUDE_MEM_VERSION}"
CLAUDE_MEM_DATA_DIR="$HOME/.claude-mem"
CLAUDE_MEM_DB="$CLAUDE_MEM_DATA_DIR/claude-mem.db"
CLAUDE_MEM_MODELS="$CLAUDE_MEM_DATA_DIR/models"
mkdir -p "$CLAUDE_MEM_DATA_DIR" "$CLAUDE_MEM_MODELS"

# Detecta IDEs instaladas (mesmos critérios do detectInstalledIDEs do claude-mem)
# e roda o install nativo para CADA uma. Ids nativos: claude-code, gemini-cli,
# codex-cli, cursor, windsurf, opencode, openclaw, goose.
INSTALLED_IDES=()
command -v claude &>/dev/null                                  && INSTALLED_IDES+=("claude-code")
[ -d "$HOME/.gemini" ]                                         && INSTALLED_IDES+=("gemini-cli")
[ -d "$HOME/.codex" ]                                          && INSTALLED_IDES+=("codex-cli")
[ -d "$HOME/.cursor" ]                                         && INSTALLED_IDES+=("cursor")
[ -d "$HOME/.codeium/windsurf" ]                              && INSTALLED_IDES+=("windsurf")
{ command -v opencode &>/dev/null || [ -d "$HOME/.config/opencode" ]; } && INSTALLED_IDES+=("opencode")
[ -d "$HOME/.openclaw" ]                                       && INSTALLED_IDES+=("openclaw")
[ -d "$HOME/.config/goose" ]                                   && INSTALLED_IDES+=("goose")
{ [ -d "$HOME/.copilot" ] || [ -d "$HOME/.github/copilot" ] || command -v copilot &>/dev/null; } && INSTALLED_IDES+=("copilot-cli")
[ -d "$HOME/.gemini/antigravity-cli" ] || [ -d "$HOME/.antigravity" ] && INSTALLED_IDES+=("antigravity")

if [ ${#INSTALLED_IDES[@]} -eq 0 ]; then
    echo -e "  ${YELLOW}⊘${NC}  Nenhuma IDE detectada (Claude Code, Gemini, Codex, Cursor, Windsurf, OpenCode, OpenClaw...)."
else
    echo -e "  IDEs detectadas: ${INSTALLED_IDES[*]}"
    
    # Detecção inteligente do provedor de memória (evita bloqueios de cota do Claude)
    MEM_PROVIDER="claude"
    if [ -n "${GEMINI_API_KEY:-}" ] || [ -n "${GOOGLE_API_KEY:-}" ]; then
        MEM_PROVIDER="gemini"
        echo -e "  ${BLUE}ℹ${NC} Gemini API Key detectada. Configurando claude-mem para usar Gemini."
    fi

    for ide in "${INSTALLED_IDES[@]}"; do
        echo -e "  Instalando hooks nativos para ${ide}..."
        CLAUDE_MEM_DATA_DIR="$CLAUDE_MEM_DATA_DIR" \
        FASTEMBED_CACHE_PATH="$CLAUDE_MEM_MODELS" \
        $CLAUDE_MEM_NPX install --ide "$ide" --runtime worker --provider "$MEM_PROVIDER" --no-auto-start 2>&1 | tail -2
        echo -e "  ${GREEN}✓${NC} $ide configurado"
        
        if [ "$ide" = "copilot-cli" ]; then
            # Tailer é a fonte oficial de captura do Copilot (IDE/CLI); não
            # forçamos wrapper para evitar drift com binários reais do usuário.
            if [ -L "$HOME/.local/bin/copilot" ] && [ "$(readlink -f "$HOME/.local/bin/copilot")" = "$PROJECT_ROOT/scripts/capture/copilot-wrapper.sh" ]; then
                rm -f "$HOME/.local/bin/copilot"
                echo -e "  ${GREEN}✓${NC} wrapper legado do copilot removido (tailer oficial)"
            fi
            echo -e "  ${GREEN}✓${NC} captura do copilot via capture-tailer (transcripts da IDE e fallback CLI)"
        fi
    done

    # Sincroniza a chave do Gemini com o settings.json global do claude-mem.
    if [ "$MEM_PROVIDER" = "gemini" ]; then
        G_KEY="${GEMINI_API_KEY:-${GOOGLE_API_KEY:-}}"
        if [ -n "$G_KEY" ]; then
            # Usa python para um merge de JSON seguro em vez de sed.
            CLAUDE_MEM_SETTINGS="$CLAUDE_MEM_DATA_DIR/settings.json" CLAUDE_MEM_GEMINI_KEY="$G_KEY" "$PYTHON" -c "
	import json, os
	path = os.environ['CLAUDE_MEM_SETTINGS']
	key = os.environ['CLAUDE_MEM_GEMINI_KEY']
	os.makedirs(os.path.dirname(path), exist_ok=True)
	data = {}
	if os.path.exists(path):
	    with open(path, 'r') as f: data = json.load(f)
	data['CLAUDE_MEM_DATA_DIR'] = os.path.dirname(path)
	data['FASTEMBED_CACHE_PATH'] = os.path.join(os.path.dirname(path), 'models')
	data['CLAUDE_MEM_WORKER_HOST'] = '127.0.0.1'
	data['CLAUDE_MEM_WORKER_PORT'] = '37700'
	data['CLAUDE_MEM_CHROMA_ENABLED'] = 'false'
	data['CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH'] = os.path.join(os.path.dirname(path), 'transcript-watch.json')
	data['CLAUDE_MEM_GEMINI_API_KEY'] = key
	data['CLAUDE_MEM_PROVIDER'] = 'gemini'
	with open(path, 'w') as f: json.dump(data, f, indent=2)
	" 2>/dev/null && echo -e "  ${GREEN}✓${NC} Chave Gemini sincronizada com claude-mem global"
        fi
    fi
    # Gemini moderno (>=0.4x) só executa hooks "confiados". O instalador nativo
    # NÃO registra trust — fazemos isso aqui para captura sem intervenção manual.
    if [ -d "$HOME/.gemini" ] && [ -x "$BUN_BIN" ]; then
        "$BUN_BIN" - "$PROJECT_ROOT" <<'GEMTRUST' 2>/dev/null || true
import {readFileSync,writeFileSync,existsSync} from "fs";import {homedir} from "os";import path from "path";
const h=homedir();const sp=path.join(h,".gemini/settings.json");const tp=path.join(h,".gemini/trusted_hooks.json");
if(!existsSync(sp))process.exit(0);
const s=JSON.parse(readFileSync(sp,"utf8"));if(!s.hooks)process.exit(0);
let t={};if(existsSync(tp)){try{t=JSON.parse(readFileSync(tp,"utf8"))}catch{}}
const proj=process.argv[2]||process.cwd();const set=new Set(t[proj]||[]);
for(const groups of Object.values(s.hooks))for(const g of groups)for(const hk of (g.hooks||[]))
  if(hk&&hk.type==="command"&&hk.name)set.add(`${hk.name}:${hk.command??""}`);
t[proj]=[...set].sort();writeFileSync(tp,JSON.stringify(t,null,2)+"\n");
console.log("  gemini trusted_hooks atualizado");
GEMTRUST
        echo -e "  ${GREEN}✓${NC} Gemini trusted_hooks registrado"
    fi

    if [ -d "$HOME/.codex" ]; then
        "$PYTHON" "$PROJECT_ROOT/scripts/setup/install_codex_claude_mem_hooks.py" >/dev/null
        echo -e "  ${GREEN}✓${NC} Codex hooks registrados para claude-mem global"
    fi
fi

if [ -f "$CLAUDE_MEM_DB" ]; then
    OBS_COUNT="$(sqlite3 "$CLAUDE_MEM_DB" "SELECT COUNT(*) FROM observations;" 2>/dev/null || echo "?")"
    echo -e "  ${GREEN}✓${NC} Banco claude-mem global preservado ($OBS_COUNT observações)"
else
    echo -e "  ${YELLOW}⊘${NC}  Banco claude-mem global ainda não existe; será criado no primeiro start."
fi

echo -e "  ${GREEN}✓${NC} claude-mem configurado para dados globais ($CLAUDE_MEM_DATA_DIR, worker :37700)"
echo ""

# =============================================================================
# 6. INSTALAÇÃO DO NEURAL MEMORY (spreading activation — associativo, do source)
# =============================================================================
echo -e "${BOLD}[6/12] Instalando NeuralMemory (spreading activation, source local)...${NC}"

NEURAL_MEMORY_SRC="$PROJECT_ROOT/integrations/neural-memory"

echo -e "  ${GREEN}✓${NC} NeuralMemory resolvido do source local ($NEURAL_MEMORY_SRC)"

# Verificar se o CLI está disponível
if [ -x "$NMEM" ]; then
    echo -e "  ${GREEN}✓${NC} nmem $("$NMEM" --version 2>/dev/null || echo 'OK')"
else
    echo -e "  ${YELLOW}⊘${NC}  nmem CLI não encontrado. Verifique PATH: ~/.local/bin"
fi

echo ""

# =============================================================================
# 7. CONFIGURAÇÃO DO RTK (do source clonado — Rust)
# =============================================================================
echo -e "${BOLD}[7/12] Compilando RTK (source local)...${NC}"

RTK_SRC="$PROJECT_ROOT/integrations/rtk"
RUST_TOOLCHAIN="1.95.0"
CARGO_BIN="$(command -v cargo 2>/dev/null || true)"

# Um binário cargo sem toolchain funcional não é suficiente. Nesse caso,
# instala toolchain fixado dentro do projeto, sem alterar o HOME do usuário.
if [ -z "$CARGO_BIN" ] || ! "$CARGO_BIN" --version >/dev/null 2>&1; then
    echo -e "  Instalando Rust $RUST_TOOLCHAIN em .tools..."
    export RUSTUP_HOME="$PROJECT_ROOT/.tools/rustup"
    export CARGO_HOME="$PROJECT_ROOT/.tools/cargo"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain "$RUST_TOOLCHAIN" --no-modify-path
    CARGO_BIN="$CARGO_HOME/bin/cargo"
    echo -e "  ${GREEN}✓${NC} Rust local instalado"
fi

# Compilar do source
cd "$RTK_SRC"
if $FORCE || [ ! -f "target/release/rtk" ]; then
    echo -e "  Compilando RTK (cargo build --release)..."
    "$CARGO_BIN" build --locked --release 2>&1 | tail -1
    echo -e "  ${GREEN}✓${NC} RTK compilado"
else
    echo -e "  ${GREEN}✓${NC} RTK já compilado"
fi

echo -e "  ${GREEN}✓${NC} RTK $(./target/release/rtk --version 2>/dev/null | awk '{print $2}') disponível no projeto"

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
            "command": "PROJECT_ROOT_PLACEHOLDER/scripts/graph/serve-graph.sh",
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
            "command": "PROJECT_ROOT_PLACEHOLDER/scripts/services/start-claude-mem.sh",
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

PY_CRON=".venv/bin/python"
CRON_SYNC_JOB="0 */6 * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && ./scripts/graph/build-graph.sh >> logs/sync.log 2>&1"
CRON_AUDIT_JOB="0 * * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/health/audit_memory.py --fix >> logs/audit.log 2>&1"
CRON_BACKUP_JOB="0 3 * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/health/backup_databases.py >> logs/backup.log 2>&1"
CRON_DREAM_JOB="0 2 * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/dream/dream_cycle.py --once --real >> logs/dream-cycle.log 2>&1"
CRON_MONTHLY_JOB="15 3 1 * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/dream/monthly_synthesizer.py --real >> logs/monthly-synthesizer.log 2>&1"
CRON_YEARLY_JOB="30 3 1 1 * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/dream/yearly_synthesizer.py --real >> logs/yearly-synthesizer.log 2>&1"
CRON_VECTOR_SUMMARY_JOB="45 3 * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && if [ \"\${VECTOR_BACKEND:-sqlite}\" = \"milvus\" ]; then $PY_CRON scripts/maintenance/vector-sync.py --collection summary_vectors --json >> logs/vector-sync.log 2>&1; fi"

if command -v crontab &>/dev/null; then
    # Remove variantes legadas/duplicadas e instala uma única entrada canônica.
    CRON_TMP=$(mktemp)
    crontab -l 2>/dev/null \
        | grep -vF "# Hive-Mind — sync vault → graph a cada 6h" \
        | grep -vF "# Hive-Mind — audit vault → SQLite hourly" \
        | grep -vF "# Hive-Mind — backup SQLite diario" \
        | grep -vF "# Hive-Mind — Dream Cycle diario" \
        | grep -vF "# Hive-Mind — sintese mensal K5" \
        | grep -vF "# Hive-Mind — sintese anual K5" \
        | grep -vF "# Hive-Mind — vector sync summaries K5" \
        | grep -vF "# sinapse_agent — sync vault → graph a cada 6h" \
        | grep -vF "./scripts/graph/build-graph.sh" \
        | grep -vF "scripts/health/audit_memory.py --fix" \
        | grep -vF "scripts/health/backup_databases.py" \
        | grep -vF "scripts/dream/dream_cycle.py --once --real" \
        | grep -vF "scripts/dream/monthly_synthesizer.py --real" \
        | grep -vF "scripts/dream/yearly_synthesizer.py --real" \
        | grep -vF "scripts/maintenance/vector-sync.py --collection summary_vectors" \
        > "$CRON_TMP" || true
    {
        cat "$CRON_TMP"
        echo "# Hive-Mind — sync vault → graph a cada 6h"
        echo "$CRON_SYNC_JOB"
        echo "# Hive-Mind — audit vault → SQLite hourly"
        echo "$CRON_AUDIT_JOB"
        echo "# Hive-Mind — backup SQLite diario"
        echo "$CRON_BACKUP_JOB"
        echo "# Hive-Mind — Dream Cycle diario"
        echo "$CRON_DREAM_JOB"
        echo "# Hive-Mind — sintese mensal K5"
        echo "$CRON_MONTHLY_JOB"
        echo "# Hive-Mind — sintese anual K5"
        echo "$CRON_YEARLY_JOB"
        echo "# Hive-Mind — vector sync summaries K5"
        echo "$CRON_VECTOR_SUMMARY_JOB"
    } | crontab -
    rm -f "$CRON_TMP"
    echo -e "  ${GREEN}✓${NC} Cron configurado sem duplicatas (sync, audit, backup, Dream Cycle, K5)"
else
    echo -e "  ${YELLOW}⊘${NC}  crontab não disponível. Use scripts/graph/build-graph.sh, scripts/health/backup_databases.py e scripts/dream/dream_cycle.py manualmente."
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
      graph_json: "$PROJECT_ROOT/cerebro/cortex/occipital/grafo/graph.json"
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

# Garante que o .env.example contém o bloco de LLM por papel (idempotente).
# O bloco vive versionado em config/env.roles.example — fonte única.
if [ -f "$PROJECT_ROOT/config/env.roles.example" ] && [ -f "$PROJECT_ROOT/.env.example" ]; then
    if ! grep -q "^HIVE_GRAPHIFY_PROVIDER=" "$PROJECT_ROOT/.env.example"; then
        printf '\n' >> "$PROJECT_ROOT/.env.example"
        cat "$PROJECT_ROOT/config/env.roles.example" >> "$PROJECT_ROOT/.env.example"
        echo -e "  ${GREEN}✓${NC} Bloco de LLM por papel adicionado ao .env.example"
    fi
fi

if [ -n "$PROVIDER" ] && [ -n "$MODEL" ]; then
    echo -e "  Salvando provedor ($PROVIDER) e modelo ($MODEL) no .env..."
    # Garante que o .env existe
    [ -f "$PROJECT_ROOT/.env" ] || cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    # Salva no .env usando python
    "$PYTHON" -c "import sys; sys.path.append('$PROJECT_ROOT'); from core.auth import save_env; save_env('HIVE_DREAMER_PROVIDER', '$PROVIDER'); save_env('HIVE_DREAMER_MODEL', '$MODEL')"
    echo -e "  ${GREEN}✓${NC} Provedor e modelo salvos (papel Dreamer)."
    echo -e "  Os papéis Graphify, Vision e Síntese herdam este modelo por padrão;"
    echo -e "  ajuste por papel (e fallbacks) com: python3 scripts/setup/setup-brain.py"
else
    echo -e "  Nenhum provedor/modelo de IA fornecido via argumentos."
    echo -e "  A configuração poderá ser realizada ao final da instalação ou posteriormente."
fi
echo ""

# 12. CONFIGURAÇÃO DE AGENTES EXTERNOS (via MCP + templates)
# =============================================================================
echo -e "${BOLD}[12/12] Configurando agentes externos (MCP + CLI)...${NC}"

# Garantir permissões de execução em todos os scripts e hooks
chmod +x $(find "$PROJECT_ROOT/scripts" -name "*.sh") 2>/dev/null || true
chmod +x $(find "$PROJECT_ROOT/scripts" -name "*.py") 2>/dev/null || true
chmod +x "$PROJECT_ROOT/cerebro/tronco/infra/agentes/.claude/scripts/"*.py 2>/dev/null || true

# Registro MCP delegado ao script standalone (idempotente, merge seguro).
# Pode ser re-executado a qualquer momento: ./scripts/setup/register-mcp.sh
if ! PROJECT_ROOT="$PROJECT_ROOT" bash "$PROJECT_ROOT/scripts/setup/register-mcp.sh"; then
    echo -e "  ${YELLOW}⊘${NC} Nenhum agente externo detectado. Use scripts/services/sinapse-write.py via CLI."
fi

# Template AGENTS.md do vault para Codex fica no Tronco, sem criar .codex no topo.
if command -v codex &>/dev/null && [ -f "$PROJECT_ROOT/cerebro/tronco/infra/agentes/.codex/AGENTS.md" ]; then
    mkdir -p "$VAULT_DIR/tronco/infra/agentes/.codex"
    cp "$PROJECT_ROOT/cerebro/tronco/infra/agentes/.codex/AGENTS.md" "$VAULT_DIR/tronco/infra/agentes/.codex/AGENTS.md" 2>/dev/null || true
fi

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}Verificando integridade...${NC}"
"$PYTHON" "$PROJECT_ROOT/scripts/setup/install_services.py" install

# Ponte de modelo: se o papel `claude_mem` foi configurado no setup-brain,
# aplica esse provider/modelo no claude-mem (via /api/settings + seed). Sai
# limpo se não houver papel configurado (usa o default do claude-mem). #modelo
"$PYTHON" "$PROJECT_ROOT/scripts/setup/sync-claude-mem-provider.py" 2>&1 | sed 's/^/  /' || true

if "$PYTHON" "$PROJECT_ROOT/scripts/services/sinapse-write.py" health >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Health check: backends operacionais"
else
    echo -e "  ${YELLOW}⊘${NC}  Health check: alguns backends offline"
    echo -e "  Execute: python3 scripts/services/sinapse-write.py health"
fi

# Checagem opcional do FalkorDB (Graphiti — lóbulo temporal).
# Se FalkorDB não estiver respondendo, o cérebro usa o fallback JSON-lines
# automaticamente; não bloqueia a instalação.
echo ""
echo -e "${BOLD}Graphiti (lóbulo temporal):${NC}"
if "$PYTHON" -c "
import os, sys
sys.path.insert(0, '$PROJECT_ROOT')
try:
    from integrations.graphiti import assert_health
    h = assert_health()
    if h['falkordb']:
        print('  OK: FalkorDB em', os.environ.get('FALKORDB_HOST', 'localhost'))
    else:
        print('  WARN: FalkorDB offline — cérebro usará fallback JSON-lines em')
        print('        cerebro/cortex/temporal/_global/grafo.jsonl')
        sys.exit(0)
except Exception as e:
    print('  WARN: Graphiti não pôde ser checado:', e)
    sys.exit(0)
"; then
    :
else
    echo -e "  ${YELLOW}⊘${NC}  Graphiti check falhou (não-bloqueante)"
fi
echo ""

# =============================================================================
# K10 — Validacao por perfil e suite real (docs/12 §K10)
# =============================================================================
echo -e "${BOLD}[K10] Perfil=${INSTALL_PROFILE} — validando servicos...${NC}"

# Habilita servicos locais adicionais em local-full. local-min mantem apenas
# claude-mem (que ja foi iniciado por install_services.py) e o watchdog
# graphify, que sao seguros mesmo sem GPU/disco extra.
if [ "$INSTALL_PROFILE" = "local-full" ]; then
    echo -e "  ${BOLD}Perfil local-full:${NC} habilitando Milvus + FalkorDB + RAGFlow (docker)"
    if [ -f "$PROJECT_ROOT/integrations/milvus/docker-compose.yml" ]; then
        (cd "$PROJECT_ROOT/integrations/milvus" && docker compose up -d)             && echo -e "  ${GREEN}OK${NC} Milvus iniciado"             || echo -e "  ${YELLOW}WARN${NC} Milvus nao subiu (docker indisponivel ou perfil sem docker)"
    fi
    if [ -f "$PROJECT_ROOT/integrations/ragflow/docker-compose.yml" ]; then
        (cd "$PROJECT_ROOT/integrations/ragflow" && docker compose up -d)             && echo -e "  ${GREEN}OK${NC} RAGFlow iniciado"             || echo -e "  ${YELLOW}WARN${NC} RAGFlow nao subiu (opcional em local-full)"
    fi
    # FalkorDB ja foi iniciado por install_services.py quando disponivel; so
    # reforcamos o aviso se ele nao estiver respondendo.
    if ! "$PYTHON" -c "import socket,os; s=socket.socket(); s.settimeout(1); s.connect((os.environ.get('FALKORDB_HOST','localhost'), int(os.environ.get('FALKORDB_PORT','6379'))))" 2>/dev/null; then
        echo -e "  ${YELLOW}WARN${NC} FalkorDB offline — cerebro usa fallback JSON-lines"
    fi
else
    echo -e "  Perfil local-min: mantendo apenas claude-mem + graphify-watch"
    echo -e "  Para subir Milvus/FalkorDB/RAGFlow depois, use:"
    echo -e "    ${BOLD}./install.sh --profile=local-full --with-real-tests${NC}"
fi

# Migrations: re-aplica schema/vetores idempotentemente. CRR-safe (B1) ja
# garantido por ensure_migrations; aqui so reforcamos que esta aplicado.
"$PYTHON" -c "
import os, sys
sys.path.insert(0, '$PROJECT_ROOT')
from core.database import ensure_migrations, get_connection
conn = get_connection()
ensure_migrations(conn)
conn.close()
print('  OK: schema/vector migrations aplicadas (idempotente)')
" 2>&1 | sed 's/^/  /' || echo -e "  ${YELLOW}WARN${NC} migrations nao puderam ser validadas"

# MCP por agente, idempotente e preservando configs externas.
"$PROJECT_ROOT/scripts/setup/register-mcp.sh" 2>&1 | sed 's/^/  /' || true
echo ""

# Smoke real da frente de conhecimento (--with-real-tests). Pula limpo
# servicos offline e falha apenas quando um teste real (sem mock) quebra.
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

if $WITH_REAL_TESTS; then
    echo -e "${BOLD}Executando suite real de conhecimento (K9) — backends reais, sem mock...${NC}"
    if [ -x "$PROJECT_ROOT/tests/run_real_knowledge.sh" ]; then
        if "$PROJECT_ROOT/tests/run_real_knowledge.sh" --report "$PROJECT_ROOT/logs/k9-real-suite-report.md" 2>&1 | tail -40; then
            echo -e "  ${GREEN}OK${NC} suite real de conhecimento executada"
        else
            echo -e "  ${RED}ERRO${NC} suite real retornou !=0; corrija o gate K9 antes de considerar o install valido"
            exit 1
        fi
    else
        echo -e "  ${RED}ERRO${NC} tests/run_real_knowledge.sh nao encontrado/exequivel"
        exit 1
    fi
    echo ""
fi

# =============================================================================
# K10 Task 8 — Relatorio final com paths, portas, modelos e health
# =============================================================================
REPORT="$PROJECT_ROOT/logs/install-report.md"
mkdir -p "$(dirname "$REPORT")"
{
    echo "# Hive-Mind — Relatorio de Instalacao"
    echo ""
    echo "- Data: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "- Perfil: \`${INSTALL_PROFILE}\`"
    echo "- With real tests: \`${WITH_REAL_TESTS}\`"
    echo "- With full tests:  \`${WITH_TESTS}\`"
    echo ""
    echo "## Paths"
    echo ""
    echo "| Recurso | Caminho |"
    echo "|---|---|"
    echo "| Vault Obsidian | \`${VAULT_DIR}\` |"
    echo "| Knowledge Graph | \`${GRAPHIFY_OUT}/graph.json\` |"
    echo "| Banco principal | \`${PROJECT_ROOT}/hive_mind.db\` |"
    echo "| claude-mem DB | \`${HOME}/.claude-mem/claude-mem.db\` |"
    echo "| Python venv | \`${PROJECT_ROOT}/.venv\` |"
    echo ""
    echo "## Portas e servicos"
    echo ""
    echo "| Servico | Porta esperada | Status |"
    echo "|---|---:|---|"
    for svc in "claude-mem 37700" "sqlite-vec 37701" "api 37702" "mcp-http 37703"; do
        name="${svc% *}"; port="${svc##* }"
        if "$PYTHON" -c "import socket; s=socket.socket(); s.settimeout(0.5); s.connect(('127.0.0.1', ${port}))" 2>/dev/null; then
            echo "| ${name} | ${port} | online |"
        else
            echo "| ${name} | ${port} | offline (nao-bloqueante) |"
        fi
    done
    echo ""
    echo "## Modelos Ollama (instalados quando disponivel)"
    echo ""
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        curl -s http://localhost:11434/api/tags | "$PYTHON" -c '
import json, sys
data = json.load(sys.stdin)
for m in data.get("models", []):
    print("- `" + m["name"] + "` (" + str(round(m["size"]/1e9, 1)) + " GB)")
'
    else
        echo "_Ollama offline neste host._"
    fi
    echo ""
    echo "## Health check"
    echo ""
    if "$PYTHON" "$PROJECT_ROOT/scripts/services/sinapse-write.py" health > "$REPORT.health" 2>&1; then
        sed 's/^/    /' "$REPORT.health" | head -40
    else
        echo "_Health check retornou !=0 (ver logs/install-report.md.health)._"
    fi
    echo ""
    echo "## Validacao real (K9)"
    echo ""
    if $WITH_REAL_TESTS; then
        echo "- \`./tests/run_real_knowledge.sh --report logs/k9-real-suite-report.md\` executado com exit 0."
        echo "- Relatorio K9: \`logs/k9-real-suite-report.md\`."
    else
        echo "- Pule \`--with-real-tests\` para rodar a suite real de conhecimento."
        echo "- Comando: \`./tests/run_real_knowledge.sh\`"
    fi
    echo ""
    echo "## Proximos passos"
    echo ""
    echo "1. Reinicie seus agentes (Claude Code, Codex CLI, etc.) para carregar o MCP."
    echo "2. Suba o Obsidian apontando para \`cerebro/\`."
    echo "3. Verifique o watcher: \`./scripts/services/start-watcher.sh status\`."
} > "$REPORT"
echo ""
echo -e "  ${GREEN}OK${NC} Relatorio final escrito em: ${BOLD}$REPORT${NC}"

# Mini-resumo no stdout (para o usuario ver sem abrir o arquivo)
echo ""
echo -e "  ${BOLD}Resumo da instalacao (perfil ${INSTALL_PROFILE}):${NC}"
echo -e "    Vault:         ${BOLD}$VAULT_DIR${NC}"
echo -e "    Banco:         ${BOLD}$PROJECT_ROOT/hive_mind.db${NC}"
echo -e "    Python:        ${BOLD}$PROJECT_ROOT/.venv/bin/python${NC}"
echo -e "    claude-mem:    ${BOLD}http://127.0.0.1:37700${NC}"
echo -e "    API REST:      ${BOLD}http://127.0.0.1:37702${NC}"
echo -e "    MCP HTTP:      ${BOLD}http://127.0.0.1:37703${NC}"
if $WITH_REAL_TESTS; then
    echo -e "    Suite real:    ${BOLD}executada (ver logs)${NC}"
fi
echo ""

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
echo -e "  ${BOLD}Ollama (modelos — baixados automaticamente acima quando detectado):${NC}"
echo -e "         ollama pull snowflake-arctic-embed2 # Embeddings 1024d (core/LightRAG/Graphiti)"
echo -e "         ollama pull qwen2.5:3b           # Extração Graphiti + LightRAG (~1.9GB)"
echo -e "         ollama pull qwen2.5-coder:3b     # Extração semântica do Graphify"
echo -e "         ollama pull minicpm-v4.6:latest  # Visão local compacta (default)"
echo -e "         ollama pull gemma3:4b            # Fallback visão/raciocínio visual (local-full)"
echo -e "         ollama pull deepseek-ocr:latest  # OCR dedicado opcional (SINAPSE_PULL_DEEPSEEK_OCR=1)"
echo -e "         ollama pull qwen2.5:7b           # Graphiti local alta qualidade (opcional, ~4.7GB)"
echo -e "         ollama pull nomic-embed-text     # Embeddings leve (alternativo)"
echo ""
echo -e "  ${BOLD}Disaster Recovery:${NC}"
echo -e "         ${BOLD}./scripts/utils/recover.sh${NC} — Verifica/Rebuilda graph.json, reinicia worker, health check"
echo ""
echo -e "  ${BOLD}API Keys (opcional):${NC}"
echo -e "         Copie .env.example para .env e configure GOOGLE_API_KEY."
echo -e "         Gemini é usado para extração semântica de alta qualidade."
echo ""
if $OLLAMA_OK; then
    echo -e "  ${BOLD}Modelos Ollama instalados:${NC}"
    curl -s http://localhost:11434/api/tags 2>/dev/null | "$PYTHON" -c "
import json, sys
for m in json.load(sys.stdin)['models']:
    print(f'         {m[\"name\"]:35s} {m[\"size\"]/1e9:.1f}GB')
"
fi
echo ""

# =============================================================================
# 13. CR-SQLite (vendor opcional — sync multi-device via CRDT)
# =============================================================================
# Politica 0.2 do roadmap: vendor externo em integrations/<nome>/.
# Binario vem de https://github.com/vlcn-io/cr-sqlite/releases (release pinada).
# E opt-in: controlado por HIVE_CRDT_SYNC=true no .env (default false).
CRSQLITE_VERSION="${CRSQLITE_VERSION:-0.16.3}"
CRSQLITE_DIR="$PROJECT_ROOT/integrations/crsqlite"

download_crsqlite_asset() {
    local asset=$1
    local url="https://github.com/vlcn-io/cr-sqlite/releases/download/v${CRSQLITE_VERSION}/${asset}"
    local tmp_dir; tmp_dir=$(mktemp -d)
    local zipfile="${tmp_dir}/${asset}"
    trap 'rm -rf "$tmp_dir"' RETURN

    echo -e "  Baixando ${url}"
    if ! curl --proto '=https' --tlsv1.2 -sSfL -o "$zipfile" "$url"; then
        echo -e "  ${YELLOW}!${NC} Falha no download de ${asset} (rede ou release)."
        return 1
    fi

    # Extrai apenas o binario nomeado pelo upstream (a partir de v0.16.1 o
    # zip ja vem com o nome final do .so/.dylib/.dll, sem rename).
    if command -v unzip >/dev/null 2>&1; then
        unzip -o -j "$zipfile" -d "$CRSQLITE_DIR" 2>/dev/null || {
            echo -e "  ${YELLOW}!${NC} unzip falhou para ${asset}"
            return 1
        }
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c "
import zipfile, sys
with zipfile.ZipFile('$zipfile') as z:
    z.extractall('$CRSQLITE_DIR')
" || return 1
    else
        echo -e "  ${YELLOW}!${NC} Nenhum unzip ou python3 disponivel para extrair."
        return 1
    fi
    return 0
}

download_crsqlite() {
    mkdir -p "$CRSQLITE_DIR"

    # Escolhe asset conforme plataforma detectada.
    local sys_name kernel
    sys_name=$(uname -s 2>/dev/null || echo "Linux")
    kernel=$(uname -m 2>/dev/null || echo "x86_64")

    local asset=""
    case "$sys_name" in
        Linux)
            case "$kernel" in
                x86_64|amd64)  asset="crsqlite-linux-x86_64.zip" ;;
                aarch64|arm64) asset="crsqlite-linux-aarch64.zip" ;;
                *) echo -e "  ${YELLOW}!${NC} Arquitetura Linux nao suportada: $kernel"; return 1 ;;
            esac ;;
        Darwin)
            case "$kernel" in
                x86_64|amd64)  asset="crsqlite-darwin-x86_64.zip" ;;
                arm64|aarch64) asset="crsqlite-darwin-aarch64.zip" ;;
                *) echo -e "  ${YELLOW}!${NC} Arquitetura Darwin nao suportada: $kernel"; return 1 ;;
            esac ;;
        *)
            echo -e "  ${YELLOW}!${NC} SO nao suportado para CR-SQLite pre-compilado: $sys_name"
            echo -e "         Compilar do source (Rust nightly + make loadable) ou desabilitar P8."
            return 1 ;;
    esac

    download_crsqlite_asset "$asset"
}

if [ -f "$CRSQLITE_DIR/crsqlite.so" ] || [ -f "$CRSQLITE_DIR/crsqlite.dylib" ] || [ -f "$CRSQLITE_DIR/crsqlite.dll" ]; then
    echo -e "${BOLD}[13] CR-SQLite vendor ja presente em $CRSQLITE_DIR — pulando download${NC}"
elif $FORCE || [ "${INSTALL_CRSQLITE:-false}" = "true" ]; then
    echo -e "${BOLD}[13] Baixando CR-SQLite v${CRSQLITE_VERSION} para integrations/crsqlite/...${NC}"
    if ! download_crsqlite; then
        echo -e "  ${YELLOW}!${NC} CR-SQLite NAO instalado. P8 (sync multi-device) fica desabilitado."
        echo -e "         Habilite depois com: INSTALL_CRSQLITE=true bash install.sh"
    else
        echo -e "  ${GREEN}OK${NC} CR-SQLite v${CRSQLITE_VERSION} em $CRSQLITE_DIR"
        ls -la "$CRSQLITE_DIR" | grep -E "crsqlite\.(so|dylib|dll)" || true
    fi
else
    echo -e "${BOLD}[13] CR-SQLite (P8) - opt-in.${NC}"
    echo -e "         Para sync multi-device via CRDT, rode:"
    echo -e "           INSTALL_CRSQLITE=true bash install.sh"
    echo -e "         e defina HIVE_CRDT_SYNC=true no .env. Mais em:"
    echo -e "           $CRSQLITE_DIR/README.md"
fi

# ── Langfuse / OpenTelemetry (P9) — opt-in ────────────────────────────────
# Tracing distribuído opt-in para Dream Cycle, capture e MCP. Com keys vazias,
# zero overhead (NoOp tracer). Para subir Langfuse local e instrumentar:
echo -e "${BOLD}[14] Langfuse / OpenTelemetry (P9) - opt-in.${NC}"
echo -e "         Para tracing distribuido dos scripts (Dream Cycle, capture, MCP):"
echo -e "           1. Suba Langfuse:  ${BOLD}docker compose -f integrations/langfuse/docker-compose.yml up -d${NC}"
echo -e "           2. Crie projeto + copie keys em http://localhost:3100"
echo -e "           3. Adicione ao .env: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST"
echo -e "         Em prod use HTTPS (basic auth vazaria keys em HTTP) + LANGFUSE_NEXTAUTH_SECRET/SALT fortes:"
echo -e "           openssl rand -hex 32"
echo -e "         Sem keys: zero overhead (traces descartados). Veja:"
echo -e "           integrations/langfuse/README.md"

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
    echo -e "${BOLD}${YELLOW}Configuração da Inteligência (Brain Selector — todos os papéis):${NC}"
    echo -e "  Configura provedor/modelo/auth de TODOS os papéis: Dreamer, Graphify, Vision e Síntese."
    echo -e "  Cada papel pode usar um modelo próprio (Gemini, OpenAI, Ollama, etc.) com fallback opcional."
    echo ""
    read -p "  Deseja configurar o seu modelo e chaves de IA interativamente agora? [S/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[SsYy]$ ]] || [ -z "$REPLY" ]; then
        "$PROJECT_ROOT/scripts/setup/setup-brain.sh"
    else
        echo -e "  Você pode realizar essa configuração mais tarde rodando: ${BOLD}./scripts/setup/setup-brain.sh${NC}"
        echo ""
    fi
fi
