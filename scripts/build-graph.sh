#!/bin/bash
# Sinapse Agent — Rebuild graph.json from vault (cron-safe)
# Chamado pelo cron a cada 6h. Sem LLM, apenas tree-sitter + Leiden clustering.
# Atomic write via temp file + rename (Fase 1.2).
set -euo pipefail

SINAPSE_HOME="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
VAULT_DIR="$SINAPSE_HOME/cerebro"
GRAPH_OUT="$VAULT_DIR/graphify-out"

cd "$SINAPSE_HOME" || exit 1

# Backup do graph atual
if [ -f "$GRAPH_OUT/graph.json" ]; then
    cp "$GRAPH_OUT/graph.json" "$GRAPH_OUT/graph.json.bak"
fi

# ── Papel Graphify (role-based LLM config) ───────────────────────────────────
# Lê HIVE_GRAPHIFY_PROVIDER/MODEL do .env; se ausentes, herda HIVE_DREAMER_*.
# Sem provedor compatível configurado, mantém o comportamento AST-only.
#
# Este script NÃO depende de core.auth.load_env() (que é o loader do lado
# Python e injeta em os.environ). Ele lê o .env diretamente via grep para
# poder exportar as chaves de API para o subprocesso `graphify extract`
# sem precisar inicializar um interpretador Python. Se a chave tiver
# '=' no valor (ex.: URLs com query string), o cut captura o restante
# da linha, o que é suficiente para o caso de uso atual.
# Vars já exportadas no shell têm PRECEDÊNCIA sobre o .env — paridade com o
# lado Python (os.environ vence) e com cron/CI que injetam env diretamente.
ENV_FILE="$SINAPSE_HOME/.env"
hive_env() {
    local shell_val="${!1:-}"
    if [ -n "$shell_val" ]; then
        printf '%s' "$shell_val"
        return
    fi
    if [ -f "$ENV_FILE" ]; then
        grep -E "^${1}=" "$ENV_FILE" | head -n1 | cut -d= -f2- || true
    fi
}

GRAPHIFY_PROVIDER="$(hive_env HIVE_GRAPHIFY_PROVIDER)"
GRAPHIFY_MODEL="$(hive_env HIVE_GRAPHIFY_MODEL)"
if [ -z "$GRAPHIFY_PROVIDER" ] || [ -z "$GRAPHIFY_MODEL" ]; then
    GRAPHIFY_PROVIDER="$(hive_env HIVE_DREAMER_PROVIDER)"
    GRAPHIFY_MODEL="$(hive_env HIVE_DREAMER_MODEL)"
fi

# Mapeia o provedor Hive-Mind para o backend equivalente do graphify
GRAPHIFY_BACKEND=""
case "$GRAPHIFY_PROVIDER" in
    google|gemini)        GRAPHIFY_BACKEND="gemini" ;;
    anthropic)            GRAPHIFY_BACKEND="claude" ;;
    openai)               GRAPHIFY_BACKEND="openai" ;;
    deepseek)             GRAPHIFY_BACKEND="deepseek" ;;
    ollama|ollama-cloud)  GRAPHIFY_BACKEND="ollama" ;;
    lmstudio)             GRAPHIFY_BACKEND="ollama"
                          export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:1234/v1}" ;;
esac

# Exporta a chave de API do provedor escolhido (nunca duplicada por papel)
export_key() {
    local v
    v="$(hive_env "$1")"
    if [ -n "$v" ]; then export "$1=$v"; fi
}
case "$GRAPHIFY_BACKEND" in
    gemini)   export_key GOOGLE_API_KEY; export_key GEMINI_API_KEY ;;
    claude)   export_key ANTHROPIC_API_KEY ;;
    openai)   export_key OPENAI_API_KEY ;;
    deepseek) export_key DEEPSEEK_API_KEY ;;
    ollama)   export_key OLLAMA_API_KEY ;;
esac

# Reindexa sem LLM (tree-sitter + regex + Leiden clustering)
graphify update "$VAULT_DIR" 2>&1

# Extração semântica opcional via papel Graphify (não bloqueia o build AST)
if [ -n "$GRAPHIFY_BACKEND" ] && [ -n "$GRAPHIFY_MODEL" ]; then
    echo "[graphify] Extração semântica via backend '$GRAPHIFY_BACKEND' (modelo: $GRAPHIFY_MODEL)..."
    if ! graphify extract "$VAULT_DIR" --backend "$GRAPHIFY_BACKEND" --model "$GRAPHIFY_MODEL" 2>&1; then
        echo "[graphify] Aviso: extração semântica falhou — grafo AST mantido." >&2
    fi
elif [ -n "$GRAPHIFY_PROVIDER" ]; then
    echo "[graphify] Provedor '$GRAPHIFY_PROVIDER' sem backend graphify equivalente — modo AST-only."
else
    echo "[graphify] Nenhum papel Graphify/Dreamer configurado — modo AST-only."
fi

# Incremental HNSW update
python3 -c "
import sys; sys.path.insert(0, '$(dirname "$0")/..')
try:
    from core.hnsw_index import incremental_update
    from core.database import get_connection
    conn = get_connection()
    # Use a simple hash-based pseudo-embedding for offline builds
    def hash_embed(text):
        import hashlib
        h = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        import struct
        vals = []
        for i in range(384):
            h, rem = divmod(h, 256)
            vals.append((rem - 128) / 128.0)
        norm = sum(v*v for v in vals)**0.5 or 1.0
        return [v/norm for v in vals]
    n = incremental_update(conn, hash_embed)
    conn.close()
    print(f'HNSW: {n} neurons indexed')
except Exception as e:
    print(f'HNSW skip: {e}')
" 2>/dev/null || true

# Verificar se o novo graph.json é válido
if python3 -c "import json; json.load(open('$GRAPH_OUT/graph.json'))" 2>/dev/null; then
    NODES=$(python3 -c "import json;g=json.load(open('$GRAPH_OUT/graph.json'));print(len(g.get('nodes',[])))")
    echo "graph.json valid — $NODES nodes — build completo"
else
    echo "ERRO: graph.json inválido, restaurando backup" >&2
    if [ -f "$GRAPH_OUT/graph.json.bak" ]; then
        mv "$GRAPH_OUT/graph.json.bak" "$GRAPH_OUT/graph.json"
        echo "Backup restaurado" >&2
    fi
    exit 1
fi

# Export causal edges
DB_PATH="$SINAPSE_HOME/hive_mind.db"
if [ -f "$DB_PATH" ]; then
    sqlite3 "$DB_PATH" "SELECT json_object('id', id, 'cause', cause_neuron_id, 'effect', effect_neuron_id, 'label', label, 'confidence', confidence) FROM causal_edges;" \
      | jq -s '.' > "$GRAPH_OUT/causal_edges.json" 2>/dev/null || echo '[]' > "$GRAPH_OUT/causal_edges.json"
else
    echo '[]' > "$GRAPH_OUT/causal_edges.json"
fi
echo "Causal edges exported to $GRAPH_OUT/causal_edges.json"
