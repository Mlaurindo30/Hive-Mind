# 05 — Blueprints e Fluxogramas

> **Hive-Mind v3.0.0** — Diagramas de arquitetura e fluxos em ASCII (compatível com qualquer editor Markdown).
> Última revisão: 2026-06-30. Inclui o **fluxo canônico de 9 etapas** (K0–K10), `RetrievalRouter` (K7), `DocumentPipeline` (K6), cadência hierárquica (K5) e a anatomia estendida com `workspace_id` (K10). Referência normativa em [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md); arquitetura destilada em [`01-architecture.md`](01-architecture.md).

---

## 1. Arquitetura de 4 Camadas

```
  ┌───────────────────────────────────────────────────────────────────┐
  │                        AGENTES DE IA                              │
  │                                                                   │
  │   ┌──────────┐  ┌────────────┐  ┌───────────┐  ┌─────────────┐  │
  │   │  Hermes  │  │ Claude Code│  │ Codex CLI  │  │ Outros MCP  │  │
  │   │  Agent   │  │ (hooks +   │  │ (hooks +   │  │ (Cursor,    │  │
  │   │ (plugin) │  │  MCP)      │  │  MCP)      │  │  OpenClaw)  │  │
  │   └────┬─────┘  └─────┬──────┘  └─────┬─────┘  └──────┬──────┘  │
  └────────┼──────────────┼───────────────┼───────────────┼──────────┘
           │              │               │               │
  ┌────────▼──────────────▼───────────────▼───────────────▼──────────┐
  │                    CAMADA DE INTEGRAÇÃO                           │
  │                                                                   │
  │  sinapse-memory.py   sinapse-mcp.py   sinapse-hook.py            │
  │  (Plugin nativo)     (MCP stdio)      (Hook universal)           │
  │                              │                                    │
  │                       sinapse-api.py                              │
  │                       (REST :37702)                               │
  │                       POST /export  (HM-12, visibility filter)   │
  │                       sinapse-write.py                            │
  │                       (CLI standalone)                            │
  └──────────────────────────────┬────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼────────────────────────────────────┐
  │                    BACKENDS DE MEMÓRIA                            │
  │                                                                   │
  │  ┌───────────────┐  ┌─────────────┐  ┌──────────┐  ┌─────────┐  │
  │  │ UMC (SQLite)  │  │  claude-mem │  │  Neural  │  │   RTK   │  │
  │  │ FTS5 + vec    │  │  :37700     │  │  Memory  │  │  (Rust) │  │
  │  │ neurons +     │  │  temporal   │  │ spreading│  │  shell  │  │
  │  │ synapses +    │  │  tracking   │  │activation│  │  optim. │  │
  │  │ causal_edges +│  │             │  │          │  │         │  │
  │  │ goals (HM-11) │  │             │  │          │  │         │  │
  │  └───────┬───────┘  └──────┬──────┘  └────┬─────┘  └─────────┘  │
  └──────────┼─────────────────┼──────────────┼──────────────────────┘
             │                 │              │
  ┌──────────▼─────────────────▼──────────────▼──────────────────────┐
  │                         STORAGE                                   │
  │                                                                   │
  │   hive_mind.db          cerebro/              backups/            │
  │   (UMC — SQLite +       (Vault Obsidian)      (daily cp)          │
  │    sqlite-vec)          cortex/ cerebelo/ tronco/                 │
  │   hnsw_neurons.idx      cortex/frontal/trabalho/ativo/            │
  │   (HNSW incremental,    config/keys/                              │
  │    HM-11)               (Ed25519, gitignored)                     │
  └───────────────────────────────────────────────────────────────────┘
```

---

## 2. Fluxo de Leitura (Read Path)

```
  Usuário escreve mensagem para o agente
                │
                ▼
  Hook SessionStart / pre_gateway_dispatch
                │
                ▼
  _query_vault_knowledge(query, timeout=8s)
                │
        ┌───────┴────────────────────────────────────┐
        │               (paralelo)                   │
        ▼               ▼              ▼             ▼
  ┌──────────┐   ┌──────────┐   ┌──────────┐  ┌──────────┐
  │ UMC SQL  │   │claude-mem│   │NeuralMem │  │Filesystem│
  │ FTS5     │   │ HTTP     │   │spreading │  │scan *.md │
  │ KNN vec  │   │ :37700   │   │activation│  │TTL 30s   │
  │          │   │ timeout3s│   │timeout 5s│  │          │
  └────┬─────┘   └────┬─────┘   └────┬─────┘  └────┬─────┘
       │              │              │              │
       └──────────────┴──────────────┴──────────────┘
                             │
                     merge + dedup
                    (source_file + title)
                             │
                     format(top-5, max 3000 chars)
                             │
                             ▼
              inject no system_message do agente
                             │
                             ▼
  Agente responde com contexto do vault
```

---

## 3. Fluxo de Escrita (Write Path)

```
  Agente chama tool de memória
  (sinapse_save_decision | sinapse_save_learning | memory_add)
                │
                ▼
  Hook PostToolUse detecta DECISION_TOOLS
                │
                ├── _sanitize_slug(title)
                │     "Minha Decisão" → "2026-06-10-minha-decisao"
                │
                ├── _validate_frontmatter_yaml()
                │     checa: tags, status, created
                │
                ├── secret_scan(content)
                │     regex: sk-proj-*, AKIA*, Bearer, api_key=
                │     → Fernet encrypt → vault table
                │     → replace by "[SECRET:uuid]" no conteúdo
                │
                ├── _atomic_write(path, content)
                │     mkstemp() → write → os.replace()  ← atômico
                │
                └── Se LEARNING_SIGNALS no content:
                      _save_learning() → cerebelo/padroes/Patterns.md
                      _dedup_check() → não duplica mesmo título
                                │
                                ▼ (~2 segundos)
              Watcher detecta FileModifiedEvent
                                │
                                ▼
              Graphify reindexa arquivo:
              UPDATE neurons / synapses / FTS5 / vec

  ─ ─ ─ ─ ─ ─ ─ Fim de sessão ─ ─ ─ ─ ─ ─ ─

  Hook Stop / on_session_end
                │
                ├── _update_current_state()
                │     brain/Current State.md
                │     (WikiLinks para decisões da sessão)
                │
                └── INSERT observations(type='session_end')
```

---

## 4. Dream Cycle — Pipeline de Consolidação

```
  hive_mind.db
  observations (archived=0, não processadas)
         │
         ▼  (batch de até N por execução)
  ┌──────────────────────┐
  │     DISTILLER        │
  │  LLM → DistilledFact │
  │  JSON schema via      │
  │  Pydantic            │
  └──────────┬───────────┘
             │ DistilledFact
             ▼
  ┌──────────────────────┐         ┌──────────────────────┐
  │     VALIDATOR        │──repro→ │     QUARENTENA       │
  │  LLM: aprovado?      │ vado    │  archived=2           │
  │  max 2 retries        │         │  (não perdido)        │
  └──────────┬───────────┘         └──────────────────────┘
             │ aprovado
             ▼
  ┌──────────────────────┐
  │      ROUTER          │
  │  classifica destino  │
  │  check duplicata     │
  │  cosine > 0.92       │
  └──────────┬───────────┘
             │
     ┌───────┴────────┐
     │                │
     ▼ novo           ▼ duplicata
  ┌─────────────┐  ┌───────────────┐
  │ ATLAS WRITE │  │ MERGE         │
  │ atomic write│  │ append unique │
  │ INSERT neuron│  │ insights only │
  └──────┬──────┘  └───────┬───────┘
         │                 │
         └────────┬─────────┘
                  │
                  ▼
  UPDATE observations SET archived=1
  (consolidated_at = NOW())
```

---

## 5. Circuit Breaker (Fallback Chain)

```
  Query chega no motor de busca
         │
         ▼
  ┌──────────────────┐      3+ falhas    ┌───────────────┐
  │ UMC SQL (FTS5 +  │──────────────────▶│   COOLDOWN    │
  │  KNN vec)        │   cooldown 30s    │   30 segundos │
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  ┌──────────────────┐      3+ falhas    ┌───────────────┐
  │ claude-mem       │──────────────────▶│   COOLDOWN    │
  │ HTTP :37700      │   cooldown 30s    │   30 segundos │
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  ┌──────────────────┐      3+ falhas    ┌───────────────┐
  │ NeuralMemory     │──────────────────▶│   COOLDOWN    │
  │ spreading activ. │   cooldown 30s    │   30 segundos │
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  ┌──────────────────┐      3+ falhas    ┌───────────────┐
  │ Filesystem scan  │──────────────────▶│   None        │
  │ cerebro/*.md     │                   │ (sem contexto)│
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  resultado retornado ao agente

  Nota: resultados vazios (não encontrado) NÃO contam como falha.
        Apenas exceções Python e timeouts disparam o circuit breaker.
```

---

## 6. Pipeline Graphify (Indexação Estrutural)

```
  cerebro/*.md  (vault Obsidian)
         │
         ▼
  ┌──────────────┐
  │  PARSER      │
  │  frontmatter │  extrai: title, tags, WikiLinks
  │  YAML        │
  └──────┬───────┘
         │
         ▼
  ┌───────────────────────────────────────────┐
  │  BACKEND (escolhido por disponibilidade)  │
  │                                           │
  │  1º: Gemini 2.5 Flash (cloud)             │
  │      NER: entidades + relações            │
  │                                           │
  │  2º: Ollama Qwen 2.5 Coder 3B (local)    │
  │      NER local, sem API key               │
  │                                           │
  │  3º: tree-sitter + regex (determinístico) │
  │      parsing sintático, sempre funciona   │
  └──────┬────────────────────────────────────┘
         │ entities + relations
         ▼
  ┌──────────────────┐
  │  EMBEDDING       │
  │  snowflake-      │  1024 dimensões, Ollama local
  │  arctic-embed2   │
  └──────┬───────────┘
         │ vetor 1024d
         ▼
  ┌────────────────────────────────────────────┐
  │  hive_mind.db                              │
  │  INSERT/UPDATE neurons (id, title, hash)   │
  │  INSERT/UPDATE synapses (source, target)   │
  │  UPDATE search_fts (trigger automático)    │
  │  UPDATE search_vec (vec0 HNSW)             │
  └────────────────────────────────────────────┘
```

---

## 7. Integração Multi-Agente

```
  ┌────────────────────────────────────────────────────────────────┐
  │  HERMES (Plugin Nativo)                                        │
  │   pre_gateway_dispatch → post_tool_call → on_session_end       │
  │   Arquivo: plugins/hermes/sinapse-memory.py                    │
  └────────────────────────────────┬───────────────────────────────┘
                                   │
  ┌────────────────────────────────┼───────────────────────────────┐
  │  CLAUDE CODE (MCP + Hooks)     │                               │
  │   SessionStart ────────────────┤                               │
  │   PostToolUse  ────────────────┤──▶  sinapse-hook.py           │
  │   Stop         ────────────────┤                               │
  │   MCP tools ──────────────────▶│──▶  sinapse-mcp.py (10 tools) │
  └────────────────────────────────┤───────────────────────────────┘
                                   │
  ┌────────────────────────────────┼───────────────────────────────┐
  │  CODEX CLI (MCP + Hooks)       │                               │
  │   SessionStart ────────────────┤                               │
  │   PostToolUse  ────────────────┤──▶  sinapse-hook.py           │
  │   Stop         ────────────────┤                               │
  │   MCP tools ──────────────────▶│──▶  sinapse-mcp.py (10 tools) │
  └────────────────────────────────┤───────────────────────────────┘
                                   │
  ┌────────────────────────────────┼───────────────────────────────┐
  │  OUTROS (MCP only)             │                               │
  │  Cursor, OpenClaw, KiloCode ───┤──▶  sinapse-mcp.py (10 tools) │
  └────────────────────────────────┤───────────────────────────────┘
                                   │
  ┌────────────────────────────────▼───────────────────────────────┐
  │  REST API (cloud mode)                                         │
  │  sinapse-api.py :37702 (Bearer token)                          │
  │  /api/v1/query  /api/v1/observations  /api/v1/health           │
  │  /api/v1/neurons/export  (HM-12, visibility filter + redact)   │
  └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                          hive_mind.db (UMC)
```

---

## 8. Atomic Write

```
  _atomic_write(filepath, content)
         │
         ▼
  mkstemp(dir=parent_dir)
         │ retorna (fd, tmppath)
         ▼
  write(fd, content.encode('utf-8'))
         │
         ▼
  close(fd)
         │
         ▼
  os.replace(tmppath, filepath)
         │                         ← ATÔMICO no Linux/POSIX
         ▼                           rename(2) syscall
  arquivo final íntegro

  Cenários de falha:
    Processo morre antes do replace:
      tmppath fica como orphan (não afeta filepath)
    Processo morre durante o replace:
      Kernel garante atomicidade — filepath ou velho ou novo
    Disco cheio durante write:
      write() lança OSError — tmppath descartado, filepath intacto
```

---

## 9. P2P Sync (Sincronização Multi-Máquina)

```
  Máquina A                    Syncthing                    Máquina B
  (cerebro/)                   (transport)                  (cerebro/)
     │                              │                            │
     │ arquivo.md criado/editado    │                            │
     │──────────────────────────────▶                            │
     │                              │──────────────────────────▶│
     │                              │  arquivo.md recebido      │
     │                                                           │
     │                                    Watcher detecta (~2s) │
     │                                    OU cron audit_memory.py│
     │                                                           │
     │                                    audit_memory.py --fix  │
     │                                       │                   │
     │                                       ▼                   │
     │                                    SHA-256(arquivo.md)    │
     │                                       │                   │
     │                                 hash == neurons.hash?     │
     │                                    │         │            │
     │                               sim (ok)   não (divergência)│
     │                                    │         │            │
     │                                  skip    reindex neuron   │
     │                                           + INSERT        │
     │                                          ambiguities      │
     │                                               │           │
     │                                        Dream Cycle:       │
     │                                        Síntese Dialética  │
     │                                        (merge/choose/     │
     │                                         branch)           │
```

---

## 10. HM-11 — Intent & Causality Flow

```
  OBJETIVO DO USUARIO
        |
        v
  [ sinapse_plan_goal ] --- LLM ---> steps (GoalStep[])
        |                                  |
        v                                  v
  goals TABLE                    observations (goal_id, why)

  neurons ---> causal_edges ---> get_causal_neighbors (BFS 2-hop)
               (causa_id,
                efeito_id)
```

Componentes envolvidos:

| Componente | Arquivo | Responsabilidade |
|------------|---------|-----------------|
| Planner | `scripts/planner.py` | Decompoe objetivo em GoalStep[] via LLM |
| MCP tool | `sinapse_plan_goal` | Expoe o planner como tool MCP |
| Tabela goals | `hive_mind.db` | Persiste objetivos e steps |
| Intent metadata | `observations.goal_id`, `.why` | Liga observacao ao objetivo ativo |
| Causal graph | `causal_edges` | Aresta causa -> efeito entre neurons |
| BFS causal | `get_causal_neighbors()` | Recupera vizinhos causais ate 2 hops |
| HNSW Index | `core/hnsw_index.py` | Indice incremental, grava `indexed_at` |

---

## 11. HM-12 — Federated Export Flow

```
  POST /api/v1/neurons/export
        |
        v
  visibility IN ('shared', 'public')
  + filtros opcionais: type, created_after
        |
        |-- redact_neuron()  <-- core/redactor.py  (PII removal)
        |   API tokens, email, IPv4/6, paths absolutos,
        |   SSH keys, CPF/CNPJ, telefone
        |   (nao modifica o neuron local)
        |
        |-- sign_neuron()    <-- core/signing.py   (Ed25519)
        |   JSON canonico (exclui timestamps e campos _prefixados)
        |   verify_neuron() para validacao pelo receptor
        |   Keys em config/keys/ (gitignored)
        |
        v
  JSON response
  { neurons[], signature?, pubkey_fingerprint? }
```

Componentes envolvidos:

| Componente | Arquivo | Responsabilidade |
|------------|---------|-----------------|
| Export endpoint | `scripts/services/sinapse-api.py` | `POST /api/v1/neurons/export`, autenticado |
| Visibility filter | `neurons.visibility` | `private` (default) / `shared` / `public` |
| Redactor | `core/redactor.py` | Remove PII irreversivelmente antes do export |
| Signing | `core/signing.py` | Ed25519 keypair, assina/verifica JSON canonico |

---

## 12. Componentes — Visao Geral v3.0.0

| Componente | Arquivo | Fase | Descricao |
|------------|---------|------|-----------|
| UMC core | `hive_mind.py` | base | SQLite + FTS5 + sqlite-vec |
| Graphify watcher | `graphify/` | base | Indexacao em tempo real |
| Dream Cycle | `scripts/dream/dream_cycle.py` | base | Consolidacao offline |
| sinapse-api | `scripts/services/sinapse-api.py` | base | REST :37702 |
| sinapse-mcp | `scripts/services/sinapse-mcp.py` | base | MCP stdio (15 tools) |
| sinapse-hook | `cerebro/tronco/infra/agentes/.claude/scripts/sinapse-hook.py` | base | Hooks universais |
| HNSW Index | `core/hnsw_index.py` | HM-11 | Indice incremental 1024d com embedding canônico `snowflake-arctic-embed2` |
| Planner | `scripts/analytics/planner.py` | HM-11 | Decompositor de objetivos via LLM |
| Signing | `core/signing.py` | HM-12 | Ed25519 assinatura/verificacao |
| Redactor | `core/redactor.py` | HM-12 | Remocao irreversivel de PII |

---

## 13. Deploy VPS

```
  Internet
     │ HTTPS (TLS via nginx/Caddy)
     ▼
  ┌──────────────────────────────────────────────────────────┐
  │  VPS                                                     │
  │                                                          │
  │  nginx/Caddy (:443) → proxy → sinapse-api.py (:37702)  │
  │                                                          │
  │  systemd units:                                          │
  │    hive-mind-api.service      (sinapse-api.py)           │
  │    hive-mind-watcher.service  (start-watcher.sh)         │
  │    claude-mem.service         (bun run serve :37700)     │
  │    syncthing.service          (P2P sync)                 │
  │    ollama.service             (:11434)                   │
  │                                                          │
  │  cron:                                                   │
  │    0 * * * * audit_memory.py --fix                       │
  │    0 3 * * * backup hive_mind.db                         │
  │                                                          │
  │  hive_mind.db ← Watcher ← cerebro/ ← Syncthing ──────┐ │
  │                                                       │ │
  └───────────────────────────────────────────────────────┼─┘
                                                          │
                                                   ┌──────┴──────┐
                                                   │  Outras      │
                                                   │  máquinas    │
                                                   │  (Syncthing) │
                                                   └─────────────┘
```

---

## 13. Fluxo Canônico de 9 Etapas (K0–K10)

Versão completa do fluxo de conhecimento ([`11-knowledge-promotion-architecture.md` §2](11-knowledge-promotion-architecture.md#2-fluxo-completo), [`01-architecture.md` §23](01-architecture.md#23-fluxo-de-captura--promoção--recuperação)):

```text
  Agente / Humano / Sistema
          |
          v
  [1] Capture Layer
      hooks · MCP · CLI · browser · documentos · codigo · screenshots · runtime
          |
          v
  [2] Temporal Hippocampus (claude-mem)
      user_prompts · observations · discoveries · session_summaries
      facts / narrative / concepts · files_read / files_modified
          |
          v
  [3] Knowledge Intake (core/knowledge/intake.py — K3)
      normaliza · classifica · deduplica · preserva evidência
          |
          v
  [4] Promotion Layer (core/knowledge/promotion.py — K4)
      Distiller → Validator → Router
      raw -> summary -> fact / learning / decision / preference / task / rationale
          |
          v
  [5] Anatomical Memory
      cerebro/ + UMC:
        cortex temporal · frontal · parietal · occipital · insula
        cerebelo · diencefalo · tronco
          |
          v
  [6] Index Layer
      FTS · sqlite-vec · Milvus · vec_observations · Graphify · Graphiti · LightRAG
      (7 coleções canônicas — K1)
          |
          v
  [7] Retrieval Router (core/retrieval/router.py — K7)
      classifica intent → escolhe temporal · memoria · documento · codigo · grafo · chunk · hibrido
          |
          v
  [8] Answer + Citation
      resposta com source · evidência · caminho · data
      (citations[{source_uri, offset_start, offset_end, score, parent}])
          |
          v
  [9] Feedback
      nova observação, decisão, aprendizado ou tarefa
```

**Regra de borda:** cada etapa é fracamente acoplada. Falha em [4] não bloqueia [1]–[3] (a observação volta com `archived=0` ou `archived=2`). Nada é deletado por falha de promoção (ADR-016).

---

## 14. RetrievalRouter (K7) — Roteamento por Intenção

```text
                            query
                              |
                              v
                +----------- RetrievalRouter ----------+
                |          (K7, classifica intent)      |
                |                                      |
                v                                      v
      intenção classificada                  confiança baixa?
                |                                      |
        +-------+-------+-------+-------+             v
        |       |       |       |       |       fallback para
        v       v       v       v       v       sinapse_query
   temporal  memoria  doc     code    grafo   (Context Fusion)
   (claude-  (memory  (doc    (code   (Graphiti/
    mem)    vectors) vectors) vectors) LightRAG)
                |
                v
       resposta com
       retrieval_path + citations + confidence + missing_context
```

**Rotas canônicas (de [`01-architecture.md` §26](01-architecture.md#26-retrievalrouter-k7--roteamento-por-intenção)):**

- recente / "o que aconteceu" → claude-mem temporal
- decisão / preferência → memory_vectors + FTS
- aprendizado → learning atoms + Patterns parent
- documento → document_vectors + parent context
- código → code_vectors + Graphify
- causalidade / quando era verdade → Graphiti
- pergunta global / multi-hop → LightRAG/GraphRAG
- saúde / autoconsciência → Ínsula (saúde/conflitos)
- config / operacional / modelo → Tronco (operational_fact)
- setor / cross-projeto → Diencéfalo + Graphiti
- ambígua → hybrid + reranker (opcional, §31.1)

**Contrato de retorno** (toda consulta K7 devolve):

```json
{
  "answer_context": [],
  "citations": [],
  "retrieval_path": [],
  "confidence": 0.0,
  "missing_context": []
}
```

Telemetria `query_route_distribution` (hash da query, não texto) é gravada em `query_route_log` para alimentar a métrica de saúde K8.

---

## 15. DocumentPipeline (K6) — Ingestão Born-Large

Inspirado em RAGFlow, mas **preservando a anatomia do Hive-Mind**:

```text
  documento (.md / .txt / .pdf / .docx)
              |
              v
  parse layout-aware
  (RAGFlow headless OU parser local)
              |
              v
  normalize
              |
              v
  chunk by structure
  (300-800 tokens; por seção para MD; por símbolo para código)
              |
              v
  metadata + citations
  (parent_id, offsets, source_uri, hash, heading, workspace_id)
              |
              v
  embedding 1024d
  (snowflake-arctic-embed2)
              |
              v
  document_memories (pai) + document_chunks (átomos) + document_vectors
              |
              v
  opcional: KnowledgePromotionPipeline (K3/K4)
            -> fact / learning / decision / preference / rationale
```

**Três níveis para evitar "texto solto" (K6):**

| Nível | Tabela/coleção | Conteúdo | Por que existe |
|---|---|---|---|
| Documento-pai | `document_memories` | `document_id`, `source_uri`, `file_hash`, `project`, `workspace_id`, metadata | Prova de origem e unidade de reingestão |
| Chunk | `document_chunks` | `parent_id`, `parent_type=document`, `chunk_index`, `heading`, offsets, `hash`, metadata | Unidade atômica recuperável |
| Vetor | `document_vectors` | embedding do chunk + metadata canônica | Busca semântica local/Milvus sem perder parent context |

**RAGFlow:** adapter/headless opcional; nunca fonte de verdade. Saída aproveitada precisa ser normalizada para UMC antes de ser recuperável. Indisponibilidade do RAGFlow **não** quebra o caminho local-first.

---

## 16. VectorBackend — 7 Coleções Canônicas (K1)

```text
                          VectorBackend
                       (contrato único, §24)
                              |
        +---------+-----------+-----------+-----------+---------+--------+
        |         |           |           |           |         |        |
        v         v           v           v           v         v        v
   memory    observation  document    code      visual    graph   summary
   _vectors  _vectors     _vectors    _vectors   _vectors  _vectors _vectors
   (facts)   (claude-mem) (chunks)   (symbols)  (shots)   (entities)(session
                                                          +rels    ->anual)
        |         |           |           |           |         |        |
        v         v           v           v           v         v        v
   sqlite-vec  sqlite-vec   sqlite-vec   sqlite-vec  sqlite-vec sqlite-vec sqlite-vec
   (UMC)       (claude-mem) (UMC)        (UMC)       (UMC)      (UMC)     (UMC)
   (local)     (read-only)  (local)      (local)     (local)    (local)   (local)
                                                                     
   ─────────────────────────────────────────────────────────────────────
                              Milvus (produção)
                              partition_key = workspace_id
```

**Metadata canônica por item vetorial** (obrigatória em todas as coleções):

- `parent_id`, `parent_type`
- `brain_lobe` (cortex temporal / frontal / parietal / occipital / insula / cerebelo / diencefalo / tronco)
- `knowledge_type` (event_raw, user_prompt, fact, decision, learning, document_chunk, code_symbol, visual_observation, …)
- `project`, `workspace_id` (K10)
- `source_uri`, `hash`, `valid_at`

**Identidade da coleção** = `(name, embedding_model, dim)`. Migração de embedding (K10): re-embed online por workspace, dual-write até cutover, métrica `vectors_model_mismatch` = 0 dentro de uma coleção.

---

## 17. Cadência Hierárquica (K5) — Sessão → Anual

```text
  +---------------+     +-----------------+     +-----------------+
  |   sessao       |     |   diario         |     |   semanal       |
  | session_       |     |  daily_writer    |     |  weekly_        |
  | summarizer     |     |  (pequeno/médio) |     |  synthesizer    |
  | (pequeno)      |     |                 |     |  (médio/forte)  |
  +-------+--------+     +--------+--------+     +--------+---------+
          |                       |                       |
          v                       v                       v
  cerebelo/sessoes/         cerebelo/diario/         cerebelo/semanal/
  YYYY/MM/YYYY-MM-          YYYY/MM/YYYY-MM-          YYYY-Wxx.md
  DD-HHMM-{slug}.md        DD.md
  summary_vectors          summary_vectors           summary_vectors

  +---------------+     +-----------------+
  |   mensal      |     |   anual         |
  |  monthly_     |     |  yearly_        |
  |  synthesizer  |     |  synthesizer    |
  |  (forte)      |     |  (forte/batch)  |
  +-------+-------+     +--------+--------+
          |                       |
          v                       v
  cerebelo/mensal/         cerebelo/anual/
  YYYY-MM.md               YYYY.md
  summary_vectors          summary_vectors
```

**Regra de ouro:** quanto mais alta a cadência, menos ela copia texto e mais ela consolida causalidade, decisão, padrão e consequência.

**Regra de promoção por cadência (de [`01-architecture.md` §29.2](01-architecture.md#292-contrato-de-promoção-por-cadência)):**

- **Permitida:** `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` — todos com fonte rastreável.
- **Proibida:** transformar todo bullet em fact; criar neurônio sem fonte; vetorizar duplicatas sem `parent_id`; promover opinião temporária como decisão arquitetural; sobrescrever decisões anteriores sem criar conflito ou `invalid_at`.

**Fail-closed:** papel sem modelo próprio nem herança do `dreamer` registra falha auditável e não inventa síntese.

---

## 18. Escala e Isolamento (K10) — Workspace e Federação

```text
  ┌──────────────────────────┐        ┌──────────────────────────┐
  │ Instância A (workspace= │  P2P   │ Instância B (workspace= │
  │ "default")               │  ───►  │ "team-1")                │
  │                          │  ◄───  │                          │
  │  todas as tabelas:       │        │  todas as tabelas:       │
  │   workspace_id = 'default'│        │   workspace_id = 'team-1'│
  │                          │        │                          │
  │  Milvus:                 │        │  Milvus:                 │
  │   partition_key =        │        │   partition_key =        │
  │   workspace_id           │        │   workspace_id           │
  │                          │        │                          │
  │  export:                 │        │  import:                 │
  │   visibility in          │        │   verify_neuron()        │
  │   (shared, public)       │        │   workspace_id do destino│
  │   + redact + sign        │        │   origin_instance        │
  │                          │        │   origin_signature       │
  └──────────────────────────┘        └──────────────────────────┘
```

**Regra crítica:** nenhum neurônio/vetor/edge cruza `workspace_id` sem passar pela camada de federação. Vazamento cross-workspace é bug de segurança, não de ranking.

---

## 19. VectorBackend & Vector Migration (K10)

```text
  coleção carrega (embedding_model, dim) na identidade
  ex.:  memory_vectors  ·  snowflake-arctic-embed2:latest  ·  1024

  +---------------------------+
  | migração de embedding     |
  +---------------------------+
  1. cria nova coleção com (name, novo_modelo, nova_dim)
  2. dual-write (antigo + novo) durante cutover
  3. backfill de embeddings antigos em batch (offline)
  4. cutover: sinapse_query + RetrievalRouter passam a consultar a nova
  5. forget() na coleção antiga (motivo 'superseded' — tombstone, sem delete físico)
```

**Contrato de borda:** `vectors_model_mismatch` = 0 dentro de uma coleção após cutover.

---

## 20. Knowledge Promotion Pipeline (K3/K4) — Camadas

```text
  claude-mem (observations, discoveries, session_summaries, facts, narrative, concepts, files_*)
        |
        v
  Knowledge Intake (K3) — core/knowledge/intake.py
    - normaliza campos
    - preserva source_id (claude-mem:<table>:<id>)
    - extrai evidência (arquivos, timestamps, project, workspace_id)
    - classifica knowledge_type
    - deduplica por source_id + hash de conteúdo
        |
        v
  Promotion Layer (K4) — core/knowledge/promotion.py
    Distiller  (DistillerOutput Pydantic)         "extraia fatos estruturados"
        |
        v
    Validator  (ValidatorOutput Pydantic)         "estes fatos são suportados pelos logs?"
        | aprovado         | reprovado → feedback → Distiller
        v
    Router  (RouterOutput Pydantic)              "para qual projeto/tópico vai?"
        |
        +-- falha transitória → archived=0 (retry)
        +-- falha estrutural   → archived=2 (quarentena com motivo)
        +-- sucesso
              v
        Persistência Anatômica (cerebro/ + UMC)
              v
        Indexação Multi-Coleção (K1)
          - FTS5
          - VectorBackend.upsert() em memory/observation/summary_vectors
          - Graphiti: push_neuron (causal_edges)
          - LightRAG: index_memory (entidades + relações)
          - Graphify: reindexa grafo estrutural
              v
        observation.neuron_id = neuron.id
        archived=1
```

**Regra de promoção automática:**

- **Permitida:** `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` — todos com fonte rastreável.
- **Proibida:** transformar todo bullet em fact; criar neurônio sem fonte; vetorizar duplicatas sem `parent_id` e hash; promover opinião temporária como decisão arquitetural; sobrescrever decisões anteriores sem criar conflito ou `invalid_at`.
