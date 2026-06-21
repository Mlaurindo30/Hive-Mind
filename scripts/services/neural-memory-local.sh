#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export NEURAL_MEMORY_DIR="$ROOT/integrations/neural-memory/data"
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3)"
fi

exec "$PYTHON" "$ROOT/scripts/services/mcp-lifecycle.py" -- \
    "$ROOT/.venv/bin/nmem-mcp" "$@"
