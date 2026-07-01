# 02 — Modelos de IA e Provedores

> **Hive-Mind v3.0.0** — Modelos, embeddings, provedores do Hive-Dreamer e cadeia de fallback.
> Última revisão: 2026-06-30 · Embeddings 1024d snowflake-arctic-embed2 · LightRAG qwen2.5:3b (P4) · **Cadência K5 (sessão/diário/semanal/mensal/anual) com papéis próprios**

---

## 1. Visão Geral

O Hive-Mind **não treina modelos próprios**. Usa modelos de terceiros em três contextos distintos, todos com configuração por papel via `HIVE_{ROLE}_*`:

1. **Graphify** — indexação estrutural do vault (extração de entidades e relações)
2. **Hive-Dreamer** — consolidação semântica offline (Dream Cycle, Knowledge Intake K3 + Promotion Layer K4)
3. **Cadência** — writers de cadência (K5: `session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer`, `yearly_synthesizer`), cada um com modelo próprio ou herança do Dreamer

Em todos os casos, a escolha do modelo é **configurável pelo usuário** via variáveis de ambiente e via o script `setup-brain.sh`. Nenhum modelo é hardcoded.

---

## 2. Hive-Dreamer — 10 Provedores Suportados

O Dream Cycle usa LLM para: Distiller (extração de fatos), Validator (verificação de qualidade), Router (classificação para Atlas), e Síntese Dialética (resolução de conflitos P2P). A partir de K3/K4, o pipeline de promoção é **em camadas** (Knowledge Intake + Promotion Layer; ver [`01-architecture.md` §27](01-architecture.md#27-knowledge-promotion-pipeline-k3k4)).

### 2.1 Configuração por papel (roles)

Cada papel que consome LLM tem configuração própria, com herança do Dreamer e fallback opt-in (regras completas em [`01-architecture.md`](01-architecture.md) §11.1 e ADR-009):

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

### 2.1.0 Papéis canônicos (constante `HIVE_LLM_ROLES` em `core/auth.py`)

Os papéis abaixo são canônicos no código (case-insensitive, `-` vira `_`); nome vazio ou não-string levanta `ValueError`. Resolução centralizada em `get_role_config()` (`core/auth.py`).

| Papel | Quem usa | Perfil de chamada |
|-------|----------|-------------------|
| `dreamer` | Knowledge Intake + Distiller, Validator, Router (legado) | Raciocínio — qualidade importa |
| `graphify` | Extração de entidades/relações na indexação | Volume — custo importa |
| `vision` | Descrição de screenshots (Phase 10) | Requer modelo multimodal |
| `synthesis` | Síntese Dialética P2P | Raciocínio crítico — decide a verdade |
| `planner` | Decomposição de objetivos (`sinapse_plan_goal`, `scripts/planner.py`) | Raciocínio estrutural — gera árvore de goals; herda de `HIVE_DREAMER_*` |
| `claude_mem` | Bridge `claude_mem_bridge.py` (K4) — classifica `knowledge_type` | Barato e rápido; herda do Dreamer se não definido |
| **`session_summarizer`** (K5) | `session_consolidator.py` — resumo da sessão | Pequeno/rápido; comprime logs locais |
| **`daily_writer`** (K5) | `daily_writer.py` — síntese do dia | Pequeno ou médio; agrega sessões do dia |
| **`weekly_synthesizer`** (K5) | `weekly_synthesizer.py` — síntese semanal | **Médio/forte**; cruza vários dias, detecta padrões |
| **`monthly_synthesizer`** (K5) | `monthly_synthesizer.py` — síntese mensal | **Forte**; produz metas, drift, riscos |
| **`yearly_synthesizer`** (K5) | `yearly_synthesizer.py` — síntese anual | **Forte/batch offline**; memória histórica, princípios |
| `alias_miner` | Mineração de aliases (slugs) | Barato |
| `topic_router` | Roteamento de fatos para o lóbulo temporal | Barato |
| `sector_classifier` | Setor cross-projeto (Diencéfalo) | Barato |
| `drift_detector` | Detecção de drift (>90d → arquivo frio) | Barato |
| `decision_promoter` | Promoção de decisões para o Córtex Frontal | Raciocínio curto |
| `project_synthesizer` | Síntese de projeto | Médio/forte |
| `pattern_distiller` | Distilação de padrões para `cerebelo/padroes/` | Raciocínio médio |
| `conflict_detector` | Detecção de conflitos na Ínsula | Barato |
| `graphiti` | Extração causal Graphiti/FalkorDB | Barato |
| `lightrag` | Extração LightRAG (entidades + relações) | `qwen2.5:3b` local (ver §4) |
| **`reranker`** (opcional, §31.1) | Rerank lexical local via `HIVE_RETRIEVAL_RERANKER=1`; cross-encoder local opt-in via `HIVE_RERANKER_PROVIDER/MODEL` + extra `reranker` | Pequeno local; off por padrão em `local-min` |

**Regra de cadência** (K5): sessão e diário podem usar modelo pequeno (compressão local); semanal usa modelo médio/forte; mensal e anual **não** devem ser rebaixados automaticamente sem aviso. Fail-closed: papel sem modelo próprio nem herança do `dreamer` registra falha auditável e não inventa síntese.

O script `setup-brain.py` / `setup-brain.sh` oferece UI interativa que pergunta **qual papel configurar**, exibe o valor atual (ou "herda do Dreamer"), e oferece o fluxo opcional de fallback (Enter pula). Também:
- lista modelos disponíveis por provider (via API em tempo real)
- testa conectividade antes de salvar
- detecta e exibe saldo disponível (DeepSeek, OpenRouter)
- **recomenda explicitamente o modelo por cadência** quando o usuário configura `session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer` ou `yearly_synthesizer`

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
| `antigravity` | Token nativo do `agy` em `~/.gemini/antigravity-cli/antigravity-oauth-token` | CLI `agy` | `gemini-3.5-flash`, `gemini-3.1-pro`, `claude-sonnet-4-6`, `gpt-oss-120b-maas` |
| `gemini-cli` | OAuth do Gemini CLI / Google VS Code extension | Code Assist `cloudcode-pa` | `gemini-2.5-flash`, `gemini-3.1-flash-lite` |
| `openai` | Bearer token | api.openai.com | `gpt-4o`, `gpt-4.1-mini` |
| `anthropic` | Bearer token | api.anthropic.com | `claude-fable-5`, `claude-haiku-4-5` |
| `deepseek` | Bearer token | api.deepseek.com | `deepseek-v3`, `deepseek-r1` |
| `huggingface` | Bearer token | api-inference.huggingface.co | `meta-llama/Llama-3-8b-instruct` |
| `qwen` | Bearer token | dashscope.aliyuncs.com | `qwen-turbo`, `qwen-plus` |
| `nvidia` | Bearer token | integrate.api.nvidia.com | `meta/llama-3.3-70b-instruct` |
| `openrouter` | Bearer token | openrouter.ai/api/v1 | `google/gemini-flash-1.5` |
| `lmstudio` | Sem auth (local) | localhost:1234/v1 | modelo carregado no LM Studio |
| `ollama` | Sem auth (local) | localhost:11434/v1 | `qwen2.5-coder:3b`, `llama3.2` |

`antigravity` e `gemini-cli` não usam o provider legado `google`. O caminho
operacional preferido para Antigravity é o token nativo do `agy`; o OAuth do
Gemini CLI continua suportado apenas para o provider `gemini-cli`/Code Assist
enquanto esse endpoint responder para a conta.

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

### 3.2 Embeddings (sqlite-vec, 1024 dimensões — Ollama snowflake-arctic-embed2)

| Modelo | Dimensões | Uso | Onde |
|--------|-----------|-----|------|
| `snowflake-arctic-embed2:latest` | 1024 | Busca semântica KNN no UMC | sqlite-vec HNSW (env `HNSW_DIM=1024`) |
| `snowflake-arctic-embed2:latest` | 1024 | Busca semântica de observações | sqlite-vec HNSW |
| `snowflake-arctic-embed2:latest` | 1024 | Embeddings de memória para LightRAG | `core/lightrag_index.py` (P4) |

O modelo é carregado via **Ollama local** (`OLLAMA_EMBED_MODEL=snowflake-arctic-embed2:latest`), exposto por `OllamaEmbedder` em `core/database.py:get_embedder()`. Não requer API key. Os vetores são persistidos na tabela virtual `search_vec` (vec0, 1024d) dentro do `hive_mind.db`. A migração do antigo 384d para 1024d aconteceu na P0; a troca de `bge-m3` para `snowflake-arctic-embed2` mantém a dimensão 1024d e exige apenas re-embedding/rebuild dos índices.

O módulo `core/hnsw_index.py` mantém um índice HNSW incremental (via `hnswlib`) sobre os mesmos vetores 1024d. O índice é atualizado a cada ingestão sem reconstrução completa.

**Por que snowflake-arctic-embed2 (1024d)?**
- Mantém a dimensão 1024d já usada pelo sqlite-vec, HNSW, LightRAG e Graphiti.
- Nos testes locais de 2026-06-27, teve 0 NaNs nos triggers problemáticos.
- Teve melhor separação PT↔EN vs. conteúdo não relacionado que `bge-m3` e `qwen3-embedding:0.6b`.
- Ollama local elimina dependência de API cloud para embeddings.

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
       │    ├── vdb_chunks.json              — embeddings de chunks (snowflake-arctic-embed2)
       │    ├── vdb_entities.json            — embeddings de entidades
       │    └── vdb_relationships.json       — embeddings de relações
       ▼
  sinapse_rag_query(question, mode="hybrid")
       │
       ▼
  MCP: retorna entidades + relações + chunks relevantes
```

**Modelo LLM do LightRAG (local por design):**
| Modelo | Provider | Justificativa |
|--------|----------|---------------|
| `qwen2.5:3b` | Ollama local | ~1.9 GB · multilíngue PT/EN · extrai entidades/relações de prosa melhor que `granite3-dense:2b` nos testes reais · cabe junto do embedder 1024d em máquina local de dev |

- Sem fallback remoto: se o modelo Ollama local falhar, o `index_memory` retorna `False` e o Dream Cycle segue.
- Com UI de troca no `setup-brain.sh`: menu `Extração local (Graphiti/LightRAG)` grava `HIVE_LIGHTRAG_MODEL`.
- `.env` (`HIVE_LIGHTRAG_MODEL`) sobrescreve o default para dev/producao local; `qwen2.5:7b` pode ser usado em máquinas com mais VRAM.
- `install.sh` baixa `qwen2.5:3b` como modelo local pequeno suficiente para Graphiti/LightRAG.

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

**Validação:** os testes reais atuais usam `qwen2.5:3b` por padrão em `core/lightrag_index.py`, com schema estruturado (`name`, `type`, `description`, `source`, `target`, `keywords`) para evitar entidades vazias e relações sem descrição.

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
| OpenAI Embeddings (text-embedding-3) | Dependência de API; snowflake-arctic-embed2 local via Ollama é suficiente |
| ChromaDB + all-MiniLM-L6-v2 | Substituído por sqlite-vec + snowflake-arctic-embed2 (1024d) embutidos no UMC (elimina processo separado) |
| all-MiniLM-L6-v2 (384d) | Substituído por embedding local 1024d no Ollama — multilingual e melhor recall |

---

## 6. Matriz de Capacidades por Cenário

| Cenário | Graphify (código) | LightRAG (texto) | Embeddings | Dream Cycle | Recall |
|---------|-------------------|------------------|-----------|-----------|--------|
| Cloud (API keys) | Provider configurado | Qwen 2.5 3B (local) | snowflake-arctic-embed2 (local) | Provider configurado | Spreading Activation |
| Local (Ollama) | Qwen 2.5 Coder 3B | Qwen 2.5 3B (local) | snowflake-arctic-embed2 (local) | Ollama configurado | Spreading Activation |
| Offline (sem Ollama) | tree-sitter + regex | Indisponível (best-effort) | Indisponível | Indisponível | Spreading Activation |
| Mínimo (sem Python) | Indisponível | Indisponível | Indisponível | Indisponível | Indisponível |

O sistema degrada graciosamente: mesmo no cenário mínimo, o vault Obsidian permanece legível e as buscas FTS5 continuam funcionando. LightRAG é o componente que mais cedo falha em ambientes mínimos — por isso o `index_memory` é best-effort (try/except) e a síntese dialética nunca é abortada por falha do grafo.

---

## 7. VectorBackend e Identidade de Coleção (K1/K10)

A partir da frente de Conhecimento Born-Large, o `VectorBackend` (§24 de [`01-architecture.md`](01-architecture.md#24-vectorbackend-contrato-coleções-canônicas-e-escala)) opera sobre **sete coleções canônicas** com identidade `(name, embedding_model, dim)`. O modelo/dimensão do embedding são parte do contrato — uma coleção carrega `snowflake-arctic-embed2:latest` em **1024d** salvo override explícito por env.

### 7.1 Contrato de migração de embedding (K10)

Trocar o modelo de embedding em escala não é script one-shot. Espaço vetorial é versionado:

```text
coleção carrega (embedding_model, dim) na identidade
upsert de modelo divergente: rejeitado ou vai pra coleção nova (nunca mistura)
migração: reembed online por workspace, dual-write (modelo antigo+novo) até cutover
métrica: vectors_model_mismatch (§28 de 01-architecture.md) = 0 dentro de uma coleção
```

Variáveis de ambiente relevantes:

| Variável | Função | Default |
|---|---|---|
| `HNSW_DIM` | Dimensão do HNSW (sqlite-vec) | `1024` |
| `OLLAMA_EMBED_MODEL` | Modelo Ollama para embeddings | `snowflake-arctic-embed2:latest` |
| `HIVE_RETRIEVAL_RERANKER` | Ativa rerank lexical determinístico no `RetrievalRouter` via adapter LlamaIndex (§31.1) | off (sem rerank) |
| `HIVE_RERANKER_PROVIDER` / `HIVE_RERANKER_MODEL` | Ativa cross-encoder local forte quando a extra `reranker` estiver instalada (`uv sync --extra reranker`) (§31.1) | off |
| `HIVE_PROMOTION_BUDGET_*` | Teto de custo de promoção por workspace (§30.5) | sem teto |

**Plano de migração típico:**

1. Cria nova coleção com `(name, novo_modelo, nova_dim)`.
2. Dual-write: novos vetores vão para coleção antiga e nova durante o cutover.
3. Backfill de embeddings antigos em batch (offline) para a coleção nova.
4. Cutover: `sinapse_query` e `RetrievalRouter` passam a consultar a coleção nova.
5. Coleção antiga entra em `forget` (motivo `superseded`, §31.2) — tombstone, sem delete físico silencioso.

---

## 8. Aceite de Fase (K0–K10) e Critério Real-Sem-Mock

A frente de Conhecimento Born-Large usa `tests/real/` (`tests/real/service_registry.py` + hook em `tests/real/conftest.py`) e **não conta mock como fechamento**. O contrato do marker `requires_service`:

```text
se o serviço real exigido estiver online: roda e falha se o comportamento falhar
se o serviço real estiver offline: skip explícito com motivo e serviço nomeado
se o teste não depende de serviço externo: roda sempre
```

Serviços conhecidos hoje: `ollama`, `milvus`, `falkordb`, `claude_mem`, `ragflow`. Cada novo backend real precisa registrar sua fixture ou service registry antes de virar gate de fase.

A suíte `./tests/run_all.sh` cobre Smoke → Unit → Integration → E2E. Em 2026-07-01 o repo tinha **706 funções `test_` em 123 arquivos com testes**; a suíte real K9 (`tests/run_real_knowledge.sh`) é separada e, no perfil `local-full` validado, executa Milvus, RAGFlow, FalkorDB, claude-mem e Ollama reais com 59/59 passed e 0 skipped.
