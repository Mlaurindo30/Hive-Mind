# 04 — Infraestrutura e Configuração

> **Hive-Mind v3.0.0** — Requisitos, serviços, portas, variáveis de ambiente e operações.
> Última revisão: 2026-06-30 · LightRAG (P4) integrado como `claude-mem/data/lightrag/` · **Born-Large (K0–K10):** VectorBackend com Milvus opcional, RAGFlow headless adapter, LlamaIndex opcional, contrato negativo de vendorização via `components.lock.json`, `workspace_id` em todas as tabelas críticas, cadência sessão→anual com papéis próprios. Ver [`01-architecture.md` §22–§31](01-architecture.md#22-arquitetura-de-conhecimento-born-large) e [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md).

---

## 1. Requisitos de Software

### 1.1 Runtime

| Dependência | Versão mínima | Uso |
|-------------|--------------|-----|
| Python | 3.10+ | Núcleo — scripts, MCP server, REST API, Dream Cycle |
| SQLite | 3.44+ | UMC com `sqlite-vec` (extensão necessária) |
| Node.js / Bun | 18+ / 1.0+ | claude-mem (TypeScript) |
| Rust / Cargo | 1.70+ | RTK (compilação única; binário pré-compilado opcional) |
| Syncthing | 1.27+ | P2P sync de arquivos Markdown entre máquinas |
| uv | 0.4+ | Gerenciador de pacotes Python |

### 1.2 Dependências Python (requirements.txt)

| Pacote | Versão | Uso |
|--------|--------|-----|
| `fastapi` | ≥0.111 | REST API (sinapse-api.py) |
| `uvicorn` | ≥0.29 | ASGI server para FastAPI |
| `pydantic` | ≥2.7 | Validação de saída LLM + schemas |
| `cryptography` | ≥42 | Fernet encryption (vault de segredos) |
| `fastembed` | ≥0.3 | Dependência legada/fallback; embeddings canônicos usam Ollama 1024d |
| `watchdog` | ≥4.0 | Watcher de arquivos real-time |
| `pypdf` | ≥4.0 | Extração de texto de PDFs |
| `python-docx` | ≥1.1 | Leitura de documentos Word |
| `PyMuPDF` | ≥1.24 | Extração de imagens de PDFs |
| `mss` | ≥9.0 | Captura de screenshots |
| `pyyaml` | ≥6.0 | Parsing de frontmatter YAML |
| `httpx` | ≥0.27 | Cliente HTTP assíncrono (cloud mode) |
| `hnswlib` | ≥0.8.0 | Índice HNSW incremental para busca vetorial (HM-11) |
| `duckdb` | ≥0.10 | Analytics read-only sobre hive_mind.db (HM-11) |

---

## 2. Variáveis de Ambiente

```
# .env na raiz do projeto (nunca commitado)
```

### 2.1 Sistema

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `SINAPSE_HOME` | Caminho raiz do projeto | auto-detectado |
| `SINAPSE_DRY_RUN` | `1` para executar sem side effects | `0` |
| `HIVE_MIND_API_KEY` | Bearer token da REST API (obrigatório) | sem padrão |
| `HIVE_MIND_API_PORT` | Porta da REST API | `37702` |

### 2.2 LLM por papel (roles)

Cada papel tem primário e fallback opcionais; papel sem par completo PROVIDER+MODEL herda do Dreamer (regras: [`01-architecture.md`](01-architecture.md) §11.1 e ADR-009). A frente de Conhecimento Born-Large adiciona os **papéis de cadência K5** e papéis especializados K3/K4/K6/K7 (ver [`02-ai-models.md` §2.1.0](02-ai-models.md#210-papéis-canônicos-constante-hive_llm_roles-em-coreauthpy)).

| Variável | Papel | Descrição |
|----------|-------|-----------|
| `HIVE_DREAMER_PROVIDER` / `HIVE_DREAMER_MODEL` | Dreamer (base de herança) | LLM do Dream Cycle (Knowledge Intake K3 + Distiller/Validator/Router K4) |
| `HIVE_DREAMER_FALLBACK_PROVIDER` / `HIVE_DREAMER_FALLBACK_MODEL` | Dreamer | Fallback opt-in se o primário falhar |
| `HIVE_GRAPHIFY_PROVIDER` / `HIVE_GRAPHIFY_MODEL` | Graphify | Extração de entidades na indexação |
| `HIVE_GRAPHIFY_FALLBACK_PROVIDER` / `HIVE_GRAPHIFY_FALLBACK_MODEL` | Graphify | Fallback opt-in |
| `HIVE_VISION_PROVIDER` / `HIVE_VISION_MODEL` | Vision | Descrição de screenshots (multimodal) |
| `HIVE_VISION_FALLBACK_PROVIDER` / `HIVE_VISION_FALLBACK_MODEL` | Vision | Fallback opt-in |
| `HIVE_OCR_PROVIDER` / `HIVE_OCR_MODEL` | OCR opcional | OCR dedicado; default documentado `ollama/deepseek-ocr:latest`, opt-in no instalador |
| `HIVE_SYNTHESIS_PROVIDER` / `HIVE_SYNTHESIS_MODEL` | Síntese P2P | Síntese Dialética de conflitos |
| `HIVE_SYNTHESIS_FALLBACK_PROVIDER` / `HIVE_SYNTHESIS_FALLBACK_MODEL` | Síntese P2P | Fallback opt-in |
| `HIVE_CLAUDE_MEM_PROVIDER` / `HIVE_CLAUDE_MEM_MODEL` | claude_mem | Bridge `claude_mem_bridge.py` (K4) — classifica `knowledge_type`; herda do Dreamer se não definido |
| `HIVE_SESSION_SUMMARIZER_PROVIDER` / `HIVE_SESSION_SUMMARIZER_MODEL` | session_summarizer (K5) | Resumo de sessão (pequeno/rápido) |
| `HIVE_DAILY_WRITER_PROVIDER` / `HIVE_DAILY_WRITER_MODEL` | daily_writer (K5) | Síntese do dia (pequeno/médio) |
| `HIVE_WEEKLY_SYNTHESIZER_PROVIDER` / `HIVE_WEEKLY_SYNTHESIZER_MODEL` | weekly_synthesizer (K5) | Síntese semanal (médio/forte) |
| `HIVE_MONTHLY_SYNTHESIZER_PROVIDER` / `HIVE_MONTHLY_SYNTHESIZER_MODEL` | monthly_synthesizer (K5) | Síntese mensal (forte) |
| `HIVE_YEARLY_SYNTHESIZER_PROVIDER` / `HIVE_YEARLY_SYNTHESIZER_MODEL` | yearly_synthesizer (K5) | Síntese anual (forte/batch) |
| `HIVE_LIGHTRAG_PROVIDER` / `HIVE_LIGHTRAG_MODEL` | lightrag (P4) | Default `ollama/qwen2.5:3b` local |
| `HIVE_RETRIEVAL_RERANKER` | reranker (K7, opcional) | Rerank lexical local/fail-open via LlamaIndex; off por padrão em `local-min` ([`01-architecture.md` §31.1](01-architecture.md#311-reranker-reordenação-por-relevância)) |
| `HIVE_RERANKER_PROVIDER` / `HIVE_RERANKER_MODEL` | reranker forte (K7, opcional) | Cross-encoder local opt-in; requer `uv sync --extra reranker`; off por padrão |
| `OLLAMA_LOCAL` | — | URL base do Ollama (`http://localhost:11434`) |
| `OLLAMA_EMBED_MODEL` | Embeddings | Default canônico `snowflake-arctic-embed2:latest`, **1024d** (K1/K10) |
| `VECTOR_BACKEND` | Vetores | `sqlite` por padrão; `milvus` quando a integração estiver habilitada (K1) |
| `HIVE_ALLOW_DEFERRED_MIGRATIONS` | Migrações estruturais (K10) | `0` (fail-closed); `1` apenas para diagnóstico de DB legado |
| `HIVE_PROMOTION_BUDGET_*` | Custo de promoção (K10) | Teto por workspace; excedente fica `archived=0` (retry) |

Exemplos de valores: provider `google`, `openai`, `anthropic`, `ollama`, `deepseek`; modelo `gemini-2.0-flash`, `gpt-4o`, `claude-haiku-4-5-20251001`, `qwen2.5-coder:3b`.
Para visão local, o default é `HIVE_VISION_PROVIDER=ollama` com
`HIVE_VISION_MODEL=minicpm-v4.6:latest` e fallback `gemma3:4b`; o instalador
usa `gemma3:4b` como primário apenas quando o daemon Ollama ainda não suporta
o manifesto MiniCPM. O modelo pesado legado `llava:7b` não faz parte da pilha.

> O modelo de **embedding é configurável**, mas o default canônico do projeto é
> `snowflake-arctic-embed2:latest` via Ollama local, **1024 dimensões**. A tabela
> `search_vec` e as 7 coleções canônicas (K1) — `memory_vectors`, `observation_vectors`,
> `document_vectors`, `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors` —
> esperam 1024d. Trocar para outro modelo exige manter a mesma dimensão ou executar
> **migração versionada** (K10, [`01-architecture.md` §30.4](01-architecture.md#30-escala-e-isolamento--workspace-e-federação)):
> re-embed online por workspace, dual-write até cutover, métrica `vectors_model_mismatch` = 0
> dentro de uma coleção.

### 2.3 Vetores e Ingestão — Milvus (K1/K2) e RAGFlow (K6)

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `VECTOR_BACKEND` | Backend vetorial ativo: `sqlite_vec` (local-first) ou `milvus` (produção) | `sqlite_vec` |
| `MILVUS_URI` | Endpoint gRPC/HTTP do container Milvus | `http://localhost:19530` |
| `MILVUS_COLLECTION_PREFIX` | Prefixo das 7 coleções canônicas dentro do Milvus | `hm_` |
| `HIVE_KNOWLEDGE_HEALTH_MILVUS` | `1` para o K8 `knowledge_health` medir `milvus_sync_lag` real em vez de reportar `milvus_not_enabled` | `0` |
| `RAGFLOW_BASE` | URL base do container headless RAGFlow (K6, ingestão de documentos) | `http://localhost:9380` |
| `RAGFLOW_API_KEY` | Chave da API do RAGFlow (gerada no primeiro boot do container) | sem padrão |

> Ambos os serviços rodam como containers Docker (`docker compose` em
> `integrations/ragflow/docker-compose.yml` e equivalente para Milvus) e são
> **opcionais**: sem `VECTOR_BACKEND=milvus`, o sistema usa `sqlite_vec` local
> e o K8 `knowledge_health` reporta `milvus_sync_lag.available=false` com
> `reason=milvus_not_enabled` (comportamento esperado, não é uma falha).
> `scripts/setup/components.py` recusa clonar `milvus`/`ragflow` como
> componente pinado em `components.lock.json` (ADR-018) — ambos só entram
> como container/wrapper via `integrations/`.

### 2.4 API Keys por Provider

| Variável | Provider |
|----------|---------|
| `GOOGLE_API_KEY` | Google AI Studio (Gemini) |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth Device Flow |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth Device Flow (**⚠️ rotacionar se comprometido**) |
| `OPENAI_API_KEY` | OpenAI / OpenRouter-compatible |
| `ANTHROPIC_API_KEY` | Anthropic |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `HF_TOKEN` | Hugging Face Inference |
| `DASHSCOPE_API_KEY` | Alibaba Qwen (DashScope) |
| `NVIDIA_API_KEY` | NVIDIA NIM |
| `OPENROUTER_API_KEY` | OpenRouter |

---

## 3. Serviços e Portas

| Serviço | Porta | Protocolo | Acesso | Processo | Fase |
|---------|-------|-----------|--------|----------|------|
| REST API (FastAPI) | 37702 | HTTP REST | localhost (VPS: Bearer token) | `scripts/services/sinapse-api.py` | base + HM-12 |
| REST API — knowledge health | 37702 (`/api/v1/knowledge/health`) | HTTP REST | localhost (VPS: Bearer token) | `scripts/health/knowledge_health.py` | K8 |
| claude-mem Worker | 37700 | HTTP REST | localhost only | upstream worker com dados em `~/.claude-mem` | base + K4 |
| Ollama | 11434 | HTTP REST | localhost | `ollama serve` | base |
| MCP Server (sinapse-mcp) | stdio | JSON-RPC | processo do agente | `scripts/services/sinapse-mcp.py` | base |
| Syncthing UI | 8384 | HTTP | localhost | `syncthing` | base |
| Milvus (K1, opcional) | 19530 (gRPC) + 9091 (HTTP) | gRPC/HTTP | localhost ou VPS | container pinado por digest | K1 |
| RAGFlow (K6, opcional) | 9380 (HTTP) | HTTP | localhost ou VPS | container headless + `ragflow-sdk` | K6 |
| FalkorDB (Graphiti) | 6379 | Redis | localhost | container | base + K10 |
| LightRAG/P4 | local (`claude-mem/data/lightrag/`) | arquivos | local | `core/lightrag_index.py` | P4 |

Nenhuma porta é exposta externamente por padrão. Para deploy em VPS:

- A REST API (:37702) é exposta atrás de nginx/Caddy com TLS.
- **Milvus** (K1) e **RAGFlow** (K6) rodam como containers em rede interna; só `pymilvus` e `ragflow-sdk` saem para rede externa (configurável). Detalhes em [`01-architecture.md` §2.6](01-architecture.md#26-ferramentas-externas-como-órgãos-do-cérebro).
- A federated REST (`/api/v1/neurons/export`) é o único endpoint cross-machine exposto.

---

## 4. Serviços em Background

### 4.1 Real-time Watcher

```bash
# Iniciar watcher em background
./scripts/services/start-watcher.sh &

# Verificar se está rodando
pgrep -f "start-watcher" && echo "OK"

# Parar
pkill -f "start-watcher"
```

O Watcher usa `watchdog` para monitorar `cerebro/`. Ao detectar mudança em `.md`:
1. Enfileira evento (debounce 500ms para evitar reindex duplo)
2. Chama Graphify para reindexar o arquivo
3. Atualiza `neurons`, `synapses`, `search_fts`, `search_vec`

### 4.2 claude-mem (Tracking Temporal)

```bash
# O runtime oficial é global e multi-projeto.
systemctl --user restart sinapse-claude-mem.service
sqlite3 ~/.claude-mem/claude-mem.db 'PRAGMA quick_check;'
```

### 4.3 Syncthing P2P

```bash
syncthing &       # inicia daemon
# UI em: http://localhost:8384
```

---

## 5. Cron Jobs

```cron
# Rebuild estrutural do grafo a cada 6h
0 */6 * * * cd $SINAPSE_HOME && ./scripts/graph/build-graph.sh >> logs/sync.log 2>&1

# Auditoria P2P dos neurônios temporais + validação search_vec (a cada hora)
0 * * * * cd $SINAPSE_HOME && .venv/bin/python scripts/health/audit_memory.py --fix >> logs/audit.log 2>&1

# Backup consistente dos bancos SQLite críticos (diário às 3am)
0 3 * * * cd $SINAPSE_HOME && .venv/bin/python scripts/health/backup_databases.py >> logs/backup.log 2>&1

# Dream Cycle e cadência K5
0 2 * * * cd $SINAPSE_HOME && .venv/bin/python scripts/dream/dream_cycle.py --once --real >> logs/dream-cycle.log 2>&1
15 3 1 * * cd $SINAPSE_HOME && .venv/bin/python scripts/dream/monthly_synthesizer.py --real >> logs/monthly-synthesizer.log 2>&1
30 3 1 1 * cd $SINAPSE_HOME && .venv/bin/python scripts/dream/yearly_synthesizer.py --real >> logs/yearly-synthesizer.log 2>&1

# Sync Milvus de summary_vectors apenas quando VECTOR_BACKEND=milvus
45 3 * * * cd $SINAPSE_HOME && if [ "${VECTOR_BACKEND:-sqlite}" = "milvus" ]; then .venv/bin/python scripts/maintenance/vector-sync.py --collection summary_vectors --json >> logs/vector-sync.log 2>&1; fi
```

O `install.sh` instala esse bloco de forma idempotente quando `crontab` está
disponível. Em ambiente sem cron, os mesmos comandos devem ser executados pelo
orquestrador do host.

`audit_memory.py --fix` audita apenas neurônios reais do córtex temporal.
Arquivos gerados com `type: moc` são artefatos de navegação e ficam fora do
índice de neurônios; se uma versão antiga os indexou, o fix remove essas linhas
legadas e seus vetores.

---

## 6. Estrutura de Diretórios

```
  Hive-Mind/
  ├── cerebro/                                Vault Obsidian (fonte única de verdade)
  │   ├── atlas/                              Fatos consolidados pelo Dream Cycle
  │   ├── brain/
  │   │   ├── Current State.md               Estado atual (atualizado no Stop hook)
  │   │   └── Patterns.md                     Aprendizados acumulados
  │   ├── work/
  │   │   └── active/                         Decisões ativas (YYYY-MM-DD-slug.md)
  │   ├── inbox/
  │   │   ├── visual/                         Screenshots capturados
  │   │   └── documents/                      PDFs e DOCXs (pais de document_chunks K6)
  │   ├── conflicts/                          Conflitos P2P resolvidos (histórico)
  │   ├── graphify-out/                       Saída do Graphify (graph.json, report)
  │   ├── .claude/
  │   │   └── settings.json                   Hooks Claude Code (SessionStart, PostToolUse, Stop)
  │   └── .codex/
  │       └── hooks.json                      Hooks Codex CLI
  ├── core/
  │   ├── umc_schema.sql                      DDL completo do banco
  │   ├── database.py                         Pool de conexões (WAL, busy_timeout=5000)
  │   ├── auth.py                             Auth de provedores LLM (papéis canônicos)
  │   ├── llm_client.py                       call_llm_structured + classify_llm_error + retry/fallback
  │   ├── vector_backend.py                   Contrato único (sqlite_vec / milvus) — K1
  │   ├── paths.py                            Constantes canônicas de path (§2.7)
  │   ├── hnsw_index.py                       Índice HNSW vetorial incremental — HM-11
  │   ├── signing.py                          Ed25519 sign/verify neuron — HM-12
  │   ├── redactor.py                         PII redaction regex, 8 categorias — HM-12
  │   ├── retrieval/router.py                 RetrievalRouter (K7) — classifica intent, escolhe rota
  │   ├── knowledge/                          (frente K0–K10)
  │   │   ├── intake.py                       Knowledge Intake (K3)
  │   │   ├── promotion.py                    Promotion Layer (K4)
  │   │   ├── claude_mem_bridge.py            Bridge SQL read-only do claude-mem (K4)
  │   │   ├── document_pipeline.py            DocumentPipeline (K6) — parent/chunk/citation
  │   │   ├── vector_sync.py                  Indexação de cadência e docs (K1/K5/K6)
  │   │   ├── topic_consolidator.py           Consolidação de tópicos no temporal (K3)
  │   │   ├── alias_miner.py                  Mineração de aliases (slugs)
  │   │   ├── sector_classifier.py            Setor cross-projeto (Diencéfalo)
  │   │   ├── generate_mocs.py                Geração de MOCs
  │   │   ├── ambiguities.py                  Síntese dialética (Ínsula)
  │   │   └── ...
  │   ├── search.py                           route_retrieval() — adaptador interno do router (K7)
  │   ├── lightrag_index.py                   P4 — entidades + relações
  │   └── schemas/                            Modelos Pydantic (Dream Cycle, cadência, K3/K4)
  ├── integrations/                           Born-Large vendors (K0–K10)
  │   ├── graphify/                           Clone (components.lock.json)
  │   ├── neural-memory/                      Clone (components.lock.json)
  │   ├── rtk/                                Clone (components.lock.json)
  │   ├── milvus/                             Wrapper (pymilvus + docker-compose, K1)
  │   ├── ragflow/                            Wrapper (ragflow-sdk headless, K6)
  │   └── graphiti/                           Wrapper (FalkorDB + docker-compose)
  ├── scripts/
  │   ├── dream/                              Consolidação offline
  │   │   ├── dream_cycle.py                  Pipeline principal
  │   │   ├── session_consolidator.py         Resumo de sessão (K5)
  │   │   ├── daily_writer.py                 Diário (K5)
  │   │   ├── weekly_synthesizer.py           Semanal (K5)
  │   │   ├── monthly_synthesizer.py          Mensal (K5)
  │   │   ├── yearly_synthesizer.py           Anual (K5)
  │   │   ├── pattern_distiller.py            Patterns (cerebelo/padroes/)
  │   │   └── semantic_diff.py                Classificação de conflitos (vetorial + LLM)
  │   ├── knowledge/
  │   │   ├── document_ingest.py              Ingestão PDF/DOCX via DocumentPipeline
  │   │   └── ...
  │   ├── services/                           sinapse-mcp, sinapse-api, sinapse-write, start-watcher
  │   ├── health/
  │   │   ├── audit_memory.py                 Auditoria P2P (hash check + reindex)
  │   │   ├── health_dashboard.py             Health da Ínsula (operacional)
  │   │   ├── alert_dispatcher.py             Alertas da Ínsula
  │   │   ├── review_writer.py                Revisão → saude/
  │   │   └── knowledge_health.py             Métricas K8 (gate knowledge)
  │   ├── capture/visual_capture.py           Screenshots → visual_memories
  │   ├── analytics/planner.py                Decomposição de objetivos — LLM + goals table
  │   ├── setup/setup-brain.py                UI de configuração do Hive-Dreamer
  │   ├── setup/setup-brain.sh                Wrapper shell
  │   ├── services/start-watcher.sh           Inicia Watcher em background
  │   └── utils/recover.sh                    Disaster recovery (rebuild do UMC)
  ├── plugins/
  │   └── hermes/
  │       └── sinapse-memory.py               Plugin nativo para Hermes Agent
  ├── tests/
  │   ├── smoke/                              Smoke tests
  │   ├── unit/                               Unit (mocks; sem LLM)
  │   ├── integration/                        Integration (backends reais)
  │   ├── e2e/                                E2E (sessão completa)
  │   ├── test_synthesis.py                   Síntese com LLM real
  │   ├── real/                               Harness real de aceite (K9) — service_registry
  │   ├── run_all.sh                          Orquestrador da suíte completa
  │   └── README.md                           Convenção da suíte
  ├── docs/                                  Esta documentação
  ├── components.lock.json                    Contrato negativo de vendorização (ADR-018)
  ├── hive_mind.db                           Unified Memory Core (SQLite + sqlite-vec) — v3: causal_edges, goals, visibility, workspace_id, source_id
  ├── claude-mem/data/lightrag/              Grafo de conhecimento LightRAG (P4) — entidades/relacionamentos/vdb
  │   ├── graph.npz                          NetworkX pickle (entidades + arestas)
  │   ├── vdb_chunks.json                    Embeddings de chunks de texto (snowflake-arctic-embed2 1024d)
  │   ├── vdb_entities.json                  Embeddings de entidades extraídas (snowflake-arctic-embed2 1024d)
  │   └── vdb_relationships.json             Embeddings de relações extraídas (snowflake-arctic-embed2 1024d)
  ├── sinapse.yaml                           Configuração central
  ├── .env                                   Segredos locais (gitignored)
  ├── .env.example                           Template de variáveis (commitado)
  ├── requirements.txt                       Dependências Python (inclui pymilvus e llama-index opt-in)
  └── install.sh                             Instalador (10 etapas)
```

### 6.1 Schema UMC — Tabelas e Colunas Notáveis (v3.0.0 + K0–K10)

| Tabela / Coluna | Tipo | Adicionado | Descrição |
|----------------|------|-----------|-----------|
| `causal_edges` | tabela | HM-12 | Grafo causal entre neurônios (source_id, target_id, weight, relation_type) |
| `goals` | tabela | HM-12 | Objetivos decompostos pelo Planner (id, description, status, parent_id) |
| `neurons.visibility` | coluna | HM-12 | Visibilidade do neurônio: `private`, `shared`, `public` |
| `neurons.workspace_id` | coluna | K10 | Fronteira de isolamento; default `'default'` (K10) |
| `observations.workspace_id` | coluna | K10 | Mesmo isolamento; bridge `claude_mem_bridge.py` preserva |
| `observations.source_id` | coluna | K4 | `claude-mem:<table>:<id>` para rastreio de origem |
| `observations.neuron_id` | coluna | K4 | FK para `neurons.id` quando promovido |
| `observations.promoted` | coluna | K3/K4 | `0` pendente / `1` consolidado / `2` quarentena estrutural |
| `synapses.workspace_id`, `goals.workspace_id`, `causal_edges.workspace_id` | coluna | K10 | Mesma fronteira; `(workspace_id, ...)` nos índices quentes |
| `document_memories` | tabela | K6 | Pais de documento (`document_id`, `source_uri`, `file_hash`, `project`, `workspace_id`) |
| `document_chunks` | tabela | K6 | Átomos de documento (`parent_id`, `parent_type=document`, `chunk_index`, offsets, hash, `workspace_id`) |
| `document_vectors` | coleção | K1/K6 | Vetores de chunks (1024d) com metadata canônica (K1) |
| `vector_metadata` | tabela | K1 | Metadata canônica (`parent_id`, `brain_lobe`, `knowledge_type`, `source_uri`, `valid_at`, `workspace_id`) para coleções UMC |
| `summary_vectors` | coleção | K1/K5 | Vetores de cadência (sessão→anual) com metadata canônica |
| `knowledge_tombstones` | tabela | K8 | Tombstones auditáveis de `forget()` (motivo, actor, target, `workspace_id`) |
| `query_route_log` | tabela | K7 | Hash da query × rota (telemetria `query_route_distribution`) |

> **Born-Large (K10):** toda query do `RetrievalRouter` e da promoção filtra por `workspace_id`. Milvus usa `partition_key=workspace_id` para isolamento por partição. Vazamento cross-workspace é bug de segurança, não de ranking. Migrações que criam essa fronteira são estruturais: falha de migração é fail-closed por padrão. O único bypass é `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` (diagnóstico de DB legado, com log visível e sem marcar a instalação como saudável).

---

## 7. Segurança

### 7.1 Princípios

1. **Fail-closed**: REST API não inicia sem `HIVE_MIND_API_KEY`
2. **API keys no `.env`**: nunca commitadas (`.gitignore` cobre `.env` e `*.db`)
3. **Tokens em tempo constante**: comparação `hmac.compare_digest` em vez de `==`
4. **Vault de segredos**: segredos detectados nos conteúdos são cifrados com Fernet e substituídos por `[SECRET:uuid]`
5. **Atomic writes**: `os.replace()` previne corrupção de arquivos em falhas

### 7.2 Superfície de Ataque

| Vetor | Risco | Mitigação |
|-------|-------|-----------|
| REST API (:37702) | Token forjado | `hmac.compare_digest` — timing-safe |
| claude-mem Worker (:37700) | Acesso local não autorizado | Bind em `127.0.0.1` only |
| Path traversal (escrita vault) | Arquivo fora de `cerebro/` | `_sanitize_slug()` remove `/` e `..` |
| Injeção de secrets (MCP input) | API key em query | Regex scan → Fernet → vault table |
| Google OAuth client_secret | Comprometido se hardcoded | Apenas via `.env` (`_env("GOOGLE_OAUTH_CLIENT_SECRET")`) |

### 7.3 Arquivos Sensíveis

| Arquivo/Diretório | Conteúdo | Proteção |
|-------------------|----------|----------|
| `.env` | API keys, tokens, OAuth secrets | `.gitignore`, chmod 600 |
| `hive_mind.db` | Toda a memória (inclui vault table) | `.gitignore` |
| `~/.claude-mem/` | Observações globais com timestamps | permissões locais + backup controlado |
| `claude-mem/data/lightrag/` | Grafo de conhecimento + embeddings (P4) | `.gitignore` (regenerável via Dream Cycle) |
| `backups/` | Backups do UMC | `.gitignore` |

---

## 8. Deploy

### 8.1 Local (desenvolvimento)

```
  ┌─────────────────────────────────────────────┐
  │                 Máquina Local                 │
  │                                               │
  │  ┌──────────────────────────────────────┐    │
  │  │          hive_mind.db (UMC)          │    │
  │  │   neurons / synapses / FTS5 / vec    │    │
  │  └──────────────────────────────────────┘    │
  │       ▲              ▲              ▲         │
  │  Watcher (~2s)   claude-mem    sinapse-api    │
  │  :watchdog       :37700        :37702         │
  │                                               │
  │  ┌──────────────────────────────────────┐    │
  │  │  claude-mem/data/lightrag/ (P4)      │    │
  │  │   grafo + vdb entidades/rels/chunks  │    │
  │  │   alimentado pelo Dream Cycle         │    │
  │  └──────────────────────────────────────┘    │
  │       ▲                                       │
  │  Dream Cycle Estágio 3.5 (best-effort)        │
  │                                               │
  │  ┌──────────────┐   ┌──────────────────────┐ │
  │  │  Obsidian    │   │  Agentes de IA        │ │
  │  │  (cerebro/)  │   │  MCP / Hooks / Plugin │ │
  │  └──────────────┘   └──────────────────────┘ │
  └─────────────────────────────────────────────┘
              │ Syncthing P2P
              ▼
        Outros dispositivos
```

### 8.2 VPS / Cloud

```
  ┌─────────────────────────────────────────────┐
  │                VPS (cloud)                    │
  │                                               │
  │  nginx/Caddy (TLS) → sinapse-api (:37702)    │
  │  systemd: watcher + claude-mem + api          │
  │  Ollama (:11434) — modelos locais             │
  │  Syncthing — recebe vault de outras máquinas  │
  └─────────────────────────────────────────────┘
              │
              │ HTTPS (Bearer token)
              ▼
  ┌──────────────────┐   ┌──────────────────┐
  │ Máquina local 1  │   │ Máquina local 2  │
  │ (cloud.enabled)  │   │ (cloud.enabled)  │
  └──────────────────┘   └──────────────────┘
```

### 8.3 O que o Hive-Mind FAZ e NÃO FAZ

| FAZ | NÃO FAZ |
|-----|---------|
| Indexa vault Obsidian em UMC queryable | Não substitui o Obsidian como editor |
| Injeta contexto automaticamente nos agentes | Não é um agente de IA |
| Consolida memória offline via Dream Cycle | Não treina modelos próprios |
| Sincroniza vault entre máquinas via Syncthing | Não é um banco de dados distribuído |
| Resolve conflitos P2P via Síntese Dialética | Não faz busca na internet |
| Processa imagens e documentos (Phase 10) | Não gerencia autenticação de usuários |
