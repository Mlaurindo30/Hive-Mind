# Plano De Implementacao Da Arquitetura De Conhecimento

> Status: plano operacional para implementar `docs/11-knowledge-promotion-architecture.md`.
> Principio: local-first por execucao, born-large por contrato, testes reais sem
> mocks como criterio de aceite.

---

## 1. Objetivo

Implementar a arquitetura de promocao de conhecimento com fases pequenas,
testaveis e conectadas:

1. capturar dados temporais, documentos, codigo, summaries e discoveries;
2. promover conhecimento atomico com evidencia;
3. indexar por FTS, vetor, grafo estrutural e grafo temporal;
4. recuperar via roteador hibrido com citacoes;
5. medir cobertura real e falhar de forma auditavel.

Este plano nao substitui o `docs/11`; ele transforma o desenho em backlog de
engenharia.

---

## 2. Decisoes Vinculantes

1. **Embeddings locais unificados:** tudo que usar embedding deve usar
   `snowflake-arctic-embed2:latest` via Ollama, 1024 dimensoes, salvo override
   explicito por env.
2. **Modelos pequenos primeiro:** tarefas de compressao, classificacao e
   extracao devem preferir modelos locais pequenos. Modelos maiores entram por
   papel/env quando a cadencia ou o risco exigir.
3. **Sem mock no aceite desta frente:** testes de aceite, smoke, integration e
   E2E devem usar SQLite real, Ollama real, arquivos reais, APIs locais reais e
   containers reais quando o backend exigir. Se dependencia real estiver
   ausente, o teste deve falhar no perfil `--real` ou ser separado em um perfil
   explicitamente marcado como `requires-service`.
4. **Vendor por tipo (clone vs wrapper vs pip):** clone so o que se builda/patcha
   do source; servico via container/SDK e wrapper; lib e pip (regra §3.1).
5. **Nada hardcoded em `core/`:** modelos, portas, endpoints, colecoes e
   backends devem ter default local e override por `.env`.
6. **Fonte de verdade anatomica:** nenhum backend externo substitui `cerebro/`
   e UMC. Milvus, RAGFlow e LlamaIndex sao orgaos/adapters, nao cerebro.
7. **Isolamento por workspace nasce no schema:** `workspace_id` (default
   `'default'`) em neurons/observations/synapses/goals/document_memories/
   visual_memories/ambiguities/causal_edges/vault; particao por workspace nas
   colecoes vetoriais; toda leitura/escrita do router e da promocao filtra por
   `workspace_id` (contrato `docs/11` §18). Single-user nao seta nada.

---

## 3. Integracoes Externas

### 3.1 Vendor: clone vs wrapper

- **Clone** (`config/components.lock.json`): só o que o `install.sh` builda/patcha
  do source — `graphify`, `neural-memory`, `rtk`.
- **Wrapper** (`integrations/<nome>/client.py` + `docker-compose.yml`, imagem
  pinada por digest): serviço via container/SDK — `graphiti`, Milvus, RAGFlow.
- **Pip** (`pyproject.toml`): LlamaIndex.

`install.sh` não usa `git clone` fora de `integrations/`. Para esta frente,
`components.lock.json` é contrato negativo para Milvus, RAGFlow e LlamaIndex:
se algum deles aparecer no lock, a implementação regrediu para clone indevido.

### 3.2 Vendors Desta Frente

| Integracao | Tipo | Em | SDK (pip) | Uso |
|---|---|---|---|---|
| Milvus | wrapper | `integrations/milvus/{client.py,docker-compose.yml}` | `pymilvus` | backend vetorial de producao (`VectorBackend`) |
| RAGFlow | wrapper (headless) | `integrations/ragflow/{client.py,docker-compose.yml}` | `ragflow-sdk` | parsing/chunking/citacoes → `document_vectors`+UMC |
| LlamaIndex | pip | `pyproject.toml` | `llama-index` | adapter p/ retrievers compostos |

RAGFlow roda headless: o store dele é cache de ingestão; `cerebro/`+UMC continuam
fonte de verdade (`docs/11` §16).

### 3.3 Bootstrap No Instalador

```bash
docker compose -f integrations/milvus/docker-compose.yml up -d    # imagem pinada por digest
docker compose -f integrations/ragflow/docker-compose.yml up -d   # imagem pinada por digest
uv sync                                                            # pymilvus, ragflow-sdk, llama-index
```

Instalador: validar digest das imagens contra o pinado no compose; Milvus/RAGFlow
não sobem em `local-min`.

### 3.4 Trilha futura — fork de UI do RAGFlow

Se o frontend do RAGFlow for customizado para virar a UI do Hive-Mind, ele migra
para **clone+patch** (`integrations/patches/`). Decisão separada, não desta frente.
A UI do RAGFlow é acoplada ao store dele (ES/Infinity+MySQL+MinIO) — não pode
virar fonte de verdade acima do UMC. UI do cérebro (grafo/neurônios) =
`integrations/neural-memory/dashboard/`.

---

## 4. Modelos E Variaveis De Ambiente

### 4.1 Embeddings

| Uso | Env | Default | Dim | Obrigatorio |
|---|---|---|---|---|
| UMC/search_vec | `OLLAMA_EMBED_MODEL` | `snowflake-arctic-embed2:latest` | 1024 | sim |
| sqlite-vec worker | `VEC_EMBED_MODEL` ou `OLLAMA_EMBED_MODEL` | `snowflake-arctic-embed2:latest` | 1024 | sim |
| LightRAG chunks/entities/rels | `OLLAMA_EMBED_MODEL` | `snowflake-arctic-embed2:latest` | 1024 | sim |
| Graphiti embeddings | `GRAPHITI_EMBED_MODEL` ou `OLLAMA_EMBED_MODEL` | `snowflake-arctic-embed2:latest` | 1024 | sim |
| Milvus collections | `OLLAMA_EMBED_MODEL` | `snowflake-arctic-embed2:latest` | 1024 | sim |

`EMBED_BACKEND=fastembed` fica apenas como fallback legado/manual. A frente de
implementacao deve tratar `ollama + snowflake-arctic-embed2:latest` como padrao.

### 4.2 LLMs Locais Pequenos Por Papel

| Papel | Env | Default local sugerido | Pode ser pequeno? | Observacao |
|---|---|---|---|---|
| `session_summarizer` | `HIVE_SESSION_SUMMARIZER_PROVIDER/MODEL` | `ollama/qwen2.5:3b` | sim | compressao local de sessao |
| `daily_writer` | `HIVE_DAILY_WRITER_PROVIDER/MODEL` | `ollama/qwen2.5:3b` | sim | diario e progresso do dia |
| `weekly_synthesizer` | `HIVE_WEEKLY_SYNTHESIZER_PROVIDER/MODEL` | `ollama/qwen2.5:7b` | medio recomendado | cruza projetos e metricas |
| `monthly_synthesizer` | `HIVE_MONTHLY_SYNTHESIZER_PROVIDER/MODEL` | `ollama/qwen2.5:7b` | medio/forte | sintese executiva e drift |
| `yearly_synthesizer` | `HIVE_YEARLY_SYNTHESIZER_PROVIDER/MODEL` | `ollama/qwen2.5:7b` | medio/forte | historico e principios |
| `pattern_distiller` | `HIVE_PATTERN_DISTILLER_PROVIDER/MODEL` | `ollama/qwen2.5:3b` | sim | atomizacao de aprendizados |
| `topic_router` | `HIVE_TOPIC_ROUTER_PROVIDER/MODEL` | `ollama/qwen2.5:3b` | sim | roteamento topico/setor |
| `sector_classifier` | `HIVE_SECTOR_CLASSIFIER_PROVIDER/MODEL` | `ollama/qwen2.5:3b` | sim | classificacao cross-projeto |
| `conflict_detector` | `HIVE_CONFLICT_DETECTOR_PROVIDER/MODEL` | `ollama/qwen2.5:7b` | medio | exige julgamento |
| `lightrag` | `HIVE_LIGHTRAG_MODEL` | `granite3-dense:2b` | sim | extracao RAG relacional |
| `graphiti` | `HIVE_GRAPHITI_MODEL` | `qwen2.5:3b` | sim | entidades/relacoes temporais |

Todos os papeis continuam configuraveis via `setup-brain`. O default de
instalacao deve baixar modelos pequenos suficientes:

```bash
ollama pull snowflake-arctic-embed2:latest
ollama pull qwen2.5:3b
ollama pull granite3-dense:2b
```

Perfil recomendado para maquina com mais folga:

```bash
ollama pull qwen2.5:7b
```

### 4.3 Perfis De Execucao

| Perfil | Objetivo | Modelos obrigatorios | Backends |
|---|---|---|---|
| `local-min` | laptop simples | snowflake embedder, qwen2.5:3b, granite3-dense:2b | SQLite, sqlite-vec, Graphify AST, claude-mem |
| `local-full` | maquina de dev completa | local-min + qwen2.5:7b | Graphiti, LightRAG, Milvus local, RAGFlow adapter |
| `prod-local` | VPS/desktop sempre ligado | local-full | Milvus Docker, API REST, watcher, metrics |
| `cloud-optional` | qualidade maior sob escolha | qualquer provider configurado | nunca obrigatorio |

### 4.4 Reconciliacao com o roadmap P (`docs/10`)

`docs/10` numera por **anatomia** (P0–P15); esta frente numera por **camada de
conhecimento** (K0–K10). Mapa para evitar dois backlogs divergentes:

| K (conhecimento) | P (anatomia, docs/10) | Relacao |
|---|---|---|
| K0 auditoria/embedding 1024d | P0 (embeddings local) | K0 estende P0: unifica modelo em todos os pontos |
| K1 vendors (Milvus/RAGFlow/LlamaIndex) | — | **eixo novo**, sem P equivalente |
| K2 VectorBackend + Milvus | — | **eixo novo** (hoje sqlite-vec direto, sem contrato) |
| K3 Promotion pipeline | — | **eixo novo** (hoje so `archived` no schema) |
| K4 Claude-mem bridge | P (claude-mem ja integrado) | formaliza promocao do que hoje so e lido |
| K5 cadencia mensal/anual | **P10 (RAPTOR)** | mesma entrega sob dois nomes |
| K6 DocumentPipeline | — | **eixo novo** (RAGFlow headless) |
| K7 RetrievalRouter | — | **eixo novo** (hoje `sinapse_query` funde 7, sem router) |
| K8 knowledge health | P (insula/health existe) | adiciona metricas de cobertura |
| K9/K10 test harness + installer | P (criterio geral) | transversal |

Visual (P11 LanceDB / P13 OmniParser / P14 Amigdala / P15 Ganglios) seguem so no
`docs/10` — nao fazem parte desta frente de conhecimento.

---

## 5. Fases De Implementacao

### K0 — Auditoria E Normalizacao De Base

**Objetivo:** eliminar contradicoes antes de implementar camadas novas.

> **Entregue (2026-06-28; revalidado em 2026-06-29):**
> - [x] task 1 — embedding unificado: `worker.py` defaulta `snowflake-arctic-embed2`
>   (era `bge-m3`); igual a `core/database.py`. Teste: `tests/real/test_embedding_stack.py::test_default_embedding_model_unified`.
> - [x] task 7 — migração CRR-safe: `alter_table_crr_safe()` +
>   `migrate_workspace_and_federation()` em `core/database.py` (chamada em
>   `ensure_migrations`); `workspace_id` nas 9 tabelas + `origin_instance`/
>   `origin_signature`/`embedding_model`/`embedding_dim` em `neurons`; colunas no
>   `umc_schema.sql` e `umc_schema_crr.sql` (neurons). Idempotente, CRR-safe.
>   Testes: `tests/unit/test_workspace_migration.py` (7) + `tests/real/...::test_real_db_has_workspace_and_federation`.
> - [x] auditoria pós-implementação — todos os `ADD COLUMN` legados dentro de
>   `ensure_migrations()` agora passam por `add_column_if_missing()` →
>   `alter_table_crr_safe()`; colunas opcionais usam `DEFAULT NULL` explícito
>   para manter compatibilidade com CRR.
> - [x] task 8 — esqueleto K9 (ver bloco K9).
> - [x] B8 — backup `hive_mind.db.pre-workspace` (API `backup()`, 1x, pula
>   `:memory:`/temp) antes da 1ª aplicação da migração. Testes em
>   `tests/unit/test_workspace_migration.py` (12 total).
> - [x] fail-closed de migração estrutural — falha em
>   `migrate_workspace_and_federation()` levanta `RuntimeError` por padrão.
>   Bypass só para diagnóstico de DB legado:
>   `HIVE_ALLOW_DEFERRED_MIGRATIONS=1`. Testes:
>   `tests/unit/test_workspace_migration.py`.
> - [ ] tasks 2–6 pendentes.
> - **Verificação atual do recorte:** `tests/unit/test_workspace_migration.py`
>   12 passed; `tests/unit/test_real_service_registry.py` 5 passed;
>   `./tests/run_real_knowledge.sh` 24 passed (Ollama up, dim=1024
>   confirmado;
>   K1 wrappers, K2 sqlite/Milvus e sync/backfill das 7 coleções canônicas
>   incluidos, com K1 digest gate, E2E bounded nos bancos reais e CLI
>   operacional `vector-sync.py`);
>   `json.tool`, `bash -n`, `py_compile` e `integrations-update.sh
>   --wrappers-only --no-pip` verdes.
> - **Verificação global atual (2026-06-28):** `./tests/run_all.sh` verde:
>   Smoke 19 passed; Unit 474 passed / 3 skipped; Integration 107 passed /
>   2 skipped; E2E 22 passed. Bloqueios anteriores foram resolvidos: Ollama
>   estava parado, logs Graphiti foram movidos para stderr para não poluir JSON
>   do CLI, e `test_live_push_neuron` passou com Graphiti real.

Tasks:

1. alinhar docs antigas que ainda citam `384d`, `fastembed` default ou `bge-m3`;
2. garantir `.env.example`, README e docs 02/03/11/12 com
   `snowflake-arctic-embed2:latest`;
3. mapear todos os pontos que geram embedding;
4. adicionar comando de health que prova dimensao 1024 em UMC, sqlite-vec worker,
   LightRAG e Graphiti;
5. declarar no `pyproject.toml` os pacotes de `.venv` necessarios para esta
   frente: `ragflow-sdk`, `pymilvus` e `llama-index`;
6. separar testes antigos mockados dos testes reais de aceite;
7. manter a **migracao unica CRR-safe** (B1+B6+B8) entregue: backup
   `hive_mind.db.pre-workspace`, `alter_table_crr_safe()`, `workspace_id`,
   `origin_instance`/`origin_signature` e `embedding_model`/`embedding_dim`.
   Erro estrutural de migração falha fechado por padrão; não pode ficar invisível
   em maquina zerada.
8. manter o **esqueleto K9 PRIMEIRO** (B3 — gate) entregue e expandir para
   fixtures reais de Milvus, claude-mem, FalkorDB e RAGFlow antes de qualquer
   fase usar esses serviços como aceite.

Conexoes:

- `core/database.py`
- `core/hnsw_index.py`
- `plugins/sqlite-vec-worker/worker.py`
- `core/lightrag_index.py`
- `integrations/graphiti/`
- `docs/02-ai-models.md`
- `.env.example`
- `pyproject.toml`
- `uv.lock`

Aceite real:

```bash
ollama list | rg 'snowflake-arctic-embed2|qwen2.5:3b|granite3-dense:2b'
.venv/bin/python -m pytest tests/real/test_embedding_stack.py -q
python3 scripts/services/sinapse-write.py health
```

---

### K1 — Vendor Bootstrap Em `integrations/`

**Objetivo:** Milvus e RAGFlow como wrappers (compose + SDK); LlamaIndex como dep
pip. Nenhum monorepo clonado.

> **Entregue (2026-06-28) — gate de update seguro:**
> - [x] `scripts/maintenance/integrations-update.sh --no-components` pula
>   `components.py bootstrap/update` e nao repina `components.lock.json`.
> - [x] `--wrappers-only` aliasa `--no-components --no-plugins` para atualizar
>   apenas deps/wrappers.
> - [x] aceite smoke sem mutação pesada:
>   `./scripts/maintenance/integrations-update.sh --no-components --no-pip --no-plugins`.
> - [x] wrappers Milvus/RAGFlow (`client.py`, compose pinado por digest,
>   `README.md`, `assert_health(strict=...)`) entregues sem clone de monorepo.
> - [x] `scripts/setup/verify_wrappers.py` valida compose real via
>   `docker compose config --quiet` e exige `image@sha256:<digest>` para
>   Milvus/RAGFlow; `install.sh` e `integrations-update.sh` chamam esse gate.
> - [x] deps `pymilvus`, `ragflow-sdk`, `llama-index` em `pyproject.toml`/`uv.lock`
>   e importadas no `.venv`.
> - [x] aceite real K1: `.venv/bin/python -m pytest
>   tests/real/test_integration_wrappers.py -q` → 7 passed; `docker compose
>   ... config` verde para Milvus/RAGFlow; `integrations-update.sh
>   --wrappers-only --no-pip` verde e validou compose/digests sem tocar
>   componentes git nem atualizar o lock.

Tasks:

1. criar `integrations/milvus/` e `integrations/ragflow/` com `client.py`,
   `docker-compose.yml` (imagem pinada por digest), `README.md` e `assert_health()`;
2. `pymilvus`, `ragflow-sdk`, `llama-index` em `pyproject.toml`/`uv.lock`;
3. incluir os wrappers em `scripts/maintenance/integrations-update.sh` sem
   atualizar componentes git por acidente: adicionar modo `--no-components`
   ou `--wrappers-only`;
4. bloquear `git clone` fora de `integrations/` nos scripts de setup.

Conexoes:

- `install.sh`
- `scripts/setup/install_services.py`
- `core/paths.py::INTEGRATIONS_ROOT`
- `config/components.lock.json` (contrato negativo: Milvus/RAGFlow/LlamaIndex
  nao entram no lock)
- `scripts/maintenance/integrations-update.sh`
- `integrations/{milvus,ragflow}/README.md`

Aceite real:

```bash
test -f integrations/milvus/docker-compose.yml
test -f integrations/ragflow/docker-compose.yml
.venv/bin/python -c "import pymilvus, ragflow_sdk, llama_index"
.venv/bin/python -m pytest tests/real/test_integration_wrappers.py -q
./scripts/maintenance/integrations-update.sh --no-components --no-plugins
.venv/bin/python - <<'PY'
import json
lock = json.load(open("config/components.lock.json"))
names = set(lock.get("components", lock).keys())
assert not {"milvus", "ragflow", "llama_index", "llama-index"} & names
PY
```

---

### K2 — VectorBackend Local E Producao

**Objetivo:** criar contrato unico para vetores, com `sqlite_vec` local e Milvus
como backend de producao.

> **Entregue (2026-06-28) — E2E real local + Milvus:**
> - [x] `core/vector_backend.py` com interface `upsert`, `delete`, `query`,
>   `hybrid_query`, `count`, `health`.
> - [x] `SQLiteVecBackend` real sobre `hive_mind.db/search_vec` para
>   `memory_vectors`, com filtro `workspace_id` e validação de dimensão.
> - [x] `SQLiteVecBackend` real sobre tabelas sqlite-vec auxiliares em
>   `hive_mind.db` para `document_vectors`, `code_vectors`, `visual_vectors`,
>   `graph_vectors` e `summary_vectors`, com metadados em `vector_metadata`.
> - [x] `MilvusBackend` real atrás de `VECTOR_BACKEND=milvus`, usando
>   `pymilvus.MilvusClient`, criação de coleção com schema explícito e índice
>   `AUTOINDEX/COSINE`.
> - [x] registro canônico em `core/vector_collections.py` para
>   `memory_vectors`, `observation_vectors`, `document_vectors`, `code_vectors`,
>   `visual_vectors`, `graph_vectors`, `summary_vectors`, incluindo o mapeamento
>   B2 de `observation_vectors` para `claude-mem.db/vec_observations`.
> - [x] metadados canônicos obrigatórios no Milvus:
>   `parent_id`, `parent_type`, `brain_lobe`, `knowledge_type`, `project`,
>   `source_uri`, `hash`, `valid_at`, `workspace_id`.
> - [x] aceite E2E K2 com Milvus real via Docker:
>   `docker compose -f integrations/milvus/docker-compose.yml up -d`;
>   `.venv/bin/python -m pytest tests/real/test_vector_backend_sqlite.py
>   tests/real/test_vector_backend_milvus.py -q` → 6 passed.
> - [x] task 5 para a coleção viva `memory_vectors`: `core/vector_sync.py`
>   sincroniza `hive_mind.db/search_vec` → Milvus via `MilvusBackend`, com
>   idempotência por `(id, hash, workspace_id)` e relatório `scanned/upserted/
>   skipped/failed/errors`.
> - [x] task 5 para a coleção viva externa `observation_vectors`:
>   `SQLiteVecBackend` consulta `claude-mem.db/vec_observations` em modo
>   read-only local; a escrita continua worker-owned pelo `sqlite-vec-worker`.
>   `core/vector_sync.py` exporta `claude-mem.db/vec_observations` → Milvus com
>   id estável `obs-<id>` e o mesmo contrato de idempotência por
>   `(id, hash, workspace_id)`.
> - [x] task 8 para `memory_vectors`: backfill real do acervo vetorial vivo,
>   hidratando metadados canônicos a partir de `neurons` + `search_vec`.
> - [x] task 8 para `observation_vectors`: backfill real do acervo já
>   materializado no claude-mem, hidratando metadados canônicos a partir de
>   `observations` + `vec_observations`.
> - [x] task 8 para coleções auxiliares: `core/vector_sync.py` vetoriza/backfilla
>   fontes reais por coleção:
>   `document_vectors` e `code_vectors` a partir de `neurons` + `search_vec`;
>   `visual_vectors` a partir de `visual_memories`;
>   `graph_vectors` a partir de `causal_edges`;
>   `summary_vectors` a partir dos Markdown em `cerebelo/{sessoes,diario,
>   semanal,mensal,padroes}`.
> - [x] migração K2: `core/umc_schema.sql` e `core/database.py` criam
>   `vec_documents`, `vec_code`, `vec_visual`, `vec_graph`, `vec_summary` e
>   `vector_metadata`; o CLI roda `ensure_migrations()` antes de operar em
>   banco existente.
> - [x] aceite E2E sync/backfill: `.venv/bin/python -m pytest
>   tests/real/test_vector_sync_milvus.py -q` → 2 passed, cobrindo primeira
>   carga, reexecução idempotente, atualização por hash e falha real de linha
>   rejeitada pelo Milvus sem esconder o erro.
> - [x] aceite E2E `observation_vectors`: `.venv/bin/python -m pytest
>   tests/real/test_observation_vectors.py -q` → 2 passed, cobrindo
>   `claude-mem.db` real temporário com `sqlite-vec`, filtros por projeto/tipo,
>   recusa de escrita direta worker-owned, sync para Milvus real e reexecução
>   idempotente.
> - [x] aceite E2E live bounded: `.venv/bin/python -m pytest
>   tests/real/test_vector_sync_live_e2e.py -q` → 1 passed, lendo
>   `hive_mind.db` real + `~/.claude-mem/claude-mem.db` real em modo read-only,
>   exportando lote limitado para coleções Milvus temporárias e validando
>   idempotência sem alterar os bancos fonte.
> - [x] CLI operacional de backfill/sync:
>   `scripts/maintenance/vector-sync.py` executa as 7 coleções K2 contra Milvus
>   real, com `--collection`, `--limit`, `--hive-db`, `--claude-mem-db`,
>   `--milvus-uri`, `--milvus-prefix` e `--json`; para auxiliares, faz backfill
>   local antes do sync. Aceite `.venv/bin/python -m pytest
>   tests/real/test_vector_sync_cli_e2e.py -q` → 1 passed, cobrindo primeira
>   carga das 7 coleções e reexecução idempotente via subprocesso.
> - [x] aceite E2E completo K2: `.venv/bin/python -m pytest
>   tests/real/test_vector_backend_sqlite.py
>   tests/real/test_vector_backend_milvus.py
>   tests/real/test_vector_sync_milvus.py
>   tests/real/test_observation_vectors.py
>   tests/real/test_vector_sync_live_e2e.py
>   tests/real/test_vector_sync_cli_e2e.py
>   tests/real/test_vector_auxiliary_collections.py -q -rA` → 14 passed.
> - [x] aceite CLI explícito:
>   `.venv/bin/python scripts/maintenance/vector-sync.py --collection
>   memory_vectors --collection observation_vectors --limit 2 --json` →
>   `failed=0`, `upserted=2` para ambas as coleções.

Tasks:

1. criar `core/vector_backend.py` com interface:
   `upsert`, `delete`, `query`, `hybrid_query`, `count`, `health`;
2. implementar `SQLiteVecBackend` sobre `hive_mind.db`;
3. implementar `MilvusBackend` atras de env `VECTOR_BACKEND=milvus`;
4. criar colecoes canonicas:
   `memory_vectors`, `observation_vectors`, `document_vectors`,
   `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors`;
5. criar sync local -> Milvus com idempotency/hash;
6. garantir metadados: `parent_id`, `parent_type`, `brain_lobe`,
   `knowledge_type`, `project`, `source_uri`, `hash`, `valid_at`, `workspace_id`;
7. **mapear colecao→(DB, processo)** (B2): `observation_vectors` hoje e
   `vec_observations` em **`claude-mem.db`** (processo `sqlite-vec-worker`), nao
   `hive_mind.db`. O contrato deve declarar onde cada colecao vive e como o backend
   fala com o worker (ou migrar `vec_observations`). "Uma interface, varias
   colecoes" nao pode esconder dois bancos;
8. **backfill por colecao** (B5): vetorizar o acervo existente (document_chunks,
   code_symbols, visual, graph, summaries) — a colecao nova nasce vazia sem isso.
   **Estado K2:** backfill implementado para o acervo real disponível hoje:
   neurons `document`/`code`, `visual_memories`, `causal_edges` e arquivos de
   resumo do Cerebelo. Quando K6 criar `document_chunks` dedicado, ele deve
   alimentar `document_vectors` pelo mesmo contrato, sem substituir o backend.

Conexoes:

- `core/database.py`
- `core/indexing.py`
- `core/search.py`
- `scripts/services/sinapse-mcp.py`
- `scripts/services/sinapse-api.py`
- `integrations/milvus/`

Aceite real:

```bash
docker compose -f integrations/milvus/docker-compose.yml up -d   # compose vendorizado, imagem pinada por digest
.venv/bin/python -m pytest tests/real/test_vector_backend_sqlite.py -q
VECTOR_BACKEND=milvus .venv/bin/python -m pytest tests/real/test_vector_backend_milvus.py -q
.venv/bin/python -m pytest tests/real/test_vector_sync_milvus.py -q
.venv/bin/python -m pytest tests/real/test_observation_vectors.py -q
.venv/bin/python -m pytest tests/real/test_vector_sync_live_e2e.py -q
.venv/bin/python -m pytest tests/real/test_vector_sync_cli_e2e.py -q
.venv/bin/python scripts/maintenance/vector-sync.py --collection memory_vectors --collection observation_vectors --limit 2 --json
```

---

### K3 — Knowledge Intake E Promotion Pipeline

**Objetivo:** transformar observations, discoveries, summaries e arquivos em
candidatos tipados, sem perder evidencia.

> **Entregue (2026-06-28):**
> - [x] `core/knowledge/intake.py`: normaliza observations/discoveries/session
>   summaries e arquivos em candidatos canonicos (`fact`, `decision`,
>   `learning`, `preference`, `rationale`, `next_step`, `project_status`,
>   `document_chunk`, `code_symbol`, `visual_observation`) preservando
>   `evidence`, `workspace_id`, `project`, `source_id` e hash idempotente.
> - [x] `core/knowledge/promotion.py`: persiste `knowledge_candidates`,
>   promove candidatos duraveis para `neurons`, `next_step` para `goals`,
>   grava `observations.neuron_id` quando ha neuronio, mantem raw intacto e
>   coloca erro estrutural em quarentena (`archived=2`, motivo, retry policy).
> - [x] arquivos/summaries: `promote_files()` classifica docs como
>   `document_chunk`, codigo como `code_symbol` e cadencias do cerebelo
>   (`sessoes`, `diario`, `semanal`, `mensal`, `anual`) como
>   `project_status`.
> - [x] promotores existentes refatorados com saida `candidate-only`:
>   `decision_promoter`, `pattern_distiller`, `conflict_detector`,
>   `sector_classifier`, `drift_detector`, `topic_consolidator`,
>   `work_tracker`, todos com `workspace_id`.
> - [x] conexoes operacionais: `sinapse-write.py promotion`, MCP
>   `sinapse_promote_knowledge`, dream cycle com intake K3 candidate-only antes
>   da sintese legada, schema principal + schema CRR + `setup_crdt.py`.
> - [x] testes adicionados/rodados: `tests/real/test_promotion_pipeline_sqlite.py`
>   (observations/discoveries, quarentena, files/docs/code/summaries),
>   `tests/unit/test_promoter_candidate_contract.py`,
>   `tests/unit/test_sinapse_mcp.py`, `tests/unit/test_dream_resilience.py`,
>   `tests/unit/test_database.py`.
> - [x] aceite real 2026-06-29:
>   `tests/real/test_promotion_pipeline_sqlite.py` = 3 passed;
>   `scripts/dream/dream_cycle.py --once --real` = `ok`, 30 observations,
>   29 candidatos K3 candidate-only, 19 neuronios persistidos em 3 projetos;
>   `sinapse-write.py query "decisoes promovidas hoje"` = exit 0 com JSON no
>   stdout. Regressao focada K3/CLI/MCP/Graphiti = 89 passed. Suite completa
>   `./tests/run_all.sh` = Smoke 19 passed; Unit 494 passed / 3 skipped;
>   Integration 109 passed / 2 skipped; E2E 22 passed.
> - [x] hardening operacional descoberto no aceite: provider `antigravity`
>   (`agy`) usa HOME real por padrao para herdar a autenticacao feita no CLI;
>   HOME isolado ficou apenas como diagnostico (`AGY_USE_ISOLATED_HOME=1`).

**JA EXISTEM promotores por area** (`docs/11` §3.1): `decision_promoter`,
`pattern_distiller`, `conflict_detector`, `sector_classifier`, `drift_detector`,
`topic_consolidator`, `work_tracker`. O intake/promotion **orquestra e tipa**
esses writers (classificacao, quarentena, idempotencia), nao os recria.

Tasks:

1. criar `core/knowledge/intake.py` (normaliza+classifica; chama os promotores §3.1);
2. criar `core/knowledge/promotion.py`;
3. normalizar fontes: claude-mem observation, discovery, session summary,
   daily/weekly/monthly/yearly summaries, docs, code symbols;
4. classificar tipos canonicos de `docs/11`:
   `fact`, `decision`, `learning`, `preference`, `rationale`, `next_step`,
   `project_status`, `document_chunk`, `code_symbol`, `visual_observation`;
5. criar quarentena para erro estrutural (`archived=2`, motivo, retry policy);
6. gravar `observation.neuron_id` quando promocao criar neuronio;
7. manter raw intacto;
8. **refatorar cada promotor existente** (B4 — `decision_promoter`,
   `pattern_distiller`, `conflict_detector`, `sector_classifier`, `drift_detector`,
   `topic_consolidator`, `work_tracker`) para `candidate-only` + idempotente +
   `workspace_id`, conforme o contrato de escrita (`docs/11` §12), com teste por
   promotor. **Sao N refactors, nao 2 arquivos novos.**

Conexoes:

- `scripts/dream/dream_cycle.py`
- `scripts/services/sinapse-write.py`
- `scripts/services/sinapse-mcp.py`
- `cerebro/cortex/temporal/`
- `cerebro/cortex/frontal/`
- `cerebro/cerebelo/`

Aceite real:

```bash
.venv/bin/python -m pytest tests/real/test_promotion_pipeline_sqlite.py -q
.venv/bin/python scripts/dream/dream_cycle.py --once --real
python3 scripts/services/sinapse-write.py query "decisoes promovidas hoje"
```

---

### K4 — Claude-Mem Promotion Bridge

**Objetivo:** usar o melhor do claude-mem: raw events, discoveries,
session_summaries, lessons learned e next steps.

**JA EXISTE:** `scripts/services/claude_mem_bridge.py` le `claude-mem.db`
read-only, preserva `project`, idempotente (`cm-{content_hash}` + INSERT OR
IGNORE) → `hive_mind.observations`. Esta fase **estende**, nao recria.

Tasks:

1. promover o bridge existente para `core/knowledge/claude_mem_bridge.py` (ou
   manter o path e importar de `core/knowledge/`);
2. **decisao de mecanismo (nao duplicar):** manter a leitura SQL direta (atual,
   robusta, sem MCP) OU migrar para `search→timeline→get_observations`; o atual
   ja funciona — so trocar com razao;
3. estender a importacao para `discoveries` e `session_summaries` com `source_id`
   estavel (hoje importa a tabela `observations`);
4. promover:
   - `investigated` -> rationale/investigation note;
   - `completed` -> operational_fact/session_summary;
   - `learned` -> learning atomico;
   - `decisions` -> decision;
   - `next_steps` -> goal/task;
5. evitar falso negativo por query longa: bridge deve aceitar ids filtrados e
   tambem varrer pendencias por janela temporal.

Conexoes:

- `scripts/services/sinapse-mcp.py`
- `claude-mem` global em `~/.claude-mem`
- `core/knowledge/promotion.py`
- `cerebro/cerebelo/sessoes`

Aceite real:

```bash
.venv/bin/python -m pytest tests/real/test_claude_mem_bridge.py -q
python3 scripts/services/sinapse-write.py query "ultimos discoveries promovidos"
```

---

### K5 — Cadencia Hierarquica Completa

**Objetivo:** concluir sessao, diario, semanal, mensal e anual como camadas
operacionais.

Tasks:

1. manter `session_consolidator.py`, `daily_writer.py` e
   `weekly_synthesizer.py` alinhados ao contrato de `docs/11`;
2. criar `scripts/dream/monthly_synthesizer.py`;
3. criar `scripts/dream/yearly_synthesizer.py`;
4. adicionar schemas Pydantic para mensal/anual;
5. escrever em `MONTHLY_ROOT` e `YEARLY_ROOT`;
6. enviar resumos para `summary_vectors`;
7. promover apenas decisoes, aprendizados, riscos e metas duraveis.

Conexoes:

- `core/paths.py`
- `core/schemas/session_models.py`
- `core/schemas/weekly_models.py`
- `scripts/dream/*_synthesizer.py`
- `setup-brain`

Aceite real:

```bash
HIVE_SESSION_SUMMARIZER_PROVIDER=ollama HIVE_SESSION_SUMMARIZER_MODEL=qwen2.5:3b \
  .venv/bin/python scripts/dream/session_consolidator.py --real
.venv/bin/python scripts/dream/monthly_synthesizer.py --month "$(date +%Y-%m)" --real
.venv/bin/python scripts/dream/yearly_synthesizer.py --year "$(date +%Y)" --real
.venv/bin/python -m pytest tests/real/test_cadence_real.py -q
```

---

### K6 — DocumentPipeline Com Parent Context

**Objetivo:** ingerir documentos e vault docs com chunks pequenos, citacoes e
recuperacao do pai.

Tasks:

1. criar `core/document_pipeline.py`;
2. implementar parser Markdown por secoes;
3. implementar parser texto/PDF quando dependencia real estiver instalada;
4. adicionar adapter RAGFlow opcional;
5. gravar `document_chunks` com offsets e hash;
6. indexar em `document_vectors`;
7. retornar citacoes com `source_uri`, offset e parent.

Conexoes:

- `cerebro/cortex/parietal/`
- `core/vector_backend.py`
- `integrations/ragflow/`
- `scripts/knowledge/document_ingest.py`

Aceite real:

```bash
.venv/bin/python -m pytest tests/real/test_document_pipeline_markdown.py -q
.venv/bin/python -m pytest tests/real/test_document_pipeline_pdf.py -q
```

---

### K7 — RetrievalRouter

**Objetivo:** rotear consulta para temporal, memoria, documento, codigo, grafo
ou hibrido, com caminho de recuperacao auditavel.

Tasks:

1. criar `core/retrieval/router.py`;
2. criar intents: `recent_activity`, `decision`, `learning`, `document`,
   `code`, `causal`, `multi_hop`, `visual`, `self_state` (insula),
   `operational` (tronco), `sector` (diencefalo), `hybrid`;
3. integrar `sinapse_query` ao router;
4. integrar `sinapse_temporal_*` para recentes;
5. integrar `VectorBackend` por colecao;
6. integrar Graphify, Graphiti e LightRAG;
7. retornar `retrieval_path`, `citations`, `confidence`, `missing_context`;
8. reranker opcional entre fusao e retorno (contrato `docs/11` §17.1; off em `local-min`);
9. **classificador de intent explicito** (B7): papel `topic_router` (local, ja
   existe em `core/auth.py`) decide o intent + fallback `hybrid` quando incerto;
   caso de roteamento errado no golden set (§17.3).

Conexoes:

- `scripts/services/sinapse-mcp.py`
- `scripts/services/sinapse-api.py`
- `core/search.py`
- `integrations/llama_index/`

Aceite real:

```bash
.venv/bin/python -m pytest tests/real/test_retrieval_router_real.py -q
python3 scripts/services/sinapse-write.py query "o que foi decidido sobre embeddings?"
```

---

### K8 — Metricas, Health E Auditoria

**Objetivo:** provar cobertura e detectar buracos de memoria.

**JA EXISTE health da insula** (`docs/11` §3.1): `health_dashboard.py`,
`alert_dispatcher.py`, `review_writer.py` (→`saude/`). `knowledge_health.py`
**adiciona metricas de cobertura de conhecimento**, nao substitui o dashboard.

Tasks:

1. criar `scripts/health/knowledge_health.py`;
2. medir `neurons_vectorized_pct`, `observations_linked_pct`,
   `discoveries_pending`, `summary_vectors_total`, `orphan_vectors`,
   `milvus_sync_lag`, `query_route_distribution`, **`*_vectorized_pct` por colecao**
   (B5: gate de cobertura cobre document/code/visual/graph/summary, nao so neurons);
3. expor no `sinapse_health`;
4. adicionar endpoint REST `/api/v1/knowledge/health`;
5. gerar report Markdown em `cerebro/cortex/insula/saude/`;
6. esquecimento intencional: podar `orphan_vectors` (nao so medir) + `forget()` tombstone (contrato `docs/11` §17.2).

Conexoes:

- `core/database.py`
- `core/vector_backend.py`
- `scripts/services/sinapse-mcp.py`
- `scripts/services/sinapse-api.py`

Aceite real:

```bash
.venv/bin/python scripts/health/knowledge_health.py --fail-closed
.venv/bin/python -m pytest tests/real/test_knowledge_health.py -q
```

---

### K9 — Test Harness Real Sem Mocks

**Objetivo:** criar uma suite real para esta frente e impedir regressao por
testes simulados.

> **Entregue (2026-06-28) — esqueleto (gate de B3):**
> - [x] marker `real` + `requires_service` em `pytest.ini`.
> - [x] `tests/real/` (`__init__.py`, `conftest.py` com fixtures `real_db` e
>   `ollama_or_skip`, `README.md`).
> - [x] `tests/run_real_knowledge.sh` (executável; `-m real`).
> - [x] 1º teste real: `tests/real/test_embedding_stack.py` (dim 1024, modelo
>   unificado, colunas da migração) — baseline inicial **3 passed**; suíte real
>   atual **24 passed** após K1 digest gate, K2 sync/backfill das 7 coleções
>   canônicas, incluindo E2E bounded nos bancos reais e CLI operacional
>   `vector-sync.py`.
> - [x] skip genérico de `requires_service` entregue em
>   `tests/real/service_registry.py`: serviços nomeados `ollama`, `milvus`,
>   `falkordb`, `claude_mem`, `ragflow`; desconhecido falha como erro de teste;
>   offline pula com motivo e serviço nomeado.
> - [x] README/runner atualizados para refletir o service registry.
> - [ ] tasks 3,6 (fixtures Milvus/claude-mem, separar mocks) e 7 (golden set §17.3) pendentes.

Tasks:

1. criar marcador pytest `real`;
2. criar `tests/real/`;
3. criar fixtures reais que usam temp project/vault/SQLite, Ollama local,
   Milvus Docker e claude-mem real;
4. criar `tests/real/README.md` com prerequisitos;
5. adicionar `./tests/run_real_knowledge.sh`;
6. separar testes antigos mockados como unitarios, sem contar como aceite da
   arquitetura de conhecimento;
7. eval de recuperacao: `tests/real/golden_retrieval.jsonl` + precision/recall@k
   como gate (contrato `docs/11` §17.3).
8. implementar skip por serviço para `requires_service`: cada teste declara o
   serviço exigido; se offline, skip com motivo; se online, falha real reprova.

Regra:

```text
Aceite de fase K* = teste real verde + health real verde.
Teste mockado pode ajudar desenvolvimento, mas nao fecha fase.
```

Aceite real:

```bash
./tests/run_real_knowledge.sh
```

---

### K10 — Installer E Maquina Zerada

**Objetivo:** instalar tudo em maquina nova e provar funcionamento end-to-end.

Tasks:

1. atualizar `install.sh` para baixar modelos locais obrigatorios;
2. `components.py bootstrap` (clona só graphify/neural-memory/rtk) + `docker compose up` dos wrappers Milvus/RAGFlow (não clona monorepo);
3. sincronizar `.venv` via `uv sync --frozen --all-groups` com
   `ragflow-sdk`, `pymilvus` e `llama-index`;
4. iniciar/validar Ollama, claude-mem, FalkorDB, Milvus local quando perfil pedir;
5. rodar migrations de schema/vetores;
6. registrar MCP por agente sem sobrescrever configs externas;
7. rodar smoke real;
8. produzir relatorio final com paths, portas, modelos e health.

Aceite real:

```bash
./install.sh --profile local-full --with-real-tests
./tests/run_real_knowledge.sh
python3 scripts/services/sinapse-write.py health
```

---

## 6. Dependencias Entre Fases

```text
K0 Auditoria
  -> K1 Vendors
  -> K2 VectorBackend
      -> K3 Promotion
          -> K4 Claude-Mem Bridge
          -> K5 Cadencia
      -> K6 DocumentPipeline
      -> K7 RetrievalRouter
          -> K8 Health
              -> K9 Test Harness
                  -> K10 Installer
```

**O esqueleto de K9 (`tests/real/` + `run_real_knowledge.sh`) e PRE-REQUISITO de
K0** (B3): sem ele, o "Aceite real" de toda fase e inexequivel. A migracao
CRR-safe (K0 task 7, B1) tambem precede qualquer fase que escreva no schema.

---

## 7. Mapa De Arquivos A Criar Ou Alterar

| Area | Arquivos |
|---|---|
| VectorBackend | `core/vector_backend.py`, `core/vector_collections.py`, `tests/real/test_vector_backend_*.py` |
| Promotion | `core/knowledge/intake.py`, `core/knowledge/promotion.py`, `core/knowledge/types.py`, `tests/real/test_promotion_pipeline_sqlite.py` |
| Claude-Mem bridge | `core/knowledge/claude_mem_bridge.py` (**promover** de `scripts/services/claude_mem_bridge.py`, já existe), `tests/real/test_claude_mem_bridge.py` |
| Cadencia | `scripts/dream/monthly_synthesizer.py`, `scripts/dream/yearly_synthesizer.py`, `core/schemas/monthly_models.py`, `core/schemas/yearly_models.py` |
| DocumentPipeline | `core/document_pipeline.py`, `scripts/knowledge/document_ingest.py`, `tests/real/test_document_pipeline_*.py` |
| Retrieval | `core/retrieval/router.py`, `core/retrieval/intents.py`, `tests/real/test_retrieval_router_real.py` |
| Health | `scripts/health/knowledge_health.py`, `tests/real/test_knowledge_health.py` |
| Installer | `install.sh`, `.env.example`, `pyproject.toml`, `uv.lock`, `scripts/setup/install_services.py`, `scripts/maintenance/integrations-update.sh`, `tests/run_real_knowledge.sh` |
| Vendors | `integrations/milvus/{client.py,docker-compose.yml,README.md}`, `integrations/ragflow/{client.py,docker-compose.yml,README.md}` (wrappers; sem clone). LlamaIndex = dep pip em `pyproject.toml` |

---

## 8. Criterio De Pronto

Uma fase so esta pronta quando:

1. o codigo usa paths canonicos e env vars;
2. os vendors externos, se houver, estao em `integrations/`;
3. existe health check real;
4. existe teste real sem mock fechando o comportamento;
5. os dados escritos preservam fonte, hash e idempotencia;
6. falhas nao apagam raw data;
7. a documentacao e o instalador foram atualizados;
8. `sinapse_query` consegue recuperar o resultado pela rota correta.

---

## 9. Riscos E Contramedidas

| Risco | Contramedida |
|---|---|
| Maquina simples nao roda modelos maiores | defaults pequenos, perfis `local-min` e `local-full`, override por env |
| Milvus aumenta complexidade local | backend opcional por env, sqlite-vec obrigatorio e sempre funcional |
| RAGFlow virar nova fonte de verdade | wrapper headless; store do RAGFlow e cache; UMC canonico |
| Inchar repo clonando monorepo de servico | wrapper: imagem pinada por digest + SDK no `uv.lock` (§3.1) |
| LlamaIndex esconder o roteamento | dep pip/adapter; `RetrievalRouter` proprio |
| Testes lentos | separar `tests/real`, mas exigir para aceite de fase |
| Promocao criar fatos falsos | candidate-only, evidencia obrigatoria, conflito com `invalid_at` |
| Duplicacao vetorial | hash + parent_id + orphan vector audit |
| **`ALTER` puro quebra tabela CRR** (B1) | `alter_table_crr_safe()` com `crsql_begin_alter`/`commit_alter`; backup antes; testar com `HIVE_CRDT_SYNC=true` |
| **VectorBackend "unico" esconde 2 bancos** (B2) | declarar colecao→(DB,processo); `observation_vectors` vive em `claude-mem.db` (worker), nao `hive_mind.db` |
| `integrations-update.sh` como aceite amplo demais | **mitigado:** `--no-components`/`--wrappers-only` implementados; wrappers K1 cobertos por teste real |
| `requires_service` prometido mas sem registry generico | **mitigado:** registry/hook implementado; fixtures reais de Milvus/FalkorDB/claude-mem/RAGFlow ainda pendentes |
| migração estrutural seguir com schema parcial | **mitigado:** fail-closed por padrão; bypass legado só com `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` |

---

## 10. Proximo Corte Recomendado

Continuar a partir da base **K0 + K1 + K2** ja verificada:

1. iniciar K3 Promotion Pipeline, preservando raw e usando candidatos tipados;
2. estender K4 para discoveries/session summaries do claude-mem sem perder
   `investigated`, `completed`, `learned`, `decisions` e `next_steps`;
3. manter K2 como gate regressivo das 7 coleções antes de qualquer mudança em
   promotion, document pipeline ou retrieval;
4. expandir K9 com fixtures reais reutilizáveis para Milvus, claude-mem,
   FalkorDB e RAGFlow usando o service registry ja entregue;
5. manter o teste real de embeddings 1024d em Ollama + SQLite + migração com
   backup como baseline regressivo.

Esse corte usa o backend vetorial ja fechado como base para escrita/promocao
real de conhecimento.

## 11. Auditoria Final De Alinhamento (2026-06-28)

Resultado comparando arquitetura, plano e testes atuais:

| Item | Estado atual verificado | Cobertura no desenho |
|---|---|---|
| modelo de embedding unico | `core/database.py` e worker usam `snowflake-arctic-embed2:latest`; teste real confirmou 1024d | coberto em K0 e §4 |
| migração workspace/federação | unit 12 passed; DB real tem `workspace_id`, `origin_instance`, `origin_signature`, `embedding_model`, `embedding_dim`; ADD COLUMN legado passa por CRR-safe | coberto em `docs/11` §18 e K0 |
| backup antes da migração | teste unitário cobre backup em DB arquivo e skip em `:memory:` | coberto em K0/B8 |
| wrappers vs clones | script atual só atualiza graphify/neural-memory/rtk como componentes git | coberto, com contrato negativo para `components.lock.json` |
| aceite real sem mock | suíte K2 completa roda 14 passed, incluindo SQLite, Milvus, `claude-mem.db`, sync/backfill das 7 coleções, E2E bounded nos bancos reais e CLI operacional `vector-sync.py`; comando de aceite explícito exportou 2 `memory_vectors` + 2 `observation_vectors` com `failed=0` | K2 coberto; K9 ainda precisa fixtures reutilizáveis dos demais serviços |
| skip de serviço offline | registry/hook em `tests/real/service_registry.py`; unit 5 passed | coberto para seleção/skip; falta fixture real por backend novo |
| update de integrações | `--no-components` e `--wrappers-only` implementados; K1 wrappers importados e `uv lock --upgrade && uv sync` verde | coberto para gate de update |
| falha de migração estrutural | falha fechado por padrão; bypass legado exige `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` | coberto no core |
| regressões globais | `./tests/run_all.sh` verde: Smoke 19 passed; Unit 474 passed / 3 skipped; Integration 107 passed / 2 skipped; E2E 22 passed | coberto no recorte atual |

Conclusao: K1 esta coberto para wrappers/pip. K2 esta coberto para as 7 colecoes
canonicas (`memory_vectors`, `observation_vectors`, `document_vectors`,
`code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors`) tanto no
backend SQLite local quanto no sync para Milvus. As proximas fases nao devem
recriar backend vetorial; devem alimentar essas colecoes pelo contrato ja
entregue. K9 ainda precisa expandir fixtures reais reutilizaveis para todos os
servicos usados nas proximas fases.
