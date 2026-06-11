# 02 — Modelos de IA e Provedores

> **Hive-Mind v2.0.0** — Modelos, embeddings, provedores do Hive-Dreamer e cadeia de fallback.

---

## 1. Visão Geral

O Hive-Mind **não treina modelos próprios**. Usa modelos de terceiros em dois contextos distintos:

1. **Graphify** — indexação estrutural do vault (extração de entidades e relações)
2. **Hive-Dreamer** — consolidação semântica offline (Dream Cycle, fases 7-10)

Em ambos os casos, a escolha do modelo é **configurável pelo usuário** via variáveis de ambiente e via o script `setup-dreamer.sh`. Nenhum modelo é hardcoded.

---

## 2. Hive-Dreamer — 10 Provedores Suportados

O Dream Cycle usa LLM para: Distiller (extração de fatos), Validator (verificação de qualidade), Router (classificação para Atlas), e Síntese Dialética (resolução de conflitos P2P).

### 2.1 Configuração

```bash
# No .env
HIVE_DREAMER_PROVIDER=google
HIVE_DREAMER_MODEL=gemini-2.0-flash
```

O script `setup-dreamer.py` / `setup-dreamer.sh` oferece UI interativa para:
- listar modelos disponíveis por provider (via API em tempo real)
- testar conectividade antes de salvar
- detectar e exibir saldo disponível (DeepSeek, OpenRouter)

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

**Cadeia de fallback:**

```
GOOGLE_API_KEY presente?
    Sim → Gemini 2.5 Flash (cloud, NER de alta qualidade)
     │
    Não ↓
Ollama rodando em :11434?
    Sim → Qwen 2.5 Coder 3B (local, gratuito, CPU-ok)
     │
    Não ↓
Fallback determinístico → tree-sitter + regex
    (extrai funções, classes, imports, WikiLinks, frontmatter YAML)
    (sempre funciona, sem dependência externa)
```

### 3.2 Embeddings (sqlite-vec, 384 dimensões)

| Modelo | Dimensões | Uso | Onde |
|--------|-----------|-----|------|
| `all-MiniLM-L6-v2` | 384 | Busca semântica KNN no UMC | sqlite-vec HNSW |
| `all-MiniLM-L6-v2` | 384 | Busca semântica de observações | sqlite-vec HNSW |

O modelo é carregado via `fastembed` (ou `sentence-transformers`), roda localmente (~80MB), e não requer API key. Os vetores são persistidos na tabela virtual `search_vec` (vec0, 384d) dentro do `hive_mind.db`.

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
