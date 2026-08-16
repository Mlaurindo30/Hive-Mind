# Pipeline de Dados

> **Hive-Mind v3.10.1** — Fluxo completo de dados: captura → intake (K3) → promotion (K4) → persistência (Atlas + UMC) → indexação (vetor/grafo/FTS) → recuperação (RetrievalRouter).
> Revisão 2026-08-15. Integra integralmente o [`cerebro-filling-map.md`](cerebro-filling-map.md) (mapa "quem preenche o quê") e o fluxo de 9 etapas do [`03-data-pipeline.md`](03-data-pipeline.md).
> Referência normativa: [`arquitetura.md`](arquitetura.md) §22–§31 (frente de conhecimento Born-Large, K0–K10).

---

## 1. Visão geral do fluxo

O pipeline v3.x tem **três fluxos paralelos** — tempo real (escrita → leitura), offline (Dream Cycle) e documental (`DocumentPipeline`) — sobre uma mesma anatomia persistente:

```text
  ┌────────────────────────────────────────────────────────────────────────┐
  │                         FLUXO TEMPO REAL                                │
  │                                                                        │
  │  Agente / Humano                                                       │
  │       │                                                                │
  │       ▼                                                                │
  │  [ CAPTURA ]──── escrita atômica ──→ vault (cerebro/*.md)              │
  │       │                                   │                           │
  │       │                     Watcher ~2s   │                           │
  │       │                                   ▼                           │
  │       │              [ INDEXAÇÃO TEMPO REAL ] → hive_mind.db           │
  │       │               neurônios + sinapses + FTS5 + sqlite-vec 1024d   │
  │       │                           │                                   │
  │       │                           ├──→ Índice HNSW (hnsw_neurons.idx)  │
  │       │                           │    (incremental, 1024d)            │
  │       │                           ├──→ causal_edges (grafo causa→efeito)│
  │       │                           └──→ goals (planner via              │
  │       │                                sinapse_plan_goal)              │
  │       │                                                                │
  │       ▼                                                                │
  │  [ CONSULTA ] ← RetrievalRouter (K7) → sinapse_query (Context Fusion)  │
  └────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────────┐
  │                    FLUXO OFFLINE (Dream Cycle)                         │
  │                                                                        │
  │  observations (pendentes, archived=0)                                  │
  │       │                                                                │
  │       ▼     execução manual ou agendada (cron 0 */4 * * *)             │
  │  [ DREAM CYCLE ] ─────────────────────────────────────────────────    │
  │    Knowledge Intake (K3) → Distiller → Validator → Router (K4)        │
  │       │                                                                │
  │       ▼                                                                │
  │  Persistência anatômica + indexação multi-coleção                       │
  │  (memory_vectors / observation_vectors / summary_vectors / Graphiti    │
  │   / LightRAG) + cadência session/daily/weekly/monthly/yearly (K5)      │
  │       │                                                                │
  │       ▼                                                                │
  │  Síntese Dialética (Fase 9) + Push para grafos                         │
  └────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────────┐
  │                 FLUXO DOCUMENTAL (DocumentPipeline, K6)                │
  │                                                                        │
  │  documento (.md / .txt / .pdf / .docx)                                 │
  │       │                                                                │
  │       ▼     DocumentPipeline.ingest(path, project)                     │
  │  parse layout-aware → normalizar → chunk por estrutura                │
  │       │                                                                │
  │       ▼     metadados canônicos + citações + embedding 1024d           │
  │  document_memories (pai) + document_chunks (átomos) + document_vectors │
  │       │                                                                │
  │       ▼     opcional: KnowledgePromotionPipeline                      │
  │  fact / learning / decision / preference / rationale (cortex)         │
  └────────────────────────────────────────────────────────────────────────┘
```

O fluxo canônico de conhecimento (AGENTS.md §1) é uma leitura condensada destes três fluxos:

```
Captura (hooks/MCP/CLI/browser/docs/code/screenshots)
  → Hippocampus Temporal (claude-mem: observations, discoveries, summaries)
  → Knowledge Intake (normalizar, classificar, deduplicar)
  → Promotion Layer (raw → fact/decision/learning/preference/task)
  → Memória Anatômica (cerebro/ + UMC)
  → Index Layer (FTS, sqlite-vec/Milvus, Graphify, Graphiti, LightRAG)
  → Retrieval Router (core/retrieval/router.py)
  → Resposta com citação
  → Feedback
```

---

## 2. Fluxo de captura e orquestração (consolidate_loop + Dream Cycle)

Diagrama mantido integralmente do [`cerebro-filling-map.md`](cerebro-filling-map.md):

```
┌────────────────────────────────────────────────────────────────────────┐
│  CAPTURA — claude-mem (worker v13.15.0, vendored)                       │
│  captura nativa de TODOS os providers (codex, copilot, hermes,          │
│  antigravity, kimi, qwen, kilo, roo, mimo, openclaw, swarmclaw)         │
│  → grava observations + session_summaries no claude-mem.db (projeto)     │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│  consolidate_loop.py (serviço sinapse-consolidate, loop contínuo)       │
│  FAST (60s)     → bridge → promote → materialize  (cortex/temporal)      │
│  MEDIUM (5min)  → decision_promoter, work_tracker, project_synthesizer,  │
│                   health_dashboard, daily_writer (lobos derivados)       │
│  SLOW (1h)      → topic_consolidator (merge de tópicos)                  │
│  DAILY (6h)     → weekly/monthly/yearly_synthesizer (cadência longa)     │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Dream Cycle (dream_cycle.py) — Hive-Dreamer, cron 0 */4 * * *           │
│  Distiller → Validator → Router (LLM) → escreve neurônios .md no vault    │
│  + Graph Push (Graphiti + LightRAG)                                       │
└────────────────────────────────────────────────────────────────────────┘
```

**Regra de ouro:**

- **Determinístico** (⚙️) reorganiza o que já existe — barato, roda sempre.
- **LLM** (🧠) gera conhecimento novo — caro, roda na cadência certa.
- **Manual** (✍️) é editado pelo humano/agente sob demanda.

---

## 3. Anatomia do vault (lóbulos)

Diagrama anatômico mantido integralmente do [`cerebro-filling-map.md`](cerebro-filling-map.md):

```
cerebro/
├── cortex/                          ← CÓRTEX (cognição) — 5 lóbulos
│   ├── temporal/                    ← memória de longo prazo (eixo primário)
│   │   ├── <projeto>/<tópico>/neuronio-*.md
│   │   ├── _global/
│   │   ├── hipocampo/
│   │   └── arquivo/
│   ├── frontal/                     ← decisão, planejamento, trabalho ativo
│   │   ├── decisoes/
│   │   ├── trabalho/{ativo,arquivo}/
│   │   ├── projetos/
│   │   ├── brain/
│   │   └── org/{people,teams}/
│   ├── parietal/                    ← sensorial (inbox, referências)
│   │   ├── inbox/{visual,documents}/
│   │   ├── referencias/
│   │   └── analises/
│   ├── occipital/                   ← visão (capturas + grafo)
│   │   ├── capturas-visuais/
│   │   └── grafo/
│   └── insula/                      ← interocepção, self-awareness
│       ├── saude/
│       └── conflitos/
├── cerebelo/                        ← CEREBELO (ritmo e coordenação)
│   ├── sessoes/
│   ├── diario/
│   ├── semanal/
│   ├── mensal/
│   ├── anual/
│   └── padroes/
├── diencefalo/                      ← DIENCÉFALO (relay cross-projeto)
│   ├── setores/
│   └── roteamento/
└── tronco/                          ← TRONCO (infra vital — irmão, não subordinado)
    ├── modelos/
    ├── paineis/
    ├── infra/
    └── meta/
```

Os caminhos são expostos como constantes em [`core/paths.py`](core/paths.py) (`CORTEX`, `TEMPORAL`, `FRONTAL`, `PARIETAL`, `OCCIPITAL`, `INSULA`, `DIENCEFALO`, `SECTORS_ROOT`, `CEREBELO`, `DAILY_ROOT`, `SESSIONS_ROOT`, `WEEKLY_ROOT`, `PADROES_ROOT`, `TRONCO`, `META_ROOT`, `MODELOS_ROOT`, `PAINEIS_ROOT`). Todo código que cria/modifica arquivo no vault deve usar essas constantes, nunca caminhos hardcoded.

---

## 4. Etapa 1 — Captura (escrita)

### 4.1 Fontes de dados

| Fonte | Formato | Gatilho | Destino |
|-------|---------|---------|---------|
| Agente (decisão) | ferramenta `sinapse_save_decision` | hook PostToolUse | `trabalho/ativo/YYYY-MM-DD-slug.md` |
| Agente (aprendizado) | ferramenta `sinapse_save_learning` | hook PostToolUse | `brain/Patterns.md` (append) |
| Agente (fim de sessão) | hook Stop | `on_session_end` | `brain/Current State.md` |
| Screenshot | ferramenta `sinapse_capture_screen` | sob demanda | `inbox/visual/` + `visual_memories` |
| Documento PDF/DOCX | `document_ingest.py` | manual / cron | `inbox/documents/` + `observations` |
| Humano (Obsidian) | editor Markdown | save manual | qualquer `.md` no vault |
| claude-mem | observações SQLite | sync periódico | tabela `observations` no UMC |

### 4.2 Formato de arquivo (vault)

```
work/active/2026-06-10-migrar-vps-para-hetzner.md:

  ---
  tags: [decision]
  status: active
  created: 2026-06-10
  source: claude-code-session
  agent: claude-fable-5
  ---

  # Migrar VPS para Hetzner

  Conteúdo com contexto, rationale e implicações.
```

### 4.3 Garantias de escrita

| Garantia | Mecanismo |
|----------|-----------|
| Atomicidade | `tempfile.mkstemp()` + `os.replace()` (atômico em Linux) |
| Deduplicação | verificação de slug antes de criar novo arquivo |
| Validação | `_validate_frontmatter_yaml()` — valida `tags`, `status`, `created` |
| Detecção de segredos | regex `sk-proj-*`, `AKIA*`, Bearer token → Fernet → tabela `vault` |
| Dry-run | `SINAPSE_DRY_RUN=1` — zero efeitos colaterais |

---

## 5. Etapa 2 — Indexação em tempo real (Watcher)

O `watchdog` monitora `cerebro/` continuamente. Qualquer mudança dispara reindexação em ~2 segundos — eliminando a lacuna de 6 horas da v1.x.

```
  Arquivo salvo/modificado em cerebro/
         │
         ▼ (watchdog FileModifiedEvent, ~2s)
  Graphify reindexa o arquivo:
    ├── Extrai entidades + relacionamentos (LLM ou tree-sitter)
    ├── Gera embedding 1024d (snowflake-arctic-embed2 via Ollama local)
    ├── UPDATE neurons SET title, content, hash, embedding, indexed_at
    ├── UPDATE/INSERT synapses (WikiLinks como arestas)
    ├── UPDATE search_fts (automático via trigger SQL)
    ├── UPDATE search_vec (vec0, HNSW sqlite-vec 1024d)
    └── INSERT/UPDATE hnsw_neurons.idx  ← core/hnsw_index.py
         (incremental, M=16, ef_construction=200, espaço cosseno)

  Resultado: hive_mind.db + hnsw_neurons.idx atualizados em disco (modo WAL)
```

> **Migração 384d → 1024d:** commit `56f1e98` (2026-06-21). O contrato global de embedding é `snowflake-arctic-embed2:latest` a **1024d**, salvo override explícito por env (`OLLAMA_EMBED_MODEL`, `HNSW_DIM`). Mudanças de modelo seguem o contrato versionado (K10): re-embed online por workspace, dual-write até o cutover, métrica `vectors_model_mismatch = 0` dentro de uma coleção.

---

## 6. Etapa 3 — Dream Cycle (consolidação offline)

O Dream Cycle processa observações brutas e as eleva a fatos estruturados no Atlas. Em v3.10.1 roda agendado a cada **4h** (`PT4H`, cron `0 */4 * * *`), com a divisão de papéis:

- **Distiller** e **Router**: instruct local `granite4.1:8b` (via config de papel).
- **Validator**: reasoning `qwen3.5:397b` (cloud).

### 6.1 Estágio 1 — Distiller

```
  SELECT * FROM observations
    WHERE archived = 0
    ORDER BY created_at
    LIMIT batch_size

  Para cada observação:
    prompt = system_prompt_distiller + observation.content
    response = llm_call(provider, model, prompt, json_schema=DistilledFact)
    fact = DistilledFact.model_validate_json(response)

    → DistilledFact {
        title: str
        summary: str
        key_insights: list[str]
        confidence: float (0-1)
        tags: list[str]
      }
```

### 6.2 Estágio 2 — Validator

```
  Para cada DistilledFact:
    prompt = system_prompt_validator + fact.json()
    verdict = ValidatorVerdict.model_validate_json(llm_call(...))

    se verdict.approved:
      → vai para o Router
    senão se retries < 2:
      → reenvia ao Distiller com feedback
    senão:
      → UPDATE observations SET archived=2  (quarentena)
```

### 6.3 Estágio 3 — Router

```
  Para cada fato aprovado:
    Classifica o destino:
      └── category em ["decision", "learning", "insight", "fact", "entity"]
      └── target_path = atlas/{category}/YYYY-MM-DD-{slug}.md

    Verifica duplicata por similaridade de embedding (cosseno > 0.92):
      └── Se duplicata: merge (append de insights únicos)
      └── Se novo: INSERT neurons + escreve atlas/*.md
```

### 6.4 Estágio 4 — Persistência no Atlas

```
  _atomic_write(target_path, markdown_with_frontmatter)
    └── frontmatter:
         agent: {provider}/{model}
         consolidated_at: {timestamp}
         source_observation_ids: [uuid1, uuid2]
         confidence: {float}

  UPDATE observations SET archived=1, consolidated_at=NOW()
    WHERE id IN (processed_ids)
```

### 6.5 Fluxo completo (ASCII)

```
  observations (archived=0)
       │
       ▼
  ┌─────────────┐
  │  DISTILLER  │ ← LLM (JSON schema obrigatório)
  └──────┬──────┘
         │ DistilledFact
         ▼
  ┌─────────────┐   rejeita    ┌─────────────┐
  │  VALIDATOR  │─────────────▶│  QUARENTENA │ archived=2
  └──────┬──────┘              └─────────────┘
         │ aprovado
         ▼
  ┌─────────────┐
  │   ROUTER    │ classifica destino + verificação de duplicata
  └──────┬──────┘
         │
         ▼
  ┌─────────────────┐
  │ ATLAS (cerebro/ │ escrita atômica + UPDATE neurons
  │  atlas/*.md)    │ archived=1
  └─────────────────┘
```

O Dream Cycle é a **única fonte de neurônios com groundedness** (Evidência + sinapses): escreve `neuronio-*.md` no vault + neurônio no UMC + vetor + Graphiti/LightRAG. O K3 (`promote_pending_observations`) é o caminho determinístico rápido (sem LLM) que materializa observações simples em neurônios.

---

## 7. K3 — Knowledge Intake

`core/knowledge/intake.py`. Camada [3] do fluxo canônico. Entrada: observações brutas do claude-mem (e candidatos de outros backends via `KnowledgePromotionPipeline`). Saída: candidatos normalizados/classificados/deduplicados, prontos para a Promotion Layer.

**Responsabilidades:**

- normalizar campos (`observations`, `discoveries`, `session_summaries`, `facts`, `narrative`, `concepts`, `files_read`/`files_modified`, `prompt_number`, `generated_by_model`);
- preservar `source_id` estável (`claude-mem:<tabela>:<id>`);
- extrair evidência (arquivos, timestamps, `project`, `workspace_id`);
- classificar `knowledge_type`;
- deduplicar por `source_id` + hash de conteúdo.

**Caminho de leitura do claude-mem (K4):** `core/knowledge/claude_mem_bridge.py` é a ponte canônica via SQL somente-leitura sobre `~/.claude-mem/claude-mem.db`. O workflow interativo `search → timeline → get_observations` (via MCP `sinapse_temporal_*`) é o caminho para **recuperar contexto bruto antes de escolher IDs**; a ponte é o caminho de promoção/backfill em lote.

---

## 8. K4 — Promotion Layer

`core/knowledge/promotion.py`. Camada [4] do fluxo. As operações `Distiller → Validator → Router` permanecem; cada wrapper expõe saída **idempotente `candidate-only`** com `workspace_id` para orquestração centralizada, e a persistência final executa `UPSERT neurons` + `VectorBackend.upsert()` na coleção canônica.

**Superfícies:** CLI `sinapse-write.py promotion`, MCP `sinapse_promote_knowledge`, Dream Cycle com intake candidate-only antes da síntese legada.

**Regras automáticas de promoção:**

- **Permitido:** `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` — todos com fonte rastreável.
- **Proibido:** transformar cada bullet em fato; criar neurônio sem fonte; vetorizar duplicatas sem `parent_id` e hash de conteúdo; promover opinião temporária como decisão arquitetural; sobrescrever decisões anteriores sem criar conflito ou `invalid_at`.

**Falha de promoção preserva dados (ADR-016):**

```text
erro transitório  -> archived=0, nova tentativa futura
erro estrutural   -> archived=2, quarentena com razão
```

Nada é apagado por falha de promoção. Ver [`arquitetura.md` ADR-016](arquitetura.mdção-preserva-dados-nunca-descarta).

---

## 9. K5 — Cadência hierárquica de escrita

A memória temporal avança por **cinco cadências** — sessão, diária, semanal, mensal, anual — com escritores, papéis de LLM e regras de promoção dedicados:

| Cadência | Escritor | Modelo padrão | Promove |
|---|---|---|---|
| Sessão | `session_consolidator.py` | `session_summarizer` (pequeno) | decisões, questões abertas, evidência |
| Diária | `daily_writer.py` | `daily_writer` (pequeno/médio) | aprendizados, progresso, próximos passos |
| Semanal | `weekly_synthesizer.py` | `weekly_synthesizer` (médio/forte) | padrões, decisões estratégicas, prioridades |
| Mensal | `monthly_synthesizer.py` | `monthly_synthesizer` (forte) | síntese executiva, drift, metas, riscos |
| Anual | `yearly_synthesizer.py` | `yearly_synthesizer` (forte/batch) | princípios, lições duráveis |

Cada cadência produz um arquivo em `cerebro/cerebelo/{sessoes,diario,semanal,mensal,anual}/...` e indexa em `summary_vectors` (K1). Contrato de promoção por cadência: `source_id`, `period_start`, `period_end`, `cadence`, `parent_summary_id`.

**Regra de ouro:** quanto maior a cadência, menos copia texto e mais consolida causalidade, decisão, padrão e consequência. Mensal/anual não devem ser rebaixadas automaticamente sem aviso.

**Fail-closed:** um papel sem modelo dedicado e sem herdar do `dreamer` registra uma falha auditável e **não inventa síntese**.

---

## 10. K6 — DocumentPipeline

`core/document_pipeline.py`. Inspirado no RAGFlow, mas **preservando a anatomia do Hive-Mind**.

```text
documento (.md / .txt / .pdf / .docx)
  |
  v
parse layout-aware (adaptador headless RAGFlow OU parser local)
  |
  v
normalizar
  |
  v
chunk por estrutura (300-800 tokens para texto regular; por seção para MD; por símbolo para código)
  |
  v
metadados + citações (parent_id, offsets, source_uri, hash)
  |
  v
embedding 1024d (snowflake-arctic-embed2)
  |
  v
document_memories (pai) + document_chunks (átomos) + document_vectors
  |
  v
opcional: KnowledgePromotionPipeline (K3/K4) → fact/learning/decision
```

**RAGFlow** é um adaptador headless opcional — nunca a fonte de verdade. Toda saída reutilizada deve ser normalizada no UMC antes de ser recuperável. Indisponibilidade do RAGFlow **não** quebra o caminho local-first.

**Contrato de citação:** `DocumentPipeline.query(text)` retorna `citations[{source_uri, offset_start, offset_end, score, parent}]` — a saída não pode ser apenas "melhor trecho".

---

## 11. K7 — RetrievalRouter (roteamento por intenção)

`core/retrieval/router.py` é o ponto de entrada canônico de consulta. Classifica a intenção, escolhe a rota especializada e retorna `{answer_context, citations, retrieval_path, confidence, missing_context}`. LlamaIndex é apenas um adaptador de rerank opcional; não decide rota nem vira fonte de verdade.

### 11.1 Rotas por intenção

| Intenção detectada | Coleção canônica (K1) | Por que esta rota |
|---|---|---|
| Recente / "o que aconteceu" | `observation_vectors` (claude-mem) | Eventos com timestamps recentes |
| Decisão / preferência | `memory_vectors` + FTS | Fatos atômicos validados |
| Aprendizado | `memory_vectors` (átomos de learning) + pai Patterns | Padrões reutilizáveis |
| Documento | `document_vectors` + contexto pai | `DocumentPipeline` (K6) com citações |
| Código | `code_vectors` + Graphify | Símbolos AST + relacionamentos |
| Causalidade / quando era verdade | Graphiti/FalkorDB (`graph_vectors` auxiliar) | `valid_at`/`invalid_at` |
| Pergunta global / multi-hop | LightRAG/GraphRAG | Entidades + relacionamentos |
| Saúde / self-awareness | Ínsula (health/conflicts) | operational_fact + ambiguidades |
| Config / operação / modelo | Tronco (brainstem) | operational_fact |
| Setor / cross-projeto | Diencéfalo + Graphiti | MOCs de setor |
| Ambígua | híbrida + reranker (§31.1) | Fallback + rerank lexical local opcional |

### 11.2 Backends paralelos (sinapse_query / Context Fusion)

```python
def _query_vault_knowledge(query: str, timeout=8.0) -> Optional[str]:
    results = []

    # Backend 1: UMC SQL (FTS5 + KNN sqlite-vec)
    results += umc_search(query)        # FTS5 MATCH + vec KNN (snowflake-arctic-embed2 1024d)
    # Backend 2: claude-mem
    results += claude_mem_search(query) # HTTP :37700, timeout 3s
    # Backend 3: NeuralMemory
    results += nmem_recall(query)       # spreading activation, timeout 5s
    # Backend 4: Filesystem
    results += fs_scan(query)           # scan cerebro/*.md, TTL 30s
    # Backend 5: LightRAG (P4) — entidades + relacionamentos + multi-hop
    results += lightrag_query(query)    # knowledge graph, timeout 8s
    # Backend 6: Graphiti (causalidade temporal)
    results += graphiti_query(query)    # causal_edges com valid_at/invalid_at
    # Backend 7: Graphify (estrutura do vault)
    results += graphify_query(query)    # comunidades + adjacências

    # Fusão + deduplicação + rerank opcional (§31.1)
    deduped = dedup(results, key=lambda r: (r.source_file, r.title, r.content))
    reranked = rerank(query, deduped) if HIVE_RETRIEVAL_RERANKER else deduped
    return format(top_n=5, max_chars=3000, results=reranked)
```

> **Nota:** `sinapse_rag_query` (MCP) usa o mesmo backend 5 (LightRAG), mas com modos `naive|local|global|hybrid`, e retorna a string bruta do grafo (entidades + relacionamentos + chunks), não os outros 6 backends.

### 11.3 Busca vetorial (KNN)

```sql
SELECT n.id, n.title, n.content, n.source_file,
       vec_distance_cosine(v.embedding, :query_vec) AS distance
FROM search_vec v
JOIN neurons n ON n.id = v.neuron_id
ORDER BY distance
LIMIT 5
```

`query_vec` = `snowflake-arctic-embed2.encode(query)` via Ollama local — vetor **1024d** gerado no momento da consulta.

### 11.4 Circuit breaker

| Estado | Condição | Comportamento |
|--------|---------|---------------|
| Fechado (normal) | Menos de 3 falhas | Backend ativo |
| Aberto (cooldown) | 3+ exceções ou timeouts | cooldown de 30s, backend pulado |
| Half-open (teste) | Após 30s | Uma tentativa para reabrir |

Somente exceções Python e timeouts contam como falhas — resultados vazios (não encontrado) não contam.

---

## 12. K8 — Métricas de saúde do conhecimento

`scripts/health/knowledge_health.py` **adiciona** métricas de cobertura; **não substitui** `health_dashboard.py`, `alert_dispatcher.py` ou `review_writer.py` (que seguem sendo saúde da Ínsula). `sinapse_health` inclui bloco `knowledge_health` somente-leitura em modo rápido; a REST expõe `GET /api/v1/knowledge/health`.

| Métrica | Sinal | Coleção canônica (K1) |
|---|---|---|
| `neurons_total` | tamanho da memória consolidada | — |
| `neurons_vectorized_pct` | cobertura vetorial | `memory_vectors` |
| `observations_pending` | backlog temporal | `observation_vectors` |
| `observations_linked_pct` | promoção efetiva | — |
| `discoveries_pending` | risco de perder aprendizado | `observation_vectors` |
| `learnings_atomized` | aprendizado granular | `memory_vectors` |
| `document_chunks_total` | ingestão de documentos | `document_vectors` |
| `code_symbols_total` | cobertura estrutural | `code_vectors` |
| `milvus_sync_lag` | divergência local/produção | todas |
| `orphan_vectors` | índice sujo (primeira fatia do `forget()` §31.2) | todas |
| `query_route_distribution` | quais camadas respondem | — |
| `*_vectorized_pct` | cobertura por coleção canônica | 7 coleções |
| `promotion_lag` | backlog de promoção por workspace | — |
| `promotion_cost` | custo de LLM por workspace | — |
| `vectors_model_mismatch` | divergência de modelo de embedding (K10) | por coleção |

**Gate mínimo de produção:**

```text
neurons_vectorized_pct >= 99%
observations_linked_pct crescente por ciclo
discoveries_pending dentro do SLA
0 vetores órfãos
todos os chunks com parent_id
citações presentes nas respostas de documento
```

> **v3.10.1:** a correção do `index_neuron_ids` (o `NameError` de import `embedding_text` que bloqueava o caminho de reindex do sqlite-vec — causa-raiz dos 32% de neurônios não vetorizados) fez a cobertura vetorial subir a **100%** (`neurons_vectorized_pct = 100%`).

---

## 13. K10 — Escala, isolamento e federação

`workspace_id` é a fronteira de isolamento obrigatória. Toda tabela crítica do UMC carrega `workspace_id` (padrão `'default'`). Toda consulta no `RetrievalRouter` e na promoção filtra por `workspace_id`. Milvus usa `partition_key=workspace_id` para isolamento em nível de partição.

**Regras de fronteira:**

- **Vazamento cross-workspace é bug de segurança**, não problema de ranking.
- Migrações estruturais que criam essa fronteira: falha é fail-closed por padrão. O único bypass é `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` (diagnóstico de DB legado, com log visível e sem marcar a instalação como saudável).
- Federação entre instâncias: reusa HM-12 (`visibility` private|shared|public + Ed25519 + redação de PII no export). Neurônio importado entra com `workspace_id` de destino e proveniência preservada. `origin_instance` e `origin_signature` são obrigatórios.
- Migração de embedding: `vectors_model_mismatch = 0` dentro de uma coleção; re-embed online por workspace, dual-write até o cutover.
- Custo de promoção: teto por workspace via `HIVE_PROMOTION_BUDGET_*`; overflow permanece `archived=0` (retry); métricas `promotion_lag` e `promotion_cost` por workspace.

---

## 14. HM-11 — Deep Reflection (Intent Memory + Causalidade)

### 14.1 Goal Planner

`scripts/planner.py` recebe uma meta em linguagem natural, chama o LLM e retorna uma lista de passos atômicos (`GoalStep`). Cada meta é persistida na tabela `goals` e exposta via ferramenta MCP `sinapse_plan_goal`.

```
  META DO USUÁRIO
        │
        ▼
  sinapse_plan_goal (ferramenta MCP)
        │
        ▼
  scripts/planner.py
        │
        ├── prompt + goal → LLM
        │
        ▼
  GoalStep[] (passos atômicos)
        │
        ├──→ INSERT goals TABLE (hive_mind.db)
        │
        └──→ observations criadas com:
               goal_id  → referência à meta ativa
               why      → rationale / intenção
```

### 14.2 Grafo de causalidade

A tabela `causal_edges` registra arestas causa → efeito entre neurônios. `get_causal_neighbors(conn, neuron_id, hops=2)` percorre o grafo com BFS até 2 hops.

```
  neurons
     │
     ▼
  causal_edges (causa_id → efeito_id)
     │
     ▼
  get_causal_neighbors(conn, neuron_id, hops=2)
     │   BFS no grafo de causalidade
     ▼
  vizinhos causais (até 2 hops)
```

### 14.3 Metadados de intenção nas observações

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `goal_id` | TEXT (FK) | Referência à meta ativa em `goals.id` |
| `why` | TEXT | Rationale / intenção da observação |

---

## 15. HM-12 — Federated Swarm (export federado)

### 15.1 Visibilidade do neurônio

A coluna `visibility` em `neurons` controla quais neurônios podem ser exportados:

| Valor | Descrição |
|-------|-----------|
| `private` | Padrão. Não exportado. |
| `shared` | Exportável a parceiros autorizados. |
| `public` | Exportável sem restrição de destinatário. |

### 15.2 Endpoint de export

`POST /api/v1/neurons/export` — autenticado via token Bearer. Filtros aceitos: `type`, `created_after`. Opções: `redact` (remoção de PII) e/ou `sign` (assinatura Ed25519).

```
  POST /api/v1/neurons/export
        │
        ▼
  SELECT neurons WHERE visibility IN ('shared', 'public')
        │  + filtros: type, created_after
        │
        ├─ redact_neuron()   ← core/redactor.py
        │   PII irreversível: tokens de API, email, IPv4/6,
        │   caminhos absolutos, chaves SSH, CPF/CNPJ, telefone
        │   (aplicado a conteúdo e label; não modifica dados locais)
        │
        ├─ sign_neuron()     ← core/signing.py
        │   Par de chaves Ed25519 (config/keys/, gitignored)
        │   Assina JSON canônico (exclui timestamps e campos _prefixados)
        │   verify_neuron() para validação no receptor
        │
        └─ resposta JSON
             { neurons[], signature?, pubkey_fingerprint? }
```

---

## 16. Mapa "quem preenche o quê" (por lóbulo)

Tabelas mantidas integralmente do [`cerebro-filling-map.md`](cerebro-filling-map.md).

### 16.1 CÓRTEX — `cortex/temporal/` (memória de longo prazo)

| Caminho (de `cerebro/`) | Conteúdo | Quem preenche | Tipo | Frequência |
|----------|----------|---------------|------|------------|
| `cortex/temporal/<projeto>/<tópico>/neuronio-*.md` | neurônios atômicos (1 fato por nota) | **Dream Cycle** (Distiller→Validator→Router) + **K3 promotion** (`promote_pending_observations`) | 🧠 + ⚙️ | FAST 60s (K3) / 4h (Dream) |
| `cortex/temporal/_global/` | conhecimento sem projeto | Dream Cycle | 🧠 | 4h |
| `cortex/temporal/hipocampo/` | staging de consolidação | Dream Cycle | 🧠 | 4h |
| `cortex/temporal/arquivo/` | memória fria (>90 dias) | `drift_detector.py` | ⚙️ | cron mensal |
| (merge de tópicos) | consolidação de tópicos similares | `topic_consolidator.py` | ⚙️ | SLOW 1h |
| (aliases) | sinônimos de busca | `alias_miner.py` | ⚙️ | cron diário |

**O que o Dream Cycle preenche exatamente no temporal:** é o **Hive-Dreamer**: lê observações do claude-mem, extrai fatos (Distiller), valida grounding contra a fonte (Validator), roteia tópico (Router), e escreve `neuronio-*.md` no vault + neurônio no UMC + vetor + Graphiti/LightRAG. É a **única fonte de neurônios com groundedness** (Evidência + sinapses). O K3 (`promote_pending_observations`) é o caminho determinístico rápido (sem LLM) que materializa observações simples em neurônios.

### 16.2 CÓRTEX — `cortex/frontal/` (decisão, planejamento, trabalho)

| Caminho (de `cerebro/`) | Conteúdo | Quem preenche | Tipo | Frequência |
|----------|----------|---------------|------|------------|
| `cortex/frontal/decisoes/<projeto>/dec-*.md` | registros de decisão (Contexto/Rationale/Alternativas/Consequências) | `decision_promoter.py` (`--with-llm`) | 🧠 | MEDIUM 5min |
| `cortex/frontal/trabalho/ativo/` | work items ativos (próximos passos) | `work_tracker.py` | ⚙️ | MEDIUM 5min |
| `cortex/frontal/trabalho/arquivo/` | concluídos | agente move ativo→arquivo | ✍️ | sob demanda |
| `cortex/frontal/projetos/` | status agregado por projeto (nome humano) | `project_synthesizer.py` | 🧠 + ⚙️ | MEDIUM 5min |
| `cortex/frontal/brain/Current State.md` | estado atual do cérebro + decisões/aprendizados da sessão | `sinapse_session_end` (MCP) | ⚙️ | fim de sessão |
| `cortex/frontal/org/people/` | pessoas (perfil individual) | agente (template `Person Note`) | ✍️ | sob demanda |
| `cortex/frontal/org/teams/` | times | agente | ✍️ | sob demanda |

### 16.3 CÓRTEX — `cortex/parietal/` (sensorial: inbox, referências)

| Caminho (de `cerebro/`) | Conteúdo | Quem preenche | Tipo | Frequência |
|----------|----------|---------------|------|------------|
| `cortex/parietal/inbox/visual/` | capturas visuais recebidas | `visual_capture.py` + `sinapse_capture_screen` | ⚙️ | sob demanda |
| `cortex/parietal/inbox/documents/` | documentos recebidos | DocumentPipeline (`document_pipeline.py`) | ⚙️ | sob demanda |
| `cortex/parietal/referencias/` | referências externas | agente (`sinapse_save_*`) | ✍️ | sob demanda |
| `cortex/parietal/analises/` | análises | agente | ✍️ | sob demanda |

### 16.4 CÓRTEX — `cortex/occipital/` (visão)

| Caminho (de `cerebro/`) | Conteúdo | Quem preenche | Tipo | Frequência |
|----------|----------|---------------|------|------------|
| `cortex/occipital/capturas-visuais/` | screenshots indexados com descrição | `sinapse_capture_screen` → visual_memories | 🧠 | sob demanda |
| `cortex/occipital/grafo/graph.json` | grafo de conhecimento (clusters Leiden) | **Graphify** (órgão externo) | ⚙️ | watch contínuo |

### 16.5 CÓRTEX — `cortex/insula/` (interocepção, self-awareness)

| Caminho (de `cerebro/`) | Conteúdo | Quem preenche | Tipo | Frequência |
|----------|----------|---------------|------|------------|
| `cortex/insula/saude/` | snapshots de saúde do sistema | `health_dashboard.py` + `audit_memory.py` (knowledge_health) | ⚙️ + 🧠 | MEDIUM 5min / cron diário |
| `cortex/insula/conflitos/` | contradições detectadas para revisão humana | `conflict_detector.py` + `review_writer.py` | 🧠 | cron semanal |

### 16.6 CEREBELO — `cerebelo/` (ritmo e coordenação — cadência hierárquica)

| Caminho (de `cerebro/`) | Conteúdo | Quem preenche | Tipo | Frequência |
|----------|----------|---------------|------|------------|
| `cerebelo/sessoes/` | logs de sessão | `session_consolidator.py` + `bridge_session_summaries.py` (importa do claude-mem) | ⚙️ | contínuo |
| `cerebelo/diario/` | reflexões diárias | `daily_writer.py` | 🧠 | MEDIUM 5min |
| `cerebelo/semanal/` | sínteses semanais | `weekly_synthesizer.py` | 🧠 | DAILY 6h |
| `cerebelo/mensal/` | sínteses mensais | `monthly_synthesizer.py` | 🧠 | DAILY 6h |
| `cerebelo/anual/` | memória histórica anual | `yearly_synthesizer.py` | 🧠 | DAILY 6h |
| `cerebelo/padroes/Patterns.md` | padrões aprendidos (referência canônica) | `pattern_distiller.py` + `sinapse_save_learning` (MCP) | 🧠 | cron semanal / sob demanda |

**Cadência hierárquica** (o cerebelo sobe de granularidade): `sessoes → diario → semanal → mensal → anual`. Cada camada consolida a anterior.

### 16.7 DIENCÉFALO — `diencefalo/` (relay cross-projeto)

| Caminho (de `cerebro/`) | Conteúdo | Quem preenche | Tipo | Frequência |
|----------|----------|---------------|------|------------|
| `diencefalo/setores/setor-*.md` | conhecimento que atravessa múltiplos projetos (ai-infra, dev-tools, pkm, infra, finance, health, research) | `sector_classifier.py` (classifica neurônios) + `sector_aggregator.py` (agrega em setores) | 🧠 + ⚙️ | sob demanda / lote |
| `diencefalo/roteamento/` | regras de routing entre projetos | `sector_classifier.py` + cross-linker | 🧠 | sob demanda |

### 16.8 TRONCO — `tronco/` (infraestrutura vital — irmão dos outros, não subordinado)

| Caminho (de `cerebro/`) | Conteúdo | Quem preenche | Tipo | Frequência |
|----------|----------|---------------|------|------------|
| `tronco/modelos/` | templates Obsidian tipados (Atom, Work, Decision, Person...) | manual (estático) | ✍️ | setup |
| `tronco/paineis/` | bases `.base` (Work Dashboard, Incidents, People...) | manual (estático) | ✍️ | setup |
| `tronco/infra/` | agentes, hooks, configuração | manual (estático) | ✍️ | setup |
| `tronco/meta/` | sub-vaults, cross-vault links | manual (decisão de design) | ✍️ | setup |

### 16.9 Raiz do vault

| Arquivo | Conteúdo | Quem preenche | Tipo | Frequência |
|---------|----------|---------------|------|------------|
| `_Consciencia.md` | MOC raiz (índice de todos os lobos) | `generate_mocs.py` | ⚙️ | sob demanda |
| `Home.md` | entry point | manual | ✍️ | setup |
| `vault-manifest.json` | manifesto do vault | manual | ✍️ | setup |

---

## 17. Resumo por tipo de preenchedor

### 🧠 LLM (gera conhecimento novo)

| Script | Preenche | Modelo recomendado |
|--------|----------|--------------------|
| `dream_cycle.py` (Distiller/Validator/Router) | neurônios `.md` + Graphiti/LightRAG | instruct `granite4.1:8b` local (Distiller/Router) + reasoning `qwen3.5:397b` (Validator) |
| `daily_writer.py` | diário | instruct 3-7b local |
| `weekly_synthesizer.py` | semanal | reasoning API leve |
| `monthly_synthesizer.py` | mensal | reasoning API |
| `yearly_synthesizer.py` | anual | reasoning API forte |
| `pattern_distiller.py` | padrões | reasoning API |
| `decision_promoter.py` | decisões | reasoning API curto |
| `conflict_detector.py` | conflitos | reasoning API leve |
| `sector_classifier.py` | setores | instruct 3-7b local |

### ⚙️ Determinístico (reorganiza)

| Script | Preenche |
|--------|----------|
| `consolidate_loop.py` (bridge→promote→materialize) | orquestra o fluxo contínuo |
| `work_tracker.py` | trabalho ativo |
| `session_consolidator.py` | sessões |
| `bridge_session_summaries.py` | importa session_summaries do claude-mem |
| `topic_consolidator.py` | merge de tópicos |
| `alias_miner.py` | aliases |
| `drift_detector.py` | arquivo frio |
| `generate_mocs.py` | MOCs |
| `sector_aggregator.py` | agrega setores |
| `health_dashboard.py` / `audit_memory.py` | saúde + métricas |

### ✍️ Manual (sob demanda do humano/agente)

| O quê | Quem |
|-------|------|
| `org/people`, `org/teams` | agente (template Person Note) |
| `referencias/`, `analises/` | agente |
| `tronco/modelos`, `paineis`, `infra`, `meta` | setup manual |
| `trabalho/arquivo/` | agente move ativo→arquivo |

---

## 18. Como tudo se conecta (o orquestrador)

O **`consolidate_loop.py`** (serviço `sinapse-consolidate`) é o coração que mantém o cérebro vivo em cascata:

```
FAST (60s):     bridge() → promote_pending_observations() → materialize_orphan_neurons()
                → escreve neurônios no lobo temporal (via K3 determinístico)

MEDIUM (5min):  decision_promoter --with-llm  → cortex/frontal/decisoes
                work_tracker --apply          → cortex/frontal/trabalho
                project_synthesizer --apply   → cortex/frontal/projetos
                health_dashboard              → cortex/insula/saude
                daily_writer --no-llm         → cerebelo/diario

SLOW (1h):      topic_consolidator            → merge de tópicos no temporal

DAILY (6h):     weekly/monthly/yearly_synthesizer → cadência longa do cerebelo
```

O **Dream Cycle** (`dream_cycle.py`, cron `0 */4 * * *`) complementa com o pipeline LLM de alta qualidade (Distiller→Validator→Router) para os neurônios que exigem groundedness e evidência — é o enriquecimento semântico, não o fluxo de volume.

---

## 19. Frequência de atualização

| Pipeline | Frequência | Gatilho |
|----------|-----------|---------|
| Escrita de decisão/aprendizado | Imediata | hook PostToolUse / Stop |
| Indexação UMC (Watcher) | ~2 segundos | watchdog FileModifiedEvent |
| Dream Cycle | 4h (cron `0 */4 * * *`) | `python3 scripts/dream/dream_cycle.py` |
| Auditoria P2P | 1x por hora | cron `audit_memory.py --fix` |
| Backup UMC | diário 3h | cron `cp hive_mind.db backups/` |

---

## 20. Volume de dados

| Métrica | Valor típico |
|---------|-------------|
| neurônios no UMC | 1.200+ |
| sinapses no UMC | 1.300+ |
| causal_edges no UMC | cresce com o uso |
| goals (planner) | por sessão de planejamento |
| observações pendentes (por sessão) | 5-30 |
| atlas/*.md (fatos consolidados) | cresce com o uso |
| tamanho do hive_mind.db | 50-200MB |
| tamanho do hnsw_neurons.idx | ~5-20MB (depende dos neurônios) |
| tamanho claude-mem/data/lightrag/ | ~5-50MB (grafo + vdb entidade/relação) |
| tempo de reindex por arquivo | ~1-3s |
| busca KNN (10k vetores, 1024d) | ~5-10ms |
| busca HNSW (1024d) | ~1-2ms |
| busca FTS5 | ~2ms |
| consulta LightRAG (hybrid, ~1k entidades) | ~100-300ms (LLM local) |

### Tabelas do banco (hive_mind.db)

| Tabela | Propósito | Fase |
|--------|-----------|------|
| `neurons` | nós de conhecimento (com `visibility` na v3 + `workspace_id` no K10) | base + K10 |
| `synapses` | arestas WikiLink entre neurônios | base |
| `observations` | dados brutos com `goal_id`/`why` (HM-11) + `workspace_id` + `source_id` (K4) | base + HM-11 + K4 + K10 |
| `search_fts` | índice Full-Text Search (FTS5) | base |
| `search_vec` | índice vetorial (vec0 sqlite-vec, 1024d) | base + K1 |
| `causal_edges` | grafo de causalidade causa→efeito | HM-11 |
| `goals` | metas decompostas pelo planner | HM-11 |
| `vector_metadata` | metadados canônicos (parent_id, brain_lobe, knowledge_type, source_uri, valid_at, workspace_id) | K1 |
| `ambiguities` | conflitos P2P (content_a, content_b, hashes, status) | base + K10 |
| `vault` | segredos criptografados (Fernet) | base |
| `document_memories` | pais de documento (K6) | K6 |
| `document_chunks` | átomos de documento (offsets, parent_id, hash) | K6 |
| `document_vectors` | vetores de chunk (K6, com metadados canônicos) | K6 |
| `knowledge_tombstones` | tombstones auditáveis de `forget()` (§31.2) | K8 |
| `query_route_log` | hash de consulta × rota (K7) — telemetria `query_route_distribution` | K7 |

---

## 21. Governança: rollback, fallback, lineage e classificação

O fluxo de dados é governado por princípios de disciplina de dados (Data & AI):

### 21.1 Rollback e fallback estruturados

- **Promoção fail-closed e preservação de dados (ADR-016):** erro transitório → `archived=0` (nova tentativa futura); erro estrutural → `archived=2` (quarentena com razão). Nada é apagado por falha de promoção.
- **Fallback de LLM (ADR-008):** em qualquer caminho de falha final, a observação vai para quarentena (`archived=2`) — **nada se perde**.
- **Indexação em tempo real:** o Watcher reindexa a partir do arquivo-fonte no vault, portanto qualquer inconsistência de índice pode ser reconstruída do vault (fonte de verdade) sem perda.
- **Migração de embedding (K10):** dual-write até o cutover; coleção antiga entra em `forget` (tombstone), nunca apagamento físico silencioso.

### 21.2 Lineage explícito

- `source_id` estável (`claude-mem:<tabela>:<id>`) é preservado do intake à promoção.
- Frontmatter de persistência no Atlas carrega `agent`, `consolidated_at`, `source_observation_ids`, `confidence`.
- Federação exige `origin_instance` e `origin_signature` no neurônio importado.
- Telemetria de rota (`query_route_log`) guarda apenas hash de consulta, nunca texto bruto.

### 21.3 Classificação de dados

- `knowledge_type` canônico classifica cada fato no K3 (fact/decision/learning/preference/task/…).
- `visibility` (private|shared|public) governa exportação federada (HM-12).
- PII é redigida de forma irreversível no export (`core/redactor.py`) e nunca nos dados locais.
- Segredos detectados na escrita vão para a tabela `vault` (Fernet), nunca em texto plano.

---

## 22. Referências cruzadas

- [`arquitetura.md`](arquitetura.md) — anatomia Born-Large (K0–K10), §22–§31, ADRs.
- [`modelos-ia.md`](modelos-ia.md) — papéis de LLM, reasoning, Model Gateway, embeddings, fallback chain.
- [`runtime.md`](runtime.md) — daemon `hive-mindd` e manifesto declarativo dos serviços (inclui `sinapse-consolidate`).
- [`instalacao.md`](instalacao.md) — instalação, setup-brain, registro de agentes.
- [`operacao.md`](operacao.md) — operação do Dream Cycle, watcher, backup, auditoria P2P.
- [`observabilidade.md`](observabilidade.md) — K8 health, `sinapse_health`, métricas de gateway e coleções.
- Fontes de origem: [`03-data-pipeline.md`](03-data-pipeline.md), [`cerebro-filling-map.md`](cerebro-filling-map.md), [`02-ai-models.md`](02-ai-models.md), [`modelos-ia.md`](modelos-ia.md), [`arquitetura.md`](arquitetura.md).
