#!/usr/bin/env bash
PROJECT_ROOT="/home/michel/Documentos/Projects/Hive-Mind"
export SINAPSE_HOME="$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT"
exec "$PROJECT_ROOT/.venv-sqlite-vec/bin/python3" "$PROJECT_ROOT/scripts/setup-dreamer.py"
