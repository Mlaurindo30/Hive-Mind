#!/usr/bin/env bash
# =============================================================================
# Sinapse Agent — Universal Installation Script
# =============================================================================
# Detects which agents are installed and configures each one automatically.
# Usage: ./install.sh [--force] [--skip-agent <name>] [--with-tests]
#
# What this script does:
#   1. Checks dependencies (uv, Node 18+, Bun, Ollama optional)
#   2. Syncs the local Python environment and reproducible (.venv + uv.lock)
#   3. Installs Graphify (graphifyy[all]) and indexes the cerebro/ vault (Gemini→Ollama→AST)
#   4. Registers skills in detected agents (Hermes, Claude, Codex, etc.)
#   5. Installs claude-mem via native npx, with global data in ~/.claude-mem
#   6. Installs NeuralMemory (nmem) — associative search with spreading activation
#   7. Compiles RTK from source (Rust) and installs the plugin in Hermes
#   8. Configures MCP servers (graphify + claude-mem) for Hermes
#   9. Installs the periodic sync cron job (rebuild of graph.json every 6h)
#  10. Installs/updates the sinapse-memory plugin (multi-backend: nmem + claude-mem + graphify)
#  11. Configures Dream Cycle intelligence (dream cycle)
#  12. Configures external agents (MCP: Claude Code, Codex, Kilo Code, etc.)
#
# Flags:
#   --force              Reinstalls components even if they already exist
#   --skip-agent=X       Skips configuration of a specific agent
#   --with-tests         Runs unit tests after installation
#   --with-real-tests    Chains the real knowledge suite at the end
#   --profile=<profile>  Services profile: local-min (default) or local-full
#   --provider=X         Dreamer provider (gemini|openai|ollama|...)
#   --model=X            Dreamer model
#   --non-interactive    Skips interactive prompts (CI/fresh machine)
# =============================================================================

set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────────────────
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
        *) echo -e "${RED}Error:${NC} unknown argument: $arg"; exit 1 ;;
    esac
done

# Default validation settings (see docs/12). --profile chooses how far the installer
# goes on a "fresh machine"; --with-real-tests chains the real suite at the end.
INSTALL_PROFILE="${INSTALL_PROFILE:-local-min}"
WITH_REAL_TESTS="${WITH_REAL_TESTS:-false}"
case "$INSTALL_PROFILE" in
    local-min|local-full) ;;
    *) echo -e "${RED}Error:${NC} --profile invalid: $INSTALL_PROFILE (use local-min|local-full)"; exit 1 ;;
esac

# ── Banner ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║          Hive-Mind — Universal Installation        ║${NC}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# =============================================================================
# 1. DEPENDENCY CHECK
# =============================================================================
echo -e "${BOLD}[1/12] Checking dependencies...${NC}"

# uv is the only accepted Python installation tool. The system Python does
# not participate in the runtime, and no global fallback is allowed.
if command -v uv &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} uv $(uv --version 2>/dev/null | awk '{print $2}')"
else
    echo -e "${RED}Error:${NC} uv not found. Install uv before running this installer."
    exit 1
fi
uv python install 3.12
BOOTSTRAP_PYTHON="$(uv python find 3.12)"

# Production requires a local .env and HIVE_MIND_API_KEY for the fail-closed REST API.
# The installer creates a local token if the operator hasn't filled one in yet,
# without committing a secret and without overwriting an existing value.
if [ -f "$PROJECT_ROOT/.env.example" ]; then
    ENV_FRESH=0
    [ -f "$PROJECT_ROOT/.env" ] || { cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"; ENV_FRESH=1; }
    "$BOOTSTRAP_PYTHON" - "$PROJECT_ROOT/.env" "$INSTALL_PROFILE" "$ENV_FRESH" <<'PY'
import secrets
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
profile = sys.argv[2]
env_fresh = sys.argv[3] == "1"
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

# .env newly created from the example outside local-full: the vector backend
# must be local (sqlite_vec). The example may bring milvus, which only exists
# in the local-full (docker) profile — without it, MCP/CLI/API break with MilvusException.
# Pre-existing .env is never changed (operator's choice).
if env_fresh and profile != "local-full":
    for idx, line in enumerate(lines):
        if line.startswith("VECTOR_BACKEND=") and line.split("=", 1)[1].strip() != "sqlite_vec":
            lines[idx] = "VECTOR_BACKEND=sqlite_vec"
            changed = True
            print("  OK: VECTOR_BACKEND=sqlite_vec (profile without Milvus)")
            break

if changed:
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  OK: HIVE_MIND_API_KEY generated in local .env")
else:
    print("  OK: HIVE_MIND_API_KEY already exists in local .env")
PY
fi

# Node 18+ is a requirement for the full runtime and smoke tests.
if command -v node &>/dev/null; then
    NODE_VERSION=$(node --version | sed 's/v//')
    NODE_MAJOR="${NODE_VERSION%%.*}"
    if [ "$NODE_MAJOR" -lt 18 ]; then
        echo -e "${RED}Error:${NC} Node 18+ is required (found: $NODE_VERSION)."
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Node $NODE_VERSION"
else
    echo -e "${RED}Error:${NC} Node 18+ is required for claude-mem."
    exit 1
fi

# Bun is copied to .tools/bin (project-managed runtime, helper scripts).
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
    echo -e "${RED}Error:${NC} Bun is required for the claude-mem managed runtime."
    exit 1
fi

# Ollama (optional, for local semantic extraction)
OLLAMA_OK=false
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    OLLAMA_MODELS=$(curl -s http://localhost:11434/api/tags | "$BOOTSTRAP_PYTHON" -c "import json,sys; print(len(json.load(sys.stdin)['models']))" 2>/dev/null || echo "?")
    OLLAMA_VERSION=$(curl -s http://localhost:11434/api/version | "$BOOTSTRAP_PYTHON" -c "import json,sys; print(json.load(sys.stdin).get('version','0.0.0'))" 2>/dev/null || echo "0.0.0")
    echo -e "  ${GREEN}✓${NC} Ollama detected ($OLLAMA_MODELS models, v$OLLAMA_VERSION)"
    OLLAMA_OK=true
else
    echo -e "  ${YELLOW}⊘${NC}  Ollama not detected (optional for local semantic extraction). Install: curl -fsSL https://ollama.com/install.sh | sh"
fi

# Download the local models that Hive-Mind needs (idempotent: skips those already present).
# - snowflake-arctic-embed2 embeddings 1024d (core/database.py, LightRAG, Graphiti)
# - qwen2.5:3b        Graphiti + LightRAG entity extraction (new default)
# - qwen2.5-coder:3b      Graphify semantic extraction
# - minicpm-v4.6:latest   compact local vision for Deep Portal and vision tests
# Optional (gate SINAPSE_PULL_QWEN7B=1): qwen2.5:7b for high-quality local Graphiti
# (HIVE_GRAPHITI_MODEL=qwen2.5:7b). ~4.7GB, requires VRAM headroom.
# Optional (local-full): gemma3:4b as a vision/visual reasoning fallback.
# Optional (SINAPSE_PULL_DEEPSEEK_OCR=1 or HIVE_OCR_MODEL=deepseek-ocr:latest):
# deepseek-ocr:latest for dedicated OCR.
# Note: MiniCPM-V 4.6 requires Ollama >= 0.30; on earlier versions the installer
# downloads gemma3:4b as a working fallback so the vision role doesn't break.
if $OLLAMA_OK; then
    version_ge() {
        [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
    }

    ollama_pull_if_missing() {
        local model="$1"; local note="$2"
        if curl -s http://localhost:11434/api/tags 2>/dev/null | grep -q "\"$model\""; then
            echo -e "  ${GREEN}✓${NC} $model already present ${note:+($note)}"
            return 0
        else
            echo -e "  ${BLUE}↓${NC} downloading $model ${note:+($note)}..."
            if ollama pull "$model" 2>&1 | tail -1; then
                return 0
            fi
            echo -e "  ${YELLOW}⊘${NC} failed to download $model (follow up manually: ollama pull $model)"
            return 1
        fi
    }
    echo -e "  ${BOLD}Hive-Mind local models:${NC}"
    ollama_pull_if_missing "snowflake-arctic-embed2" "embeddings 1024d" || true
    ollama_pull_if_missing "qwen2.5:3b"       "Graphiti/LightRAG extraction" || true
    ollama_pull_if_missing "qwen2.5-coder:3b" "Graphify extraction" || true
    if version_ge "$OLLAMA_VERSION" "0.30.0"; then
        VISION_PRIMARY="minicpm-v4.6:latest"
    else
        VISION_PRIMARY="gemma3:4b"
        echo -e "  ${YELLOW}⊘${NC}  minicpm-v4.6 requires Ollama >=0.30 (current: $OLLAMA_VERSION); using gemma3:4b as local vision"
    fi
    if ! ollama_pull_if_missing "$VISION_PRIMARY" "local vision"; then
        echo -e "  ${YELLOW}⊘${NC}  $VISION_PRIMARY unavailable; downloading gemma3:4b as a working fallback"
        ollama_pull_if_missing "gemma3:4b" "vision/visual reasoning fallback" || true
    fi
    if [ "$INSTALL_PROFILE" = "local-full" ]; then
        ollama_pull_if_missing "gemma3:4b" "vision/visual reasoning fallback" || true
    else
        echo -e "  ${YELLOW}⊘${NC}  gemma3:4b skipped (local-full). For vision fallback: ./install.sh --profile=local-full"
    fi
    if [ "${SINAPSE_PULL_DEEPSEEK_OCR:-0}" = "1" ] || [ "${HIVE_OCR_MODEL:-}" = "deepseek-ocr:latest" ]; then
        ollama_pull_if_missing "deepseek-ocr:latest" "optional dedicated OCR" || true
    else
        echo -e "  ${YELLOW}⊘${NC}  deepseek-ocr:latest skipped (optional). For dedicated OCR: SINAPSE_PULL_DEEPSEEK_OCR=1 ./install.sh"
    fi
    if [ "${SINAPSE_PULL_QWEN7B:-0}" = "1" ] || [ "${HIVE_GRAPHITI_MODEL:-}" = "qwen2.5:7b" ]; then
        ollama_pull_if_missing "qwen2.5:7b"   "high-quality local Graphiti" || true
    else
        echo -e "  ${YELLOW}⊘${NC}  qwen2.5:7b skipped (optional). For high-quality local Graphiti: SINAPSE_PULL_QWEN7B=1 ./install.sh"
    fi
fi

echo ""

# Editable components must exist before uv sync. The manifest pins exact
# commits and preserves already-modified local checkouts.
"$BOOTSTRAP_PYTHON" "$PROJECT_ROOT/scripts/setup/components.py" bootstrap

# =============================================================================
# 2. LOCAL PYTHON ENVIRONMENT
# =============================================================================
echo -e "${BOLD}[2/12] Syncing local Python environment (.venv)...${NC}"
uv sync --frozen --all-groups
PYTHON="$PROJECT_ROOT/.venv/bin/python"
GRAPHIFY="$PROJECT_ROOT/.venv/bin/graphify"
NMEM="$PROJECT_ROOT/.venv/bin/nmem"
export PATH="$PROJECT_ROOT/.venv/bin:$PROJECT_ROOT/integrations/rtk/target/release:$PATH"
"$PYTHON" -c "import fastapi, yaml, pydantic, graphify, neural_memory, sqlite_vec, pymilvus, llama_index, ragflow_sdk"
# Milvus/RAGFlow wrappers only come up under local-full; docker is only required there.
if [ "$INSTALL_PROFILE" = "local-full" ]; then
    "$PYTHON" "$PROJECT_ROOT/scripts/setup/verify_wrappers.py" --require-docker
else
    "$PYTHON" "$PROJECT_ROOT/scripts/setup/verify_wrappers.py"
fi
mkdir -p "$PROJECT_ROOT/integrations/neural-memory/data"
"$PYTHON" "$PROJECT_ROOT/scripts/setup/setup_umc.py" >/dev/null
echo -e "  ${GREEN}✓${NC} Python $("$PYTHON" -c 'import sys; print(sys.version.split()[0])') at $PROJECT_ROOT/.venv"

echo ""

# =============================================================================
# 3. GRAPHIFY INSTALLATION (from cloned source, NOT from PyPI)
# =============================================================================
echo -e "${BOLD}[3/12] Installing Graphify (local source)...${NC}"

GRAPHIFY_SRC="$PROJECT_ROOT/integrations/graphify"

echo -e "  ${GREEN}✓${NC} graphify resolved from local source ($GRAPHIFY_SRC)"

# ── Materialize the Obsidian vault (cerebro/) from shipped templates ────────
# Idempotent: skips if the vault already exists. Creates 70+ empty directories
# that are filled by the pipelines in use (sessoes/, decisoes/, inbox/, grafo/).
# The schema's source of truth is templates/vault/vault-manifest.json.
materialize_vault() {
    if [ -f "$VAULT_DIR/vault-manifest.json" ] && [ -d "$VAULT_DIR/cortex/temporal" ]; then
        echo -e "  ${GREEN}✓${NC} vault already materialized at $VAULT_DIR"
        return 0
    fi
    echo -e "  Materializing obsidian-mind v6.1.0 vault at $VAULT_DIR..."

    # 1. Shipped templates (hub docs, models, panels, sectors, subvaults, configs)
    if [ -d "$PROJECT_ROOT/templates/vault" ]; then
        cp -r "$PROJECT_ROOT/templates/vault/." "$VAULT_DIR/"
    else
        echo -e "  ${YELLOW}!${NC} templates/vault/ not found; creating empty structure"
        mkdir -p "$VAULT_DIR"
    fi

    # 2. Directory structure (created empty, populated in use)
    mkdir -p \
        "$VAULT_DIR/cerebelo/anual" \
        "$VAULT_DIR/cerebelo/diario" \
        "$VAULT_DIR/cerebelo/mensal" \
        "$VAULT_DIR/cerebelo/padroes" \
        "$VAULT_DIR/cerebelo/semanal" \
        "$VAULT_DIR/cerebelo/sessoes" \
        "$VAULT_DIR/cortex/frontal/brain" \
        "$VAULT_DIR/cortex/frontal/decisoes" \
        "$VAULT_DIR/cortex/frontal/org/people" \
        "$VAULT_DIR/cortex/frontal/org/teams" \
        "$VAULT_DIR/cortex/frontal/projetos" \
        "$VAULT_DIR/cortex/frontal/rascunhos" \
        "$VAULT_DIR/cortex/frontal/trabalho/active" \
        "$VAULT_DIR/cortex/frontal/trabalho/ativo" \
        "$VAULT_DIR/cortex/frontal/trabalho/pipeline" \
        "$VAULT_DIR/cortex/insula/conflitos" \
        "$VAULT_DIR/cortex/insula/saude" \
        "$VAULT_DIR/cortex/occipital/capturas-visuais" \
        "$VAULT_DIR/cortex/occipital/grafo" \
        "$VAULT_DIR/cortex/parietal/inbox/visual" \
        "$VAULT_DIR/cortex/parietal/inbox/documents" \
        "$VAULT_DIR/cortex/parietal/referencias/analises" \
        "$VAULT_DIR/cortex/temporal/_global" \
        "$VAULT_DIR/cortex/temporal/hipocampo" \
        "$VAULT_DIR/cortex/temporal/arquivo" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/agent_skills" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/atlas" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/atoms" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/decision" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/error_handling" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/infrastructure" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/preferences" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/project_management" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/security" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/testing" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/test_swarm" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/test_topic" \
        "$VAULT_DIR/diencefalo/roteamento" \
        "$VAULT_DIR/tronco/infra/obsidian-trash" \
        "$VAULT_DIR/attachments"

    # 3. Vault .gitignore (runtime regenerated, never commit)
    if [ ! -f "$VAULT_DIR/.gitignore" ]; then
        cat > "$VAULT_DIR/.gitignore" <<'VAULT_EOF'
# Vault runtime — regenerated, do not commit
.smart-env/
.claude-flow/
.obsidian/
graphify-out/
cortex/occipital/grafo/cache/
cortex/occipital/grafo/graphify-out/
cortex/occipital/grafo/manifest.json
cortex/occipital/grafo/.rebuild.lock
cortex/occipital/grafo/.pending_changes
cortex/temporal/**/neuronio-*.md
cerebelo/sessoes/
cortex/frontal/decisoes/
cortex/frontal/projetos/
cortex/frontal/trabalho/
cortex/insula/
cortex/parietal/inbox/
attachments/
VAULT_EOF
    fi

    local n_files n_dirs
    n_files=$(find "$VAULT_DIR" -type f 2>/dev/null | wc -l)
    n_dirs=$(find "$VAULT_DIR" -type d 2>/dev/null | wc -l)
    echo -e "  ${GREEN}✓${NC} vault materialized ($n_files shipped files, $n_dirs directories)"
}
materialize_vault

# Python dependencies (requirements.txt) already installed in step 2.

# Index the vault with semantic extraction if API key is available, otherwise AST-only
echo -e "  Indexing cerebro/ vault..."
if [ -n "${GOOGLE_API_KEY:-}" ] || [ -n "${GEMINI_API_KEY:-}" ]; then
    echo -e "  Using Gemini for semantic extraction..."
    "$GRAPHIFY" "$VAULT_DIR" 2>&1 | tail -3
elif [ "${SINAPSE_OLLAMA:-0}" = "1" ] && curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e "  Ollama detected. Using qwen2.5-coder:3b for semantic extraction..."
    OLLAMA_MODEL=qwen2.5-coder:3b "$GRAPHIFY" "$VAULT_DIR" --backend ollama 2>&1 | tail -3
else
    echo -e "  Using fast AST-only (tree-sitter + Leiden clustering)..."
    "$GRAPHIFY" update "$VAULT_DIR" 2>&1 | tail -3
fi

if [ -f "$GRAPHIFY_OUT/graph.json" ]; then
    NODE_COUNT=$("$PYTHON" -c "import json; g=json.load(open('$GRAPHIFY_OUT/graph.json')); print(len(g.get('nodes',[])))" 2>/dev/null || echo "?")
    echo -e "  ${GREEN}✓${NC} Knowledge graph generated ($NODE_COUNT nodes)"
else
    echo -e "  ${RED}✗${NC} Failed to generate graph.json"
    exit 1
fi
"$PYTHON" "$PROJECT_ROOT/scripts/graph/build_hnsw.py"

echo ""

# =============================================================================
# 4. REGISTRATION IN DETECTED AGENTS
# =============================================================================
echo -e "${BOLD}[4/12] Registering skills in agents...${NC}"

# Associative array: detection command → graphify platform
# Some agents don't have a detectable CLI (Cursor, Copilot) — we use a file path
declare -A AGENT_DETECTORS=(
    # Detectable CLI commands
    ["hermes"]="hermes"
    ["claude"]="claude"
    ["codex"]="codex"
    ["opencode"]="opencode"
    ["gemini"]="gemini"
    ["aider"]="aider"
)

# Agents by configuration file (no detectable CLI)
declare -A AGENT_CONFIG_FILES=(
    ["copilot"]="$HOME/.github-copilot/hosts.json"
    ["cursor"]="$HOME/.cursor/rules/"
    ["openclaw"]="$HOME/.claw/config.yaml"
    ["trae"]="$HOME/.trae/config.json"
    ["kiro"]="$HOME/.kiro/config.json"
    ["antigravity"]="$HOME/.antigravity/config.json"
)

echo -e "  Detecting agents..."

# ── CLI agents ───────────────────────────────────────────────────────
for agent in "${!AGENT_DETECTORS[@]}"; do
    if [[ " ${SKIP_AGENTS[*]:-} " == *" $agent "* ]]; then
        continue
    fi
    if command -v "$agent" &>/dev/null; then
        platform="${AGENT_DETECTORS[$agent]}"
        echo -e "  ${GREEN}✓${NC} $agent → registering skill..."
        graphify install --platform "$platform" 2>&1 | tail -1
    fi
done

# ── Config-file agents ──────────────────────────────────────────────
for agent in "${!AGENT_CONFIG_FILES[@]}"; do
    if [[ " ${SKIP_AGENTS[*]:-} " == *" $agent "* ]]; then
        continue
    fi
    config_path="${AGENT_CONFIG_FILES[$agent]}"
    if [ -e "$config_path" ]; then
        echo -e "  ${GREEN}✓${NC} $agent (detected via config)"
        case "$agent" in
            copilot)
                graphify install --platform copilot 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registered" || echo -e "    ${YELLOW}⊘${NC} failed to register"
                ;;
            cursor)
                graphify cursor install 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registered" || echo -e "    ${YELLOW}⊘${NC} failed to register"
                ;;
            openclaw)
                graphify install --platform claw 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registered" || echo -e "    ${YELLOW}⊘${NC} failed to register"
                ;;
            trae)
                graphify install --platform trae 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registered" || echo -e "    ${YELLOW}⊘${NC} failed to register"
                ;;
            kiro)
                graphify kiro install 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registered" || echo -e "    ${YELLOW}⊘${NC} failed to register"
                ;;
            antigravity)
                graphify antigravity install 2>/dev/null && echo -e "    ${GREEN}✓${NC} skill registered" || echo -e "    ${YELLOW}⊘${NC} failed to register"
                ;;
        esac
    fi
done
echo ""

# ── Hermes-specific configuration ──────────────────────────────────
if command -v hermes &>/dev/null; then
    echo -e "  ${BOLD}Configuring Hermes...${NC}"
    if [ -d "$HOME/.hermes/skills/" ]; then
        cp "$PROJECT_ROOT/docs/skills/sinapse-consulta.md" "$HOME/.hermes/skills/sinapse-consulta.md" 2>/dev/null && \
            echo -e "    ${GREEN}✓${NC} sinapse-consulta skill"
    fi
    if [ -d "$HOME/.hermes/plugins/" ]; then
        mkdir -p "$HOME/.hermes/plugins/sinapse-memory/"
        cp "$PROJECT_ROOT/plugins/hermes/sinapse-memory.py" "$HOME/.hermes/plugins/sinapse-memory/__init__.py" 2>/dev/null && \
            echo -e "    ${GREEN}✓${NC} sinapse-memory plugin"
    fi
fi

echo ""

# =============================================================================
# 5. CLAUDE-MEM INSTALLATION (native npx, global data)
# =============================================================================
echo -e "${BOLD}[5/12] Installing claude-mem (native npx, global data)...${NC}"

# claude-mem uses the native installation (npx/marketplace) to keep hooks and
# worker compatible with upstream. The official temporal runtime is global and
# multi-project, with data in ~/.claude-mem.

CLAUDE_MEM_VERSION="13.6"
CLAUDE_MEM_NPX="npx -y claude-mem@${CLAUDE_MEM_VERSION}"
CLAUDE_MEM_DATA_DIR="$HOME/.claude-mem"
CLAUDE_MEM_DB="$CLAUDE_MEM_DATA_DIR/claude-mem.db"
CLAUDE_MEM_MODELS="$CLAUDE_MEM_DATA_DIR/models"
mkdir -p "$CLAUDE_MEM_DATA_DIR" "$CLAUDE_MEM_MODELS"

# Detects installed IDEs (same criteria as claude-mem's detectInstalledIDEs)
# and runs the native install for EACH. Native ids: claude-code, gemini-cli,
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
    echo -e "  ${YELLOW}⊘${NC}  No IDE detected (Claude Code, Gemini, Codex, Cursor, Windsurf, OpenCode, OpenClaw...)."
else
    echo -e "  IDEs detected: ${INSTALLED_IDES[*]}"
    
    # Intelligent memory provider detection (avoids Claude quota blocks)
    MEM_PROVIDER="claude"
    if [ -n "${GEMINI_API_KEY:-}" ] || [ -n "${GOOGLE_API_KEY:-}" ]; then
        MEM_PROVIDER="gemini"
        echo -e "  ${BLUE}ℹ${NC} Gemini API Key detected. Configuring claude-mem to use Gemini."
    fi

    for ide in "${INSTALLED_IDES[@]}"; do
        echo -e "  Installing native hooks for ${ide}..."
        CLAUDE_MEM_DATA_DIR="$CLAUDE_MEM_DATA_DIR" \
        FASTEMBED_CACHE_PATH="$CLAUDE_MEM_MODELS" \
        $CLAUDE_MEM_NPX install --ide "$ide" --runtime worker --provider "$MEM_PROVIDER" --no-auto-start 2>&1 | tail -2
        echo -e "  ${GREEN}✓${NC} $ide configured"
        
        if [ "$ide" = "copilot-cli" ]; then
            # Tailer is the official capture source for Copilot (IDE/CLI); we
            # don't force a wrapper to avoid drift with real user binaries.
            if [ -L "$HOME/.local/bin/copilot" ] && [ "$(readlink -f "$HOME/.local/bin/copilot")" = "$PROJECT_ROOT/scripts/capture/copilot-wrapper.sh" ]; then
                rm -f "$HOME/.local/bin/copilot"
                echo -e "  ${GREEN}✓${NC} legacy copilot wrapper removed (official tailer)"
            fi
            echo -e "  ${GREEN}✓${NC} copilot capture via capture-tailer (IDE transcripts and CLI fallback)"
        fi
    done

    # Sync the Gemini key with the global claude-mem settings.json.
    if [ "$MEM_PROVIDER" = "gemini" ]; then
        G_KEY="${GEMINI_API_KEY:-${GOOGLE_API_KEY:-}}"
        if [ -n "$G_KEY" ]; then
            # Use python for a safe JSON merge instead of sed.
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
	" 2>/dev/null && echo -e "  ${GREEN}✓${NC} Gemini key synced with global claude-mem"
        fi
    fi
    # Modern Gemini (>=0.4x) only runs "trusted" hooks. The native installer
    # does NOT register trust — we do it here for capture without manual intervention.
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
console.log("  gemini trusted_hooks updated");
GEMTRUST
        echo -e "  ${GREEN}✓${NC} Gemini trusted_hooks registered"
    fi

    if [ -d "$HOME/.codex" ]; then
        "$PYTHON" "$PROJECT_ROOT/scripts/setup/install_codex_claude_mem_hooks.py" >/dev/null
        echo -e "  ${GREEN}✓${NC} Codex hooks registered for global claude-mem"
    fi
fi

if [ -f "$CLAUDE_MEM_DB" ]; then
    OBS_COUNT="$(sqlite3 "$CLAUDE_MEM_DB" "SELECT COUNT(*) FROM observations;" 2>/dev/null || echo "?")"
    echo -e "  ${GREEN}✓${NC} Global claude-mem database preserved ($OBS_COUNT observations)"
else
    echo -e "  ${YELLOW}⊘${NC}  Global claude-mem database does not exist yet; will be created on first start."
fi

echo -e "  ${GREEN}✓${NC} claude-mem configured for global data ($CLAUDE_MEM_DATA_DIR, worker :37700)"
echo ""

# =============================================================================
# 6. NEURAL MEMORY INSTALLATION (spreading activation — associative, from source)
# =============================================================================
echo -e "${BOLD}[6/12] Installing NeuralMemory (spreading activation, local source)...${NC}"

NEURAL_MEMORY_SRC="$PROJECT_ROOT/integrations/neural-memory"

echo -e "  ${GREEN}✓${NC} NeuralMemory resolved from local source ($NEURAL_MEMORY_SRC)"

# Check if the CLI is available
if [ -x "$NMEM" ]; then
    echo -e "  ${GREEN}✓${NC} nmem $("$NMEM" --version 2>/dev/null || echo 'OK')"
else
    echo -e "  ${YELLOW}⊘${NC}  nmem CLI not found. Check PATH: ~/.local/bin"
fi

echo ""

# =============================================================================
# 7. RTK CONFIGURATION (from cloned source — Rust)
# =============================================================================
echo -e "${BOLD}[7/12] Compiling RTK (local source)...${NC}"

RTK_SRC="$PROJECT_ROOT/integrations/rtk"
RUST_TOOLCHAIN="1.95.0"
CARGO_BIN="$(command -v cargo 2>/dev/null || true)"

# A cargo binary without a working toolchain isn't enough. In that case,
# install a pinned toolchain inside the project, without touching the user's HOME.
if [ -z "$CARGO_BIN" ] || ! "$CARGO_BIN" --version >/dev/null 2>&1; then
    echo -e "  Installing Rust $RUST_TOOLCHAIN in .tools..."
    export RUSTUP_HOME="$PROJECT_ROOT/.tools/rustup"
    export CARGO_HOME="$PROJECT_ROOT/.tools/cargo"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain "$RUST_TOOLCHAIN" --no-modify-path
    CARGO_BIN="$CARGO_HOME/bin/cargo"
    echo -e "  ${GREEN}✓${NC} Local Rust installed"
fi

# Compile from source
cd "$RTK_SRC"
if $FORCE || [ ! -f "target/release/rtk" ]; then
    echo -e "  Compiling RTK (cargo build --release)..."
    "$CARGO_BIN" build --locked --release 2>&1 | tail -1
    echo -e "  ${GREEN}✓${NC} RTK compiled"
else
    echo -e "  ${GREEN}✓${NC} RTK already compiled"
fi

echo -e "  ${GREEN}✓${NC} RTK $(./target/release/rtk --version 2>/dev/null | awk '{print $2}') available in project"

# Hermes plugin — RTK native hook
if [ -d "$HOME/.hermes/plugins/" ]; then
    mkdir -p "$HOME/.hermes/plugins/rtk-rewrite/"
    cp "$RTK_SRC/hooks/hermes/rtk-rewrite/"* "$HOME/.hermes/plugins/rtk-rewrite/" 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} RTK plugin (native hook) copied to Hermes"
fi

cd "$PROJECT_ROOT"

echo ""

# =============================================================================
# 8. MCP CONFIGURATION (GRAPHIFY + CLAUDE-MEM)
# =============================================================================
echo -e "${BOLD}[8/12] Configuring MCP servers...${NC}"

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
    # Replace placeholder with the real path
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

    echo -e "  ${GREEN}✓${NC} MCP configs generated at $MCP_DIR"
else
    echo -e "  ${YELLOW}⊘${NC}  Hermes not detected, MCP configs skipped"
fi

echo ""

# =============================================================================
# 9. PERIODIC SYNC CRON
# =============================================================================
echo -e "${BOLD}[9/12] Configuring sync cron...${NC}"

PY_CRON=".venv/bin/python"
CRON_SYNC_JOB="0 */6 * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && ./scripts/graph/build-graph.sh >> logs/sync.log 2>&1"
CRON_AUDIT_JOB="0 * * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/health/audit_memory.py --fix >> logs/audit.log 2>&1"
CRON_BACKUP_JOB="0 3 * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/health/backup_databases.py >> logs/backup.log 2>&1"
CRON_DREAM_JOB="0 2 * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/dream/dream_cycle.py --once --real >> logs/dream-cycle.log 2>&1"
CRON_MONTHLY_JOB="15 3 1 * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/dream/monthly_synthesizer.py --real >> logs/monthly-synthesizer.log 2>&1"
CRON_YEARLY_JOB="30 3 1 1 * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/dream/yearly_synthesizer.py --real >> logs/yearly-synthesizer.log 2>&1"
CRON_VECTOR_SUMMARY_JOB="45 3 * * * SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && if [ \"\${VECTOR_BACKEND:-sqlite}\" = \"milvus\" ]; then $PY_CRON scripts/maintenance/vector-sync.py --collection summary_vectors --json >> logs/vector-sync.log 2>&1; fi"

# Drain quarantine (archived=2) weekly. Runs Sunday at 04:00
# (between backup 03:00 and vector-sync 03:45). This drains ~95% of stuck
# obs; what remains goes to archived=3 terminal after 30d.
CRON_QUARANTINE_DRAIN_JOB="0 4 * * 0 SINAPSE_HOME=$PROJECT_ROOT && export SINAPSE_HOME && cd \$SINAPSE_HOME && $PY_CRON scripts/health/reprocess_quarantine.py --max-age-days 7 >> logs/quarantine-drain.log 2>&1"

if command -v crontab &>/dev/null; then
    # Remove legacy/duplicate variants and install a single canonical entry.
    CRON_TMP=$(mktemp)
    crontab -l 2>/dev/null \
        | grep -vF "# Hive-Mind — sync vault → graph a cada 6h" \
        | grep -vF "# Hive-Mind — audit vault → SQLite hourly" \
        | grep -vF "# Hive-Mind — backup SQLite diario" \
        | grep -vF "# Hive-Mind — Dream Cycle diario" \
        | grep -vF "# Hive-Mind — sintese mensal" \
        | grep -vF "# Hive-Mind — sintese anual" \
        | grep -vF "# Hive-Mind — vector sync summaries" \
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
        echo "# Hive-Mind — sintese mensal"
        echo "$CRON_MONTHLY_JOB"
        echo "# Hive-Mind — sintese anual"
        echo "$CRON_YEARLY_JOB"
        echo "# Hive-Mind — vector sync summaries"
        echo "$CRON_VECTOR_SUMMARY_JOB"
        echo "# Hive-Mind — quarantine drain semanal"
        echo "$CRON_QUARANTINE_DRAIN_JOB"
    } | crontab -
    rm -f "$CRON_TMP"
    echo -e "  ${GREEN}✓${NC} Cron configured without duplicates (sync, audit, backup, Dream Cycle, vector sync)"
else
    echo -e "  ${YELLOW}⊘${NC}  crontab not available. Run scripts/graph/build-graph.sh, scripts/health/backup_databases.py and scripts/dream/dream_cycle.py manually."
fi

echo ""

# =============================================================================
# 10. SINAPSE-MEMORY PLUGIN (HERMES)
# =============================================================================
echo -e "${BOLD}[10/12] Installing sinapse-memory plugin...${NC}"

if command -v hermes &>/dev/null && [ -d "$HOME/.hermes/plugins/" ]; then
    PLUGIN_DIR="$HOME/.hermes/plugins/sinapse-memory"
    mkdir -p "$PLUGIN_DIR"

    # Copy plugin from the project
    if [ -f "$PROJECT_ROOT/plugins/hermes/sinapse-memory.py" ]; then
        cp "$PROJECT_ROOT/plugins/hermes/sinapse-memory.py" "$PLUGIN_DIR/__init__.py"
    fi

    # plugin.yaml
    cat > "$PLUGIN_DIR/plugin.yaml" << 'PLUGINEOF'
name: sinapse-memory
description: >
  Bidirectional Hermes ↔ Obsidian vault integration via Sinapse Agent.
  Multi-backend search: claude-mem (semantic Chroma + FTS5) → Graphify (structural Leiden).
  Writes decisions and learnings to the vault with YAML frontmatter + WikiLinks.
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

    echo -e "  ${GREEN}✓${NC} sinapse-memory plugin (multi-backend)"
else
    echo -e "  ${YELLOW}⊘${NC}  Hermes not detected"
fi

echo ""

# ── INTELLIGENCE CONFIGURATION (Dream Cycle) ───────────────────────────────
echo -e "${BOLD}[11/12] Configuring Dream Cycle intelligence...${NC}"

# Ensures that .env.example contains the per-role LLM block (idempotent).
# The block lives versioned at config/env.roles.example — single source of truth.
if [ -f "$PROJECT_ROOT/config/env.roles.example" ] && [ -f "$PROJECT_ROOT/.env.example" ]; then
    if ! grep -q "^HIVE_GRAPHIFY_PROVIDER=" "$PROJECT_ROOT/.env.example"; then
        printf '\n' >> "$PROJECT_ROOT/.env.example"
        cat "$PROJECT_ROOT/config/env.roles.example" >> "$PROJECT_ROOT/.env.example"
        echo -e "  ${GREEN}✓${NC} Per-role LLM block added to .env.example"
    fi
fi

if [ -n "$PROVIDER" ] && [ -n "$MODEL" ]; then
    echo -e "  Saving provider ($PROVIDER) and model ($MODEL) to .env..."
    # Ensures that .env exists
    [ -f "$PROJECT_ROOT/.env" ] || cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    # Save to .env using python
    "$PYTHON" -c "import sys; sys.path.append('$PROJECT_ROOT'); from core.auth import save_env; save_env('HIVE_DREAMER_PROVIDER', '$PROVIDER'); save_env('HIVE_DREAMER_MODEL', '$MODEL')"
    echo -e "  ${GREEN}✓${NC} Provider and model saved (Dreamer role)."
    echo -e "  The Graphify, Vision, and Synthesis roles inherit this model by default;"
    echo -e "  tune per role (and fallbacks) with: python3 scripts/setup/setup-brain.py"
else
    echo -e "  No AI provider/model provided via arguments."
    echo -e "  The configuration can be done at the end of the installation or later."
fi
echo ""

# 12. EXTERNAL AGENT CONFIGURATION (via MCP + templates)
# =============================================================================
echo -e "${BOLD}[12/12] Configuring external agents (MCP + CLI)...${NC}"

# Ensure execute permissions on all scripts and hooks
chmod +x $(find "$PROJECT_ROOT/scripts" -name "*.sh") 2>/dev/null || true
chmod +x $(find "$PROJECT_ROOT/scripts" -name "*.py") 2>/dev/null || true
chmod +x "$PROJECT_ROOT/cerebro/tronco/infra/agentes/.claude/scripts/"*.py 2>/dev/null || true

# MCP registration delegated to the standalone script (idempotent, safe merge).
# Can be re-run at any time: ./scripts/setup/register-mcp.sh
if ! PROJECT_ROOT="$PROJECT_ROOT" bash "$PROJECT_ROOT/scripts/setup/register-mcp.sh"; then
    echo -e "  ${YELLOW}⊘${NC} No external agent detected. Use scripts/services/sinapse-write.py via CLI."
fi

# AGENTS.md template for Codex lives in the Tronco, without creating .codex at the top.
if command -v codex &>/dev/null && [ -f "$PROJECT_ROOT/cerebro/tronco/infra/agentes/.codex/AGENTS.md" ]; then
    mkdir -p "$VAULT_DIR/tronco/infra/agentes/.codex"
    cp "$PROJECT_ROOT/cerebro/tronco/infra/agentes/.codex/AGENTS.md" "$VAULT_DIR/tronco/infra/agentes/.codex/AGENTS.md" 2>/dev/null || true
fi

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}Checking integrity...${NC}"
"$PYTHON" "$PROJECT_ROOT/scripts/setup/install_services.py" install

# Model bridge: if the `claude_mem` role was configured in setup-brain,
# apply that provider/model to claude-mem (via /api/settings + seed). Exits
# cleanly if no role is configured (uses claude-mem's default). #modelo
"$PYTHON" "$PROJECT_ROOT/scripts/setup/sync-claude-mem-provider.py" 2>&1 | sed 's/^/  /' || true

if "$PYTHON" "$PROJECT_ROOT/scripts/services/sinapse-write.py" health >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Health check: backends operational"
else
    echo -e "  ${YELLOW}⊘${NC}  Health check: some backends offline"
    echo -e "  Run: python3 scripts/services/sinapse-write.py health"
fi

# Optional FalkorDB check (Graphiti — temporal lobe).
# If FalkorDB isn't responding, the brain automatically uses the JSON-lines
# fallback; it doesn't block the installation.
echo ""
echo -e "${BOLD}Graphiti (temporal lobe):${NC}"
if "$PYTHON" -c "
import os, sys
sys.path.insert(0, '$PROJECT_ROOT')
try:
    from integrations.graphiti import assert_health
    h = assert_health()
    if h['falkordb']:
        print('  OK: FalkorDB at', os.environ.get('FALKORDB_HOST', 'localhost'))
    else:
        print('  WARN: FalkorDB offline — brain will use JSON-lines fallback at')
        print('        cerebro/cortex/temporal/_global/grafo.jsonl')
        sys.exit(0)
except Exception as e:
    print('  WARN: Graphiti could not be checked:', e)
    sys.exit(0)
"; then
    :
else
    echo -e "  ${YELLOW}⊘${NC}  Graphiti check failed (non-blocking)"
fi
echo ""

# =============================================================================
# Validation per profile and real suite (see docs/12)
# =============================================================================
echo -e "${BOLD}[Validation] Profile=${INSTALL_PROFILE} — validating services...${NC}"

# Enable additional local services under local-full. local-min keeps only
# claude-mem (already started by install_services.py) and the graphify
# watchdog, which are safe even without extra GPU/disk.
if [ "$INSTALL_PROFILE" = "local-full" ]; then
    echo -e "  ${BOLD}local-full profile:${NC} enabling Milvus + FalkorDB + RAGFlow (docker)"
    if [ -f "$PROJECT_ROOT/integrations/milvus/docker-compose.yml" ]; then
        (cd "$PROJECT_ROOT/integrations/milvus" && docker compose up -d)             && echo -e "  ${GREEN}OK${NC} Milvus started"             || echo -e "  ${YELLOW}WARN${NC} Milvus did not start (docker unavailable or profile without docker)"
    fi
    if [ -f "$PROJECT_ROOT/integrations/ragflow/docker-compose.yml" ]; then
        (cd "$PROJECT_ROOT/integrations/ragflow" && docker compose up -d)             && echo -e "  ${GREEN}OK${NC} RAGFlow started"             || echo -e "  ${YELLOW}WARN${NC} RAGFlow did not start (optional under local-full)"
    fi
    # FalkorDB was already started by install_services.py when available; we
    # only reinforce the warning if it isn't responding.
    if ! "$PYTHON" -c "import socket,os; s=socket.socket(); s.settimeout(1); s.connect((os.environ.get('FALKORDB_HOST','localhost'), int(os.environ.get('FALKORDB_PORT','6379'))))" 2>/dev/null; then
        echo -e "  ${YELLOW}WARN${NC} FalkorDB offline — brain uses JSON-lines fallback"
    fi
else
    echo -e "  local-min profile: keeping only claude-mem + graphify-watch"
    echo -e "  To start Milvus/FalkorDB/RAGFlow later, use:"
    echo -e "    ${BOLD}./install.sh --profile=local-full --with-real-tests${NC}"
fi

# Migrations: re-apply schema/vectors idempotently. CRR-safety (B1) is
# already guaranteed by ensure_migrations; here we only reinforce that it ran.
"$PYTHON" -c "
import os, sys
sys.path.insert(0, '$PROJECT_ROOT')
from core.database import ensure_migrations, get_connection
conn = get_connection()
ensure_migrations(conn)
conn.close()
print('  OK: schema/vector migrations applied (idempotent)')
" 2>&1 | sed 's/^/  /' || echo -e "  ${YELLOW}WARN${NC} migrations could not be validated"

# MCP per agent, idempotent and preserving external configs.
"$PROJECT_ROOT/scripts/setup/register-mcp.sh" 2>&1 | sed 's/^/  /' || true
echo ""

# Real smoke for the knowledge front (--with-real-tests). Cleanly skips
# offline services and only fails when a real (non-mock) test breaks.
if $WITH_TESTS; then
    echo -e "${BOLD}Running the full test suite...${NC}"
    if ./tests/run_all.sh; then
        echo -e "  ${GREEN}✓${NC} All tests passed successfully!"
    else
        echo -e "  ${RED}✗${NC} Some tests failed!"
        exit 1
    fi
    echo ""
fi

if $WITH_REAL_TESTS; then
    echo -e "${BOLD}Running real knowledge suite — real backends, no mock...${NC}"
    if [ -x "$PROJECT_ROOT/tests/run_real_knowledge.sh" ]; then
        if "$PROJECT_ROOT/tests/run_real_knowledge.sh" --report "$PROJECT_ROOT/logs/k9-real-suite-report.md" 2>&1 | tail -40; then
            echo -e "  ${GREEN}OK${NC} real knowledge suite executed"
        else
            echo -e "  ${RED}ERROR${NC} real suite returned !=0; fix the real knowledge suite before considering the install valid"
            exit 1
        fi
    else
        echo -e "  ${RED}ERROR${NC} tests/run_real_knowledge.sh not found/executable"
        exit 1
    fi
    echo ""
fi

# =============================================================================
# Final report with paths, ports, models, and health
# =============================================================================
REPORT="$PROJECT_ROOT/logs/install-report.md"
mkdir -p "$(dirname "$REPORT")"
{
    echo "# Hive-Mind — Installation Report"
    echo ""
    echo "- Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "- Profile: \`${INSTALL_PROFILE}\`"
    echo "- With real tests: \`${WITH_REAL_TESTS}\`"
    echo "- With full tests:  \`${WITH_TESTS}\`"
    echo ""
    echo "## Paths"
    echo ""
    echo "| Resource | Path |"
    echo "|---|---|"
    echo "| Obsidian Vault | \`${VAULT_DIR}\` |"
    echo "| Knowledge Graph | \`${GRAPHIFY_OUT}/graph.json\` |"
    echo "| Main database | \`${PROJECT_ROOT}/hive_mind.db\` |"
    echo "| claude-mem DB | \`${HOME}/.claude-mem/claude-mem.db\` |"
    echo "| Python venv | \`${PROJECT_ROOT}/.venv\` |"
    echo ""
    echo "## Ports and services"
    echo ""
    echo "| Service | Expected port | Status |"
    echo "|---|---:|---|"
    for svc in "claude-mem 37700" "sqlite-vec 37701" "api 37702" "mcp-http 37703"; do
        name="${svc% *}"; port="${svc##* }"
        if "$PYTHON" -c "import socket; s=socket.socket(); s.settimeout(0.5); s.connect(('127.0.0.1', ${port}))" 2>/dev/null; then
            echo "| ${name} | ${port} | online |"
        else
            echo "| ${name} | ${port} | offline (non-blocking) |"
        fi
    done
    echo ""
    echo "## Ollama models (installed when available)"
    echo ""
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        curl -s http://localhost:11434/api/tags | "$PYTHON" -c '
import json, sys
data = json.load(sys.stdin)
for m in data.get("models", []):
    print("- `" + m["name"] + "` (" + str(round(m["size"]/1e9, 1)) + " GB)")
'
    else
        echo "_Ollama offline on this host._"
    fi
    echo ""
    echo "## Health check"
    echo ""
    if "$PYTHON" "$PROJECT_ROOT/scripts/services/sinapse-write.py" health > "$REPORT.health" 2>&1; then
        sed 's/^/    /' "$REPORT.health" | head -40
    else
        echo "_Health check returned !=0 (see logs/install-report.md.health)._"
    fi
    echo ""
    echo "## Real validation"
    echo ""
    if $WITH_REAL_TESTS; then
        echo "- \`./tests/run_real_knowledge.sh --report logs/k9-real-suite-report.md\` executed with exit 0."
        echo "- Real suite report: \`logs/k9-real-suite-report.md\`."
    else
        echo "- Pass \`--with-real-tests\` to run the real knowledge suite."
        echo "- Command: \`./tests/run_real_knowledge.sh\`"
    fi
    echo ""
    echo "## Next steps"
    echo ""
    echo "1. Restart your agents (Claude Code, Codex CLI, etc.) to load the MCP."
    echo "2. Open Obsidian pointing to \`cerebro/\`."
    echo "3. Check the watcher: \`./scripts/services/start-watcher.sh status\`."
} > "$REPORT"
echo ""
echo -e "  ${GREEN}OK${NC} Final report written at: ${BOLD}$REPORT${NC}"

# Mini summary on stdout (for the user to see without opening the file)
echo ""
echo -e "  ${BOLD}Installation summary (profile ${INSTALL_PROFILE}):${NC}"
echo -e "    Vault:         ${BOLD}$VAULT_DIR${NC}"
echo -e "    Database:      ${BOLD}$PROJECT_ROOT/hive_mind.db${NC}"
echo -e "    Python:        ${BOLD}$PROJECT_ROOT/.venv/bin/python${NC}"
echo -e "    claude-mem:    ${BOLD}http://127.0.0.1:37700${NC}"
echo -e "    REST API:      ${BOLD}http://127.0.0.1:37702${NC}"
echo -e "    MCP HTTP:      ${BOLD}http://127.0.0.1:37703${NC}"
if $WITH_REAL_TESTS; then
    echo -e "    Real suite:    ${BOLD}executed (see logs)${NC}"
fi
echo ""

echo -e "${BOLD}${GREEN}║       Sinapse Agent installed successfully!          ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Obsidian Vault:  ${BOLD}$VAULT_DIR${NC}"
echo -e "  Knowledge Graph: ${BOLD}$GRAPHIFY_OUT/graph.json${NC}"
echo -e "  MCP Servers:     ${BOLD}$HOME/.hermes/mcp/${NC}"
echo ""
echo -e "  Open the folder ${BOLD}cerebro/${NC} in Obsidian as a vault."
echo -e "  Every file created/edited will be indexed automatically."
echo ""
echo -e "  ${YELLOW}Restart your agents to apply the changes.${NC}"
echo ""

# ── Post-installation notes ───────────────────────────────────────────────
echo -e "${BOLD}${BLUE}Post-installation notes:${NC}"
echo ""
echo -e "  ${BOLD}Obsidian:${NC} Open the cerebro/ folder as a vault in Obsidian."
echo -e "         Flatpak: flatpak run md.obsidian.Obsidian --vault \"$VAULT_DIR\""
echo -e "         In Settings > Files and links, enable 'Show hidden files'."
echo ""
echo -e "  ${BOLD}Ollama (models — downloaded automatically above when detected):${NC}"
echo -e "         ollama pull snowflake-arctic-embed2 # 1024d embeddings (core/LightRAG/Graphiti)"
echo -e "         ollama pull qwen2.5:3b           # Graphiti + LightRAG extraction (~1.9GB)"
echo -e "         ollama pull qwen2.5-coder:3b     # Graphify semantic extraction"
echo -e "         ollama pull minicpm-v4.6:latest  # Compact local vision (default)"
echo -e "         ollama pull gemma3:4b            # Vision/visual reasoning fallback (local-full)"
echo -e "         ollama pull deepseek-ocr:latest  # Optional dedicated OCR (SINAPSE_PULL_DEEPSEEK_OCR=1)"
echo -e "         ollama pull qwen2.5:7b           # High-quality local Graphiti (optional, ~4.7GB)"
echo -e "         ollama pull nomic-embed-text     # Lightweight embeddings (alternative)"
echo ""
echo -e "  ${BOLD}Disaster Recovery:${NC}"
echo -e "         ${BOLD}./scripts/utils/recover.sh${NC} — Checks/Rebuilds graph.json, restarts worker, health check"
echo ""
echo -e "  ${BOLD}API Keys (optional):${NC}"
echo -e "         Copy .env.example to .env and configure GOOGLE_API_KEY."
echo -e "         Gemini is used for high-quality semantic extraction."
echo ""
if $OLLAMA_OK; then
    echo -e "  ${BOLD}Ollama models installed:${NC}"
    curl -s http://localhost:11434/api/tags 2>/dev/null | "$PYTHON" -c "
import json, sys
for m in json.load(sys.stdin)['models']:
    print(f'         {m[\"name\"]:35s} {m[\"size\"]/1e9:.1f}GB')
"
fi
echo ""

# =============================================================================
# 13. CR-SQLite (optional vendor — multi-device sync via CRDT)
# =============================================================================
# Roadmap policy 0.2: external vendor at integrations/<name>/.
# Binary comes from https://github.com/vlcn-io/cr-sqlite/releases (pinned release).
# It is opt-in: controlled by HIVE_CRDT_SYNC=true in .env (default false).
CRSQLITE_VERSION="${CRSQLITE_VERSION:-0.16.3}"
CRSQLITE_DIR="$PROJECT_ROOT/integrations/crsqlite"

download_crsqlite_asset() {
    local asset=$1
    local url="https://github.com/vlcn-io/cr-sqlite/releases/download/v${CRSQLITE_VERSION}/${asset}"
    local tmp_dir; tmp_dir=$(mktemp -d)
    local zipfile="${tmp_dir}/${asset}"
    trap 'rm -rf "$tmp_dir"' RETURN

    echo -e "  Downloading ${url}"
    if ! curl --proto '=https' --tlsv1.2 -sSfL -o "$zipfile" "$url"; then
        echo -e "  ${YELLOW}!${NC} Failed to download ${asset} (network or release)."
        return 1
    fi

    # Extract only the binary named by upstream (from v0.16.1 the zip
    # already comes with the final .so/.dylib/.dll name, no rename).
    if command -v unzip >/dev/null 2>&1; then
        unzip -o -j "$zipfile" -d "$CRSQLITE_DIR" 2>/dev/null || {
            echo -e "  ${YELLOW}!${NC} unzip failed for ${asset}"
            return 1
        }
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c "
import zipfile, sys
with zipfile.ZipFile('$zipfile') as z:
    z.extractall('$CRSQLITE_DIR')
" || return 1
    else
        echo -e "  ${YELLOW}!${NC} No unzip or python3 available to extract."
        return 1
    fi
    return 0
}

download_crsqlite() {
    mkdir -p "$CRSQLITE_DIR"

    # Pick asset according to detected platform.
    local sys_name kernel
    sys_name=$(uname -s 2>/dev/null || echo "Linux")
    kernel=$(uname -m 2>/dev/null || echo "x86_64")

    local asset=""
    case "$sys_name" in
        Linux)
            case "$kernel" in
                x86_64|amd64)  asset="crsqlite-linux-x86_64.zip" ;;
                aarch64|arm64) asset="crsqlite-linux-aarch64.zip" ;;
                *) echo -e "  ${YELLOW}!${NC} Unsupported Linux architecture: $kernel"; return 1 ;;
            esac ;;
        Darwin)
            case "$kernel" in
                x86_64|amd64)  asset="crsqlite-darwin-x86_64.zip" ;;
                arm64|aarch64) asset="crsqlite-darwin-aarch64.zip" ;;
                *) echo -e "  ${YELLOW}!${NC} Unsupported Darwin architecture: $kernel"; return 1 ;;
            esac ;;
        *)
            echo -e "  ${YELLOW}!${NC} Unsupported OS for pre-compiled CR-SQLite: $sys_name"
            echo -e "         Build from source (Rust nightly + make loadable) or disable P8."
            return 1 ;;
    esac

    download_crsqlite_asset "$asset"
}

if [ -f "$CRSQLITE_DIR/crsqlite.so" ] || [ -f "$CRSQLITE_DIR/crsqlite.dylib" ] || [ -f "$CRSQLITE_DIR/crsqlite.dll" ]; then
    echo -e "${BOLD}[13] CR-SQLite vendor already present at $CRSQLITE_DIR — skipping download${NC}"
elif $FORCE || [ "${INSTALL_CRSQLITE:-false}" = "true" ]; then
    echo -e "${BOLD}[13] Downloading CR-SQLite v${CRSQLITE_VERSION} to integrations/crsqlite/...${NC}"
    if ! download_crsqlite; then
        echo -e "  ${YELLOW}!${NC} CR-SQLite NOT installed. P8 (multi-device sync) stays disabled."
        echo -e "         Enable later with: INSTALL_CRSQLITE=true bash install.sh"
    else
        echo -e "  ${GREEN}OK${NC} CR-SQLite v${CRSQLITE_VERSION} at $CRSQLITE_DIR"
        ls -la "$CRSQLITE_DIR" | grep -E "crsqlite\.(so|dylib|dll)" || true
    fi
else
    echo -e "${BOLD}[13] CR-SQLite (P8) - opt-in.${NC}"
    echo -e "         For multi-device sync via CRDT, run:"
    echo -e "           INSTALL_CRSQLITE=true bash install.sh"
    echo -e "         and set HIVE_CRDT_SYNC=true in .env. More at:"
    echo -e "           $CRSQLITE_DIR/README.md"
fi

# ── Langfuse / OpenTelemetry (P9) — opt-in ────────────────────────────────
# Distributed tracing opt-in for Dream Cycle, capture, and MCP. With empty
# keys, zero overhead (NoOp tracer). To start Langfuse locally and instrument:
echo -e "${BOLD}[14] Langfuse / OpenTelemetry (P9) - opt-in.${NC}"
echo -e "         For distributed tracing of scripts (Dream Cycle, capture, MCP):"
echo -e "           1. Start Langfuse:  ${BOLD}docker compose -f integrations/langfuse/docker-compose.yml up -d${NC}"
echo -e "           2. Create a project + copy keys at http://localhost:3100"
echo -e "           3. Add to .env: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST"
echo -e "         In prod use HTTPS (empty basic auth would leak keys over HTTP) + strong LANGFUSE_NEXTAUTH_SECRET/SALT:"
echo -e "           openssl rand -hex 32"
echo -e "         Without keys: zero overhead (traces dropped). See:"
echo -e "           integrations/langfuse/README.md"

echo ""

# ── Post-Installation Interactive Configuration (Optional) ───────────────────────
HAS_DREAMER=false
if [ -f "$PROJECT_ROOT/.env" ]; then
    # Checks if HIVE_DREAMER_PROVIDER is set and non-empty
    if grep -q "^HIVE_DREAMER_PROVIDER=" "$PROJECT_ROOT/.env" && [ -n "$(grep "^HIVE_DREAMER_PROVIDER=" "$PROJECT_ROOT/.env" | cut -d= -f2-)" ]; then
        HAS_DREAMER=true
    fi
fi

if [ "$HAS_DREAMER" = "false" ] && [ "$NON_INTERACTIVE" = "false" ] && [ -t 0 ]; then
    echo -e "${BOLD}${YELLOW}Intelligence Configuration (Brain Selector — all roles):${NC}"
    echo -e "  Configures provider/model/auth of ALL roles: Dreamer, Graphify, Vision, and Synthesis."
    echo -e "  Each role can use its own model (Gemini, OpenAI, Ollama, etc.) with optional fallback."
    echo ""
    read -p "  Do you want to configure your AI model and keys interactively now? [S/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[SsYy]$ ]] || [ -z "$REPLY" ]; then
        "$PROJECT_ROOT/scripts/setup/setup-brain.sh"
    else
        echo -e "  You can run this configuration later with: ${BOLD}./scripts/setup/setup-brain.sh${NC}"
        echo ""
    fi
fi
