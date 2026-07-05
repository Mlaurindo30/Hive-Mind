#!/usr/bin/env bash
# Teste de instalação limpa (zero-to-green) do Hive-Mind em container, usando a
# ÁRVORE LOCAL (branch corrente, incluindo alterações não commitadas) em vez de
# clonar do GitHub. Companheiro de run-clean-install-test.sh: aquele valida um
# ref publicado (main/tag); este valida o working tree atual sem exigir push.
#
# Sobe a mesma "máquina virgem" (Ubuntu 24.04 + systemd + uv/Node/Bun, sem nada
# do Hive-Mind), injeta a árvore local via `git archive` + `docker cp` e roda o
# instalador oficial:
#
#   ./install.sh --profile=local-min --with-tests --non-interactive
#
# O gate é o exit code do próprio install.sh: com --with-tests ele falha se
# qualquer suíte (smoke/unit/integration/e2e) falhar. No final o teste ainda
# valida o install-report, as units systemd e o health da REST API.
#
# Uso:
#   ./tests/install/run-clean-install-test-local.sh
#   HIVE_INSTALL_TEST_KEEP=1 ...   # não remove o container ao final
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
IMG="hive-mind-clean-install"
NAME="hive-mind-install-test-local"
KEEP="${HIVE_INSTALL_TEST_KEEP:-0}"

USER_ENV=(-u hive -e XDG_RUNTIME_DIR=/run/user/1000
          -e DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
          -e PATH=/home/hive/.local/bin:/home/hive/.bun/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin)

cleanup() {
    if [ "$KEEP" != "1" ]; then
        docker rm -f "$NAME" >/dev/null 2>&1 || true
    else
        echo "[keep] container '$NAME' preservado para inspeção"
    fi
}
trap cleanup EXIT

echo "==> [1/6] Build da imagem de máquina virgem"
docker build -t "$IMG" "$HERE"

echo "==> [2/6] Subindo container com systemd (PID 1)"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --privileged --cgroupns=host \
    --tmpfs /run --tmpfs /run/lock \
    -v /sys/fs/cgroup:/sys/fs/cgroup:rw "$IMG" >/dev/null

echo "==> [3/6] Aguardando systemd + user manager (linger)"
docker exec "$NAME" bash -c \
    'for i in $(seq 1 60); do state=$(systemctl is-system-running 2>/dev/null || true); \
     case "$state" in running|degraded) exit 0;; esac; sleep 1; done; \
     echo "systemd não estabilizou: $state"; exit 1'
docker exec "$NAME" loginctl enable-linger hive
docker exec "$NAME" bash -c \
    'for i in $(seq 1 30); do [ -S /run/user/1000/bus ] && exit 0; sleep 1; done; \
     echo "user bus ausente"; exit 1'

echo "==> [4/6] Injetando árvore local (branch $(git -C "$ROOT" branch --show-current), incl. não commitado e não rastreado)"
docker exec "$NAME" mkdir -p /home/hive/Hive-Mind
# git archive/stash create only capture tracked files — new untracked files
# (e.g. a freshly-added template) would silently be missing from the
# container. List tracked + untracked-but-not-gitignored paths instead, so
# the container sees exactly what `git status` would show as "would be
# committed if you git add -A", without touching the real index.
git -C "$ROOT" ls-files -z --cached --others --exclude-standard \
    | tar -cf - -C "$ROOT" --null -T - \
    | docker cp - "$NAME:/home/hive/Hive-Mind"
docker exec "$NAME" chown -R hive:hive /home/hive/Hive-Mind

echo "==> [5/6] Instalação real: ./install.sh --profile=local-min --with-tests --non-interactive"
INSTALL_EXIT=0
docker exec "${USER_ENV[@]}" -w /home/hive/Hive-Mind "$NAME" \
    env HIVE_DREAMER_PROVIDER=ollama HIVE_DREAMER_MODEL=qwen2.5:3b \
    ./install.sh --profile=local-min --with-tests --non-interactive || INSTALL_EXIT=$?
echo "install.sh exit code: $INSTALL_EXIT"

echo "==> [6/6] Validação pós-install"
echo "--- install-report.md ---"
docker exec "$NAME" cat /home/hive/Hive-Mind/logs/install-report.md || true
echo "--- units sinapse ativas ---"
docker exec "${USER_ENV[@]}" "$NAME" systemctl --user list-units 'sinapse*' --state=active --no-pager || true
echo "--- health da REST API ---"
HEALTH_BODY="$(docker exec "$NAME" curl -sf http://127.0.0.1:37702/api/v1/health)"
echo "$HEALTH_BODY"

echo "--- Model Gateway: config presente e .env.example atualizado ---"
MG_CHECK_EXIT=0
docker exec "$NAME" test -f /home/hive/Hive-Mind/config/model-gateway.yaml \
    && echo "  OK: config/model-gateway.yaml presente" \
    || { echo "  FALHA: config/model-gateway.yaml ausente"; MG_CHECK_EXIT=1; }
docker exec "$NAME" test -f /home/hive/Hive-Mind/config/model-gateway.env.example \
    && echo "  OK: config/model-gateway.env.example presente" \
    || { echo "  FALHA: config/model-gateway.env.example ausente"; MG_CHECK_EXIT=1; }
docker exec "$NAME" grep -q "^MODEL_GATEWAY_MODE=" /home/hive/Hive-Mind/.env.example \
    && echo "  OK: .env.example contém MODEL_GATEWAY_MODE (bloco idempotente aplicado pelo install.sh)" \
    || { echo "  FALHA: .env.example não contém o bloco do Model Gateway"; MG_CHECK_EXIT=1; }
docker exec "$NAME" grep -q "model_gateway" /home/hive/Hive-Mind/config/sinapse.yaml \
    && echo "  OK: config/sinapse.yaml contém a seção model_gateway" \
    || { echo "  FALHA: config/sinapse.yaml sem seção model_gateway"; MG_CHECK_EXIT=1; }
if echo "$HEALTH_BODY" | grep -q "model_gateway"; then
    echo "  OK: /api/v1/health inclui model_gateway"
else
    echo "  FALHA: /api/v1/health sem model_gateway"
    MG_CHECK_EXIT=1
fi
if [ "$MG_CHECK_EXIT" -ne 0 ]; then
    INSTALL_EXIT=1
fi

if [ "$INSTALL_EXIT" -eq 0 ]; then
    echo "RESULTADO: ZERO-TO-GREEN OK (árvore local)"
else
    echo "RESULTADO: FALHA (exit $INSTALL_EXIT)"
    exit "$INSTALL_EXIT"
fi
