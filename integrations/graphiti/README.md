# Graphiti (Vendor) — Lóbulo Temporal do Cérebro

`graphiti-core` ([getzep/graphiti](https://github.com/getzep/graphiti)) +
FalkorDB (in-memory graph DB, backend open-source) + Ollama local
(LLM + embeddings).

Este é um **órgão do lóbulo temporal** do cérebro do Hive-Mind (ver
`docs/01-architecture.md` seção 2 e `AGENTS.md` seção 2). Complementa
o `claude-mem` (tálamo sensorial do mesmo lobo): enquanto o claude-mem
captura eventos brutos, o Graphiti extrai relações causais com janelas
de validade temporal (`valid_from`, `valid_until`).

## Onde entra na anatomia

- **Lobo:** Córtex Temporal (memória de longo prazo)
- **Sub-região do lobo:** grafo causal (`cortex/temporal/_global/grafo.jsonl`
  como fallback quando FalkorDB offline; FalkorDB em si é storage
  externo recomendado, mas o cérebro degrada graciosamente sem ele)
- **Cérebro:** Componente que dá ao cérebro a capacidade de responder
  "o que era verdade sobre X em tal data" — sem isso, o lóbulo temporal
  só tem sinapses estáticas (sem timestamping de validade).

## Configuração (env vars)

| Var | Default | Função |
|---|---|---|
| `FALKORDB_HOST` | `localhost` | Host do FalkorDB |
| `FALKORDB_PORT` | `6379` | Porta |
| `FALKORDB_USER` | (vazio) | Auth user |
| `FALKORDB_PASSWORD` | (vazio) | Auth password |
| `FALKORDB_DB` | `sinapse` | Nome do database |
| `GRAPHITI_LLM_BASE` | `http://localhost:11434/v1` | Ollama base URL |
| `GRAPHITI_LLM_MODEL` | `qwen2.5-coder:3b` | LLM para extração de entidades |
| `GRAPHITI_EMBED_MODEL` | `snowflake-arctic-embed2:latest` | Embeddings (consistente com resto do cérebro) |
| `HIVE_GRAPHITI_RETRIES` | `3` | Tentativas com backoff 1s, 2s, 4s |
| `HIVE_GRAPHITI_CB_FAILS` | `3` | Falhas consecutivas que abrem o circuit |
| `HIVE_GRAPHITI_CB_COOLDOWN` | `30` | Segundos de pausa do circuit |
| `HIVE_TEMPORAL_GRAFO` | (vazio) | Override do path do fallback JSON-lines |

## Robustez (4 camadas)

1. **Smoke test** (`assert_health()`) — FalkorDB + modelos Ollama + write/read.
2. **Circuit breaker** — 3 falhas consecutivas abrem cooldown de 30s.
3. **Persistência** — JSON-lines em `cortex/temporal/_global/grafo.jsonl` quando FalkorDB offline.
4. **Retry com backoff** — 1s, 2s, 4s por operação.

## Instalação

```bash
# Deps Python (já em pyproject.toml):
#   falkordb>=1.1.2,<2.0.0
#   graphiti-core>=0.29.0

# Modelos Ollama:
ollama pull qwen2.5-coder:3b
ollama pull snowflake-arctic-embed2:latest

# FalkorDB (Docker):
docker run -d --name sinapse-falkordb -p 6379:6379 \
  -v sinapse-falkordb-data:/data \
  falkordb/falkordb:latest
```

## Uso

```python
from integrations.graphiti import push_neuron, search_graph, assert_health

# Smoke test
health = assert_health()
if not health["errors"]:
    print("Graphiti operacional")

# Indexar neurônio
push_neuron("neuron-abc123", "Fato consolidado pelo Dream Cycle", source="dream")

# Buscar com janelas de validade
results = search_graph("o que mudou em X em 2026-06", num_results=10)
for r in results:
    print(f"{r['fact']} (valid: {r['valid_at']}, invalid: {r['invalid_at']})")
```

## Por que é vendor e não pip install

Porque o `graphiti-core` precisa de adaptação local:
- Modelos Ollama configurados (não OpenAI default).
- Cross-encoder aponta para Ollama (não OpenAI).
- `small_model = llm_model` para evitar fallback para `gpt-4.1-nano`.
- Persistência via fallback JSON-lines no lóbulo temporal.
- Circuit breaker + retry com backoff.

Essas adaptações não são genéricas — são específicas do cérebro do
Hive-Mind. Por isso o vendor fica em `integrations/graphiti/` em vez
de `pip install` direto.
