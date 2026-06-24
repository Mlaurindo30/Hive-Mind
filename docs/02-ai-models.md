# 02 — Modelos de IA e Provedores

> **Hive-Mind v3.0.0** — Modelos, embeddings, provedores do Hive-Dreamer e cadeia de fallback.
> Última revisão: 2026-06-24 · Embeddings 1024d bge-m3 (P0) · LightRAG granite3-dense:2b (P4)

---

## 1. Visão Geral

O Hive-Mind **não treina modelos próprios**. Usa modelos de terceiros em dois contextos distintos:

1. **Graphify** — indexação estrutural do vault (extração de entidades e relações)
2. **Hive-Dreamer** — consolidação semântica offline (Dream Cycle, fases 7-10)

Em ambos os casos, a escolha do modelo é **configurável pelo usuário** via variáveis de ambiente e via o script `setup-brain.sh`. Nenhum modelo é hardcoded.

---

## 2. Hive-Dreamer — 10 Provedores Suportados

O Dream Cycle usa LLM para: Distiller (extração de fatos), Validator (verificação de qualidade), Router (classificação para Atlas), e Síntese Dialética (resolução de conflitos P2P).

### 2.1 Configuração por papel (roles)

Cada papel que consome LLM tem configuração própria, com herança do Dreamer e fallback opt-in (regras completas em [`01-architecture.md`](01-architecture.md) §10.1 e ADR-009):

```bash
# No .env — caso mínimo: só o Dreamer (todos os papéis herdam dele)
HIVE_DREAMER_PROVIDER=google
HIVE_DREAMER_MODEL=gemini-2.0-flash

# Caso diferenciado: extração barata no Graphify + fallback local no Dreamer
HIVE_GRAPHIFY_PROVIDER=ollama
HIVE_GRAPHIFY_MODEL=qwen2.5-coder:3b
HIVE_DREAMER_FALLBACK_PROVIDER=ollama
HIVE_DREAMER_FALLBACK_MODEL=qwen2.5-coder:7b
```

| Papel | Quem usa | Perfil de chamada |
|-------|----------|-------------------|
| `dreamer` | Distiller, Validator, Router | Raciocínio — qualidade importa |
| `graphify` | Extração de entidades/relações na indexação | Volume — custo importa |
| `vision` | Descrição de screenshots (Phase 10) | Requer modelo multimodal |
| `synthesis` | Síntese Dialética P2P | Raciocínio crítico — decide a verdade |
| `planner` | Decomposição de objetivos (`sinapse_plan_goal`, `scripts/planner.py`) | Raciocínio estrutural — gera árvore de goals; herda de `HIVE_DREAMER_*` |

O script `setup-brain.py` / `setup-brain.sh` oferece UI interativa que pergunta **qual papel configurar**, exibe o valor atual (ou "herda do Dreamer"), e oferece o fluxo opcional de fallback (Enter pula). Também:
- lista modelos disponíveis por provider (via API em tempo real)
- testa conectividade antes de salvar
- detecta e exibe saldo disponível (DeepSeek, OpenRouter)

### 2.1.1 Classificação de erros e política de fallback

Implementada em `core/llm_client.py` (`classify_llm_error()` + `call_llm_with_fallback()`):

| Classe de erro | Exemplos | Ação |
|----------------|----------|------|
| **Transitório** | timeout, erro de conexão, HTTP 429, 5xx | retry com backoff `min(2^n, 8s)` → fallback (se definido) → quarentena `archived=2` |
| **Auth/saldo** | HTTP 401/402/403, "insufficient balance/quota", saldo insuficiente | fallback **direto, sem retry** → senão quarentena + warning |
| **Validação Pydantic** | saída da LLM reprovada no schema | retry no **mesmo modelo** → quarentena. **NUNCA dispara fallback** (problema de qualidade, não disponibilidade) |
| **Desconhecido** | qualquer outra exceção | tratado como transitório |

Quando o fallback é acionado, o log registra: `[Fallback] Papel 'X': alternando de A/B para C/D (motivo)`. Em todos os caminhos de falha final, a observação vai para quarentena (`archived=2`) — **nada é perdido** (ADR-008).

### 2.2 Tabela de Provedores

| Provider | Autenticação | Endpoint | Exemplo de Modelo |
|----------|-------------|----------|-------------------|
| `google` | OAuth Device Flow | AI Studio / Vertex | `gemini-2.0-flash` |
| `openai` | Bearer token | api.openai.com | `gpt-4o`, `gpt-4.1-mini` |
| `anthropic` | Bearer token | api.anthropic.com | `claude-fable-5`, `claude-haiku-4-5` |
| `deepseek` | Bearer token | api.deepseek.com | `deepseek-v3`, `deepseek-r1` |
| `huggingface` | Bearer token | api-inference.huggingface.co | `meta-llama/Llama-3-8b-instruct` |
| `qwen` | Bearer token | dashscope.aliyuncs.com | `qwen-turbo`, `qwen-plus` |
| `nvidia` | Bearer token | integrate.api.nvidia.com | `meta/llama-3.3-70b-instruct` |
| `openrouter` | Bearer token | openrouter.ai/api/v1 | `google/gemini-flash-1.5` |
| `lmstudio` | Sem auth (local) | localhost:1234/v1 | modelo carregado no LM Studio |
| `ollama` | Sem auth (local) | localhost:11434/v1 | `qwen2.5-coder:3b`, `llama3.2` |

### 2.3 Saída Estruturada (Pydantic)

Todas as chamadas LLM no Dream Cycle usam JSON Schema derivado dos modelos Pydantic:

```
Chamada LLM:
  input:  texto da observação + system prompt com schema JSON
  output: JSON → model_validate_json(response) → objeto tipado

  Se falha de validação:
    → Distiller re-tenta (máx 2x)
    → Se persistir: archived=2 (quarentena)
```

Isso garante que qualquer provider (Ollama local ou Anthropic cloud) produza a mesma estrutura processável.

---

## 3. Graphify — Modelos de Indexação

### 3.1 Extração de Entidades e Relações

| Modelo | Provider | Backend Flag | Qualidade |
|--------|----------|-------------|-----------|
| `gemini-2.5-flash` | Google AI | `--backend gemini` | Alta (cloud) |
| `qwen2.5-coder:3b` | Ollama local | `--backend ollama` | Média (local, gratuito) |
| `tree-sitter + regex` | Determinístico | `--backend ast` | Estrutural (sem LLM) |

**Seleção do backend (via papel `graphify`):**

O `scripts/build-graph.sh` lê `HIVE_GRAPHIFY_PROVIDER/MODEL` do `.env` (com herança de `HIVE_DREAMER_*` se ausente) e mapeia o provedor para o backend do graphify:

```
HIVE_GRAPHIFY_* (ou herdado do Dreamer) definido?
    │
    ├── Sim → mapeia provedor → backend:
    │     google → gemini       anthropic → claude
    │     openai → openai       deepseek  → deepseek
    │     ollama → ollama       lmstudio  → ollama (OLLAMA_BASE_URL=127.0.0.1:1234/v1)
    │     huggingface/qwen/nvidia/openrouter → sem equivalente,
    │                                          AST-only com aviso
    │
    └── Não → fallback determinístico: tree-sitter + regex (AST-only)
              (extrai funções, classes, imports, WikiLinks, frontmatter YAML)
              (sempre funciona, sem dependência externa)
```

### 3.2 Embeddings (sqlite-vec, 1024 dimensões — Ollama bge-m3)

| Modelo | Dimensões | Uso | Onde |
|--------|-----------|-----|------|
| `bge-m3:latest` | 1024 | Busca semântica KNN no UMC | sqlite-vec HNSW (env `HNSW_DIM=1024`) |
| `bge-m3:latest` | 1024 | Busca semântica de observações | sqlite-vec HNSW |
| `bge-m3:latest` | 1024 | Embeddings de memória para LightRAG | `core/lightrag_index.py` (P4) |

O modelo é carregado via **Ollama local** (`OLLAMA_EMBED_MODEL=bge-m3:latest`, 1.2 GB), exposto por `OllamaEmbedder` em `core/database.py:get_embedder()`. Não requer API key. Os vetores são persistidos na tabela virtual `search_vec` (vec0, 1024d) dentro do `hive_mind.db`. Migração do antigo 384d para 1024d foi feita na P0 (commit `56f1e98`, 2026-06-21) via `scripts/setup/migrate_embed_dim.py`.

O módulo `core/hnsw_index.py` mantém um índice HNSW incremental (via `hnswlib`) sobre os mesmos vetores 1024d. O índice é atualizado a cada ingestão sem reconstrução completa.

**Por que bge-m3 (1024d) em vez de all-MiniLM-L6-v2 (384d)?**
- bge-m3 é multilingual (PT/EN) com qualidade superior para frases técnicas
- 1024d dá ganho real de recall em queries multi-hop (que LightRAG e FTS5 juntos usam)
- Ollama local elimina dependência de API cloud para embeddings
- Migração uma-vez (P0) absorveu o custo de re-indexação; o ganho composto (KNN melhor + LightRAG funcional) compensa o espaço 4x maior em disco

---

## 4. LightRAG — Extração de Entidades + Grafo de Conhecimento (P4)

LightRAG (HKUDS/EMNLP 2025) é o **segundo extrator** ao lado do Graphify: enquanto o Graphify extrai entidades de **código** (AST + LLM), o LightRAG extrai entidades e relações de **memórias consolidadas** pelo Dream Cycle (texto livre, decisões, aprendizados).

```
  Dream Cycle (Estágio 3 — Síntese)
       │
       │ synthesis.final_content
       ▼
  core/lightrag_index.py:index_memory()
       │
       ├──> LightRAG working_dir: claude-mem/data/lightrag/
       │    ├── graph.npz (NetworkX)         — entidades + arestas
       │    ├── vdb_chunks.json              — embeddings de chunks (bge-m3)
       │    ├── vdb_entities.json            — embeddings de entidades
       │    └── vdb_relationships.json       — embeddings de relações
       ▼
  sinapse_rag_query(question, mode="hybrid")
       │
       ▼
  MCP: retorna entidades + relações + chunks relevantes
```

**Modelo LLM do LightRAG (FIXO por design):**
| Modelo | Provider | Justificativa |
|--------|----------|---------------|
| `granite3-dense:2b` | Ollama local | 1.5 GB · cabe em qualquer máquina · especializado em RAG/extração · JSON schema confiável (4/4 entities + 3/3 rels em teste live) |

- Sem fallback: se o `granite3-dense:2b` falhar, o `index_memory` retorna `False` e o Dream Cycle segue.
- Sem UI de troca no `setup-brain.sh`: o modelo é fixo em `core/lightrag_index.py:_LIGHTRAG_CHAT_MODEL`.
- `.env` (`HIVE_LIGHTRAG_MODEL`) sobrescreve apenas para debug/dev, não para produção.
- `install.sh` adiciona `ollama pull granite3-dense:2b` na nota pós-instalação.

**Modo de query (`sinapse_rag_query`):**
| Mode | Comportamento |
|------|---------------|
| `naive` | Busca vetorial simples (similar a KNN) |
| `local` | Entidades mencionadas na query + seus vizinhos |
| `global` | Traversal de arestas (relações entre entidades) |
| `hybrid` (default) | Combina local + global — melhor para perguntas multi-hop |

**Diferença prática vs FTS5 + KNN:**
- FTS5: match de palavras-chave exatas (não entende sinônimos nem contexto)
- KNN: similaridade semântica entre query e documento (não entende estrutura relacional)
- LightRAG: entende **relações** — "quem criou X?", "que ferramentas Y usa?", "qual a relação entre A e B?"

**Validação:** commit `fe68300` confirma que 4 entities + 3 relationships são extraídos corretamente de uma frase simples com o `granite3-dense:2b` (campos `entity_name`, `entity_type`, `entity_description`, `source_entity`, `target_entity`, `relationship_keywords`, `relationship_description` todos preenchidos, sem alucinação).

---

## 4. NeuralMemory — Sem LLM

O NeuralMemory (`neural-memory/`) usa **spreading activation** — algoritmo puramente matemático, sem chamada a LLM:

```
Entrada: query string
   ↓
TF-IDF + Cosine Similarity → conceitos iniciais candidatos
   ↓
Spreading Activation:
   para cada conceito com ativação > threshold:
     propaga ativação para vizinhos via 24 tipos de aresta
     (causes, prevents, requires, is_a, part_of, enables, ...)
   atenuação de 0.7 por salto
   ↓
Saída: lista de conceitos ativados com score de ativação
```

Os pesos das arestas (24 tipos de relações) foram definidos baseados em psicologia cognitiva e não mudam dinamicamente.

---

## 5. Modelos NÃO Usados (e por quê)

| Modelo | Por que não |
|--------|------------|
| GPT-4 / Claude Opus | Overkill para extração de entidades; custo proibitivo para indexação diária |
| BERT multilíngue | Mais pesado que Qwen 2.5 Coder 3B para o mesmo resultado em NER |
| Fine-tuned próprios | Complexidade de manutenção incompatível com o princípio de soberania de modelos |
| OpenAI Embeddings (text-embedding-3) | Dependência de API; bge-m3 local via Ollama é suficiente |
| ChromaDB + all-MiniLM-L6-v2 | Substituído por sqlite-vec + bge-m3 (1024d) embutidos no UMC (elimina processo separado) |
| all-MiniLM-L6-v2 (384d) | Substituído por bge-m3 (1024d) na P0 (commit `56f1e98`, 2026-06-21) — multilingual e melhor recall |

---

## 6. Matriz de Capacidades por Cenário

| Cenário | Graphify (código) | LightRAG (texto) | Embeddings | Dream Cycle | Recall |
|---------|-------------------|------------------|-----------|-----------|--------|
| Cloud (API keys) | Gemini 2.5 Flash | Granite 3 Dense 2b (local) | bge-m3 (local) | Provider configurado | Spreading Activation |
| Local (Ollama) | Qwen 2.5 Coder 3B | Granite 3 Dense 2b (local) | bge-m3 (local) | Ollama configurado | Spreading Activation |
| Offline (sem Ollama) | tree-sitter + regex | Indisponível (best-effort) | Indisponível | Indisponível | Spreading Activation |
| Mínimo (sem Python) | Indisponível | Indisponível | Indisponível | Indisponível | Indisponível |

O sistema degrada graciosamente: mesmo no cenário mínimo, o vault Obsidian permanece legível e as buscas FTS5 continuam funcionando. LightRAG é o componente que mais cedo falha em ambientes mínimos — por isso o `index_memory` é best-effort (try/except) e a síntese dialética nunca é abortada por falha do grafo.
