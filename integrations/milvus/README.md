# Milvus Wrapper

Milvus entra no Hive-Mind como backend vetorial de producao atras do contrato
`core.vector_backend.VectorBackend`. Este diretorio nao e clone do monorepo
Milvus; e apenas wrapper operacional:

- `client.py`: SDK real `pymilvus`, leitura de env e `assert_health()`.
- `docker-compose.yml`: Milvus standalone local com imagem pinada por digest.

Variaveis:

- `MILVUS_URI` ou `MILVUS_HOST`/`MILVUS_PORT`
- `MILVUS_USER`, `MILVUS_PASSWORD`, `MILVUS_TOKEN`
- `MILVUS_DB_NAME`
- `MILVUS_TIMEOUT`

Comandos:

```bash
docker compose -f integrations/milvus/docker-compose.yml up -d
.venv/bin/python -c "from integrations.milvus.client import assert_health; print(assert_health())"
```

O uso pela aplicacao deve passar por `core.vector_backend`, nunca por chamada
direta a `pymilvus` fora do wrapper/adapter.
