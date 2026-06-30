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
| `lightrag` | `HIVE_LIGHTRAG_MODEL` | `qwen2.5:3b` | sim | extracao RAG relacional local |
| `graphiti` | `HIVE_GRAPHITI_MODEL` | `qwen2.5:3b` | sim | entidades/relacoes temporais |

Todos os papeis continuam configuraveis via `setup-brain`. O default de
instalacao deve baixar modelos pequenos suficientes:

```bash
ollama pull snowflake-arctic-embed2:latest
ollama pull qwen2.5:3b
ollama pull qwen2.5-coder:3b
```

Perfil recomendado para maquina com mais folga:

```bash
ollama pull qwen2.5:7b
```

### 4.3 Perfis De Execucao

| Perfil | Objetivo | Modelos obrigatorios | Backends |
|---|---|---|---|
| `local-min` | laptop simples | snowflake embedder, qwen2.5:3b, qwen2.5-coder:3b | SQLite, sqlite-vec, Graphify AST, claude-mem |
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
ollama list | rg 'snowflake-arctic-embed2|qwen2.5:3b|qwen2.5-coder:3b'
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

> Status K4 (2026-06-29):
>
> - [x] `core/knowledge/claude_mem_bridge.py` criado; o script
>   `scripts/services/claude_mem_bridge.py` agora e wrapper de compatibilidade.
> - [x] Mecanismo mantido como leitura SQL direta read-only do
>   `~/.claude-mem/claude-mem.db`. Decisao: este caminho evita falso negativo
>   por query longa e permite backfill deterministico por tabela, id e janela
>   temporal. O fluxo `search -> timeline -> get_observations` continua sendo o
>   melhor caminho interativo para agentes, mas nao substitui o bridge de
>   promocao/backfill.
> - [x] Importa `observations`, `session_summaries` e, quando existir no runtime,
>   `discoveries`. No schema real atual do claude-mem, nao ha tabela
>   `discoveries`; discoveries ricos aparecem como `observations.type =
>   'discovery'` com `facts`, `narrative`, `concepts`, `files_*`.
> - [x] Cada registro recebe `source_id` estavel:
>   `claude-mem:<table>:<id>`, preservado em `metadata.source_id` e evidencia.
> - [x] `session_summaries` promove `investigated -> rationale`,
>   `completed -> operational_fact`, `learned -> learning`, `decisions ->
>   decision`, `next_steps -> goal/task`.
> - [x] Bridge aceita ids filtrados (`source_ids`) e janela temporal
>   (`since_epoch`, `until_epoch`), tambem expostos no CLI/MCP:
>   `sinapse-write.py promotion --import-claude-mem --source-id ...` e
>   `sinapse_promote_knowledge(import_claude_mem=true, ...)`.
> - [x] Aceite real adicionado em `tests/real/test_claude_mem_bridge.py` e
>   validado com SQLite real, sem mocks: 2 passed.
> - [x] Aceite operacional contra o runtime atual:
>   `sinapse-write.py promotion --import-claude-mem --source-id ...` importou
>   2 registros reais do claude-mem global e promoveu 6 candidatos com
>   `source_id` preservado.
> - [x] Aceite de CLI em maquina sem `sqlite_vec` no Python do sistema:
>   `python3 scripts/services/sinapse-write.py query "ultimos discoveries
>   promovidos"` reexecuta pela `.venv` e sai 0.
> - [x] Verificacao global final: `./tests/run_all.sh` verde em 2026-06-29
>   (Smoke 19 passed; Unit 496 passed / 3 skipped; Integration 109 passed /
>   2 skipped; E2E 22 passed). O teste de visao real usa a configuracao ativa
>   do `setup-brain`/`.env` (`HIVE_VISION_*`), que neste runtime aponta para
>   Ollama local (`llava:7b`), e passou sem depender de Ollama Cloud.

---

### K5 — Cadencia Hierarquica Completa

**Objetivo:** concluir sessao, diario, semanal, mensal e anual como camadas
operacionais.

> **Entregue (2026-06-29) — K5 cadencia hierarquica completa:**
>
> - [x] `session_consolidator.py`, `daily_writer.py` e
>   `weekly_synthesizer.py` alinham escrita de cadencia com `summary_vectors`.
>   A indexacao de sessao e best-effort para nao quebrar hook de encerramento;
>   daily/weekly registram aviso quando o vetor estiver indisponivel.
> - [x] `scripts/dream/monthly_synthesizer.py` criado com `--month YYYY-MM`,
>   `--real`, frontmatter auditavel, bloco idempotente `auto:start/end`,
>   escrita em `MONTHLY_ROOT` e indexacao imediata em `summary_vectors`.
> - [x] `scripts/dream/yearly_synthesizer.py` criado com `--year YYYY`,
>   `--real`, frontmatter auditavel, bloco idempotente `auto:start/end`,
>   escrita em `YEARLY_ROOT` e indexacao imediata em `summary_vectors`.
> - [x] Schemas Pydantic adicionados:
>   `core/schemas/monthly_models.py::MonthlySummaryModel` e
>   `core/schemas/yearly_models.py::YearlySummaryModel`.
> - [x] `core/vector_sync.py` ganhou `index_summary_file_to_sqlite()` e o
>   backfill de `summary_vectors` inclui `cerebelo/anual`.
> - [x] Mensal/anual so estruturam itens duraveis: decisoes, aprendizados,
>   riscos, metas, drift/principios. Microdetalhe operacional fica nas
>   camadas inferiores.
> - [x] Aceite real executado:
>   `session_consolidator.py --real` exit 0 com `summary_vector`;
>   `monthly_synthesizer.py --month "$(date +%Y-%m)" --real` exit 0;
>   `yearly_synthesizer.py --year "$(date +%Y)" --real` exit 0;
>   `tests/real/test_cadence_real.py` 1 passed.
> - [x] Regressao focada: `tests/unit/test_session_cadence.py` +
>   `tests/real/test_vector_auxiliary_collections.py` +
>   `tests/real/test_cadence_real.py` -> 15 passed, 1 skipped.
> - [x] Gate global: `./tests/run_all.sh` verde (Smoke 19 passed; Unit
>   496 passed / 3 skipped; Integration 109 passed / 2 skipped; E2E
>   22 passed).
>
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

**Status:** ✅ Entregue em 2026-06-30 (`v3.4.0`).

**Objetivo:** ingerir documentos e vault docs com chunks pequenos, citacoes e
recuperacao do pai.

**Por que este K existe:** K6 fecha a lacuna entre "arquivo lido" e
"conhecimento recuperavel com prova". O sistema nao deve apenas salvar texto
bruto: ele precisa preservar o documento-pai, dividir em chunks auditaveis,
indexar em `document_vectors` e devolver citacoes que permitam reconstruir de
onde a resposta veio.

**Contrato operacional K6:**

1. **Entrada canonica:** arquivo local ou vault doc recebido por
   `DocumentPipeline.ingest(path, project, workspace_id?)`.
2. **Parent document:** cada documento vira um registro em `document_memories`
   com `document_id=doc-<sha16>`, `source_uri`, `file_hash`, metadata e
   `workspace_id`.
3. **Chunk atomico:** cada trecho vira `document_chunks`, sempre ligado ao pai
   por `parent_id`/`parent_type=document`, com `chunk_index`, `heading`,
   offsets absolutos, `hash` e metadata.
4. **Vetor canonico:** cada chunk entra em `document_vectors` via
   `VectorBackend`, usando o modelo canonico de embedding
   `snowflake-arctic-embed2:latest` por padrao e metadados obrigatorios.
5. **Recuperacao auditavel:** consulta documental deve devolver chunk,
   `source_uri`, offsets, score e parent completo; nunca apenas texto solto.
6. **RAGFlow headless:** RAGFlow pode ajudar em parsing/chunking/citacoes, mas
   seu store e cache. Tudo que sobreviver precisa ser normalizado para UMC +
   `document_vectors`.
7. **Idempotencia:** reingestao do mesmo documento substitui parent/chunks e
   remove vetores antigos daquele `document_id` antes de reindexar.

**Fluxo de ingestao esperado:**

```text
arquivo/vault doc
    -> parser especifico (.md/.txt/.pdf/.docx/RAGFlow opcional)
    -> parent document em document_memories
    -> chunks estruturais em document_chunks
    -> embedding local
    -> document_vectors
    -> consulta com citacao + parent context
```

**Componentes implementados:**

| Componente | Papel | Contrato |
|---|---|---|
| `core/document_pipeline.py` | Pipeline canonico K6 | Parseia, normaliza, chunkiza, grava parent/chunks, indexa vetores e consulta com citacao |
| `DocumentPipeline.ingest()` | Entrada de escrita | Recebe path real, calcula hash, recria parent/chunks/vetores de forma idempotente |
| `DocumentPipeline.query()` | Entrada de leitura | Consulta `document_vectors` e retorna chunk + parent + offsets + score |
| `scripts/knowledge/document_ingest.py` | Ponte operacional | Usa K6 em banco real e preserva observation `document_ingest` para o Dream Cycle |
| `integrations/ragflow/` | Adapter opcional | Verifica/encapsula RAGFlow sem transformar RAGFlow em fonte canonica |
| `document_memories` | Registro pai | Guarda documento, hash, origem, metadata, projeto e workspace |
| `document_chunks` | Unidades recuperaveis | Guarda chunks atomicos com parent, heading, offsets, hash e metadata |
| `document_vectors` | Indice semantico | Guarda embeddings dos chunks via `VectorBackend` local-first |

**Contrato de banco e metadados:**

| Campo | Onde aparece | Obrigatorio | Motivo |
|---|---|---:|---|
| `document_id` | `document_memories`, `document_chunks`, metadata vetorial | sim | ID estavel para reingestao e parent context |
| `parent_id` / `parent_type` | `document_chunks`, `document_vectors` | sim | Permite subir do chunk para o documento-pai |
| `source_uri` | parent, chunk, vetor | sim | Citacao auditavel e reconstrucao da fonte |
| `file_hash` | parent | sim | Detecta mudanca do arquivo e evita duplicidade logica |
| `hash` | chunk, metadata vetorial | sim | Idempotencia por chunk e sync futuro |
| `offset_start` / `offset_end` | chunk | sim | Citacao precisa dentro do documento |
| `heading` | chunk | nao | Contexto estrutural para Markdown/documentos seccionados |
| `workspace_id` | parent, chunk, vetor | sim | Isolamento multi-workspace e Milvus futuro |
| `project` | parent, metadata vetorial | sim | Roteamento por projeto e filtro de busca |

**Fluxo de consulta documental:**

```text
query documental
    -> DocumentPipeline.query()
    -> VectorBackend.query(collection=document_vectors)
    -> join metadata/chunk
    -> parent document
    -> resposta com citations[{source_uri, offsets, score, parent}]
```

K6 nao deve responder com texto sem origem. Resultado valido precisa carregar
o trecho recuperado e a prova minima: `source_uri`, offsets e parent.

**Cobertura obrigatoria de edge cases:**

- Markdown com multiplos headings deve preservar contexto estrutural.
- Texto longo sem headings deve quebrar por paragrafo e depois por janela fixa.
- PDF com texto deve usar parser real; PDF sem texto nao pode sumir, deve gerar
  fallback auditavel.
- DOCX deve funcionar quando `python-docx` estiver instalado e falhar de forma
  clara quando a dependencia faltar.
- Reingestao precisa provar que nao sobram chunks/vetores obsoletos.
- Banco minimo antigo continua aceito apenas como compatibilidade; banco real
  deve usar `document_chunks` + `document_vectors`.
- `workspace_id`, `project`, `hash`, `source_uri` e parent metadata sao
  obrigatorios para permitir sync futuro com Milvus e isolamento por workspace.
- Falha de embedding deve ser reportada como falha operacional do pipeline; nao
  pode criar chunk "recuperavel" sem vetor quando o banco real tem sqlite-vec.
- RAGFlow indisponivel nao pode bloquear o caminho local-first; apenas reduz a
  capacidade de parsing avancado quando explicitamente habilitado.
- Documentos duplicados por conteudo em caminhos diferentes preservam
  `source_uri` proprio, mas compartilham hash auditavel para deduplicacao
  posterior.
- Reindexacao precisa limpar `document_vectors` antigos do mesmo parent antes
  de gravar os novos chunks.
- Consulta deve ser deterministica o bastante para teste real: top-k, score e
  parent metadata precisam ser validaveis sem mock.

**Fronteiras explicitas:**

- K6 ingere e recupera documento. Ele nao promove automaticamente qualquer
  trecho para fato/aprendizado duravel; essa promocao continua sendo K3/K4.
- K6 nao substitui K7. O roteamento entre documento, memoria, temporal, codigo
  e grafo acontece no `RetrievalRouter`; K6 e a rota documental.
- K6 nao transforma RAGFlow em banco paralelo. RAGFlow e parser/adapter; o
  material persistente fica em UMC + `document_vectors`.
- K6 nao grava resumo hierarquico de sessao/diario/semanal/mensal/anual; isso
  pertence a K5 e `summary_vectors`.

> **Entregue (2026-06-30) — K6 DocumentPipeline local-first:**
>
> - [x] `core/document_pipeline.py` criado como pipeline canonico para
>   documentos. Ele calcula `file_hash`, gera `document_id` estavel
>   (`doc-<sha16>`), grava o parent em `document_memories` e retorna
>   `IngestResult` auditavel.
> - [x] Parser Markdown por secoes implementado: headings entram como contexto
>   estrutural, offsets absolutos sao preservados, textos longos quebram por
>   paragrafo antes de cair para janela fixa.
> - [x] Parser texto/PDF/DOCX implementado com dependencias reais:
>   `.md`/`.markdown`, `.txt`, `.pdf` via `pypdf` com fallback `PyMuPDF`, e
>   `.docx` via `python-docx` quando instalado. PDF sem texto gera chunk
>   fallback auditavel em vez de perder parent/hash.
> - [x] Adapter RAGFlow opcional entregue em `integrations/ragflow/`. Ele expoe
>   health operacional, mas nao vira fonte de verdade; UMC + `cerebro/`
>   continuam canonicos.
> - [x] Schema UMC recebeu `document_chunks` em caminho normal e CRR-safe,
>   incluindo `document_id`, `parent_id`, `parent_type`, `source_uri`,
>   `chunk_index`, `heading`, `offset_start`, `offset_end`, `hash`,
>   `metadata` e `workspace_id`.
> - [x] `document_vectors` integrado ao `SQLiteVecBackend`, com embedding real
>   de `core.database.embed_text` e metadata canonica:
>   `parent_id`, `parent_type`, `brain_lobe=parietal`,
>   `knowledge_type=document_chunk`, `project`, `source_uri`, `hash`,
>   `valid_at`, `workspace_id`.
> - [x] Recuperacao por citacao entregue em `DocumentPipeline.query()`,
>   retornando `source_uri`, offsets, conteudo do chunk e parent completo
>   (`id`, `type`, `source_uri`, `file_hash`, metadata).
> - [x] `scripts/knowledge/document_ingest.py` conectado ao pipeline novo:
>   em banco real com `sqlite-vec`, PDF/DOCX passam pelo DocumentPipeline e
>   ainda preservam a observation `document_ingest` para o Dream Cycle; schemas
>   minimos antigos seguem pelo caminho legado.
> - [x] Idempotencia garantida: reingestao do mesmo arquivo substitui parent e
>   chunks, remove vetores antigos do documento e reindexa os chunks atuais.
> - [x] Aceite real executado:
>   `test_document_pipeline_markdown.py`,
>   `test_document_pipeline_pdf.py`,
>   `test_document_ingest_pipeline.py` -> 3 passed;
>   `tests/unit/test_document_ingest.py` -> 8 passed;
>   gate global `./tests/run_all.sh` verde.
>
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
.venv/bin/python -m pytest tests/real/test_document_pipeline_markdown.py tests/real/test_document_pipeline_pdf.py tests/real/test_document_ingest_pipeline.py -q
# 3 passed

.venv/bin/python -m pytest tests/unit/test_document_ingest.py -q
# 8 passed

./tests/run_all.sh
# Smoke 19 passed; Unit 497 passed / 3 skipped; Integration 109 passed / 2 skipped; E2E 22 passed
```

---

### K7 — RetrievalRouter

**Status:** ✅ Entregue em 2026-06-30 (`v3.5.0`).

**Objetivo:** rotear consulta para temporal, memoria, documento, codigo, grafo
ou hibrido, com caminho de recuperacao auditavel.

> **Entregue (2026-06-30) — K7 RetrievalRouter auditavel:**
>
> - [x] `core/retrieval/router.py` criado com contrato proprio inspirado em
>   LlamaIndex, sem esconder o roteamento. A saida sempre inclui:
>   `answer_context`, `citations`, `retrieval_path`, `confidence` e
>   `missing_context`.
> - [x] Intents canonicas implementadas:
>   `recent_activity`, `decision`, `learning`, `document`, `code`, `causal`,
>   `multi_hop`, `visual`, `self_state`, `operational`, `sector`, `hybrid`.
> - [x] Classificador explicito entregue: heuristica deterministica local como
>   default e gancho opcional para o papel `topic_router` via
>   `HIVE_RETRIEVAL_LLM_INTENT=1`. Se o classificador ficar incerto, cai em
>   `hybrid`.
> - [x] `sinapse_query` foi integrado ao router mantendo compatibilidade:
>   Context Fusion continua sendo chamado e seus campos legados (`source`,
>   `observations`, `nodes`, etc.) sao preservados; K7 anexa os campos
>   auditaveis por cima.
> - [x] Fluxo temporal integrado para atividade recente:
>   `claude-mem /api/search` -> ids -> `/api/observations/batch` quando
>   houver ids filtrados. Falha temporal nao derruba a query; vira
>   `missing_context` e segue para fallback hibrido.
> - [x] `VectorBackend` usado por colecao:
>   via factory `get_vector_backend()` para respeitar `VECTOR_BACKEND`
>   (`sqlite_vec` local-first ou Milvus quando configurado);
>   `memory_vectors` para decisoes/aprendizados/operacional/setor/self-state,
>   `document_vectors` para documentos com parent context,
>   `code_vectors` + Graphify para codigo,
>   `visual_vectors` para memoria visual,
>   `graph_vectors` para causalidade quando Graphiti/LightRAG nao bastam.
> - [x] Graphify, Graphiti e LightRAG integrados como rotas especificas:
>   codigo usa Graphify estrutural, causal usa Graphiti + `graph_vectors`, e
>   `multi_hop` usa LightRAG com fallback para `graph_vectors`.
> - [x] Reranker opcional entregue via `integrations/llama_index/`: off por
>   padrao (`local-min`), ativado por `HIVE_RETRIEVAL_RERANKER`. O adapter
>   tem health proprio e reordena de forma deterministica/fail-open.
> - [x] CLI/API/MCP conectados:
>   `scripts/services/sinapse-write.py query`, `sinapse_query` no MCP e
>   `POST /api/v1/query` passam pelo router. `core/search.py` expoe
>   `route_retrieval()` para callers internos que precisam do contrato K7 sem
>   chamar servico.
> - [x] Golden set inicial entregue em `tests/real/golden_retrieval.jsonl`,
>   cobrindo `intent_accuracy` minimo e casos de roteamento errado futuros.
> - [x] Aceite real executado:
>   `tests/real/test_retrieval_router_real.py` -> 3 passed;
>   regressao MCP/CLI/API/K7 -> 29 passed / 1 skipped;
>   comando de aceite `sinapse-write.py query "o que foi decidido sobre
>   embeddings?"` saiu 0 e retornou `intent`, `retrieval_path`, `citations`,
>   `confidence` e `missing_context`.
> - [x] Gate global executado com `./tests/run_all.sh`:
>   Smoke 19 passed; Unit 497 passed / 3 skipped; Integration 109 passed /
>   2 skipped; E2E 22 passed.
>
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
# 3 passed

.venv/bin/python -m pytest tests/unit/test_sinapse_mcp.py tests/unit/test_sinapse_write_cli.py tests/integration/test_sinapse_api.py tests/real/test_retrieval_router_real.py -q
# 29 passed, 1 skipped

python3 scripts/services/sinapse-write.py query "o que foi decidido sobre embeddings?"
# exit 0; retorna intent, retrieval_path, citations, confidence, missing_context

./tests/run_all.sh
# Smoke 19 passed; Unit 497 passed / 3 skipped; Integration 109 passed / 2 skipped; E2E 22 passed
```

---

### K8 — Metricas, Health E Auditoria

**Status:** ✅ Entregue em 2026-06-30 (`v3.6.0`).

**Objetivo:** provar cobertura e detectar buracos de memoria.

**JA EXISTE health da insula** (`docs/11` §3.1): `health_dashboard.py`,
`alert_dispatcher.py`, `review_writer.py` (→`saude/`). `knowledge_health.py`
**adiciona metricas de cobertura de conhecimento**, nao substitui o dashboard.

> **Entregue (2026-06-30) — K8 cobertura, health e forget auditavel:**
>
> - [x] `scripts/health/knowledge_health.py` criado como gate de cobertura de
>   conhecimento. Ele mede UMC + sqlite-vec + claude-mem vectors e escreve
>   report Markdown em `cerebro/cortex/insula/saude/knowledge-health-YYYY-MM-DD.md`.
> - [x] Metricas principais implementadas:
>   `neurons_vectorized_pct`, `observations_linked_pct`,
>   `discoveries_pending`, `summary_vectors_total`, `orphan_vectors`,
>   `milvus_sync_lag`, `query_route_distribution` e
>   `*_vectorized_pct` por colecao canonica.
> - [x] Cobertura por colecao cobre as 7 colecoes K2:
>   `memory_vectors`, `observation_vectors`, `document_vectors`,
>   `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors`.
> - [x] `query_route_distribution` deixou de ser estimativa: K7 grava
>   `query_route_log` em modo best-effort com `query_hash`, `intent`,
>   `first_route`, `retrieval_path_json`, `confidence` e `workspace_id`.
>   A escrita da telemetria e fail-open/fail-fast sob lock de SQLite para nao
>   travar `sinapse-write.py query`.
> - [x] `core/database.py`, `core/umc_schema.sql` e
>   `core/umc_schema_crr.sql` receberam tabelas K8:
>   `knowledge_tombstones` e `query_route_log`.
> - [x] Esquecimento intencional implementado para vetores orfaos:
>   `forget_vector()` remove o vetor da colecao, remove `vector_metadata`
>   quando aplicavel e grava tombstone auditavel com motivo `orphan_vector`.
> - [x] Poda real executada pelo aceite: o primeiro run encontrou 1 orfao em
>   `document_vectors`, podou, criou tombstone e deixou `orphan_vectors=0`.
> - [x] `sinapse_health` expoe `knowledge_health` em modo read-only/quick, sem
>   varredura pesada de `observation_vectors` e sem substituir o health
>   dashboard da Insula. O gate completo fica no CLI/API K8.
> - [x] REST API adicionou `GET /api/v1/knowledge/health` autenticado.
>   Default read-only; `prune=true` executa a manutencao com tombstones.
> - [x] Testes reais adicionados em `tests/real/test_knowledge_health.py`,
>   cobrindo metricas, poda, tombstone, distribuicao de rotas, report Markdown
>   e aceite CLI.
> - [x] Aceite real executado:
>   `.venv/bin/python scripts/health/knowledge_health.py --fail-closed --json`
>   -> exit 0, `failures=[]`, `orphan_vectors=0`;
>   `tests/real/test_knowledge_health.py` -> 2 passed;
>   regressao CLI/MCP/API/K8 -> 21 passed / 1 skipped;
>   `./tests/run_all.sh` -> Smoke 19 passed; Unit 497 passed / 3 skipped;
>   Integration 111 passed / 2 skipped; E2E 22 passed.
>
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
# exit 0; failures=[]; orphan_vectors=0; 7 colecoes reportadas

.venv/bin/python -m pytest tests/real/test_knowledge_health.py -q
# 2 passed

.venv/bin/python -m pytest tests/unit/test_sinapse_mcp.py tests/integration/test_sinapse_api.py tests/real/test_knowledge_health.py -q
# 20 passed, 1 skipped
```

---

### K9 — Test Harness Real Sem Mocks

**Status:** ✅ Entregue em 2026-06-30 (`v3.7.0`).

**Objetivo:** garantir que toda fase K* tenha aceite real, sem mocks, e que a
fronteira entre real × unit × integration fique auditavel em CI e em maquina
zerada.

**Por que este K existe:** B3 do roadmap. Sem um test harness real, qualquer
fase K* pode "ficar verde" no CI com testes simulados e quebrar no
runtime real (Ollama offline, Milvus com schema diferente, claude-mem com
worker morto). K9 transforma o gate em prova: o `pytest -m real` precisa
rodar contra os mesmos backends que o sistema usa em producao, e os
testes mockados precisam ficar visivelmente fora desse gate.

**Contrato operacional K9:**

1. **Marcador canonico:** `pytest.ini` declara `markers = real, requires_service(...)`.
   Todo teste em `tests/real/` carrega `@pytest.mark.real`. Marcador ausente
   em arquivo de `tests/real/` e regressao silenciosa — K9 falha.
2. **Service registry:** `tests/real/service_registry.py` e o unico
   resolvedor de "servico online?". Servicos conhecidos: `ollama`,
   `milvus`, `falkordb`, `claude_mem`, `ragflow`. Servico desconhecido
   em `requires_service(...)` falha o setup com motivo explicito
   ("servico requires_service desconhecido: ...; conhecidos: ...").
3. **Skip por servico offline:** servico registrado mas offline -> skip
   com `pytest.skip("<motivo> (requires_service:<servico>)")`. Nada
   que dependa de servico externo quebra o gate por causa de ambiente.
4. **Mock apenas em unit:** `tests/real/` nao pode usar `MagicMock`,
   `@patch`, `@mock` nem `from unittest.mock import ...`. Defesa em
   dois lugares: (a) `test_acceptance_split.py` falha a coleta se
   aparecer; (b) `scripts/setup/audit_test_layering.py` varre o
   repositorio e escreve relatorio Markdown versionado.
5. **Golden retrieval gate:** `tests/real/golden_retrieval.jsonl` + 
   `tests/real/test_golden_retrieval.py` avaliam o router real com
   dois gates minimos:
   - **intent accuracy** >= 75% (gate da frente de conhecimento);
   - **precision@k / recall@k** >= 0.5 quando o caso declara
     `expected_source_ids` (gate do envelope de retrieval, `docs/11`
     §17.3).
   Caso sem corpus compativel pula explicito (nao passa silencioso).
6. **Fixture contract:** cada fixture real isola o teste de outros
   runs — Milvus usa prefixo de colecao unico e teardown automatico;
   claude-mem usa SQLite temporario com schema real e `CLAUDE_MEM_DB`
   redirecionado; `real_db` usa `tmp_path` para que cada teste receba
   banco proprio.
7. **Reporte automatico:** `tests/run_real_knowledge.sh --report=<path>`
   grava `--junitxml` + Markdown com totais (passed/failed/errors/
   skipped). Idempotente: re-rodar sobrescreve.
8. **Auditoria versionada:** `scripts/setup/audit_test_layering.py` e
   executado no fim do gate K10 e grava
   `docs/reports/k9/test-layering-audit.md`. Em CI, o caminho e
   estavel e nao depende de `cerebro/cortex/insula/` (gitignored).

**Fluxo do gate K9:**

```text
install.sh --with-real-tests
    -> ./tests/run_real_knowledge.sh --report=docs/reports/k9-real-suite-report.md
        -> .venv/bin/python -m pytest tests/real -m real -v
            -> service_registry: para cada teste, verifica servicos exigidos
                -> online: roda o teste (sem mock)
                -> offline: pytest.skip("<motivo> (requires_service:<nome>)")
                -> desconhecido: pytest.fail("<motivo>")
        -> parse junitxml
        -> grava docs/reports/k9-real-suite-report.md
    -> .venv/bin/python scripts/setup/audit_test_layering.py
        -> varre tests/{real,unit,integration}
        -> grava docs/reports/k9/test-layering-audit.md
```

**Componentes implementados:**

| Componente | Papel | Contrato |
|---|---|---|
| `tests/real/conftest.py` | Fixtures reais | `ollama_or_skip`, `real_db` (sqlite-vec em tmp), `milvus_or_skip`, `milvus_backend` (com teardown), `claude_mem_or_skip` (SQLite temporario com schema real, `CLAUDE_MEM_DB` apontado) |
| `tests/real/service_registry.py` | Skip generico | Resolve `requires_service` para 5 servicos nomeados; servico desconhecido falha a coleta com lista dos conhecidos |
| `tests/real/test_acceptance_split.py` | Guarda de fronteira | Falha se algum `tests/real/test_*.py` (excluindo o proprio guard) usar MagicMock/@patch ou se `tests/unit/`/`tests/integration/` marcar `real` |
| `tests/real/test_golden_retrieval.py` | Gate K7 | Aplica intent accuracy >= 75% e precision/recall@k >= 0.5 sobre `golden_retrieval.jsonl`; pula explicito quando o corpus nao cobre o caso |
| `tests/real/golden_retrieval.jsonl` | Golden set | 4 casos: decision, document, recent_activity, multi_hop — espinha minima do router |
| `tests/run_real_knowledge.sh` | Runner oficial | `pytest tests/real -m real`; aceita `--report=<path>` para junitxml + Markdown |
| `scripts/setup/audit_test_layering.py` | Auditoria | Varre `tests/real/`, `tests/unit/`, `tests/integration/`; conta markers e mocks; escreve relatorio em `docs/reports/k9/test-layering-audit.md`. `--strict` falha em ofensor grave |
| `pytest.ini` | Marcadores | Define `markers = real, requires_service(...)`; testes sem marker nao contam para o gate |

**Contrato de marcador e skip:**

| Campo | Onde aparece | Obrigatorio | Motivo |
|---|---|---:|---|
| `@pytest.mark.real` | `tests/real/test_*.py` | sim | Teste so conta no gate real se o marker esta explicito; evita coletar refactor por engano |
| `@pytest.mark.requires_service("<nome>")` | teste que precisa de backend externo | quando aplicavel | Garante skip explicito (com motivo) em vez de falha por ambiente; servico desconhecido falha a coleta |
| `MagicMock`/`@patch` | proibido em `tests/real/` | sim | Defesa em duas camadas (teste + auditoria) para nao regredir a fronteira real/unit |
| `requires_service` argumento | um dos 5 nomes: `ollama`, `milvus`, `falkordb`, `claude_mem`, `ragflow` | sim | Forca o caller a conhecer o servico; servico novo exige patch no registry + PR |

**Fronteiras explicitas:**

- K9 e a suite de aceite, nao a suite de TDD. Testes mockados podem
  continuar existindo em `tests/unit/` e ajudam o desenvolvimento, mas
  **nunca** contam para fechar uma fase K*. O auditor e o guard
  existem exatamente para evitar que isso vaze.
- K9 nao substitui o gate global `./tests/run_all.sh` (Smoke + Unit
  + Integration + E2E). E uma camada a mais: o gate real roda por
  cima do gate unit, nao no lugar dele.
- K9 nao e uma ferramenta de performance. Ele aceita que pular Milvus
  ou FalkorDB e um resultado legitimo (`requires_service` skip). O
  objetivo e provar que a arquitetura de conhecimento funciona em
  maquina real quando os servicos estao online, nao obrigar todo
  host a ter Milvus.
- K9 nao exige Docker. Quando `--profile=local-min`, o instalador
  sobe apenas claude-mem e graphify-watch; Milvus/RAGFlow ficam
  offline e pulam. O gate continua passando (com skips honestos).

**Cobertura obrigatoria de edge cases:**

- Teste real que exige Milvus sem Milvus online nao pode falhar
  coleta nem setup; tem que pular com motivo nomeado.
- Servico nomeado em `requires_service` que nao existe no registry
  tem que falhar a coleta (bug do caller, nao do ambiente).
- `tests/unit/` marcando `real` por engano tem que ser barrado pelo
  guard e pelo auditor (defesa em profundidade).
- O guard `test_acceptance_split.py` tem que se autoexcluir do
  proprio scan (ele importa a regex `MagicMock` no codigo).
- Golden set sem casos com `expected_source_ids` nao pode fazer o
  teste falhar — o teste pula explicito, nao vira `1/1 passed`
  silencioso.
- Re-rodar `./tests/run_real_knowledge.sh --report=X` tem que
  sobrescrever X sem erro; o relatorio precisa ser idempotente.
- Fixture `milvus_backend` tem que dropar as colecoes com o
  prefixo do teste mesmo se a chamada `upsert` falhou no meio;
  vazar colecao entre testes viola isolamento.

> **Entregue (2026-06-30) — K9 test harness real sem mocks (v3.7.0):**
>
> - [x] Marcador `real` + `requires_service(...)` em `pytest.ini`; servicos
>   conhecidos (`ollama`, `milvus`, `falkordb`, `claude_mem`, `ragflow`),
>   desconhecido falha a coleta com motivo explicito.
> - [x] Fixtures reais em `tests/real/conftest.py`:
>   `ollama_or_skip` (existente), `real_db` (existente), `milvus_or_skip`
>   (novo), `milvus_backend` (novo, com teardown das colecoes prefixadas),
>   `claude_mem_or_skip` (novo, SQLite temporario com schema real e
>   `CLAUDE_MEM_DB` redirecionado).
> - [x] `tests/real/test_acceptance_split.py` defende a fronteira: falha
>   coleta se `tests/real/` (excluindo o proprio guard) usar MagicMock/
>   `@patch`, ou se `tests/unit/`/`tests/integration/` marcar `real`.
> - [x] `tests/real/test_golden_retrieval.py` implementa o gate de
>   `docs/11` §17.3: intent accuracy >= 75% e precision/recall@k >= 0.5
>   sobre `tests/real/golden_retrieval.jsonl` (pula explicito quando o
>   corpus nao cobre o caso).
> - [x] `tests/real/test_knowledge_health.py` marcado com `@pytest.mark.real`
>   (estava sem marker, vazava para o gate de forma silenciosa).
> - [x] `scripts/setup/audit_test_layering.py` separa real × unit ×
>   integration e escreve `docs/reports/k9/test-layering-audit.md`.
>   Suporta `--strict` para falhar em ofensor grave.
> - [x] `tests/run_real_knowledge.sh` aceita `--report=<path>`: roda
>   pytest com `--junitxml`, parseia o resultado e grava Markdown com
>   totais. Idempotente (sobrescreve o relatorio).
> - [x] Aceite real executado:
>   `.venv/bin/python -m pytest tests/real -m real -q` ->
>   **37 passed, 8 skipped, 0 failed, 0 errors em 38.88s**;
>   `./tests/run_real_knowledge.sh --report=docs/reports/k9-real-suite-report.md`
>   -> 45 collected, 37 passed, 8 skipped, 0 failed, 0 errors;
>   `.venv/bin/python -m pytest tests/real/test_acceptance_split.py -q`
>   -> 4 passed;
>   `.venv/bin/python -m pytest tests/real/test_golden_retrieval.py -q`
>   -> 2 passed;
>   `.venv/bin/python scripts/setup/audit_test_layering.py` -> 18/18
>   testes em `tests/real/` com marker `real`, 0 com mock, 0 unit/
>   integration marcando `real`.
> - [x] Relatorios versionados gravados em
>   `docs/reports/k9/test-layering-audit.md` e
>   `docs/reports/k9-real-suite-report.md`.
> - [x] Gate global `./tests/run_all.sh` continua verde (suite real
>   e adicional, nao substitui o gate unit/integration/E2E).

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

Conexoes:

- `tests/real/service_registry.py`
- `tests/real/conftest.py`
- `tests/real/test_acceptance_split.py`
- `tests/real/test_golden_retrieval.py`
- `tests/real/golden_retrieval.jsonl`
- `scripts/setup/audit_test_layering.py`
- `tests/run_real_knowledge.sh`
- `pytest.ini`

Aceite real:

```bash
.venv/bin/python -m pytest tests/real -m real -q
# 37 passed, 8 skipped (requires_service:milvus offline neste host)

./tests/run_real_knowledge.sh --report=docs/reports/k9-real-suite-report.md
# 45 collected; 37 passed; 8 skipped; 0 failed; 0 errors

.venv/bin/python -m pytest tests/real/test_acceptance_split.py -q
# 4 passed

.venv/bin/python -m pytest tests/real/test_golden_retrieval.py -q
# 2 passed

.venv/bin/python scripts/setup/audit_test_layering.py
# 18/18 real com marker; 0 com mock; 0 unit/integration com marker real
# relatorio: docs/reports/k9/test-layering-audit.md
```

---

### K10 — Installer E Maquina Zerada

**Status:** ✅ Entregue em 2026-06-30 (`v3.7.0`).

**Objetivo:** instalar tudo em maquina nova e provar funcionamento end-to-end
com flags explicitas, relatorio final e suite real encadeada quando pedida.

**Por que este K existe:** B0 (maquina zerada) e B2 (vendor sem clone) do
roadmap. K10 fecha o ciclo: a v3.7.0 precisa instalar do zero sem prompts
ocultos, precisa ser capaz de subir o cerebro com `uv sync` + componentes
pinados + opcionalmente Milvus/RAGFlow, precisa registrar MCP por agente
sem sobrescrever configs externas e precisa entregar um relatorio final
com paths, portas, modelos e health. Sem isso, todo o trabalho de K0..K9
fica dependente de setup manual que nao escala.

**Contrato operacional K10:**

1. **Perfil de servicos:** `--profile=local-min|local-full`.
   `local-min` (default) sobe apenas claude-mem + graphify-watch — eh o
   minimo para o cerebro rodar e nada mais. `local-full` tenta subir
   Milvus + RAGFlow via `docker compose up` em `integrations/{milvus,
   ragflow}/` e avisa se FalkorDB estiver offline. Perfil invalido
   (`--profile=foo`) aborta com mensagem clara.
2. **Idempotencia:** rodar `install.sh` duas vezes na mesma maquina
   nao quebra nada. `components.py bootstrap` clona apenas o que
   falta, `install_services.py install` so regrava units com
   conteudo diferente, `register-mcp.sh` e idempotente, e as
   fixtures re-aplicam migrations sem erro.
3. **Vinculo com K9:** `--with-real-tests` encadeia
   `./tests/run_real_knowledge.sh --report=docs/reports/k9-real-suite-report.md`
   no fim do install. Sem a flag, o install nao roda testes
   (mantem compatibilidade com CI rapido).
4. **Vinculo com o gate global:** `--with-tests` continua disparando
   `./tests/run_all.sh` (Smoke + Unit + Integration + E2E) como antes.
   As duas flags sao ortogonais: `--with-tests` = suite completa;
   `--with-real-tests` = gate K9.
5. **MCP por agente sem sobrescrita:** o bloco K10 invoca
   `scripts/setup/register-mcp.sh` apos o profile. O script e
   idempotente, merge-safe (nao apaga MCPs alheios) e ja remove
   entradas legadas do proprio Hive-Mind. Roda apenas quando ha
   agente detectado.
6. **Relatorio final versionado:** `logs/install-report.md` (nao
   versionado) e `install-report.md` resumo no stdout. O relatorio
   contem: paths (vault, banco, venv, claude-mem), portas
   (claude-mem 37700, sqlite-vec 37701, api 37702, mcp-http 37703),
   modelos Ollama instalados, e a saida completa de
   `sinapse-write.py health`. Em maquina sem Ollama, o relatorio
   marca "Ollama offline neste host" sem falhar.
7. **Argumentos backward-compatible:** `--force`, `--with-tests`,
   `--skip-agent=`, `--provider=`, `--model=`, `--non-interactive`
   continuam funcionando exatamente como antes. `--profile=` e
   `--with-real-tests` sao puramente aditivos.
8. **Health por chamada:** a verificacao de saude
   (`sinapse-write.py health`) e feita apos o bloco K10 e gravada
   no relatorio. Nao falha o install por causa de backend offline
   (e um gate, nao um pre-requisito).

**Fluxo do install K10:**

```text
install.sh --profile=local-full --with-real-tests
    [passos 1-12 do install original, intactos]
    [bloco K10]
        if profile=local-full:
            integrations/milvus:    docker compose up -d
            integrations/ragflow:   docker compose up -d
            FalkorDB check         (warn-only)
        ensure_migrations (idempotente, CRR-safe)
        register-mcp.sh (merge-safe, idempotente)
    [bloco K10 - encadeamento]
        if --with-tests:         ./tests/run_all.sh
        if --with-real-tests:    ./tests/run_real_knowledge.sh --report=...
    [bloco K10 - relatorio]
        logs/install-report.md com paths/portas/modelos/health
        resumo no stdout
```

**Componentes implementados:**

| Componente | Papel | Contrato |
|---|---|---|
| `install.sh` | Entry point K10 | Adiciona `--profile=local-min\|local-full` e `--with-real-tests`. Bloco K10 roda profile -> migrations -> register-mcp -> encadeia testes -> grava relatorio. Mantem flags e passos 1-12 originais intactos |
| `install.sh::ollama_pull_if_missing` | Modelos locais | Baixa `snowflake-arctic-embed2`, `qwen2.5:3b`, `qwen2.5-coder:3b`; `qwen2.5:7b` so com `SINAPSE_PULL_QWEN7B=1` ou `HIVE_GRAPHITI_MODEL=qwen2.5:7b` (opt-in para nao exigir VRAM em maquina simples) |
| `install.sh` (bloco local-full) | Stack pesada | `cd integrations/milvus && docker compose up -d`; mesma coisa em `integrations/ragflow`. Falha de docker so warn, nao aborta |
| `install.sh` (bloco migrations) | Schema/vectors | `core.database.ensure_migrations(get_connection())` idempotente. CRR-safe (B1) garantido por `ensure_migrations` + `crsql_begin_alter/commit_alter` |
| `install.sh` (bloco MCP) | Registro por agente | `scripts/setup/register-mcp.sh` detecta agentes suportados (Claude Code, Codex CLI, Gemini CLI, Kiro, Cursor, OpenClaw etc.) e registra apenas o `sinapse-memory`, sem apagar MCPs externos |
| `install.sh` (bloco encadeamento) | Encadeia K9 + global | `--with-real-tests` -> `./tests/run_real_knowledge.sh` (gera `docs/reports/k9-real-suite-report.md`); `--with-tests` -> `./tests/run_all.sh` (suite completa) |
| `install.sh` (bloco relatorio) | Saida versionavel | Grava `logs/install-report.md` (nao versionado) com paths, portas, modelos e saida completa de `sinapse-write.py health`; mini-resumo impresso no stdout para o operador ver sem abrir arquivo |
| `tests/run_real_knowledge.sh` | Runner K9 | `pytest tests/real -m real`; `--report=<path>` para junitxml + Markdown; sem `--report`, saida silenciosa em `-q` |

**Contrato de perfil e encadeamento:**

| Flag | Default | Efeito | Quando usar |
|---|---|---|---|
| `--profile=local-min` | sim | Apenas claude-mem + graphify-watch; Milvus/RAGFlow offline | CI rapido, maquina sem docker, smoke do cerebro |
| `--profile=local-full` | nao | Tenta subir Milvus + RAGFlow via docker; FalkorDB avisado se offline | Maquina nova com docker, gate K9 com todos os servicos |
| `--with-real-tests` | nao | Encadeia `./tests/run_real_knowledge.sh --report=...` no fim | Validacao de release, gate K9 |
| `--with-tests` | nao | Encadeia `./tests/run_all.sh` (Smoke + Unit + Integration + E2E) | CI completo, regressao ampla |
| `--force` | nao | Reinstala componentes mesmo se ja existirem | Atualizacao de versao, reset de patch |
| `--non-interactive` | nao | Pula prompts interativos (setup-brain) | CI, maquina zerada, `--profile=*` ja e suficiente na maioria dos casos |
| `--provider=X` | vazio | Seta `HIVE_DREAMER_PROVIDER` no `.env` | Setup inicial com provedor conhecido |
| `--model=X` | vazio | Seta `HIVE_DREAMER_MODEL` no `.env` | Idem |
| `--skip-agent=X` | vazio | Pula registro MCP em um agente especifico | Ex.: nao registrar em copilot por politica da organizacao |

**Fronteiras explicitas:**

- K10 nao transforma a instalacao em um "modo" novo. Ele mantem os 12
  passos originais intactos e adiciona o bloco K10 depois deles.
  Qualquer regressao em `--force`, `--with-tests`, etc. e bug de K10.
- K10 nao exige Docker. Quando `--profile=local-min`, o install sobe
  sem subir container nenhum. O `docker compose up` so roda em
  `local-full`, e mesmo assim e warn-only se docker faltar.
- K10 nao muda o comportamento do MCP. Ele apenas garante que
  `register-mcp.sh` seja chamado no fim. A logica de merge-safe e
  do script, nao do install.
- K10 nao esconde o relatorio no cerebro. O relatorio e em
  `logs/install-report.md` (nao versionado) + mini-resumo no stdout.
  O cerebro (`cerebro/cortex/insula/`) e gitignored e nao e destino
  de saida do install.
- K10 nao introduz dependencias novas alem das ja declaradas em
  `pyproject.toml` (ragflow-sdk, pymilvus, llama-index). O bloco K10
  re-aplica `uv sync --frozen --all-groups` que ja era o padrao.
- K10 nao roda suite real automaticamente. O usuario precisa pedir
  `--with-real-tests`. Isso preserva o comportamento de CI rapido
  (so `--with-tests`) e da controle explicito.

**Cobertura obrigatoria de edge cases:**

- Rodar o install com `--profile=invalid` aborta antes de fazer
  qualquer mutacao; o perfil default `local-min` e seguro para
  re-rodar em CI.
- `install.sh --with-real-tests` em maquina sem Milvus nao pode
  falhar: o gate K9 pula com `requires_service:milvus` e segue.
  Relatorio final marca "Milvus offline (nao-bloqueante)".
- Relatorio final nao pode quebrar quando Ollama esta offline: o
  bloco de modelos marca "Ollama offline neste host" e segue.
- Relatorio nao pode quebrar quando `sinapse-write.py health`
  retorna !=0: ele captura a saida, anexa ao relatorio e marca
  "health check retornou !=0 (ver logs)".
- Flag desconhecida (typo) aborta com mensagem clara, sem tentar
  continuar em estado parcial.
- `install.sh` rodando duas vezes seguidas nao pode duplicar
  unidades systemd, duplicar entradas no crontab, nem duplicar
  MCPs. `install_services.py install` e `register-mcp.sh` ja
  tratam isso; K10 apenas orquestra.
- Re-rodar `./tests/run_real_knowledge.sh --report=X` com o mesmo
  X tem que sobrescrever X (nao falhar nem duplicar). O runner
  garante isso parseando o junitxml e reescrevendo o Markdown.

> **Entregue (2026-06-30) — K10 installer e maquina zerada (v3.7.0):**
>
> - [x] Flags novas no `install.sh`:
>   `--profile=local-min|local-full` (default `local-min`, rejeita valor
>   invalido com mensagem clara) e `--with-real-tests` (encadeia o gate K9
>   no fim do install). Flags antigas (`--force`, `--with-tests`,
>   `--skip-agent=`, `--provider=`, `--model=`, `--non-interactive`)
>   preservadas intactas.
> - [x] Help do `install.sh` atualizado listando as novas flags e os
>   perfis disponiveis.
> - [x] Bloco K10 executa em ordem:
>   1. **profile**: se `local-full`, tenta `docker compose up -d` em
>      `integrations/milvus` e `integrations/ragflow`; warn-only se
>      docker indisponivel ou servico offline; `local-min` mantem
>      apenas claude-mem + graphify-watch.
>   2. **migrations**: `core.database.ensure_migrations(get_connection())`
>      idempotente (CRR-safe B1).
>   3. **register-mcp.sh**: idempotente, merge-safe, nao sobrescreve
>      MCPs externos; remove legados do proprio Hive-Mind.
>   4. **encadeamento**: `--with-tests` -> `./tests/run_all.sh`;
>      `--with-real-tests` -> `./tests/run_real_knowledge.sh --report=...`.
>   5. **relatorio final**: `logs/install-report.md` com paths, portas
>      (claude-mem 37700, sqlite-vec 37701, api 37702, mcp-http 37703),
>      modelos Ollama instalados, e saida completa de
>      `sinapse-write.py health`. Mini-resumo no stdout.
> - [x] `tests/run_real_knowledge.sh` reescrito: aceita `--report=<path>`;
>   roda `pytest -m real -v --junitxml=...`; parseia o junitxml e grava
>   Markdown com totais. Sem `--report`, mantem saida `-q` original.
> - [x] `docs/12-knowledge-implementation-plan.md` marca K9 e K10 como
>   entregues com Status, Por que existe, Contrato, Componentes,
>   Fronteiras e Cobertura obrigatoria.
> - [x] Aceite real executado:
>   `bash -n install.sh` e `bash -n tests/run_real_knowledge.sh` -> sem
>   erro de sintaxe;
>   `pytest tests/unit -q` -> 497 passed, 3 skipped (sem regressao);
>   `./tests/run_real_knowledge.sh --report=docs/reports/k9-real-suite-report.md`
>   -> 45 collected; 37 passed; 8 skipped; 0 failed; 0 errors;
>   `.venv/bin/python scripts/services/sinapse-write.py health` ->
>   `healthy=true`, 7/7 backends up, 1020 graph nodes, 5706 neurons,
>   97.76% vectorized;
>   `grep "v3.7.0" CHANGELOG.md` -> entrada presente.

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

Conexoes:

- `install.sh`
- `scripts/setup/components.py`
- `scripts/setup/install_services.py`
- `scripts/setup/register-mcp.sh`
- `tests/run_real_knowledge.sh`
- `scripts/services/sinapse-write.py`
- `core/database.py`
- `integrations/milvus/docker-compose.yml`
- `integrations/ragflow/docker-compose.yml`

Aceite real:

```bash
# perfil minimo (default): smoke do cerebro sem subir docker
./install.sh --profile=local-min --with-real-tests

# perfil completo: stack pesada + gate K9 + relatorio
./install.sh --profile=local-full --with-real-tests

# gate K9 isolado
./tests/run_real_knowledge.sh --report=docs/reports/k9-real-suite-report.md
# 45 collected; 37 passed; 8 skipped; 0 failed; 0 errors

# health real (mesmo criterio de aceite de fase K*)
.venv/bin/python scripts/services/sinapse-write.py health
# healthy=true; 7/7 backends up; 1020 graph nodes; 5706 neurons; 97.76% vectorized

# relatorio final do install
cat logs/install-report.md
# paths, portas, modelos Ollama, saida de health completa
```

---
