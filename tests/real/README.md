# tests/real — suíte de aceite da frente de conhecimento

Aceite de fase K* (docs/12) = **teste real verde**. Estes testes usam SQLite
real, Ollama local e serviços reais — **sem mock**. Testes mockados ajudam no
desenvolvimento mas não fecham fase.

## Como rodar

```bash
./tests/run_real_knowledge.sh            # toda a suíte real
./tests/run_real_knowledge.sh -k embedding
.venv/bin/python -m pytest tests/real/test_integration_wrappers.py -q
.venv/bin/python scripts/setup/verify_wrappers.py
docker compose -f integrations/milvus/docker-compose.yml up -d
.venv/bin/python -m pytest tests/real/test_vector_backend_sqlite.py tests/real/test_vector_backend_milvus.py -q
.venv/bin/python -m pytest tests/real/test_vector_sync_milvus.py -q
.venv/bin/python -m pytest tests/real/test_observation_vectors.py -q
.venv/bin/python -m pytest tests/real/test_vector_sync_live_e2e.py -q
.venv/bin/python scripts/maintenance/vector-sync.py --collection memory_vectors --collection observation_vectors --limit 2 --json
.venv/bin/python -m pytest tests/real/test_promotion_pipeline_sqlite.py -q
python3 scripts/services/sinapse-write.py promotion --limit 10 --dry-run
```

## Pré-requisitos por serviço

| Serviço | Necessário para | Se offline |
|---|---|---|
| Ollama (`OLLAMA_BASE`, default `http://localhost:11434`) | embeddings 1024d | testes `requires_service` **pulam** (não falham) |
| Milvus (`MILVUS_URI` ou `MILVUS_HOST:PORT`) | K2 / VectorBackend produção | idem |
| FalkorDB (`FALKORDB_HOST:PORT`) | Graphiti causal/temporal | idem |
| claude-mem (`CLAUDE_MEM_WORKER_HOST:PORT` ou `CLAUDE_MEM_DB`) | K4 bridge/discoveries | idem |
| RAGFlow (`RAGFLOW_BASE` ou `RAGFLOW_API_URL`) | K6 DocumentPipeline | idem |

Testes marcados `@pytest.mark.requires_service` pulam automaticamente quando o
serviço nomeado está offline. Serviço desconhecido falha como erro de teste. O
que não depende de serviço (migração de schema, defaults) roda sempre.

## Cobertura K1/K2

- K1 importações/wrappers: SDKs reais (`pymilvus`, `ragflow_sdk`,
  `llama_index`), artefatos `integrations/milvus` e `integrations/ragflow`, sem
  clone de monorepo; compose validado por `docker compose config --quiet` e
  imagem obrigatoriamente pinada por digest `@sha256`.
- K2 local: `SQLiteVecBackend` contra SQLite real + `sqlite-vec`.
- K2 produção: `MilvusBackend` contra Milvus real via Docker compose pinado por
  digest.
- K2 sync/backfill: `memory_vectors` de `hive_mind.db/search_vec` e
  `observation_vectors` de `claude-mem.db/vec_observations` para Milvus com
  idempotência por hash e falha por linha reportada.
- K2 claude-mem: `SQLiteVecBackend` consulta `observation_vectors` em
  `claude-mem.db` read-only; escrita direta fica reservada ao
  `sqlite-vec-worker`.
- K2 E2E live bounded: `hive_mind.db` real + `~/.claude-mem/claude-mem.db` real
  são lidos sem mutação e exportados em lote limitado para coleções Milvus
  temporárias com prefixo randômico.
- K2 CLI operacional: `scripts/maintenance/vector-sync.py` executa o mesmo
  backfill/sync como rotina de manutenção, com seleção de coleção, `--limit`,
  prefixo Milvus, override de DBs e relatório JSON.

## Cobertura K3

- K3 intake/promotion: `core/knowledge/intake.py` normaliza observations,
  discoveries, session summaries e arquivos em candidatos canonicos com
  evidencia e `workspace_id`.
- K3 promotion: `core/knowledge/promotion.py` grava `knowledge_candidates`,
  promove conhecimento duravel para `neurons`, `next_step` para `goals`, liga
  `observations.neuron_id` quando aplicavel e preserva raw.
- K3 quarentena: erro estrutural fica em `observations.archived=2` com motivo e
  retry policy, sem apagar `content`.
- K3 arquivos/summaries: `promote_files()` cobre docs, codigo e cadencias do
  cerebelo (`sessoes`, `diario`, `semanal`, `mensal`, `anual`).
- K3 superficies: CLI `sinapse-write.py promotion`, MCP
  `sinapse_promote_knowledge`, e dream cycle com intake candidate-only antes da
  sintese legada.
