# RAGFlow Wrapper

RAGFlow entra no Hive-Mind como adapter headless de ingestao documental. O store
do RAGFlow e cache operacional; a fonte de verdade continua sendo `cerebro/` e
UMC.

Este diretorio nao e clone do monorepo RAGFlow:

- `client.py`: SDK real `ragflow-sdk`, leitura de env e `assert_health()`.
- `docker-compose.yml`: servico local com imagem pinada por digest.

Variaveis:

- `RAGFLOW_BASE` ou `RAGFLOW_API_URL`
- `RAGFLOW_API_KEY`
- `RAGFLOW_API_VERSION`
- `RAGFLOW_TIMEOUT`

Comandos:

```bash
docker compose -f integrations/ragflow/docker-compose.yml up -d
.venv/bin/python -c "from integrations.ragflow.client import assert_health; print(assert_health())"
```

Sem `RAGFLOW_API_KEY`, `assert_health(strict=False)` retorna `ok=False` com
motivo explicito; nao existe sucesso falso.
