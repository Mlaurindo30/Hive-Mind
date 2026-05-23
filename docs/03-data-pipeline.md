# 03 — Pipeline de Dados

> **Sinapse Agent v1.1.0** — Fluxo completo de dados: coleta → processamento → indexação → consulta.

---

## 1. Visão Geral do Pipeline

```
┌──────────┐    ┌──────────────┐    ┌─────────────┐    ┌────────────┐
│ COLETA   │───▶│ PROCESSAMENTO│───▶│  INDEXAÇÃO   │───▶│  CONSULTA  │
│ (Escrita)│    │ (Parsing)    │    │ (Grafo + DB) │    │ (Query)    │
└──────────┘    └──────────────┘    └─────────────┘    └────────────┘
     │                │                    │                  │
     ▼                ▼                    ▼                  ▼
 vault .md      tree-sitter +         graph.json +        sinapse-memory
 + claude-mem   regex + LLM          SQLite FTS5 +        multi-backend
 observations   (NER + embeddings)   Chroma + nmem        query engine
```

---

## 2. Etapa 1 — Coleta de Dados (Escrita)

### 2.1 Fontes de Dados

| Fonte | Formato | Gatilho | Destino |
|-------|---------|---------|---------|
| Agente (decisão) | `memory_add` tool call | `post_tool_use` hook | `work/active/YYYY-MM-DD-slug.md` |
| Agente (aprendizado) | `memory_add` com learning signals | `post_tool_use` hook | `brain/Patterns.md` (append) |
| Agente (sessão) | `session_summary` | `post_session_end` hook | `brain/Current State.md` |
| claude-mem (observações) | SQLite rows | sync via HTTP API | `work/active/` (export) |
| Humano (Obsidian) | Editor Markdown | salvamento manual | Qualquer `.md` no vault |

### 2.2 Formato dos Dados

**Decisão** (`work/active/YYYY-MM-DD-slug.md`):
```yaml
---
tags: [decision]
status: active
created: 2026-05-23
updated: 2026-05-23
source: hermes-session
---

# Título da Decisão

Conteúdo completo com contexto, rationale e implicações.
```

**Aprendizado** (`brain/Patterns.md`):
```markdown
---

## Padrão Identificado (2026-05-23)

Descrição do insight, lição aprendida ou padrão descoberto.
```

**Current State** (`brain/Current State.md`):
```markdown
## Last Update: 2026-05-23 14:00

## Session: 2026-05-23 14:00

### Decisions
- Decisão: [[2026-05-23-migrar-servidor-hetzner]]

### Learnings
- Aprendizado: [[2026-05-23-padrao-system-prompts]]

### Summary
Resumo da sessão atual...
```

### 2.3 Garantias de Escrita

| Garantia | Mecanismo |
|----------|-----------|
| Atomicidade | `tempfile.mkstemp()` + `os.replace()` (atômico no Linux) |
| Deduplicação | Verificação de título antes de append em Patterns.md |
| Validação | `_validate_frontmatter_yaml()` checa `tags:`, `status:`, `created:` |
| Dry-run | `SINAPSE_DRY_RUN=1` — sem side effects |
| Logging | Falhas de escrita logadas via `_log("error", ...)` |

---

## 3. Etapa 2 — Processamento (Parsing + Embeddings)

### 3.1 Fluxo Determinístico (tree-sitter + regex)

**Sempre disponível. Sem dependência de LLM.**

```
1. tree-sitter parse → AST de arquivos de código (.py, .ts, .rs, .sh)
   └─ Extrai: funções, classes, imports, variáveis
2. regex parse → frontmatter YAML de arquivos .md
   └─ Extrai: tags, status, created, title, WikiLinks
3. Normalização → _normalize() (NFKD unicode → ASCII lowercase)
```

### 3.2 Fluxo com LLM (Gemini / Ollama Qwen)

**Opcional. Ativado com `--backend gemini` ou `--backend ollama`.**

```
1. Envia conteúdo do arquivo para LLM
2. LLM extrai:
   └─ Entidades nomeadas (pessoas, projetos, tecnologias)
   └─ Relações entre entidades (related_to, depends_on, managed_by)
   └─ Comunidades semânticas (tópicos)
3. Output estruturado → nodes + edges + communities
```

### 3.3 Embeddings (Leiden Clustering)

```
1. BGE-M3 (ou Nomic) gera embeddings (1024-d ou 768-d)
2. Matriz de similaridade entre todos os nodes
3. Leiden algorithm → agrupa nodes em comunidades
4. Comunidades recebem labels (tópicos)
```

---

## 4. Etapa 3 — Indexação

### 4.1 graph.json (Graphify)

**Formato:**
```json
{
  "nodes": [
    {
      "id": "thoth",
      "label": "Thoth (Hermes Agent)",
      "file_type": "document",
      "source_file": "AGENTS.md",
      "community": 1,
      "norm_label": "thoth hermes agent"
    }
  ],
  "links": [
    {
      "source": "thoth",
      "target": "vps",
      "relation": "related_to",
      "confidence": "EXTRACTED",
      "source_file": "AGENTS.md",
      "weight": 1.0
    }
  ]
}
```

**Métricas atuais:** 1266+ nodes, 1319+ edges, 117+ comunidades.

**Atualização:** Cron a cada 6h (`build-graph.sh`). Com backup automático e validação.

### 4.2 SQLite FTS5 (claude-mem)

```
Tabela: observations
  └─ id, content, created_at, session_id
  └─ FTS5 virtual table para full-text search
Tabela: corpora
  └─ Coleções temáticas de observações
```

### 4.3 ChromaDB (claude-mem)

```
Collection: observations
  └─ Embeddings: all-MiniLM-L6-v2 (384-d)
  └─ Metadata: session_id, timestamp, tool_name
```

### 4.4 NeuralMemory Index

```
Modelo associativo em memória:
  └─ 24 tipos de relações (causes, prevents, requires, is_a, part_of, ...)
  └─ Pesos de ativação configuráveis
  └─ Spreading activation algorithm
```

---

## 5. Etapa 4 — Consulta (Query)

### 5.1 Motor de Busca Unificado

```python
def _query_vault_knowledge(query: str) -> Optional[Dict]:
    # Backend 0: NeuralMemory (spreading activation)
    result = _backend_neural_memory(query)  # nmem recall
    
    # Backend 1: claude-mem (semântico + temporal)
    result = _backend_claude_mem(query)     # HTTP API → Chroma / FTS5
    
    # Backend 2: Graphify (estrutural)
    result = _backend_graphify(query)       # graph.json textual search
    
    # Circuit breaker + global timeout + exception logging
```

### 5.2 Algoritmo de Busca Textual (Graphify)

```
1. Normaliza query (_normalize: NFKD → ASCII → lowercase)
2. Tokeniza por whitespace → set de palavras
3. Itera todos os nodes:
   └─ Se palavra in label OR palavra in file_type OR palavra in community
      → match! Adiciona ao resultado com score (contagem de matches)
4. Itera todos os links:
   └─ Se palavra in source OR target OR relation → match!
5. Ordena nodes por score decrescente
6. Trunca em MAX_NODES (5)
7. Trunca edges em MAX_NODES (5)
```

### 5.3 Cache e Performance

| Otimização | Mecanismo |
|-----------|-----------|
| Cache graph.json | `_load_graph()` com TTL 60s, invalidação por mtime |
| Circuit breaker | Backend com 3+ falhas → cooldown 30s |
| Global timeout | `_query_vault_knowledge` tem deadline de 8s |
| Timeouts individuais | claude-mem: 3s, nmem: 5s |

### 5.4 Formatação de Contexto

```
[Sinapse — graphify (structural)]
  • Thoth (Hermes Agent) (document) — AGENTS.md
  • VPS Migration (document) — work/active/vps.md
  ↳ thoth → vps (related_to)
  ↳ vps → deploy (managed_by)
```

---

## 6. Frequência de Atualização

| Pipeline | Frequência | Gatilho |
|----------|-----------|---------|
| Escrita de decisões | Tempo real | `post_tool_use` hook |
| Escrita de aprendizados | Tempo real | `post_tool_use` hook |
| Update Current State | Fim de sessão | `post_session_end` / Stop hook |
| Sync claude-mem → vault | Manual/cron | `sync_claude_mem_to_vault()` |
| Rebuild graph.json | A cada 6h | Cron `build-graph.sh` |
| Rebuild completo | Domingo 2am | Cron `sync-diario.sh --force` |

---

## 7. Volume de Dados

| Métrica | Valor típico |
|---------|-------------|
| Nodes no graph.json | 1.266+ |
| Edges no graph.json | 1.319+ |
| Comunidades | 117+ |
| Tamanho graph.json | ~2MB |
| Observações claude-mem | Variável por uso |
| Notas no vault | ~200 arquivos .md |
| Decisões/learning por sessão | 0-5 |
| Tempo de rebuild graph.json | 30-60s |
