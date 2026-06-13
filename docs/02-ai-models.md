# 02 — Modelos de IA e Provedores

> **Hive-Mind v3.0.0** — Modelos, embeddings, provedores do Hive-Dreamer e cadeia de fallback.

---

## 1. Visão Geral

O Hive-Mind **não treina modelos próprios**. Usa modelos de terceiros em dois contextos distintos:

1. **Graphify** — indexação estrutural do vault (extração de entidades e relações)
2. **Hive-Dreamer** — consolidação semântica offline (Dream Cycle, fases 7-10)

Em ambos os casos, a escolha do modelo é **configurável pelo usuário** via variáveis de ambiente e via o script `setup-dreamer.sh`. Nenhum modelo é hardcoded.

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

O script `setup-dreamer.py` / `setup-dreamer.sh` oferece UI interativa que pergunta **qual papel configurar**, exibe o valor atual (ou "herda do Dreamer"), e oferece o fluxo opcional de fallback (Enter pula). Também:
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

### 3.2 Embeddings (sqlite-vec, 384 dimensões)

| Modelo | Dimensões | Uso | Onde |
|--------|-----------|-----|------|
| `all-MiniLM-L6-v2` | 384 | Busca semântica KNN no UMC | sqlite-vec HNSW |
| `all-MiniLM-L6-v2` | 384 | Busca semântica de observações | sqlite-vec HNSW |

O modelo é carregado via `fastembed` (ou `sentence-transformers`), roda localmente (~80MB), e não requer API key. Os vetores são persistidos na tabela virtual `search_vec` (vec0, 384d) dentro do `hive_mind.db`.

A partir da HM-11, o módulo `core/hnsw_index.py` mantém um índice HNSW incremental (via `hnswlib`) sobre os mesmos vetores 384d gerados pelo `fastembed`. O índice é atualizado a cada ingestão sem reconstrução completa, reduzindo a latência de busca KNN para ~1ms em coleções grandes.

**Por que all-MiniLM-L6-v2 em vez de BGE-M3?**
- BGE-M3 (1024d) era usado na v1.x com ChromaDB separado
- all-MiniLM-L6-v2 (384d) é suficiente para similaridade semântica de frases curtas
- 384d ocupa 4x menos espaço em disco que 1024d
- sqlite-vec HNSW tem performance excelente em 384d (busca em ~5ms para 10k vetores)

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
| OpenAI Embeddings (text-embedding-3) | Dependência de API; all-MiniLM-L6-v2 local é suficiente |
| ChromaDB + all-MiniLM-L6-v2 | Substituído por sqlite-vec embutido no UMC (elimina processo separado) |

---

## 6. Matriz de Capacidades por Cenário

| Cenário | Graphify (extração) | Embeddings | Dream Cycle | Recall |
|---------|--------------------|-----------|-----------|---------| 
| Cloud (API keys) | Gemini 2.5 Flash | all-MiniLM (local) | Provider configurado | Spreading Activation |
| Local (Ollama) | Qwen 2.5 Coder 3B | all-MiniLM (local) | Ollama configurado | Spreading Activation |
| Offline (sem Ollama) | tree-sitter + regex | all-MiniLM (local) | Indisponível | Spreading Activation |
| Mínimo (sem Python) | Indisponível | Indisponível | Indisponível | Indisponível |

O sistema degrada graciosamente: mesmo no cenário mínimo, o vault Obsidian permanece legível e as buscas FTS5 continuam funcionando.
