#!/usr/bin/env sh
# Hive-Mind container entrypoint.
#
# Materializa o vault (cerebro/) a partir dos templates versionados
# (templates/vault/) na PRIMEIRA execução do volume — replicando o
# materialize_vault() do install.sh de forma idempotente. Depois delega para
# o CMD (hive-mindd run --serve).
set -e

VAULT_DIR="${VAULT_DIR:-/app/cerebro}"
TEMPLATES_DIR="/app/templates/vault"

materialize_vault() {
    if [ -f "$VAULT_DIR/vault-manifest.json" ] && [ -d "$VAULT_DIR/cortex/temporal" ]; then
        echo "[entrypoint] vault already materialized at $VAULT_DIR"
        return 0
    fi

    echo "[entrypoint] materializing vault at $VAULT_DIR..."
    if [ -d "$TEMPLATES_DIR" ]; then
        cp -r "$TEMPLATES_DIR/." "$VAULT_DIR/"
    else
        echo "[entrypoint] templates/vault/ not found; creating empty structure"
        mkdir -p "$VAULT_DIR"
    fi

    mkdir -p \
        "$VAULT_DIR/cerebelo/anual" \
        "$VAULT_DIR/cerebelo/diario" \
        "$VAULT_DIR/cerebelo/mensal" \
        "$VAULT_DIR/cerebelo/padroes" \
        "$VAULT_DIR/cerebelo/semanal" \
        "$VAULT_DIR/cerebelo/sessoes" \
        "$VAULT_DIR/cortex/frontal/brain" \
        "$VAULT_DIR/cortex/frontal/decisoes" \
        "$VAULT_DIR/cortex/frontal/org/people" \
        "$VAULT_DIR/cortex/frontal/org/teams" \
        "$VAULT_DIR/cortex/frontal/projetos" \
        "$VAULT_DIR/cortex/frontal/rascunhos" \
        "$VAULT_DIR/cortex/frontal/trabalho/active" \
        "$VAULT_DIR/cortex/frontal/trabalho/ativo" \
        "$VAULT_DIR/cortex/frontal/trabalho/pipeline" \
        "$VAULT_DIR/cortex/insula/conflitos" \
        "$VAULT_DIR/cortex/insula/saude" \
        "$VAULT_DIR/cortex/occipital/capturas-visuais" \
        "$VAULT_DIR/cortex/occipital/grafo" \
        "$VAULT_DIR/cortex/parietal/inbox/visual" \
        "$VAULT_DIR/cortex/parietal/inbox/documents" \
        "$VAULT_DIR/cortex/parietal/referencias/analises" \
        "$VAULT_DIR/cortex/temporal/_global" \
        "$VAULT_DIR/cortex/temporal/hipocampo" \
        "$VAULT_DIR/cortex/temporal/arquivo" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/agent_skills" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/atlas" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/atoms" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/decision" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/error_handling" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/infrastructure" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/preferences" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/project_management" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/security" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/testing" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/test_swarm" \
        "$VAULT_DIR/cortex/temporal/Hive-Mind/test_topic" \
        "$VAULT_DIR/diencefalo/roteamento" \
        "$VAULT_DIR/tronco/infra/obsidian-trash" \
        "$VAULT_DIR/attachments"

    if [ ! -f "$VAULT_DIR/.gitignore" ]; then
        cat > "$VAULT_DIR/.gitignore" <<'VAULT_EOF'
# Vault runtime — regenerated, do not commit
.smart-env/
.claude-flow/
.obsidian/
graphify-out/
cortex/occipital/grafo/cache/
cortex/occipital/grafo/graphify-out/
cortex/occipital/grafo/manifest.json
cortex/occipital/grafo/.rebuild.lock
cortex/occipital/grafo/.pending_changes
cortex/temporal/**/neuronio-*.md
cerebelo/sessoes/
cortex/frontal/decisoes/
cortex/frontal/projetos/
cortex/frontal/trabalho/
cortex/insula/
cortex/parietal/inbox/
attachments/
VAULT_EOF
    fi

    echo "[entrypoint] vault materialized"
}

materialize_vault

exec "$@"
