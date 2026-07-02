#!/usr/bin/env bash
# Teste de instalação limpa (zero-to-green) do Hive-Mind em container.
#
# Sobe uma "máquina virgem" (Ubuntu 24.04 + systemd + uv/Node/Bun, sem nada
# do Hive-Mind), clona o repositório do GitHub e roda o instalador oficial:
#
#   ./install.sh --profile=local-min --with-tests --non-interactive
#
# O gate é o exit code do próprio install.sh: com --with-tests ele falha se
# qualquer suíte (smoke/unit/integration/e2e) falhar. No final o teste ainda
# valida o install-report, as units systemd e o health da REST API.
#
# Uso:
#   ./tests/install/run-clean-install-test.sh            # main do GitHub
#   HIVE_INSTALL_TEST_REF=v3.7.11 ./tests/install/run-clean-install-test.sh
#   HIVE_INSTALL_TEST_KEEP=1 ...                         # não remove o container
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMG="hive-mind-clean-install"
NAME="hive-mind-install-test"
REPO_URL="${HIVE_INSTALL_TEST_REPO:-https://github.com/Mlaurindo30/Hive-Mind.git}"
REF="${HIVE_INSTALL_TEST_REF:-main}"
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

echo "==> [4/6] Clone do repositório ($REPO_URL @ $REF)"
docker exec "${USER_ENV[@]}" "$NAME" \
    git clone --depth 1 --branch "$REF" "$REPO_URL" /home/hive/Hive-Mind

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
docker exec "$NAME" curl -sf http://127.0.0.1:37702/api/v1/health && echo

if [ "$INSTALL_EXIT" -eq 0 ]; then
    echo "RESULTADO: ZERO-TO-GREEN OK"
else
    echo "RESULTADO: FALHA (exit $INSTALL_EXIT)"
    exit "$INSTALL_EXIT"
fi
