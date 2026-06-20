#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export NEURAL_MEMORY_DIR="$ROOT/integrations/neural-memory/data"
exec "$ROOT/.venv/bin/nmem-mcp" "$@"
