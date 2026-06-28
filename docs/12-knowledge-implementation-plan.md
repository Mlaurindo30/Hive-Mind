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
4. **Vendors externos em `integrations/`:** todo projeto externo usado como
   referencia, adapter ou backend deve ser clonado em `integrations/<nome>`.
   Runtime pode usar Docker/pip quando fizer sentido, mas o source upstream
   fica versionado localmente como vendor auditavel.
5. **Nada hardcoded em `core/`:** modelos, portas, endpoints, colecoes e
   backends devem ter default local e override por `.env`.
6. **Fonte de verdade anatomica:** nenhum backend externo substitui `cerebro/`
   e UMC. Milvus, RAGFlow e LlamaIndex sao orgaos/adapters, nao cerebro.

---

## 3. Integracoes Externas

### 3.1 Politica De Clone

Cada integracao nova deve seguir este contrato:

```text
integrations/<nome>/
  upstream/ ou repo source clonado
  README.md do Hive-Mind explicando papel, comandos e env
  client.py ou adapter local quando aplicavel
  health.py ou assert_health()
  tests reais de conectividade/contrato
```

`install.sh` deve criar ou atualizar os clones de forma idempotente. Nao usar
`git clone` fora de `integrations/`.

### 3.2 Clones Obrigatorios Para Esta Frente

| Integracao | Clone em | Upstream | Uso no Hive-Mind | Runtime esperado |
|---|---|---|---|---|
| RAGFlow | `integrations/ragflow/` | `https://github.com/infiniflow/ragflow.git` | referencia/adapter de ingestao documental, parsing e citacoes | adapter local primeiro; servico opcional |
| Milvus | `integrations/milvus/` | `https://github.com/milvus-io/milvus.git` | backend vetorial de producao via `VectorBackend` | Docker Compose local para testes reais |
| LlamaIndex | `integrations/llama_index/` | `https://github.com/run-llama/llama_index.git` | referencia/adapter para retrievers compostos/workflows | pacote Python + source auditavel |

### 3.3 Comandos Esperados No Instalador

```bash
git clone --depth 1 https://github.com/infiniflow/ragflow.git integrations/ragflow
git clone --depth 1 https://github.com/milvus-io/milvus.git integrations/milvus
git clone --depth 1 https://github.com/run-llama/llama_index.git integrations/llama_index
```

O instalador deve:

1. nao apagar alteracoes locais sem confirmacao;
2. validar remotes corretos;
3. registrar commit upstream atual em `integrations/<nome>/README.md`;
4. instalar apenas o runtime necessario para o perfil escolhido;
5. executar health real apos install.

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

---

## 5. Fases De Implementacao

### K0 — Auditoria E Normalizacao De Base

**Objetivo:** eliminar contradicoes antes de implementar camadas novas.

Tasks:

1. alinhar docs antigas que ainda citam `384d`, `fastembed` default ou `bge-m3`;
2. garantir `.env.example`, README e docs 02/03/11/12 com
   `snowflake-arctic-embed2:latest`;
3. mapear todos os pontos que geram embedding;
4. adicionar comando de health que prova dimensao 1024 em UMC, sqlite-vec worker,
   LightRAG e Graphiti;
5. declarar no `pyproject.toml` os pacotes de `.venv` necessarios para esta
   frente: `ragflow-sdk`, `pymilvus` e `llama-index`;
6. separar testes antigos mockados dos testes reais de aceite.

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

**Objetivo:** trazer RAGFlow, Milvus e LlamaIndex para dentro da politica de
vendors auditaveis.

Tasks:

1. adicionar funcao idempotente `clone_or_update_integration()` no instalador;
2. clonar `ragflow`, `milvus`, `llama_index` em `integrations/`;
3. escrever `integrations/<nome>/README.md` com commit, papel e comandos;
4. adicionar health checks por integracao;
5. registrar `ragflow`, `milvus` e `llama_index` em
   `config/components.lock.json`;
6. incluir os tres vendors em `scripts/maintenance/integrations-update.sh`;
7. bloquear clone fora de `integrations/` nos scripts de setup.

Conexoes:

- `install.sh`
- `scripts/setup/install_services.py`
- `core/paths.py::INTEGRATIONS_ROOT`
- `config/components.lock.json`
- `scripts/maintenance/integrations-update.sh`
- `integrations/*/README.md`

Aceite real:

```bash
test -d integrations/ragflow/.git
test -d integrations/milvus/.git
test -d integrations/llama_index/.git
git -C integrations/ragflow rev-parse HEAD
git -C integrations/milvus rev-parse HEAD
git -C integrations/llama_index rev-parse HEAD
.venv/bin/python -m pytest tests/real/test_integration_clones.py -q
./scripts/maintenance/integrations-update.sh --no-plugins
```

---

### K2 — VectorBackend Local E Producao

**Objetivo:** criar contrato unico para vetores, com `sqlite_vec` local e Milvus
como backend de producao.

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
   `knowledge_type`, `project`, `source_uri`, `hash`, `valid_at`.

Conexoes:

- `core/database.py`
- `core/indexing.py`
- `core/search.py`
- `scripts/services/sinapse-mcp.py`
- `scripts/services/sinapse-api.py`
- `integrations/milvus/`

Aceite real:

```bash
docker compose -f integrations/milvus/deployments/docker/standalone/docker-compose.yml up -d
.venv/bin/python -m pytest tests/real/test_vector_backend_sqlite.py -q
VECTOR_BACKEND=milvus .venv/bin/python -m pytest tests/real/test_vector_backend_milvus.py -q
```

---

### K3 — Knowledge Intake E Promotion Pipeline

**Objetivo:** transformar observations, discoveries, summaries e arquivos em
candidatos tipados, sem perder evidencia.

Tasks:

1. criar `core/knowledge/intake.py`;
2. criar `core/knowledge/promotion.py`;
3. normalizar fontes: claude-mem observation, discovery, session summary,
   daily/weekly/monthly/yearly summaries, docs, code symbols;
4. classificar tipos canonicos de `docs/11`:
   `fact`, `decision`, `learning`, `preference`, `rationale`, `next_step`,
   `project_status`, `document_chunk`, `code_symbol`, `visual_observation`;
5. criar quarentena para erro estrutural (`archived=2`, motivo, retry policy);
6. gravar `observation.neuron_id` quando promocao criar neuronio;
7. manter raw intacto.

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

Tasks:

1. criar adapter `core/knowledge/claude_mem_bridge.py`;
2. consumir fluxo temporal `search -> timeline -> get_observations`;
3. importar discoveries e summaries com `source_id` estavel;
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
   `code`, `causal`, `multi_hop`, `visual`, `hybrid`;
3. integrar `sinapse_query` ao router;
4. integrar `sinapse_temporal_*` para recentes;
5. integrar `VectorBackend` por colecao;
6. integrar Graphify, Graphiti e LightRAG;
7. retornar `retrieval_path`, `citations`, `confidence`, `missing_context`.

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

Tasks:

1. criar `scripts/health/knowledge_health.py`;
2. medir `neurons_vectorized_pct`, `observations_linked_pct`,
   `discoveries_pending`, `summary_vectors_total`, `orphan_vectors`,
   `milvus_sync_lag`, `query_route_distribution`;
3. expor no `sinapse_health`;
4. adicionar endpoint REST `/api/v1/knowledge/health`;
5. gerar report Markdown em `cerebro/cortex/insula/saude/`.

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

Tasks:

1. criar marcador pytest `real`;
2. criar `tests/real/`;
3. criar fixtures reais que usam temp project/vault/SQLite, Ollama local,
   Milvus Docker e claude-mem real;
4. criar `tests/real/README.md` com prerequisitos;
5. adicionar `./tests/run_real_knowledge.sh`;
6. separar testes antigos mockados como unitarios, sem contar como aceite da
   arquitetura de conhecimento.

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
2. rodar `components.py bootstrap` para clonar vendors em `integrations/`;
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

K9 deve comecar cedo em paralelo, mas nenhuma fase fecha sem teste real.

---

## 7. Mapa De Arquivos A Criar Ou Alterar

| Area | Arquivos |
|---|---|
| VectorBackend | `core/vector_backend.py`, `core/vector_collections.py`, `tests/real/test_vector_backend_*.py` |
| Promotion | `core/knowledge/intake.py`, `core/knowledge/promotion.py`, `core/knowledge/types.py`, `tests/real/test_promotion_pipeline_sqlite.py` |
| Claude-Mem bridge | `core/knowledge/claude_mem_bridge.py`, `tests/real/test_claude_mem_bridge.py` |
| Cadencia | `scripts/dream/monthly_synthesizer.py`, `scripts/dream/yearly_synthesizer.py`, `core/schemas/monthly_models.py`, `core/schemas/yearly_models.py` |
| DocumentPipeline | `core/document_pipeline.py`, `scripts/knowledge/document_ingest.py`, `tests/real/test_document_pipeline_*.py` |
| Retrieval | `core/retrieval/router.py`, `core/retrieval/intents.py`, `tests/real/test_retrieval_router_real.py` |
| Health | `scripts/health/knowledge_health.py`, `tests/real/test_knowledge_health.py` |
| Installer | `install.sh`, `.env.example`, `pyproject.toml`, `uv.lock`, `scripts/setup/install_services.py`, `scripts/maintenance/integrations-update.sh`, `tests/run_real_knowledge.sh` |
| Vendors | `integrations/ragflow/`, `integrations/milvus/`, `integrations/llama_index/` |

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
| RAGFlow virar nova fonte de verdade | adapter apenas; parent document e UMC continuam canonicos |
| LlamaIndex esconder o roteamento | usar como referencia/adapter, mas manter `RetrievalRouter` proprio |
| Testes lentos | separar `tests/real`, mas exigir para aceite de fase |
| Promocao criar fatos falsos | candidate-only, evidencia obrigatoria, conflito com `invalid_at` |
| Duplicacao vetorial | hash + parent_id + orphan vector audit |

---

## 10. Proximo Corte Recomendado

Comecar por K0 + K1 + esqueleto K9:

1. corrigir docs/envs restantes para `snowflake-arctic-embed2:latest`;
2. adicionar `ragflow-sdk`, `pymilvus` e `llama-index` no `pyproject.toml`
   e atualizar `uv.lock`;
3. registrar `ragflow`, `milvus`, `llama_index` em `components.lock.json`;
4. incluir os tres vendors em `scripts/maintenance/integrations-update.sh`;
5. clonar `ragflow`, `milvus`, `llama_index` em `integrations/`;
6. criar `tests/real/README.md` e `tests/run_real_knowledge.sh`;
7. adicionar primeiro teste real: embeddings 1024d em Ollama + SQLite.

Esse corte cria a base verificavel para o resto sem ainda mexer no fluxo de
promocao em producao.
