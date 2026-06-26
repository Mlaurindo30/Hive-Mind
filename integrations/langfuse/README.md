# Langfuse (instr. tracing para Hive-Mind)

Langfuse self-hosted para tracing distribuído via OpenTelemetry.
Usado pela Fase P9 do Hive-Mind.

## Subir (dev local)

```bash
# Da raiz do projeto
docker compose -f integrations/langfuse/docker-compose.yml up -d

# UI em http://localhost:3100
# Criar projeto + copiar keys em Settings → API Keys
# Adicionar ao .env do Hive-Mind:
#   LANGFUSE_PUBLIC_KEY=pk-lf-...
#   LANGFUSE_SECRET_KEY=sk-lf-...
#   LANGFUSE_HOST=http://localhost:3100
```

## Secrets

Por padrão, o compose usa placeholders `local-dev-...-change-me` via variáveis
de ambiente. Para gerar secrets fortes em produção:

```bash
openssl rand -hex 32  # para LANGFUSE_NEXTAUTH_SECRET e LANGFUSE_SALT
```

Adicione ao `.env` (que está em `.gitignore`):

```bash
LANGFUSE_NEXTAUTH_SECRET=<hex gerado>
LANGFUSE_SALT=<hex gerado>
LANGFUSE_NEXTAUTH_URL=https://langfuse.seu-dominio.com  # se HTTPS em prod
```

## Storage

Volume local: `claude-mem/data/langfuse/` (relativo à raiz do projeto).
Adicionado ao `.gitignore` via `claude-mem/`.

## Disable / Uninstall

```bash
docker compose -f integrations/langfuse/docker-compose.yml down
```

## Refs

- P9 (Fase 9) do roadmap: `docs/10-implementation-roadmap.md §2 P9`
- Spec Langfuse: https://langfuse.com/docs
- OTLP endpoint: `/api/public/otel/v1/traces` (hardcoded em `core/telemetry.py:71`)