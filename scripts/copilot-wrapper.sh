#!/usr/bin/env bash
# =============================================================================
# copilot-wrapper.sh — Wrapper para o Copilot CLI (IDE)
#
# Intercepta chamadas ao binário real do Copilot CLI, envia eventos de sessão
# ao worker do claude-mem (:37700) antes e depois da execução, e sanitiza
# toda informação sensível via sanitizer.py antes do envio.
#
# INSTALAÇÃO:
#   Adicione ao ~/.bashrc ou ~/.zshrc:
#     alias copilot="/home/michel/Documentos/Projects/Hive-Mind/scripts/copilot-wrapper.sh"
#   OU coloque em ~/.local/bin/copilot (precedência > binário real):
#     ln -sf /home/michel/Documentos/Projects/Hive-Mind/scripts/copilot-wrapper.sh ~/.local/bin/copilot
#
# DEPENDÊNCIAS:
#   - curl
#   - python3 (com scripts/sanitizer.py no mesmo diretório)
#   - Worker claude-mem rodando em localhost:37700
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
REAL_COPILOT="/home/michel/.config/Code/User/globalStorage/github.copilot-chat/copilotCli/copilot"
WORKER_HOST="${CLAUDE_MEM_WORKER_HOST:-127.0.0.1}"
WORKER_PORT="${CLAUDE_MEM_WORKER_PORT:-37700}"
WORKER_BASE="http://${WORKER_HOST}:${WORKER_PORT}"
PROJECT="${CAPTURE_BRIDGE_PROJECT:-Hive-Mind}"
PLATFORM="copilot"
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANITIZER="${SCRIPTS_DIR}/sanitizer.py"

# ---------------------------------------------------------------------------
# Gera session ID único para esta invocação
# ---------------------------------------------------------------------------
SESSION_ID="$(python3 -c "import uuid; print(str(uuid.uuid4()))")"
PROMPT_ARGS="${*:-copilot session}"
# sanitiza os argumentos antes de qualquer envio
PROMPT_CLEAN="$(echo "${PROMPT_ARGS}" | python3 "${SANITIZER}" 2>/dev/null || echo "${PROMPT_ARGS}")"

# ---------------------------------------------------------------------------
# Verifica se o worker está vivo (silenciosamente — não bloqueia o usuário)
# ---------------------------------------------------------------------------
worker_alive() {
    curl -s --max-time 2 "${WORKER_BASE}/api/health" > /dev/null 2>&1
}

# ---------------------------------------------------------------------------
# POST seguro ao worker (falha silenciosa para não atrapalhar o usuário)
# ---------------------------------------------------------------------------
post_event() {
    local path="$1"
    local payload="$2"
    # sanitiza o payload via python
    local clean_payload
    clean_payload="$(echo "${payload}" | python3 -c "
import sys, json
sys.path.insert(0, '${SCRIPTS_DIR}')
try:
    from sanitizer import sanitize
    data = json.load(sys.stdin)
    print(json.dumps(sanitize(data)))
except Exception as e:
    sys.stdin.seek(0) if hasattr(sys.stdin, 'seek') else None
    print(sys.argv[0] if False else sys.stdin.read() if False else payload)
" 2>/dev/null || echo "${payload}")"

    curl -s --max-time 5 \
        -X POST "${WORKER_BASE}${path}" \
        -H "Content-Type: application/json" \
        -d "${clean_payload}" > /dev/null 2>&1 || true
}

# ---------------------------------------------------------------------------
# Captura output do copilot real em arquivo temporário
# ---------------------------------------------------------------------------
TMPOUT="$(mktemp /tmp/copilot-out-XXXXXX.txt)"
TIMESTAMP_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# Evento: session-init
# ---------------------------------------------------------------------------
if worker_alive; then
    post_event "/api/sessions/init" "$(python3 -c "
import json
print(json.dumps({
    'contentSessionId': '${SESSION_ID}',
    'project': '${PROJECT}',
    'platformSource': '${PLATFORM}',
    'prompt': '${PROMPT_CLEAN}',
    'customTitle': '[copilot] ${PROMPT_CLEAN:0:60}'
}))
")"
fi

# ---------------------------------------------------------------------------
# Executa o Copilot CLI real (passando todos os argumentos originais)
# Captura stdout+stderr em TMPOUT E ainda exibe em tempo real via tee
# ---------------------------------------------------------------------------
EXIT_CODE=0
"${REAL_COPILOT}" "$@" 2>&1 | tee "${TMPOUT}" || EXIT_CODE=$?

TIMESTAMP_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# Lê output capturado (limitado a 4 KB para não sobrecarregar o worker)
# ---------------------------------------------------------------------------
OUTPUT_SNIPPET="$(head -c 4096 "${TMPOUT}" | python3 -c "
import sys
text = sys.stdin.read()
# sanitiza output antes de enviar
sys.path.insert(0, '${SCRIPTS_DIR}')
try:
    from sanitizer import sanitize
    print(sanitize(text))
except Exception:
    print(text)
" 2>/dev/null || head -c 4096 "${TMPOUT}")"

rm -f "${TMPOUT}"

# ---------------------------------------------------------------------------
# Evento: observation (input+output da chamada)
# ---------------------------------------------------------------------------
if worker_alive; then
    OBS_PAYLOAD="$(python3 -c "
import json
print(json.dumps({
    'contentSessionId': '${SESSION_ID}',
    'tool_name': 'CopilotCLI',
    'tool_input': {
        'args': '${PROMPT_CLEAN}',
        'started_at': '${TIMESTAMP_START}'
    },
    'tool_response': {'result': '''${OUTPUT_SNIPPET}''', 'exit_code': ${EXIT_CODE}},
    'platformSource': '${PLATFORM}',
    'cwd': '$(pwd)'
}))
" 2>/dev/null)"
    if [ -n "${OBS_PAYLOAD}" ]; then
        post_event "/api/sessions/observations" "${OBS_PAYLOAD}"
    fi

    # Evento: summarize / session-end
    post_event "/api/sessions/summarize" "$(python3 -c "
import json
status = 'sucesso' if ${EXIT_CODE} == 0 else 'erro (exit ${EXIT_CODE})'
print(json.dumps({
    'contentSessionId': '${SESSION_ID}',
    'last_assistant_message': f'Copilot CLI executado: ${PROMPT_CLEAN}. Status: {status}. Fim em ${TIMESTAMP_END}.',
    'platformSource': '${PLATFORM}'
}))
")"
fi

# Propaga o exit code do copilot real
exit ${EXIT_CODE}
