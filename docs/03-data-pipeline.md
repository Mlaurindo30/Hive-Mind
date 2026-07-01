# 03 — Pipeline de Dados

> **Hive-Mind v3.0.0** — Fluxo completo: coleta → indexação em tempo real → Dream Cycle → consulta → Deep Reflection → Federated Export. **Revisão 2026-06-30:** consolidação da frente de Conhecimento Born-Large (K0–K10) com Knowledge Intake (K3), Promotion Layer (K4), cadência hierárquica (K5), `DocumentPipeline` (K6), `RetrievalRouter` (K7), métricas K8 e contratos de workspace (K10). Referência normativa em [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md); arquitetura destilada em [`01-architecture.md` §22–§31](01-architecture.md#22-arquitetura-de-conhecimento-born-large).

---

## 1. Visão Geral

O pipeline v3.0.0 tem **três fluxos** paralelos — tempo real (write→read), offline (Dream Cycle), e **documental** (DocumentPipeline) — além de três camadas adicionais (HM-11, HM-12 e a frente K0–K10):

```text
  ┌────────────────────────────────────────────────────────────────────────┐
  │                         FLUXO TEMPO REAL                              │
  │                                                                        │
  │  Agente / Humano                                                       │
  │       │                                                                │
  │       ▼                                                                │
  │  [ COLETA ]──── escrita atômica ──→ vault (cerebro/*.md)              │
  │       │                                   │                           │
  │       │                     Watcher ~2s   │                           │
  │       │                                   ▼                           │
  │       │              [ INDEXAÇÃO REAL-TIME ] → hive_mind.db           │
  │       │               neurons + synapses + FTS5 + sqlite-vec 1024d     │
  │       │                           │                                   │
  │       │                           ├──→ HNSW Index (hnsw_neurons.idx)  │
  │       │                           │    (incremental, 1024d)            │
  │       │                           │                                   │
  │       │                           ├──→ causal_edges (grafo causa→     │
  │       │                           │    efeito entre neurons)          │
  │       │                           │                                   │
  │       │                           └──→ goals (planner via             │
  │       │                                sinapse_plan_goal)             │
  │       │                                observations.goal_id / why     │
  │       │                                                                │
  │       ▼                                                                │
  │  [ CONSULTA ] ← RetrievalRouter (K7) → sinapse_query (Context Fusion) │
  └────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────────┐
  │                       FLUXO OFFLINE (Dream Cycle)                      │
  │                                                                        │
  │  observations (pendentes, archived=0)                                  │
  │       │                                                                │
  │       ▼     execução manual ou agendada                                │
  │  [ DREAM CYCLE ] ─────────────────────────────────────────────────    │
  │    Knowledge Intake (K3) → Distiller → Validator → Router (K4)        │
  │       │                                                                │
  │       ▼                                                                │
  │  Persistência Anatômica + Indexação multi-coleção                      │
  │  (memory_vectors / observation_vectors / summary_vectors / Graphiti   │
  │   / LightRAG) + cadência sessão/diário/semanal/mensal/anual (K5)     │
  │       │                                                                │
  │       ▼                                                                │
  │  Síntese Dialética (Fase 9) + Push para grafos                         │
  └────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────────┐
  │                  FLUXO DOCUMENTAL (DocumentPipeline, K6)              │
  │                                                                        │
  │  documento (.md / .txt / .pdf / .docx)                                 │
  │       │                                                                │
  │       ▼     DocumentPipeline.ingest(path, project)                     │
  │  parse layout-aware → normalize → chunk by structure                   │
  │       │                                                                │
  │       ▼     metadados canônicos + citações + embedding 1024d          │
  │  document_memories (pai) + document_chunks (átomos) + document_vectors │
  │       │                                                                │
  │       ▼     opcional: KnowledgePromotionPipeline                      │
  │  fact / learning / decision / preference / rationale (cortex)         │
  └────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Etapa 1 — Coleta (Escrita)

### 2.1 Fontes de Dados

| Fonte | Formato | Gatilho | Destino |
|-------|---------|---------|---------|
| Agente (decisão) | `sinapse_save_decision` tool | PostToolUse hook | `work/active/YYYY-MM-DD-slug.md` |
| Agente (aprendizado) | `sinapse_save_learning` tool | PostToolUse hook | `brain/Patterns.md` (append) |
| Agente (sessão end) | Stop hook | `on_session_end` | `brain/Current State.md` |
| Screenshot | `sinapse_capture_screen` tool | On demand | `inbox/visual/` + `visual_memories` |
| Documento PDF/DOCX | `document_ingest.py` | Manual / cron | `inbox/documents/` + `observations` |
| Humano (Obsidian) | Markdown editor | Salvamento manual | Qualquer `.md` no vault |
| claude-mem | SQLite observations | Sync periódico | `observations` table do UMC |

### 2.2 Formato de Arquivo (Vault)

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

### 2.3 Garantias de Escrita

| Garantia | Mecanismo |
|----------|-----------|
| Atomicidade | `tempfile.mkstemp()` + `os.replace()` (atômico no Linux) |
| Deduplicação | Verificação de slug antes de criar novo arquivo |
| Validação | `_validate_frontmatter_yaml()` — checa `tags`, `status`, `created` |
| Detecção de segredos | Regex `sk-proj-*, AKIA*, Bearer token` → Fernet → vault table |
| Dry-run | `SINAPSE_DRY_RUN=1` — zero side effects |

---

## 3. Etapa 2 — Indexação em Tempo Real (Watcher)

O `watchdog` monitora `cerebro/` continuamente. Qualquer mudança dispara reindexação em ~2 segundos — eliminando o gap de 6h da v1.x.

```
  Arquivo salvo/modificado em cerebro/
         │
         ▼ (watchdog FileModifiedEvent, ~2s)
  Graphify reindexa arquivo:
    ├── Extrai entidades + relações (LLM ou tree-sitter)
    ├── Gera embedding 1024d (snowflake-arctic-embed2 via Ollama local)
    ├── UPDATE neurons SET title, content, hash, embedding, indexed_at
    ├── UPDATE/INSERT synapses (WikiLinks como edges)
    ├── UPDATE search_fts (trigger automático via SQL)
    ├── UPDATE search_vec (vec0, HNSW sqlite-vec 1024d)
    └── INSERT/UPDATE hnsw_neurons.idx  ← core/hnsw_index.py
         (incremental, M=16, ef_construction=200, espaço cosseno)

  Resultado: hive_mind.db + hnsw_neurons.idx atualizados em disco (WAL mode)
```

> **Migração 384d → 1024d:** commit `56f1e98` (2026-06-21). O contrato global de embedding é `snowflake-arctic-embed2:latest` em **1024d** salvo override explícito por env (`OLLAMA_EMBED_MODEL`, `HNSW_DIM`). Mudança de modelo segue o contrato de migração versionada (K10, [`01-architecture.md` §30.4](01-architecture.md#30-escala-e-isolamento--workspace-e-federação)): re-embed online por workspace, dual-write até cutover, métrica `vectors_model_mismatch` = 0 dentro de uma coleção.

---

## 4. Etapa 3 — Dream Cycle (Consolidação Offline)

O Dream Cycle processa observations brutas e as eleva a fatos estruturados no Atlas.

### 4.1 Estágio 1 — Distiller

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

### 4.2 Estágio 2 — Validator

```
  Para cada DistilledFact:
    prompt = system_prompt_validator + fact.json()
    verdict = ValidatorVerdict.model_validate_json(llm_call(...))

    if verdict.approved:
      → passa para Router
    elif retries < 2:
      → re-envia ao Distiller com feedback
    else:
      → UPDATE observations SET archived=2  (quarentena)
```

### 4.3 Estágio 3 — Router

```
  Para cada fato aprovado:
    Classifica destino:
      └── category in ["decision", "learning", "insight", "fact", "entity"]
      └── target_path = atlas/{category}/YYYY-MM-DD-{slug}.md

    Verifica duplicata por embedding similarity (cosine > 0.92):
      └── Se duplicata: merge (append insights únicos)
      └── Se novo: INSERT neurons + write atlas/*.md
```

### 4.4 Estágio 4 — Atlas Persistence

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

### 4.5 Fluxo Completo (ASCII)

```
  observations (archived=0)
       │
       ▼
  ┌─────────────┐
  │  DISTILLER  │ ← LLM (JSON schema obrigatório)
  └──────┬──────┘
         │ DistilledFact
         ▼
  ┌─────────────┐   reprova    ┌─────────────┐
  │  VALIDATOR  │─────────────▶│  QUARENTENA │ archived=2
  └──────┬──────┘              └─────────────┘
         │ aprovado
         ▼
  ┌─────────────┐
  │   ROUTER    │ classifica destino + dedup check
  └──────┬──────┘
         │
         ▼
  ┌─────────────────┐
  │ ATLAS (cerebro/ │ atomic write + UPDATE neurons
  │  atlas/*.md)    │ archived=1
  └─────────────────┘
```

---

## 5. HM-11 — Deep Reflection (Intent Memory + Causalidade)

### 5.1 Planner de Objetivos

O `scripts/planner.py` recebe um objetivo em linguagem natural, chama o LLM e retorna uma lista de steps atômicos (`GoalStep`). Cada goal é persistido na tabela `goals` e exposto via MCP tool `sinapse_plan_goal`.

```
  OBJETIVO DO USUÁRIO
        │
        ▼
  sinapse_plan_goal (MCP tool)
        │
        ▼
  scripts/planner.py
        │
        ├── prompt + objetivo → LLM
        │
        ▼
  GoalStep[] (steps atômicos)
        │
        ├──→ INSERT goals TABLE (hive_mind.db)
        │
        └──→ observations criadas com:
               goal_id  → referência ao goal ativo
               why      → justificativa / intenção
```

### 5.2 Grafo de Causalidade

A tabela `causal_edges` registra arestas causa → efeito entre neurons. A função `get_causal_neighbors(conn, neuron_id, hops=2)` percorre o grafo via BFS para recuperar vizinhos causais até 2 hops.

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

### 5.3 Intent Metadata em Observations

Cada observação pode referenciar um objetivo ativo via colunas adicionais:

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `goal_id` | TEXT (FK) | Referência ao goal ativo em `goals.id` |
| `why` | TEXT | Justificativa / intenção da observação |

---

## 6. HM-12 — Federated Swarm (Export Federado)

### 6.1 Visibilidade de Neurons

A coluna `visibility` em `neurons` controla quais neurons podem ser exportados:

| Valor | Descrição |
|-------|-----------|
| `private` | Padrão. Não exportado. |
| `shared` | Exportável para parceiros autorizados. |
| `public` | Exportável sem restrição de destinatário. |

### 6.2 Endpoint de Export

`POST /api/v1/neurons/export` — autenticado via Bearer token.

Filtros aceitos: `type`, `created_after`. Opções: `redact` (remoção de PII) e/ou `sign` (assinatura Ed25519).

```
  POST /api/v1/neurons/export
        │
        ▼
  SELECT neurons WHERE visibility IN ('shared', 'public')
        │  + filtros: type, created_after
        │
        ├─ redact_neuron()   ← core/redactor.py
        │   PII irreversível: API tokens, email, IPv4/6,
        │   paths absolutos, SSH keys, CPF/CNPJ, telefone
        │   (aplicado sobre content e label; não modifica local)
        │
        ├─ sign_neuron()     ← core/signing.py
        │   Ed25519 keypair (config/keys/, gitignored)
        │   Assina JSON canônico (exclui timestamps e campos _prefixados)
        │   verify_neuron() para validação pelo receptor
        │
        └─ JSON response
             { neurons[], signature?, pubkey_fingerprint? }
```

---

## 7. Etapa 4 — Consulta (RetrievalRouter K7 + sinapse_query)

A partir da frente K0–K10, a consulta canônica passa pelo **`RetrievalRouter`** ([`01-architecture.md` §26](01-architecture.md#26-retrievalrouter-k7--roteamento-por-intenção); `core/retrieval/router.py`). O router classifica a intenção da query, escolhe a rota especializada e devolve `retrieval_path`, `citations`, `confidence` e `missing_context`. Quando a confiança é baixa ou a query é ambígua, ele cai para `sinapse_query`/Context Fusion.

### 7.0 Rotas por intenção (K7)

| Intenção detectada | Coleção canônica (K1) | Por que esta rota |
|---|---|---|
| Recente / "o que aconteceu" | `observation_vectors` (claude-mem) | Eventos com timestamp recente |
| Decisão / preferência | `memory_vectors` + FTS | Fatos atômicos validados |
| Aprendizado | `memory_vectors` (learning atoms) + Patterns parent | Padrões reutilizáveis |
| Documento | `document_vectors` + parent context | `DocumentPipeline` (K6) com citações |
| Código | `code_vectors` + Graphify | Símbolos AST + relações |
| Causalidade / quando era verdade | Graphiti/FalkorDB (`graph_vectors` auxiliar) | `valid_at`/`invalid_at` |
| Pergunta global / multi-hop | LightRAG/GraphRAG | Entidades + relações |
| Saúde / autoconsciência | Ínsula (saúde/conflitos) | operational_fact + ambiguities |
| Config / operacional / modelo | Tronco | operational_fact |
| Setor / cross-projeto | Diencéfalo + Graphiti | Setores MOC |
| Ambigua | hybrid + reranker (§31.1) | Fallback + cross-encoder local opcional |

### 7.1 Backends Paralelos (sinapse_query / Context Fusion)

```python
def _query_vault_knowledge(query: str, timeout=8.0) -> Optional[str]:

    # 5+ backends em paralelo (ThreadPoolExecutor) com circuit breaker
    results = []

    # Backend 1: UMC SQL (FTS5 + KNN sqlite-vec)
    results += umc_search(query)        # FTS5 MATCH + vec KNN (snowflake-arctic-embed2 1024d)

    # Backend 2: claude-mem
    results += claude_mem_search(query) # HTTP :37700, timeout 3s

    # Backend 3: NeuralMemory
    results += nmem_recall(query)       # spreading activation, timeout 5s

    # Backend 4: Filesystem
    results += fs_scan(query)           # scan cerebro/*.md, TTL 30s

    # Backend 5: LightRAG (P4) — entidades + relações + multi-hop
    results += lightrag_query(query)    # grafo de conhecimento, timeout 8s

    # Backend 6: Graphiti (causalidade temporal)
    results += graphiti_query(query)    # causal_edges com valid_at/invalid_at

    # Backend 7: Graphify (estrutural do vault)
    results += graphify_query(query)    # communities + adjacências

    # Fusão e deduplicação + rerank opcional (§31.1)
    deduped = dedup(results, key=lambda r: (r.source_file, r.title, r.content))
    reranked = rerank(query, deduped) if HIVE_RERANKER_PROVIDER else deduped
    return format(top_n=5, max_chars=3000, results=reranked)
```

> **Nota:** O `sinapse_rag_query` (MCP) usa o mesmo backend 5 (LightRAG) mas com modos `naive|local|global|hybrid` e retorna string bruta do grafo (entidades + relações + chunks), não os outros 6 backends.

### 7.2 Busca Vetorial (KNN)

```sql
SELECT n.id, n.title, n.content, n.source_file,
       vec_distance_cosine(v.embedding, :query_vec) AS distance
FROM search_vec v
JOIN neurons n ON n.id = v.neuron_id
ORDER BY distance
LIMIT 5
```

`query_vec` = `snowflake-arctic-embed2.encode(query)` via Ollama local — vetor **1024d** gerado no momento da query. Tabela virtual `search_vec` (vec0, 1024d). Migração do antigo 384d → 1024d aconteceu na P0 (commit `56f1e98`, 2026-06-21).

### 7.3 Circuit Breaker

| Estado | Condição | Comportamento |
|--------|---------|---------------|
| Fechado (normal) | Menos de 3 falhas | Backend ativo |
| Aberto (cooldown) | 3+ exceções ou timeouts | Cooldown 30s, backend ignorado |
| Semi-aberto (teste) | Após 30s | Uma tentativa para resetar |

Apenas exceções Python e timeouts contam como falha — resultados vazios (não encontrado) não.

---

## 8. Frequência de Atualização

| Pipeline | Frequência | Gatilho |
|----------|-----------|---------|
| Escrita de decisões/aprendizados | Imediata | PostToolUse / Stop hook |
| Indexação no UMC (Watcher) | ~2 segundos | watchdog FileModifiedEvent |
| Dream Cycle | Manual ou cron | `python3 scripts/dream/dream_cycle.py` |
| Auditoria P2P | 1x por hora | Cron `audit_memory.py --fix` |
| Backup UMC | Diário 3am | Cron `cp hive_mind.db backups/` |

---

## 9. Volume de Dados

| Métrica | Valor típico |
|---------|-------------|
| neurons no UMC | 1.200+ |
| synapses no UMC | 1.300+ |
| causal_edges no UMC | cresce com uso |
| goals (planner) | por sessão de planejamento |
| observations pendentes (por sessão) | 5-30 |
| atlas/*.md (fatos consolidados) | cresce com uso |
| Tamanho do hive_mind.db | 50-200MB |
| Tamanho do hnsw_neurons.idx | ~5-20MB (depende de neurons) |
| Tamanho de claude-mem/data/lightrag/ | ~5-50MB (grafo + vdb de entidades/rels) |
| Tempo de reindexação por arquivo | ~1-3s |
| Tempo de busca KNN (10k vetores, 1024d) | ~5-10ms |
| Tempo de busca HNSW (1024d) | ~1-2ms |
| Tempo de busca FTS5 | ~2ms |
| Tempo de query LightRAG (hybrid, ~1k entidades) | ~100-300ms (LLM local) |

### Tabelas do Banco (hive_mind.db)

| Tabela | Propósito | Fase |
|--------|-----------|------|
| `neurons` | Nós de conhecimento (com `visibility` em v3 + `workspace_id` em K10) | base + K10 |
| `synapses` | Arestas WikiLink entre neurons | base |
| `observations` | Dados brutos com `goal_id`/`why` (HM-11) + `workspace_id` + `source_id` (K4) | base + HM-11 + K4 + K10 |
| `search_fts` | Índice Full-Text Search (FTS5) | base |
| `search_vec` | Índice vetorial (vec0 sqlite-vec, 1024d) | base + K1 |
| `causal_edges` | Grafo de causalidade causa→efeito | HM-11 |
| `goals` | Objetivos decompostos pelo planner | HM-11 |
| `vector_metadata` | Metadata canônica (parent_id, brain_lobe, knowledge_type, source_uri, valid_at, workspace_id) | K1 |
| `ambiguities` | Conflitos P2P (content_a, content_b, hashes, status) | base + K10 |
| `vault` | Segredos cifrados (Fernet) | base |
| `document_memories` | Pais de documentos (K6) | K6 |
| `document_chunks` | Átomos de documento (offsets, parent_id, hash) | K6 |
| `document_vectors` | Vetores de chunks (K6, com metadata canônica) | K6 |
| `knowledge_tombstones` | Tombstones auditáveis de `forget()` (§31.2) | K8 |
| `query_route_log` | Hash da query × rota (K7) — telemetria `query_route_distribution` | K7 |

---

## 10. K3 — Knowledge Intake

`core/knowledge/intake.py`. Camada [3] do fluxo canônico ([`11-knowledge-promotion-architecture.md` §3](11-knowledge-promotion-architecture.md#3-preenchimento-por-parte-do-cérebro)). Entrada: observações brutas do claude-mem (e candidatos de outros backends via `KnowledgePromotionPipeline`). Saída: candidatos normalizados/classificados/deduplicados, prontos para a Promotion Layer.

**Responsabilidades:**

- normaliza campos (`observations`, `discoveries`, `session_summaries`, `facts`, `narrative`, `concepts`, `files_read/files_modified`, `prompt_number`, `generated_by_model`);
- preserva `source_id` estável (`claude-mem:<table>:<id>`);
- extrai evidência (arquivos, timestamps, `project`, `workspace_id`);
- classifica `knowledge_type` (ver [`01-architecture.md` §27.2](01-architecture.md#272-tipos-canônicos-de-conhecimento));
- deduplica por `source_id` + hash de conteúdo.

**Caminho de leitura do claude-mem (K4):** `core/knowledge/claude_mem_bridge.py` é a bridge canônica via SQL read-only em `~/.claude-mem/claude-mem.db`. O `scripts/services/claude_mem_bridge.py` legado apenas delega ao core. O workflow interativo `search → timeline → get_observations` (via MCP `sinapse_temporal_*`) é o caminho para **recuperar contexto bruto antes de escolher IDs**; a bridge é o caminho de promoção/backfill em batch.

**Estado K3 (2026-06-28):** pipeline SQLite real, Dream Cycle `--once --real`, query via CLI e suite completa `./tests/run_all.sh` verdes.

---

## 11. K4 — Promotion Layer

`core/knowledge/promotion.py`. Camada [4] do fluxo. Operações `Distiller → Validator → Router` continuam; agora cada wrapper expõe **saída `candidate-only`** idempotente com `workspace_id` para orquestração central, e a persistência final faz `UPSERT neurons` + `VectorBackend.upsert()` em coleção canônica.

**Superfícies:** CLI `sinapse-write.py promotion`, MCP `sinapse_promote_knowledge`, Dream Cycle com intake candidate-only antes da síntese legada.

**Regras de promoção automática:**

- **Permitida:** `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` — todos com fonte rastreável.
- **Proibida:** transformar todo bullet em fact; criar neurônio sem fonte; vetorizar duplicatas sem `parent_id` e hash de conteúdo; promover opinião temporária como decisão arquitetural; sobrescrever decisões anteriores sem criar conflito ou `invalid_at`.

**Falha de promoção preserva dados (ADR-016):**

```text
erro transitorio -> archived=0, retry futuro
erro estrutural  -> archived=2, quarentena com motivo
```

Nada é deletado por falha de promoção. Ver [`01-architecture.md` ADR-016](01-architecture.md#adr-016--falha-de-promoção-preserva-dados-nunca-descarta).

**Estado K4 (2026-06-29):** bridge real 2 passed, promoção operacional contra `~/.claude-mem/claude-mem.db` importou registros reais por `source_id`, CLI com `python3` do sistema saiu 0 via reexecução na `.venv`, `./tests/run_all.sh` fechou verde. A validação de visão real usa o papel `vision` configurado no `setup-brain`/`.env` (`HIVE_VISION_*`), sem hardcode de Ollama Cloud.

---

## 12. K5 — Cadência Hierárquica de Escrita

A memória temporal do cérebro sobe em **cinco cadências** — sessão, diário, semanal, mensal, anual — com writers, papéis de LLM e regras de promoção próprios. Detalhe normativo em [`11-knowledge-promotion-architecture.md` §14](11-knowledge-promotion-architecture.md#14-cadencia-hierarquica-de-escrita).

| Cadência | Writer | Modelo padrão | Promove |
|---|---|---|---|
| Sessão | `session_consolidator.py` | `session_summarizer` (pequeno) | decisões, perguntas abertas, evidências |
| Diário | `daily_writer.py` | `daily_writer` (pequeno/médio) | aprendizados, progresso, próximos passos |
| Semanal | `weekly_synthesizer.py` | `weekly_synthesizer` (médio/forte) | padrões, decisões estratégicas, prioridades |
| Mensal | `monthly_synthesizer.py` | `monthly_synthesizer` (forte) | síntese executiva, drift, metas, riscos |
| Anual | `yearly_synthesizer.py` | `yearly_synthesizer` (forte/batch) | princípios, lessons learned duráveis |

Cada cadência produz arquivo no `cerebro/cerebelo/{sessoes,diario,semanal,mensal,anual}/...` e indexa em `summary_vectors` (K1). Contrato de promoção por cadência: `source_id`, `period_start`, `period_end`, `cadence`, `parent_summary_id` (ver [`01-architecture.md` §29.2](01-architecture.md#292-contrato-de-promoção-por-cadência)).

**Regra de ouro:** quanto mais alta a cadência, menos ela copia texto e mais ela consolida causalidade, decisão, padrão e consequência. Mensal/anual não devem ser rebaixados automaticamente sem aviso.

**Fail-closed:** papel sem modelo próprio nem herança do `dreamer` registra falha auditável e não inventa síntese.

---

## 13. K6 — DocumentPipeline

`core/knowledge/document_pipeline.py`. Inspirado em RAGFlow, mas **preservando a anatomia do Hive-Mind**. Ver [`01-architecture.md` §25](01-architecture.md#25-documentpipeline-k6--ingestao-born-large) para o detalhamento arquitetural.

```text
documento (.md / .txt / .pdf / .docx)
  |
  v
parse layout-aware (RAGFlow adapter headless OU parser local)
  |
  v
normalize
  |
  v
chunk by structure (300-800 tokens para texto comum; por seção para MD; por símbolo para código)
  |
  v
metadata + citations (parent_id, offsets, source_uri, hash)
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

**RAGFlow** entra como adapter/headless opcional — nunca como fonte de verdade. A saída aproveitada precisa ser normalizada para UMC antes de ser recuperável. Indisponibilidade do RAGFlow **não** quebra o caminho local-first.

**Contrato de citação:** `DocumentPipeline.query(text)` retorna `citations[{source_uri, offset_start, offset_end, score, parent}]` — o retorno não pode ser apenas "melhor trecho".

---

## 14. K7 — RetrievalRouter (Roteamento por Intenção)

`core/retrieval/router.py`. Porta de entrada canônica para queries. Classifica intenção, escolhe rota especializada, devolve `{answer_context, citations, retrieval_path, confidence, missing_context}`. LlamaIndex entra apenas como adapter opcional de rerank; não decide rota nem vira fonte de verdade. Detalhes em [`01-architecture.md` §26](01-architecture.md#26-retrievalrouter-k7--roteamento-por-intenção).

**Métricas telemetrizadas** (hash da query, nunca texto bruto):

- `query_route_distribution` — quais rotas respondem com que frequência
- `confidence` média por rota
- `missing_context` quando o router não encontra camada apropriada (sinal de gap de cobertura)

---

## 15. K8 — Métricas de Saúde do Conhecimento

`scripts/health/knowledge_health.py` (entregue em v3.6.0, 2026-06-30). Este módulo **adiciona** métricas de cobertura de conhecimento; ele **não substitui** `health_dashboard.py`, `alert_dispatcher.py` nem `review_writer.py` (que continuam sendo o health da Ínsula). `sinapse_health` inclui um bloco `knowledge_health` read-only em modo quick; a REST API expõe `GET /api/v1/knowledge/health` para o gate completo.

| Métrica | Sinal | Coleção canônica (K1) |
|---|---|---|
| `neurons_total` | tamanho da memória consolidada | — |
| `neurons_vectorized_pct` | cobertura vetorial | `memory_vectors` |
| `observations_pending` | backlog temporal | `observation_vectors` |
| `observations_linked_pct` | promoção efetiva | — |
| `discoveries_pending` | risco de perder aprendizado | `observation_vectors` |
| `learnings_atomized` | aprendizado granular | `memory_vectors` |
| `document_chunks_total` | ingestão documental | `document_vectors` |
| `code_symbols_total` | cobertura estrutural | `code_vectors` |
| `milvus_sync_lag` | divergência local/produção | todas |
| `orphan_vectors` | índice sujo (primeira fatia de `forget()` §31.2) | todas |
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
0 orphan vectors
todos os chunks com parent_id
citations presentes nas respostas documentais
```

---

## 16. K10 — Escala, Isolamento e Federação

`workspace_id` é a fronteira de isolamento obrigatória ([`01-architecture.md` §30.1](01-architecture.md#30-escala-e-isolamento--workspace-e-federação)). Toda tabela crítica do UMC carrega `workspace_id` (default `'default'`). Toda query do `RetrievalRouter` e da promoção filtra por `workspace_id`. Milvus usa `partition_key=workspace_id` para isolamento por partição.

**Regras de borda:**

- **Vazamento cross-workspace é bug de segurança**, não de ranking.
- Migrações estruturais que criam essa fronteira: falha é fail-closed por padrão. O único bypass é `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` (diagnóstico de DB legado, com log visível e sem marcar a instalação como saudável).
- Federação entre instâncias: reusa HM-12 (`visibility` private|shared|public + Ed25519 + redação PII no export). Neurônio importado entra com `workspace_id` do destino e proveniência preservada. `origin_instance` e `origin_signature` são obrigatórios.
- Migração de embedding: `vectors_model_mismatch` = 0 dentro de uma coleção; re-embed online por workspace, dual-write até cutover (§30.4).
- Custo de promoção: teto por workspace via `HIVE_PROMOTION_BUDGET_*`; excedente fica `archived=0` (retry); métricas `promotion_lag` e `promotion_cost` por workspace.
