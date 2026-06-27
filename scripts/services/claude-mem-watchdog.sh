#!/bin/bash
# Watchdog: verifica se o worker claude-mem está realmente inicializado (initialized=true)
# Se não estiver, força o restart. Chamado via ExecStartPre do timer.
HEALTH_URL="http://127.0.0.1:37700/api/health"
MAX_WAIT=10          # segundos para aguardar initialized=true
POLL_INTERVAL=2      # intervalo entre verificações
SERVICE="sinapse-claude-mem.service"

elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    response=$(curl -sf "$HEALTH_URL" 2>/dev/null)
    if [ -n "$response" ]; then
        initialized=$(echo "$response" | grep -o '"initialized":[^,}]*' | head -1)
        if echo "$initialized" | grep -q '"initialized":true'; then
            echo "[watchdog] OK — worker is initialized"
            exit 0
        fi
    fi
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))
done

echo "[watchdog] FAILED — worker not initialized after ${MAX_WAIT}s, restarting ${SERVICE}"
systemctl --user restart "$SERVICE"
exit 1
