#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="${SINAPSE_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export SINAPSE_HOME="$PROJECT_ROOT"
exec "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/setup-brain.py"
