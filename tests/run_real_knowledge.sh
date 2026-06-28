#!/usr/bin/env bash
# Suíte de aceite da frente de conhecimento (docs/12 §K9) — backends reais, sem mock.
# Testes cujo serviço nomeado está offline PULAM (requires_service).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x "$PY" ] || PY="$(command -v python3)"
exec "$PY" -m pytest tests/real -m real -q --no-header "$@"
