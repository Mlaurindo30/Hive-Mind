# 02 — Modelos de IA

> **Sinapse Agent v1.1.0** — Modelos, embeddings e rationale de seleção.

---

## 1. Visão Geral

O Sinapse Agent **não treina modelos próprios**. Ele utiliza modelos de terceiros como parte do pipeline de indexação e busca semântica. A escolha de modelos segue uma **cadeia de fallback** para garantir funcionamento mesmo offline ou sem API keys.

---

## 2. Modelos por Componente

### 2.1 Graphify — Indexação do Knowledge Graph

| Modelo | Provider | Uso | Modo |
|--------|----------|-----|------|
| **Gemini 2.5 Flash** | Google AI | Extração semântica de entidades e relações do vault | `--backend gemini` |
| **Qwen 2.5 Coder 3B** | Ollama (local) | Fallback local para extração semântica | `--backend ollama` |
| **tree-sitter + regex** | Determinístico | Fallback AST-only — parsing sintático sem LLM | `--backend ast` |

**Cadeia de fallback do Graphify:**
```
Gemini API key presente? → usa Gemini (cloud, alta qualidade)
    ↓ não
Ollama rodando localmente? → usa Qwen 2.5 Coder (local, gratuito)
    ↓ não
    → tree-sitter + regex (determinístico, sem LLM, sempre funciona)
```

**Rationale:**
- **Gemini 2.5 Flash**: Melhor relação custo/qualidade para extração de entidades. Suporta português nativamente (idioma do vault). API gratuita até 1500 req/dia.
- **Qwen 2.5 Coder 3B**: Modelo pequeno (3B parâmetros) que roda em CPU. Suficiente para tarefas de NER (Named Entity Recognition) em código e documentação.
- **tree-sitter + regex**: Fallback determinístico que não depende de nenhum modelo. Extrai estrutura sintática de arquivos (funções, classes, imports) e faz regex matching para documentos Markdown.

### 2.2 Graphify — Embeddings para Leiden Clustering

| Modelo | Provider | Uso |
|--------|----------|-----|
| **BGE-M3** | Ollama (local) | Embeddings multilíngue de alta qualidade (1024 dimensões) |
| **Nomic Embed Text** | Ollama (local) | Embeddings leve (768 dimensões), rápido |

**Rationale:**
- **BGE-M3**: Suporta 100+ idiomas incluindo português. Dense + sparse embeddings para melhor recuperação.
- **Nomic Embed Text**: Alternativa mais leve quando recursos são limitados.

Os embeddings são usados pelo Leiden clustering para agrupar nodes semanticamente relacionados em comunidades.

### 2.3 claude-mem — Busca Semântica Temporal

| Modelo | Provider | Uso |
|--------|----------|-----|
| **Chroma + all-MiniLM-L6-v2** | Local (via ChromaDB) | Embeddings para busca semântica de observações |
| **FTS5** | SQLite (determinístico) | Full-text search textual (fallback sem embeddings) |

**Rationale:**
- **all-MiniLM-L6-v2**: Modelo sentence-transformer pequeno (384 dimensões, ~80MB) que roda localmente via ChromaDB. Suficiente para similaridade semântica de frases curtas.
- **FTS5**: Fallback determinístico que não requer embeddings. Busca textual com ranking TF-IDF.

### 2.4 NeuralMemory — Spreading Activation

| Algoritmo | Tipo | Uso |
|-----------|------|-----|
| **Spreading Activation** | Algoritmo de grafo | Propagação de ativação em rede de 24 tipos de relações |
| **TF-IDF + Cosine Similarity** | Estatístico | Matching inicial de conceitos antes da propagação |

**Rationale:**
NeuralMemory **não usa LLMs** para recall. O algoritmo de spreading activation é puramente matemático: a partir de um conceito inicial, a ativação se propaga pelas arestas do grafo associativo, ativando conceitos relacionados. Os pesos das arestas (24 tipos de relações como `causes`, `prevents`, `requires`, `is_a`) foram definidos manualmente com base em psicologia cognitiva.

---

## 3. Modelos NÃO Utilizados

| Modelo | Por que NÃO |
|--------|------------|
| GPT-4 / Claude Opus | Overkill para extração de entidades. Custo proibitivo para indexação diária. |
| BERT multilíngue | Mais pesado que Qwen 2.5 Coder para a mesma qualidade em NER. |
| Fine-tuned models próprios | Complexidade de manutenção. Preferência por modelos off-the-shelf. |
| OpenAI embeddings (text-embedding-3) | Dependência de API. BGE-M3 local é comparável em qualidade. |

---

## 4. Por que a Abordagem Multi-Modelo com Fallback?

### 4.1 Resiliência Offline

O sistema foi projetado para funcionar em um **Raspberry Pi ou VPS de $5** sem acesso à internet:

```
Sem API keys → Ollama local (Qwen + BGE-M3)
Sem Ollama → tree-sitter + regex + FTS5
Sem nada → leitura direta de arquivos Markdown
```

### 4.2 Custo Zero para Operação Básica

Com Ollama rodando localmente, todo o pipeline de indexação e busca funciona sem custo de API. Apenas o uso do Gemini (opcional) gera custo — e mesmo assim, dentro da cota gratuita.

### 4.3 Independência de Provider

Nenhum componente tem hard-dependency em um provider específico. Se a API do Google mudar, o fallback para Ollama mantém o sistema funcionando. Se a Ollama quebrar, o fallback determinístico (tree-sitter + FTS5) garante operação mínima.

---

## 5. Matriz de Decisão

| Cenário | Extração (Graphify) | Embeddings (Graphify) | Busca (claude-mem) | Recall (NeuralMemory) |
|---------|--------------------|-----------------------|--------------------|-----------------------|
| Cloud (com API keys) | Gemini 2.5 Flash | BGE-M3 (local) | Chroma + MiniLM | Spreading Activation |
| Local (com Ollama) | Qwen 2.5 Coder 3B | BGE-M3 (local) | Chroma + MiniLM | Spreading Activation |
| Offline (sem Ollama) | tree-sitter + regex | — (skip) | FTS5 | Spreading Activation |
| Mínimo (sem Python) | — | — | — | — |

---

## 6. Configuração

```yaml
# sinapse.yaml — seção graphify
graphify:
  package: graphifyy
  extras: [all]         # inclui ollama, mcp, neo4j
```

```bash
# Modelos recomendados para Ollama
ollama pull qwen2.5-coder:3b     # Extração semântica local
ollama pull bge-m3                # Embeddings multilíngue
ollama pull nomic-embed-text      # Embeddings leve (fallback)

# API Gemini (opcional)
# Configurar GOOGLE_API_KEY no .env
```
