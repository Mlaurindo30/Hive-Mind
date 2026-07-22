#!/usr/bin/env bash
# =============================================================================
# register-mcp.sh - thin wrapper (D009-R6)
#
# This script used to be 444 lines of product logic: provider detection, config
# paths, JSON and TOML merging, instruction injection, backups. All of that now
# lives in the Python package, in src/hive_mind/agents/**, where a single
# implementation serves POSIX and Windows alike.
#
# What remains is the only thing a shell script may own: find the executable,
# forward the arguments, preserve the streams, return the exit code.
#
# Every option the old script accepted is still accepted - by the CLI, not by
# this file. See src/hive_mind/agents/compat.py for why the translation lives
# there: a wrapper that reinterpreted its own arguments would be product logic
# again, in the place this delivery removed it from.
# =============================================================================
set -euo pipefail

if command -v hive-mind >/dev/null 2>&1; then
    exec hive-mind agents register "$@"
fi

# The bootstrap creates a virtual environment at the project root. That is the
# documented contract both installers rely on; nothing below is provider-aware.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${PROJECT_ROOT:-$(dirname "$(dirname "$SCRIPT_DIR")")}"

for relative in bin/hive-mind Scripts/hive-mind.exe; do
    candidate="$ROOT/.venv/$relative"
    [ -x "$candidate" ] && exec "$candidate" agents register "$@"
done

# Last resort: the package's own module entry point. Used only when the console
# script was not installed, and supported by the package itself.
for relative in bin/python Scripts/python.exe; do
    candidate="$ROOT/.venv/$relative"
    [ -x "$candidate" ] && exec "$candidate" -m hive_mind.cli agents register "$@"
done

cat >&2 <<EOF
hive-mind executable not found.

Looked for 'hive-mind' on PATH and under $ROOT/.venv.
Install the package first, for example:

    uv sync
    uv run hive-mind agents register --apply
EOF
exit 127
