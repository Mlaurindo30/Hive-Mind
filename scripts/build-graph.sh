#!/bin/bash
# Sinapse Agent — Rebuild graph.json from vault (cron-safe)
# Chamado pelo cron a cada 6h. Sem LLM, apenas tree-sitter + Leiden clustering.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT_DIR="$PROJECT_ROOT/cerebro"

cd "$PROJECT_ROOT" || exit 1

# Reindexa sem LLM (tree-sitter + regex + Leiden clustering)
graphify update "$VAULT_DIR" 2>&1
