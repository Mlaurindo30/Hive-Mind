#!/usr/bin/env bash
# Sobe FalkorDB + RAGFlow via docker compose, espera healthchecks, e roda
# o gate K9 (--profile=local-full). E o caminho de "cobertura 100% na
# maquina de referencia" do proximo corte (§10.1 item 4).
#
# Idempotente: re-rodar nao duplica containers. Falha limpo se o servico
# nao ficar online dentro do timeout.
set -euo pipefail
cd "$(dirname "$0")/.."

REPORT="${REPORT:-docs/reports/k9-real-suite-local-full.md}"
COMPOSE_FALKORDB="docker-compose.falkordb.yml"
COMPOSE_MILVUS="integrations/milvus/docker-compose.yml"
COMPOSE_RAGFLOW="integrations/ragflow/docker-compose.yml"

docker compose version >/dev/null 2>&1 || {
    echo "[local-full] docker compose indisponivel; abortando" >&2
    exit 1
}

echo "[local-full] Subindo FalkorDB..."
docker compose -f "$COMPOSE_FALKORDB" up -d --quiet-pull

echo "[local-full] Subindo Milvus..."
docker compose -f "$COMPOSE_MILVUS" up -d --quiet-pull

echo "[local-full] Subindo RAGFlow..."
docker compose -f "$COMPOSE_RAGFLOW" up -d --quiet-pull

# Healthchecks
wait_for() {
    local name=$1 url=$2 timeout=${3:-120}
    echo -n "[local-full] Aguardando $name em $url"
    for i in $(seq 1 "$timeout"); do
        if curl -fsS -m 2 "$url" >/dev/null 2>&1; then
            echo " OK (${i}s)"
            return 0
        fi
        echo -n "."
        sleep 1
    done
    echo " TIMEOUT"
    return 1
}

wait_for "FalkorDB" "http://localhost:6379" 30 || true
wait_for "Milvus metrics" "http://localhost:9091/healthz" 60 || true
wait_for "RAGFlow" "http://localhost:9380/api/v1/health" 120 || true

# Roda o gate
echo "[local-full] Rodando gate K9..."
if ! ./tests/run_real_knowledge.sh --report="$REPORT"; then
    echo "[local-full] gate K9 retornou !=0" >&2
    exit 1
fi
echo "[local-full] Relatorio: $REPORT"

# Auditoria
.venv/bin/python scripts/setup/audit_test_layering.py
