# 03 — Pipeline de Dados

> **Hive-Mind v2.0.0** — Fluxo completo: coleta → indexação em tempo real → Dream Cycle → consulta.

---

## 1. Visão Geral

O pipeline v2.0.0 tem dois fluxos paralelos:

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │                         FLUXO PRINCIPAL                                │
  │                                                                        │
  │  Agente / Humano                                                       │
  │       │                                                                │
  │       ▼                                                                │
  │  [ COLETA ]──── escrita atômica ──→ vault (cerebro/*.md)              │
  │       │                                   │                           │
  │       │                     Watcher ~2s   │                           │
  │       │                                   ▼                           │
  │       │              [ INDEXAÇÃO REAL-TIME ] → hive_mind.db           │
  │       │               neurons + synapses + FTS5 + sqlite-vec          │
  │       │                                                                │
  │       ▼                                                                │
  │  [ CONSULTA ] ← UMC SQL / FTS5 / KNN / claude-mem / NeuralMemory      │
  └────────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────────────┐
  │                         FLUXO OFFLINE                                  │
  │                                                                        │
  │  observations (pendentes, archived=0)                                  │
  │       │                                                                │
  │       ▼     execução manual ou agendada                                │
  │  [ DREAM CYCLE ] ─────────────────────────────────────────────────    │
  │    Distiller → Validator → Router → Atlas persistence                  │
  │       │                                                                │
  │       ▼                                                                │
  │  atlas/ (fatos consolidados) + neurons atualizados                     │
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
    ├── Gera embedding 384d (all-MiniLM-L6-v2)
    ├── UPDATE neurons SET title, content, hash, embedding
    ├── UPDATE/INSERT synapses (WikiLinks como edges)
    ├── UPDATE search_fts (trigger automático via SQL)
    └── UPDATE search_vec (vec0, HNSW)

  Resultado: hive_mind.db atualizado em memória e em disco (WAL mode)
```

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

## 5. Etapa 4 — Consulta

### 5.1 Backends Paralelos

```python
def _query_vault_knowledge(query: str, timeout=8.0) -> Optional[str]:

    # 4 backends em paralelo (ThreadPoolExecutor)
    results = []

    # Backend 1: UMC SQL (FTS5 + KNN)
    results += umc_search(query)        # FTS5 MATCH + vec KNN

    # Backend 2: claude-mem
    results += claude_mem_search(query) # HTTP :37700, timeout 3s

    # Backend 3: NeuralMemory
    results += nmem_recall(query)       # spreading activation, timeout 5s

    # Backend 4: Filesystem
    results += fs_scan(query)           # scan cerebro/*.md, TTL 30s

    # Fusão e deduplicação
    deduped = dedup(results, key=lambda r: (r.source_file, r.title))
    return format(top_n=5, max_chars=3000, results=deduped)
```

### 5.2 Busca Vetorial (KNN)

```sql
SELECT n.id, n.title, n.content, n.source_file,
       vec_distance_cosine(v.embedding, :query_vec) AS distance
FROM search_vec v
JOIN neurons n ON n.id = v.neuron_id
ORDER BY distance
LIMIT 5
```

`query_vec` = `all-MiniLM-L6-v2.encode(query)` — vetor 384d gerado no momento da query.

### 5.3 Circuit Breaker

| Estado | Condição | Comportamento |
|--------|---------|---------------|
| Fechado (normal) | Menos de 3 falhas | Backend ativo |
| Aberto (cooldown) | 3+ exceções ou timeouts | Cooldown 30s, backend ignorado |
| Semi-aberto (teste) | Após 30s | Uma tentativa para resetar |

Apenas exceções Python e timeouts contam como falha — resultados vazios (não encontrado) não.

---

## 6. Frequência de Atualização

| Pipeline | Frequência | Gatilho |
|----------|-----------|---------|
| Escrita de decisões/aprendizados | Imediata | PostToolUse / Stop hook |
| Indexação no UMC (Watcher) | ~2 segundos | watchdog FileModifiedEvent |
| Dream Cycle | Manual ou cron | `python3 scripts/dream_cycle.py` |
| Auditoria P2P | 1x por hora | Cron `audit_memory.py --fix` |
| Backup UMC | Diário 3am | Cron `cp hive_mind.db backups/` |

---

## 7. Volume de Dados

| Métrica | Valor típico |
|---------|-------------|
| neurons no UMC | 1.200+ |
| synapses no UMC | 1.300+ |
| observations pendentes (por sessão) | 5-30 |
| atlas/*.md (fatos consolidados) | cresce com uso |
| Tamanho do hive_mind.db | 50-200MB |
| Tempo de reindexação por arquivo | ~1-3s |
| Tempo de busca KNN (10k vetores) | ~5ms |
| Tempo de busca FTS5 | ~2ms |
