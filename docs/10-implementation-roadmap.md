# Roadmap de Implementação — Hive-Mind Integrações
**Data:** 2026-06-25 | **Base anatômica:** `docs/01-architecture.md` §2 e `AGENTS.md` §2 | **Base de pesquisa:** `docs/09-integration-study.md`

> Documento de engenharia orientado pela **anatomia do cérebro**. Cada fase adiciona
> ou reforça um órgão. Clones de projetos externos vivem em `integrations/<nome>/`;
> deps Python vão no `pyproject.toml`; deps de sistema (binários, Docker, Ollama)
> vão no `install.sh`. Nomes em `cerebro/` (projetos, tópicos, setores) são fictícios —
> projetos reais são instalados pelo usuário em `cerebro/cortex/temporal/<projeto>/`.
>
> **3ª passada de validação (2026-06-25) + refinamento posterior (sessão #S2864):** cada afirmação abaixo foi verificada
> contra código real (ver §0.6 "Metodologia de validação"). A 2ª passada listava 13
> fases pendentes. Reduzimos para **6** (P7..P13; **gap em P12** — aposentado na §3.2
> por já existir como DuckDB) por dois motivos:
> - 7 projetos do `09` já estão implementados dentro de `integrations/neural-memory/`
>   (Mem0, OpenMemory, Cognee, MemoryOS, MemOS, A-MEM, HippoRAG 2) — não são fases,
>   são capacidades existentes (rastreabilidade em §3.1).
> - P6 sqlite-lembed/GGUF foi **descartado** nesta 4ª passada porque Ollama `bge-m3`
>   (P0) já é 100% local e sqlite-lembed exigiria modelo GGUF/llama.cpp avulso,
>   violando a política §0.3.1 — ver §5.

---

## Índice

- [§0 Princípios e anatomia](#0-princípios-e-anatomia)
- [§1 Estado atual do cérebro](#1-estado-atual-do-cérebro)
- [§2 Fases concluídas (P0..P5)](#2-fases-concluídas-p0p5)
- [§3 Já integrado no `integrations/neural-memory/` (rastreabilidade)](#3-já-integrado-no-integrationsneural-memory-rastreabilidade)
- [§4 Fases pendentes (P7..P13)](#4-fases-pendentes-p7p13)
- [§5 Rejeitados com razão](#5-rejeitados-com-razão)
- [§6 Critério geral de "pronto"](#6-critério-geral-de-pronto)
- [§7 Sprints](#7-sprints)
- [§8 Mapa de arquivos por fase](#8-mapa-de-arquivos-por-fase)
- [§9 Gaps conhecidos](#9-gaps-conhecidos-2026-06-25)

---

## 0. Princípios e anatomia

### 0.1 Anatomia canônica (4 lobos irmãos, não hierárquicos)

- **Córtex** (cognição superior, 5 lóbulos): temporal, frontal, parietal, occipital, ínsula
- **Cerebelo** (ritmo): sessões, diário, semanal, padrões
- **Diencéfalo** (relay cross-projeto): setores + roteamento
- **Tronco** (infra vital): modelos, painéis, infra, meta

Ver `docs/01-architecture.md` §2 e `AGENTS.md` §2. **Nenhuma fase pode violar a anatomia** — projetos vão em lobos apropriados ou em `integrations/` (vendors externos, que são órgãos mas não são o cérebro central).

### 0.2 Vendors externos (clones reais + wrappers locais)

```
integrations/
├── graphify/             # córtex occipital — clustering estrutural (Leiden)
├── graphiti/             # lóbulo temporal — causalidade com validade (P2)
├── neural-memory/        # córtex (associação) + diencéfalo (evolução) — PROJETO COMPLETO (ver §3)
├── rtk/                  # tronco — otimização de shell
├── claude-mem-plugins/   # lóbulo temporal — eventos brutos
├── patches/              # patches aplicados sobre os clones (graphify, neural-memory) durante o install.sh
├── lancedb/              # P11 — wrapper local (pip `lancedb`, NÃO é clone) — storage multimodal
└── omniparser/           # P13 — clone real de microsoft/OmniParser — UI parsing
```

> **Taxonomia:** `graphify`, `neural-memory`, `rtk` e `omniparser` (P13) são **clones git reais** (build a partir do source pelo `install.sh`). `graphiti` e `lancedb` (P11) são **wrappers locais** sobre um pacote pip (`graphiti-core` / `lancedb`) — só hospedam um `client.py`. `claude-mem-plugins` é um shim. `patches/` aplica ajustes sobre os clones.

### 0.3 Dependências

- **Python:** `pyproject.toml` (fonte de verdade única, `uv sync`)
- **Sistema (binários, Docker, Ollama):** `install.sh`
- **Env vars:** default sensato + override via `.env`
- **Nada hardcoded em `core/`:** sempre env vars ou `pyproject.toml`

### 0.3.1 Política de modelos (Ollama + visão dedicada)

- **Texto / embeddings / LLM → Ollama, sempre.** `bge-m3` (1024d) p/ embeddings; `granite3-dense:2b` e afins p/ LLM. **Nenhum modelo GGUF/llama.cpp avulso, nenhum peso PyTorch para texto.** (Por isso não há fase sqlite-lembed/GGUF — ver §5.)
- **Visão → modelos dedicados, CPU-friendly, por _tier_ de máquina.** Os modelos de visão do Ollama são pesados e **não cobrem detecção estruturada de UI**; o alvo vai da máquina robusta à mais simples. Logo a visão usa modelos dedicados (CLIP p/ embedding visual em P11; OmniParser/YOLO p/ parsing de UI em P13), **sempre opcionais e graduáveis** via env `HIVE_VISION_TIER`: `none` (máquina simples — sem visão dedicada) → `lite` (modelos CPU pequenos) → `full` (pesos maiores / GPU).
- **Regra:** nenhuma fase pode forçar um runtime de modelo que quebre máquinas simples. Visão dedicada é **opt-in**.

### 0.4 Robustez por padrão (4 camadas, do P2)

1. **Smoke test** (`assert_health()`)
2. **Circuit breaker** (3 falhas → cooldown)
3. **Persistência degradada** (fallback local se backend externo cai)
4. **Retry com backoff** (1s, 2s, 4s)

### 0.5 Mapa de vendors (estado atual)

| Lobo | Vendor | `integrations/` | `pyproject.toml` | `install.sh` | Status |
|---|---|---|---|---|---|
| Córtex occipital | Graphify | `integrations/graphify/` | `graphifyy[watch]` | clone + install.sh (não existe `setup_brain.sh`) | ✅ |
| **Lóbulo temporal** | **Graphiti (FalkorDB)** | `integrations/graphiti/` (wrapper, não clone) | `graphiti-core`, `falkordb` | pip + Docker FalkorDB | ✅ P2 |
| **Lóbulo temporal** | claude-mem | `integrations/claude-mem-plugins/` | (indep, npm) | (indep) | ✅ |
| Córtex + Diencéfalo | Neural Memory | `integrations/neural-memory/` | `neural-memory[pro]` | clone + install.sh (não existe `setup_brain.sh`) | ✅ (ver §3) |
| **Córtex** (RAG) | LightRAG | `core/lightrag_index.py` (não vendor) | `lightrag-hku` | `ollama pull granite3-dense:2b` | ✅ P3 |
| Tronco | RTK | `integrations/rtk/` | (indep, cargo) | cargo install | ✅ |
| Córtex | SQLite-vec | (nativo) | `sqlite-vec` | (extensão nativa) | ✅ |
| Córtex (visual) | Screenpipe | (npm) | (indep, npm) | npm install -g @screenpipe/cli | ✅ P1 |
| Córtex | Fastembed | (nativo) | `fastembed` | (fallback P0) | ✅ |
| **Cerebelo (analytics)** | **DuckDB** | `scripts/analytics/hive_analytics.py` | `duckdb>=0.10` | (nativo, 4 queries) | ✅ DONE (ver §3) |

### 0.6 Metodologia de validação (3ª passada)

Cada afirmação "cérebro já tem X" foi verificada com:

```bash
grep -rln "X" core/ scripts/ integrations/
ls -la <arquivo>
.venv/bin/python -c "import <módulo>; print(hasattr(...))"
```

Resultados:
- 7 projetos do `09` descobertos como **já implementados** em `integrations/neural-memory/` (ver §3)
- DuckDB analytics descoberto em `scripts/analytics/hive_analytics.py` (4 queries)
- `core/telemetry.py` é OTEL completo e funcional (não draft como afirmei antes), MAS não está em `pyproject.toml` e não é importado em nenhum script — Langfuse é gap real de **instrumentação**, não de código
- A-MEM e Graphiti são **complementares** (Graphiti extrai edges novas; A-MEM evolui links existentes) — e A-MEM já está no neural-memory

---

## 1. Estado atual do cérebro

```
core/                              ← código do cérebro central
├── database.py                    # OllamaEmbedder (bge-m3 1024d) ✅P0
│   # get_connection():93 carrega sqlite-vec (extensão)
│   # add_visual_memory():221 (visual_memories table, só texto — sem embedding CLIP)
├── indexing.py                    # index_neuron_ids() ✅P0
├── hnsw_index.py                  # HNSW_DIM=1024 ✅P0
├── umc_schema.sql                 # 9 tabelas: neurons, synapses, observations, vault,
│   #                              #   ambiguities, visual_memories, document_memories,
│   #                              #   causal_edges, goals ✅P0
├── lightrag_index.py             # LightRAG v1.5.4 wrapper (granite3-dense:2b fixo) ✅P3
├── telemetry.py                   # OTEL completo (init_telemetry, span()) — MAS NÃO INSTRUMENTADO
└── paths.py                       # constantes anatômicas (CORTEX, TEMPORAL, INTEGRATIONS_ROOT, ...)

integrations/
├── graphify/                      # córtex occipital
├── graphiti/                      # lóbulo temporal ✅P2 (commit b11d6d6)
│   ├── client.py                  # 4 camadas: smoke + circuit + retry + persist
│   ├── __init__.py                # API pública + whitebox
│   └── README.md
├── neural-memory/                 # ✅ PROJETO COMPLETO (ver §3) — cobre 7 projetos do 09
│   ├── src/neural_memory/
│   │   ├── integration/adapters/mem0_adapter.py    # Mem0 + OpenMemory
│   │   ├── mcp/{evolution,recall,cognitive}_handler.py  # Cognee + A-MEM
│   │   └── engine/
│   │       ├── ppr_activation.py                  # HippoRAG 2 (Personalized PageRank)
│   │       ├── consolidation.py, lifecycle.py     # MemoryOS (BAI-LAB)
│   │       ├── brain_evolution.py                 # A-MEM (link evolution)
│   │       └── learning_rule.py, workflow_suggest.py  # MemOS (skill reuse)
│   └── (conectado ao cérebro via _backend_neural_memory)
├── rtk/                           # tronco (otimização shell)
└── claude-mem-plugins/            # lóbulo temporal (eventos brutos)

plugins/
├── hermes/
│   └── sinapse-memory.py          # 7 backends federados via _query_vault_knowledge ✅P4
│       # _READ_BACKENDS: umc, neural_memory, sqlite_vec, claude_mem, graphify, graphiti, filesystem
└── sqlite-vec-worker/worker.py    # VEC_EMBED_DIM=1024 ✅P0

scripts/
├── dream/
│   ├── dream_cycle.py             # ETL Distiller→Validator→Router→Síntese
│   #                              # Stage 3.5: push_neuron (Graphiti) + index_memory (LightRAG)
│   ├── daily_writer.py            # nível 1 (diário) ✅
│   └── weekly_synthesizer.py      # nível 2 (semanal) ✅ — FALTA mensal/anual (P10)
├── services/
│   ├── sinapse-mcp.py             # MCP stdio (13 tools), sinapse_query orquestrador ✅P4
│   ├── sinapse-api.py             # REST API FastAPI :37702
│   └── sinapse-write.py           # CLI: decision, learning, query, health, session-end
├── capture/
│   ├── capture_core.py            # SeenStore SQLite WAL ✅
│   ├── capture_adapters.py        # ADAPTERS dict (screenpipe, ...)
│   └── parsers/                   # 11 parsers
├── analytics/
│   └── hive_analytics.py          # DuckDB OLAP (4 queries: growth, top_topics, ...) ✅ DONE
├── knowledge/
│   └── pattern_distiller.py       # extração de padrões (cerebelo/padroes)
└── setup/
    └── migrate_embed_dim.py       # 384 → 1024 one-shot ✅P0

cerebro/cerebelo/padroes/          # Patterns.md + pattern_models.py (procedural parcial) ✅
```

---

## 2. Fases concluídas (P0..P5)

### Fase P0 — Embeddings 100% Local (Ollama bge-m3) ✅ CONCLUÍDO

**Objetivo:** eliminar `fastembed + all-MiniLM-L6-v2 (384d)` e usar modelo multilingual PT+EN 1024d local.
**Status:** ✅ | **Commits:** `93db445`, `f087279` | **Data:** 2026-06-21

**Modelo:** `bge-m3:latest` (1024d, MTEB multilingual #1 2024, 91ms warm, EXCELENTE PT-BR)

**Arquivos modificados:**

| Arquivo | Linha | Mudança |
|---|---|---|
| `core/database.py` | 28-31 | `OLLAMA_EMBED_MODEL` env + `class OllamaEmbedder` via HTTP; `EMBED_BACKEND=ollama` default |
| `core/hnsw_index.py` | 25 | `HNSW_DIM` 384 → 1024 |
| `core/umc_schema.sql` | 92 | `FLOAT[384]` → `FLOAT[1024]` em `search_vec` |
| `plugins/sqlite-vec-worker/worker.py` | 54 | `VEC_EMBED_DIM` 384 → 1024 |
| `scripts/setup/migrate_embed_dim.py` | — | script one-shot (3639/3642 re-indexados em 407s) |
| `tests/unit/test_p0_embedding.py` | — | 10 testes (backend, determinismo, dim, live) |

**Bloqueio original:** `sqlite-lembed` (plano inicial) incompatível com Python 3.12+ (`OperationalError: misuse sqlite3_result_subtype()`). Solução: Ollama HTTP API. sqlite-lembed foi **descartado** (embeddings rodam no Ollama `bge-m3`; ver §5 e a política de modelos §0.3.1).

**Rollback:** `EMBED_BACKEND=fastembed` + `HNSW_DIM=384` + `OLLAMA_EMBED_MODEL=all-MiniLM-L6-v2`.

### Fase P1 — Screenpipe via REST substitui mss ✅ CONCLUÍDO

**Objetivo:** deprecar `mss + LLM Vision` e consumir Screenpipe via REST local.
**Status:** ✅ | **Commits:** `9597ef5`, `2a4cdc8` | **Data:** 2026-06-21
**Testes:** 13/13 (10 offline + 3 live, skip se Screenpipe offline)

**Arquivos:**

| Arquivo | Mudança |
|---|---|
| `scripts/capture/parsers/screenpipe.py` (NOVO) | Cliente REST: `screenpipe_alive()`, `fetch_recent_ocr()`, `fetch_recent_audio()`, `capture_screenshot()` |
| `scripts/capture/capture_adapters.py` | entrada `"screenpipe"` em ADAPTERS |
| `scripts/services/sinapse-mcp.py` | `_capture_screen()` tenta Screenpipe primeiro, fallback `visual_capture.py` |
| `scripts/setup/install_services.py` | `_install_screenpipe()` (npm) |

**Env vars:** `SCREENPIPE_BASE` (default `http://localhost:3030`), `SCREENPIPE_TIMEOUT=5`, `SCREENPIPE_API_KEY` (opcional)

### Fase P2 — Graphiti + FalkorDB (lóbulo temporal) ✅ CONCLUÍDO

**Objetivo:** janelas de validade temporal (`valid_at`/`invalid_at`) no grafo.
**Status:** ✅ | **Commits:** `5d90f51`, `41fac0c` (robustez), `b11d6d6` (move para integrations), `16e0387` (fusão no cérebro)
**Testes:** 14/14 (11 offline + 3 live)

**Evolução em 4 commits:**
1. `5d90f51` — Cria `core/graphiti_client.py` + Docker FalkorDB + hook no Dream Cycle
2. `41fac0c` — 4 camadas de robustez (smoke, circuit breaker, retry backoff, persistência JSON-lines em `cortex/temporal/_global/grafo.jsonl`)
3. `b11d6d6` — Move `core/` → `integrations/graphiti/` (anatomia: vendors em `integrations/`)
4. `16e0387` — Funda no `sinapse_query` como 7º backend (`_backend_graphiti` em `plugins/hermes/sinapse-memory.py`)

**Arquivos atuais:**

| Arquivo | Papel |
|---|---|
| `integrations/graphiti/client.py` | Wrapper Graphiti/FalkorDB/Ollama; smoke + circuit + retry + persist |
| `integrations/graphiti/__init__.py` | API pública (`push_neuron`, `search_graph`, `assert_health`, `circuit_state`) + whitebox internals |
| `integrations/graphiti/README.md` | Anatomia (lóbulo temporal), env vars, instalação |
| `plugins/hermes/sinapse-memory.py` | `_backend_graphiti` (7º backend do orquestrador) |
| `docker-compose.falkordb.yml` | Container FalkorDB porta 6379 |
| `tests/integration/test_graphiti.py` | 14 testes (movido de `tests/unit/test_p2_graphiti.py`) |
| `pyproject.toml` | `graphiti-core>=0.29.0`, `falkordb>=1.1.2,<2.0.0` |

**Env vars:** `FALKORDB_HOST/PORT/USER/PASSWORD/DB`, `GRAPHITI_LLM_BASE/MODEL`, `GRAPHITI_EMBED_MODEL`, `HIVE_GRAPHITI_RETRIES/CB_FAILS/CB_COOLDOWN`, `HIVE_TEMPORAL_GRAFO` (path do fallback)

**Robustez (4 camadas):**
1. `assert_health()` — FalkorDB + Ollama LLM + Ollama embed + write/read de prova
2. Circuit breaker (3 falhas consecutivas → cooldown 30s)
3. Persistência JSON-lines em `cerebro/cortex/temporal/_global/grafo.jsonl` quando FalkorDB offline
4. Retry com backoff 1s/2s/4s

### Fase P3 — LightRAG no Dream Cycle ✅ CONCLUÍDO

**Objetivo:** indexação automática de entidades/relações no corpus consolidado.
**Status:** ✅ | **Commits:** `56f1e98`, `fe68300`, `61c5285`, `dee365b`, integração Dream Cycle em 2026-06-24

**Decisão arquitetural (commit `dee365b`):** LightRAG LLM fixo em `granite3-dense:2b` (1.5GB, Ollama local). Razões: (1) roda em qualquer máquina, (2) validação live: extrai 4 entities + 3 rels com JSON schema válido, (3) sem fallback Gemini/cloud — `.env` permite override só em dev. Config em `core/lightrag_index.py:25-29` (comentário explicativo) e linha 29 (`_LIGHTRAG_CHAT_MODEL`).

**Arquivos:**

| Arquivo | Papel |
|---|---|
| `core/lightrag_index.py` | Wrapper LightRAG v1.5.4 (modelo local fixo) |
| `scripts/dream/dream_cycle.py` | 372-381: `index_memory()` best-effort após `push_neuron` Graphiti |
| `scripts/services/sinapse-mcp.py` | tool `sinapse_rag_query` (modos `naive|local|global|hybrid`) |
| `install.sh` | nota pós-instalação `ollama pull granite3-dense:2b` |
| `pyproject.toml` | `lightrag-hku>=1.0.0` |

### Fase P4 — sinapse_query funciona como cérebro federador (7 órgãos) ✅ CONCLUÍDO

**Objetivo:** o `sinapse_query` (entry point único do cérebro) funde os 7 órgãos via Context Fusion paralelo.
**Status:** ✅ | **Commit:** `16e0387` | **Data:** 2026-06-24
**Testes:** 14/14 (`test_sinapse_mcp.py`)

**Anatomia:** orquestrador `_query_vault_knowledge` em `plugins/hermes/sinapse-memory.py:376` itera `_READ_BACKENDS` em paralelo (circuit breaker + timeout 8s):

```
sinapse_query → _query_vault_knowledge (Context Fusion paralelo)
                 ├── _backend_umc            # lóbulo temporal (índice SQLite consolidado)
                 ├── _backend_neural_memory # córtex (associação + PPR + evolução)
                 ├── _backend_sqlite_vec     # córtex (semântico local)
                 ├── _backend_claude_mem     # tálamo sensorial (eventos)
                 ├── _backend_graphify       # lobo occipital (estrutural/Leiden)
                 ├── _backend_graphiti       # lóbulo temporal (causalidade) ✓ P2
                 └── _backend_filesystem     # lobo parietal (leitura)
```

**Bug corrigido:** antes do Passo 2, `sinapse_query` chamava `sm._backend_umc()` (apenas 1 backend) — quebrava a anatomia prometida. Agora chama `sm._query_vault_knowledge()` que funde os 7.

**Verificado end-to-end:** query de teste roda os 7 em paralelo, Graphiti respondeu em ~1.35s (live FalkorDB), tempo total ~1.4s sob `GLOBAL_QUERY_TIMEOUT=8s`.

**Tool `sinapse_temporal_graph_search`** marcada como DEPRECATED no docstring — clientes existentes não quebram, mas o canônico é `sinapse_query`.

### Fase P5 — Anatomia canônica em 3 documentos ✅ CONCLUÍDO

**Objetivo:** documento único de verdade para a anatomia do cérebro.
**Status:** ✅ | **Commits:** `ca1ff96`, `3eb4a35`, `ddf5504` | **Data:** 2026-06-23/24

**Seção de anatomia (§2) sincronizada nos 3 documentos** (a reconciliação de §2.6 / contagem de tools / contagem de testes foi feita numa passada posterior, 2026-06-25):
- `AGENTS.md` (root) — seção 2: anatomia resumida (4 lobos + 5 lóbulos do córtex)
- `README.md` — "Anatomia do Cérebro" antes de "Visão Geral"
- `docs/01-architecture.md` — seção 2: anatomia completa (constantes, mapeamento, ferramentas)

**Nomes fictícios** (projeto-A..I, topico-1..N, setor-1..5) — projetos reais instalados pelo usuário. Root do repo limpo: `CLAUDE.md` (Ruflo config), `AGENT_BOOTSTRAP.md` (órfão) removidos em `ddf5504`.

---

## 3. Já integrado no `integrations/neural-memory/` (rastreabilidade)

O `integrations/neural-memory/` é um **projeto completo** (não um wrapper) que já implementa capacidades equivalentes a 7 projetos do `09-integration-study.md`. Está conectado ao cérebro via `_backend_neural_memory` (chama binário `nmem`). Esta seção documenta quais projetos do estudo já têm equivalente funcional, para que o roadmap §4 não os liste como pendentes.

### 3.1 Mapeamento verificado (cada arquivo confirmado em disco)

| Projeto do `09` | Onde no `09` | Equivalente em `integrations/neural-memory/` | Verificado |
|---|---|---|---|
| **Mem0** | §1 | `src/neural_memory/integration/adapters/mem0_adapter.py` + `mcp/mem0_sync_handler.py` + testes `test_mem0_sync_handler.py`, `test_mem0_self_hosted.py` | ✅ |
| **OpenMemory** | §1 | `tests/unit/test_openmemory_features.py` + docs `docs/guides/memory-layer-unification.md` | ✅ |
| **Cognee** | §1 | `mcp/cognitive_handler.py` + `mcp/recall_handler.py` (roteamento via handlers) | ✅ |
| **MemoryOS (BAI-LAB)** | §1 | `engine/consolidation.py` + `engine/lifecycle.py` (4 módulos: Storage/Updating/Retrieval/Generation mapeiam para consolidation/lifecycle/retrieval/enrichment) | ✅ |
| **MemOS** | §1 | `engine/learning_rule.py` + `engine/workflow_suggest.py` + `cerebro/cerebelo/padroes/Patterns.md` (skill reuse via learning rules + padrões) | ✅ |
| **A-MEM** | §1 + §6 | `engine/brain_evolution.py` + `engine/consolidation.py` + testes `test_related_memories.py`, `test_cross_memory_link.py` (link evolution contínuo — complementa Graphiti que extrai edges novas) | ✅ |
| **HippoRAG 2** | §4 | `engine/ppr_activation.py` (Personalized PageRank com `damping`, `max_iterations`, `epsilon` — exato algoritmo do HippoRAG) | ✅ |

### 3.2 DuckDB analytics (descoberta em §0.6)

O DuckDB (P12 da 2ª passada) **não é fase pendente** — já está em `scripts/analytics/hive_analytics.py` com 4 queries analíticas (growth, top_topics, quarantine_rate, intent_by_goal). Dep `duckdb>=0.10` já no `pyproject.toml`. Marcar como DONE.

> **Escopo (DONE parcial):** entregue a metade **OLAP** (analytics). A extensão vetorial `vss`/HNSW do DuckDB (estudada no `09 §3`) **não** foi implementada — busca vetorial fica no `sqlite-vec`/HNSW 1024d. Reabrir como item futuro só se quiser analytics-sobre-embeddings no DuckDB.

### 3.3 Implicação para o roadmap

A 2ª passada deste roadmap listava 13 fases pendentes (P6..P18). Esta 3ª passada reduz para **6** (P7,P8,P9,P10,P11,P13; P6 sqlite-lembed/GGUF descartado — ver §5; P12 aposentado→DuckDB §3.2) porque:
- Mem0, OpenMemory, Cognee, MemoryOS, MemOS, A-MEM, HippoRAG 2 → já no neural-memory (rastreabilidade em §3.1)
- DuckDB → já em `scripts/analytics/` (§3.2)
- Microsoft GraphRAG → coberto por RAPTOR (P10) + PPR do neural-memory (§5)

---

## 4. Fases pendentes (P7..P13)

6 fases, cada uma com: origem no `09`, lobo do cérebro, estado atual verificado, arquivos a criar/modificar (linhas exatas quando aplicável), código de exemplo, env vars, comandos de instalação, testes, critério de pronto.

### Fase P7 — MegaMem Streamable HTTP (MCP spec 2025-03-26) 🔜

**Origem:** `09` §2 — MegaMem (Obsidian + MCP + SQLite, suporte Streamable HTTP).
**Lobo:** Tronco (transporte MCP). Migra de stdio para Streamable HTTP — habilita múltiplos agentes conectados simultaneamente ao mesmo cérebro.
**ROI:** Alto | **Esforço:** Médio | **Status:** 🔜 Pendente

**Estado atual (verificado):**
- `scripts/services/sinapse-mcp.py` é **stdio** (stdin.readline loop, JSON-RPC, 644 linhas)
- `scripts/services/sinapse-api.py` é REST FastAPI :37702 (não é MCP Streamable HTTP)
- Não existe `*mcp-http*` ou `aiohttp` em nenhum arquivo MCP

**Tarefas:**
- [ ] Criar `scripts/services/sinapse-mcp-http.py` (paralelo ao stdio, não substitui):
  ```python
  #!/usr/bin/env python3
  """MCP server via Streamable HTTP (spec 2025-03-26).
  Roda em paralelo ao sinapse-mcp.py (stdio). Permite múltiplos agentes simultâneos.
  Uso: python sinapse-mcp-http.py --port 37703
  """
  from aiohttp import web
  from scripts.services.sinapse_mcp import handle_request, TOOLS  # reutiliza lógica

  async def handle_mcp(request: web.Request) -> web.Response:
      body = await request.json()
      result = handle_request(body)
      return web.json_response(result or {"jsonrpc": "2.0", "result": None, "id": body.get("id")})

  async def handle_tools_list(request: web.Request) -> web.Response:
      return web.json_response({"tools": TOOLS})

  def main():
      import argparse, os
      ap = argparse.ArgumentParser()
      ap.add_argument("--port", type=int, default=int(os.environ.get("SINAPSE_MCP_HTTP_PORT", "37703")))
      ap.add_argument("--host", default="127.0.0.1")
      args = ap.parse_args()
      app = web.Application()
      app.router.add_post("/mcp", handle_mcp)
      app.router.add_get("/mcp/tools", handle_tools_list)
      app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))
      print(f"MCP HTTP server em http://{args.host}:{args.port}/mcp")
      web.run_app(app, host=args.host, port=args.port)

  if __name__ == "__main__":
      main()
  ```
- [ ] `pyproject.toml`: adicionar `aiohttp>=3.9`
- [ ] `scripts/setup/install_services.py` — adicionar unit systemd:
  ```python
  "sinapse-mcp-http.service": """[Unit]
  Description=Hive-Mind MCP HTTP Server (Streamable HTTP spec 2025-03-26)
  After=network.target
  [Service]
  Type=simple
  ExecStart={venv}/python {project}/scripts/services/sinapse-mcp-http.py --port 37703
  Restart=always
  RestartSec=5
  [Install]
  WantedBy=default.target
  """,
  ```
- [ ] **Env vars:** `SINAPSE_MCP_HTTP_PORT` (default 37703), `SINAPSE_MCP_HTTP_HOST` (default 127.0.0.1) — **não hardcodar a porta** (systemd + register-mcp leem do env)
- [ ] `register-mcp.sh` — adicionar bloco que detecta agentes Streamable HTTP (spec 2025-03-26) e escreve `{"url":"http://localhost:${SINAPSE_MCP_HTTP_PORT}/mcp"}` no config do agente em vez do entry stdio (especificar o trecho exato a editar por agente)
- [ ] Testes: `tests/integration/test_mcp_http.py` — cliente MCP Streamable HTTP contra o server

**Critério de pronto:**
- 2+ clientes MCP (ex: Claude Code + Codex) conectados simultaneamente ao mesmo server sem conflito
- Testes E2E Streamable HTTP passam (initialize, tools/list, tools/call)
- stdio server continua funcionando (compatibilidade retroativa)
- `sinapse_health` reporta o novo endpoint

**Decisão dependente:** avaliar se agentes atuais (Kilo, Hermes, Codex, Cursor) suportam spec 2025-03-26. Se nenhum suportar, deferir.

### Fase P8 — CR-SQLite (sync multi-dispositivo) 🔜

**Origem:** `09` §7 — CR-SQLite (vlcn-io).
**Lobo:** Tronco (infra de sincronização). Habilita instâncias Hive-Mind em workstation + laptop + servidor convergindo sem conflitos.
**ROI:** Alto | **Esforço:** Médio | **Status:** 🔜 Pendente | **Risco:** Médio (migração de schema — backup antes)

**Estado atual (verificado):**
- Nenhum arquivo em `core/` ou `scripts/` menciona `crsqlite`, `crsql_as_crr`, ou `crsql_changes` — gap real confirmado
- Tabelas sincronizáveis (de `core/umc_schema.sql`): `neurons`, `synapses`, `observations`, `vault`, `ambiguities`, `visual_memories`, `document_memories`, `causal_edges`, `goals`
- `capture-state.db` NÃO deve sincronizar (local-only, SeenStore)

**Tarefas:**
- [ ] `uv add crsqlite` (extensão loadable) — **verificar se o pacote PyPI traz o binário nativo (`.so`/`.dylib`) pré-compilado para a plataforma alvo; se não, adicionar download/compilação do binário ao `install.sh`**
- [ ] Criar `core/crdt_sync.py`:
  ```python
  """CR-SQLite: sincronização CRDT para hive_mind.db."""
  from __future__ import annotations
  import sqlite3
  import os

  # Tabelas que participam da sincronização CRDT.
  # NÃO incluir capture-state.db — ele é local-only.
  CRDT_TABLES = ["neurons", "synapses", "observations", "visual_memories",
                 "document_memories", "causal_edges", "goals", "vault", "ambiguities"]

  _crdt_initialized = False

  def enable_crdt(conn: sqlite3.Connection) -> bool:
      """Habilita CR-SQLite e converte tabelas para CRR."""
      global _crdt_initialized
      if _crdt_initialized:
          return True
      try:
          import crsqlite
          conn.enable_load_extension(True)
          crsqlite.load(conn)
          for table in CRDT_TABLES:
              try:
                  conn.execute(f"SELECT crsql_as_crr('{table}')")
              except sqlite3.OperationalError:
                  pass  # tabela já é CRR ou não existe
          conn.commit()
          _crdt_initialized = True
          return True
      except ImportError:
          return False

  def get_changes_since(conn: sqlite3.Connection, db_version: int = 0) -> list[tuple]:
      return conn.execute(
          "SELECT * FROM crsql_changes WHERE db_version > ?", (db_version,)
      ).fetchall()

  def apply_changes(conn: sqlite3.Connection, changes: list[tuple]) -> int:
      applied = 0
      for change in changes:
          try:
              conn.execute("INSERT INTO crsql_changes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", change)
              applied += 1
          except sqlite3.Error:
              pass
      conn.commit()
      return applied

  def current_db_version(conn: sqlite3.Connection) -> int:
      row = conn.execute("SELECT crsql_db_version()").fetchone()
      return row[0] if row else 0
  ```
- [ ] Integrar em `core/database.py:93` `get_connection()` — adicionar antes do `return conn`:
  ```python
  if os.environ.get("HIVE_CRDT_SYNC", "").lower() == "true":
      from core.crdt_sync import enable_crdt
      enable_crdt(conn)
  return conn
  ```
- [ ] Criar `scripts/services/sinapse-sync.py` (CLI):
  ```python
  #!/usr/bin/env python3
  """Sincronização CRDT entre instâncias Hive-Mind.
  Uso:
    sinapse-sync.py --export > changes.json
    sinapse-sync.py --import changes.json
    sinapse-sync.py --push http://remote:37702
    sinapse-sync.py --pull http://remote:37702
  """
  import argparse, json, sys
  from pathlib import Path
  from core.database import get_connection
  from core.crdt_sync import get_changes_since, apply_changes, current_db_version

  def cmd_export(since_version: int = 0):
      conn = get_connection()
      changes = get_changes_since(conn, since_version)
      print(json.dumps({"version": current_db_version(conn),
                         "changes": [list(c) for c in changes]}))

  def cmd_import(path: str):
      data = json.loads(Path(path).read_text())
      conn = get_connection()
      applied = apply_changes(conn, [tuple(c) for c in data["changes"]])
      print(f"Aplicadas {applied} mudanças (versão remota: {data['version']})")

  def main():
      ap = argparse.ArgumentParser()
      ap.add_argument("--export", action="store_true")
      ap.add_argument("--import", dest="import_file")
      ap.add_argument("--since", type=int, default=0)
      args = ap.parse_args()
      if args.export: cmd_export(args.since)
      elif args.import_file: cmd_import(args.import_file)
      else: ap.print_help()

  if __name__ == "__main__":
      main()
  ```
- [ ] Backup de `hive_mind.db` antes de habilitar CRDT (migration irreversível)
- [ ] `.env`: `HIVE_CRDT_SYNC=true`
- [ ] `tests/integration/test_crdt.py` — sync entre dois diretórios

**Critério de pronto:**
- Dois diretórios sincronizam alterações sem perda (test A: inst1 adiciona neurônio, export→import→inst2 tem o neurônio)
- `tests/integration/test_crdt.py` passa (4+ testes: export, import, conflict resolution, version tracking)
- `capture-state.db` permanece local-only (não sincroniza)
- Backup restaurável se migration falhar

### Fase P9 — Langfuse Self-Hosted (instrumentação real) 🔜

**Origem:** `09` §5 — Langfuse + OpenTelemetry.
**Lobo:** Cerebelo (ritmo/observabilidade). Tracing distribuído do Dream Cycle e pipeline de captura.
**ROI:** Alto | **Esforço:** Médio | **Status:** 🔜 Pendente

**Estado atual (verificado):**
- `core/telemetry.py` é **OTEL completo e funcional** (NÃO draft como afirmei na 1ª passada):
  - `_langfuse_headers()` — auth Basic via `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`
  - `init_telemetry()` — idempotente, cria `TracerProvider` + `BatchSpanProcessor` + `OTLPSpanExporter` → `/api/public/otel/v1/traces`
  - `span(name, attributes)` — context manager que cria span OTEL (no-op se desabilitado)
- `docker-compose.langfuse.yml` existe (porta 3100, volume `claude-mem/data/langfuse`)
- **GAP REAL:** `opentelemetry-sdk` e `opentelemetry-exporter-otlp-proto-http` **NÃO** estão no `pyproject.toml`
- **GAP REAL:** `telemetry.py` **não é importado em nenhum script** (`grep -rln "from core.telemetry import" scripts/ core/` retorna vazio) — não está instrumentado

**Tarefas:**
- [ ] `pyproject.toml`: adicionar
  ```
  opentelemetry-sdk>=1.20
  opentelemetry-exporter-otlp-proto-http>=1.20
  ```
- [ ] Deploy Langfuse: `docker compose -f docker-compose.langfuse.yml up -d` (porta 3100)
- [ ] Gerar keys no dashboard `http://localhost:3100` → `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
- [ ] Instrumentar `scripts/dream/dream_cycle.py` — no início de `_run_dream_cycle_inner()`:
  ```python
  from core.telemetry import init_telemetry, span
  init_telemetry()
  # Envolver etapas:
  with span("dream.distiller", {"obs_count": len(observations)}):
      distilled = agent_distill_and_validate(...)
  with span("dream.validator", {"distiller_output": str(distilled)[:200]}):
      validated = agent_validate(...)
  with span("dream.synthesis", {"session_id": session_id}):
      synthesis = run_synthesis_cycle(...)
  with span("dream.persist", {"persisted": total_persisted}):
      _route_and_persist_project(...)
  ```
- [ ] Instrumentar `scripts/capture/capture_core.py` — em `ingest()`:
  ```python
  from core.telemetry import span
  with span("capture.ingest", {"platform": platform, "sid": sid}):
      # ... loop de turns existente ...
  ```
- [ ] Instrumentar `scripts/services/sinapse-mcp.py` — em `handle_request()`:
  ```python
  from core.telemetry import span, init_telemetry
  init_telemetry()  # no main()
  with span(f"mcp.{tool_name}", {"tool": tool_name}):
      result = handler(tool_args)
  ```
- [ ] `.env`:
  ```bash
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_SECRET_KEY=sk-lf-...
  LANGFUSE_HOST=http://localhost:3100
  ```
- [ ] `install.sh` — nota pós-instalação sobre Langfuse (opt-in via env)
- [ ] **Langfuse MCP** (`avivsinai/langfuse-mcp`, projeto distinto do `09 §2`): status **DEFERIDO** — sub-item opcional, sem arquivos/testes próprios nesta passada. Decisão: implementar só após P9 base validado, OU mover para §5 (Rejeitados) se o cérebro consultar traces via REST do Langfuse direto

**Critério de pronto:**
- Dream Cycle gera traces visíveis em `http://localhost:3100` (replay de sessão)
- Cada span tem atributos (`obs_count`, `session_id`, etc.)
- `sinapse_query` aceita correlação com trace_id (opcional)
- Opt-in: sem `LANGFUSE_PUBLIC_KEY` no `.env`, `telemetry.py` é no-op (zero overhead)
- `tests/unit/test_telemetry.py` — 4 testes (init idempotente, span no-op quando desabilitado, span com attributes, erro não propagado)

### Fase P10 — RAPTOR (nível mensal/anual — recursão real) 🔜

**Origem:** `09` §6 — RAPTOR (Stanford 2024).
**Lobo:** Córtex frontal (síntese hierárquica multi-nível).
**ROI:** Médio | **Esforço:** Alto | **Status:** 🔜 Pendente

**Estado atual (verificado):**
- `scripts/dream/daily_writer.py` — nível 1 (diário) ✅ existe
- `scripts/dream/weekly_synthesizer.py` — nível 2 (semanal, 325 linhas, gerado por `sinapse-weekly.timer` Sun 04:00) ✅ existe
- **GAP REAL:** não existe `monthly_synthesizer.py` nem `yearly_synthesizer.py` — só 2 níveis, sem recursão real (sem nível 3 mensal sobre as semanas, sem nível 4 anual sobre os meses)
- `grep -c "recursive\|hierarchical\|level.*3\|monthly\|mensal" scripts/dream/weekly_synthesizer.py` → 0

**Tarefas:**
- [ ] Criar `scripts/dream/monthly_synthesizer.py` — nível 3, baseado no `weekly_synthesizer.py`:
  ```python
  #!/usr/bin/env python3
  """Monthly Synthesizer — nível 3 do RAPTOR.
  Consolida 4-5 semanais do mês em 1 sumário mensal.
  Disparado por systemd `sinapse-monthly.timer` (1º de cada mês 05:00).
  Uso: python monthly_synthesizer.py --year 2026 --month 6
  """
  import argparse, sys
  from pathlib import Path
  from datetime import date
  from scripts.dream.weekly_synthesizer import collect_daily_logs, generate_markdown

  def get_month_weeks(year: int, month: int) -> list[tuple[int, int]]:
      """Retorna [(year, week_num), ...] para todas as semanas do mês."""
      # ... calendar.isocalendar() ...

  def collect_weekly_summaries(year: int, month: int) -> list[dict]:
      """Lê os .md das semanas do mês de cerebro/cerebelo/semanal/."""
      # ...

  def main():
      ap = argparse.ArgumentParser()
      ap.add_argument("--year", type=int, required=True)
      ap.add_argument("--month", type=int, required=True)
      args = ap.parse_args()
      # ... consolidar semanas → mensal ...
  ```
- [ ] Criar `scripts/dream/yearly_synthesizer.py` — nível 4, sobre os mensais
- [ ] `scripts/setup/install_services.py` — adicionar timers:
  ```python
  "sinapse-monthly.timer": """[Unit]
  Description=Hive-Mind Monthly Synthesizer (RAPTOR nível 3)
  [Timer]
  OnCalendar=*-*-01 05:00
  Persistent=true
  [Install]
  WantedBy=default.target
  """,
  "sinapse-yearly.timer": """[Unit]
  Description=Hive-Mind Yearly Synthesizer (RAPTOR nível 4)
  [Timer]
  OnCalendar=*-01-01 06:00
  Persistent=true
  [Install]
  WantedBy=default.target
  """,
  ```
- [ ] Tool `sinapse_hierarchical_search` no MCP — consulta top-down (mês → semana → dia):
  ```python
  def _hierarchical_search(query: str, level: str = "auto") -> dict:
      """Busca em múltiplos níveis de abstração.
      level: 'daily' | 'weekly' | 'monthly' | 'yearly' | 'auto' (todos)
      """
  ```
- [ ] **Registrar `sinapse_hierarchical_search` em `TOOLS` + `tools/list` do `sinapse-mcp.py`** (senão fica invisível aos clientes). É tool separada e **NÃO entra em `_READ_BACKENDS`** — não é backend de fusão, é busca multinível sob demanda
- [ ] `tests/integration/test_raptor.py` — 4 testes (consolidação mensal, anual, hierarchical search, levels)

**Critério de pronto:**
- Query "resuma o que aconteceu em 2026-06" retorna sumário do nível 3 (mês)
- Query "resuma 2026" retorna sumário do nível 4 (ano)
- Timers `sinapse-monthly.timer` e `sinapse-yearly.timer` ativos
- Cada nível armazenado em `cerebro/cerebelo/{mensal,anual}/`
- 4+ testes passando

### Fase P11 — LanceDB (storage multimodal para captura visual) 🔜

**Origem:** `09` §3 — LanceDB (embedded columnar + vector, multimodal).
**Lobo:** Córtex occipital (storage multimodal). Suporta embeddings de imagens/vídeos (CLIP), não só texto.
**ROI:** Médio | **Esforço:** Alto | **Status:** 🔜 Pendente

**Estado atual (verificado):**
- `core/database.py:221` `add_visual_memory(image_path, description, ocr_text, neuron_id, metadata)` existe
- `core/umc_schema.sql:110` `visual_memories` table existe — MAS armazena só `image_path` + `description` + `ocr_text` (texto), **não embedding visual CLIP**
- LanceDB ausente do `pyproject.toml` e de todo código — gap real
- Screenpipe (P1) captura screenshots mas não gera embedding visual

**Tarefas:**
- [ ] `uv add lancedb`
- [ ] **Decisão de pacote (fixar uma):** `uv add open-clip-torch torch` (wheel CPU por default; CUDA via `.env`). `clip_embed` no código de exemplo abaixo é **placeholder** — substituir por `open_clip` real
- [ ] Criar `integrations/lancedb/client.py`:
  ```python
  """LanceDB — storage multimodal para embeddings visuais (córtex occipital).
  Indexa screenshots do Screenpipe como embeddings CLIP para busca visual.
  """
  from pathlib import Path
  import lancedb
  import os

  _db = None
  _WORKING_DIR = str(Path(os.environ.get("SINAPSE_HOME", ".")) / "claude-mem" / "data" / "lancedb")

  def get_db():
      global _db
      if _db is None:
          Path(_WORKING_DIR).mkdir(parents=True, exist_ok=True)
          _db = lancedb.connect(_WORKING_DIR)
      return _db

  def index_screenshot(image_path: str, description: str, ocr_text: str = "") -> bool:
      """Indexa screenshot com embedding CLIP + texto."""
      try:
          import clip_embed  # ou transformers CLIP
          db = get_db()
          table = db.open_table("screenshots") if "screenshots" in db.table_names() \
              else db.create_table("screenshots", data=[{"image_path": "", "vector": [0.0]*512, "description": "", "ocr_text": ""}])
          vec = clip_embed.embed_image(image_path)  # CLIP 512d ou 768d
          table.add([{
              "image_path": image_path,
              "vector": vec,
              "description": description,
              "ocr_text": ocr_text,
          }])
          return True
      except Exception as e:
          print(f"  [LanceDB] index falhou: {e}")
          return False

  def search_visual(query_image_path: str = None, query_text: str = None, top_k: int = 10) -> list[dict]:
      """Busca screenshots por similaridade visual (CLIP) ou texto."""
      db = get_db()
      if "screenshots" not in db.table_names():
          return []
      table = db.open_table("screenshots")
      if query_image_path:
          qvec = clip_embed.embed_image(query_image_path)
      else:
          qvec = clip_embed.embed_text(query_text)
      return table.search(qvec).limit(top_k).to_list()
  ```
- [ ] Conectar ao Dream Cycle `run_visual_dream_stage()` — após `add_visual_memory()`, chamar `index_screenshot()`:
  ```python
  # Em scripts/dream/dream_cycle.py, dentro de run_visual_dream_stage:
  try:
      from integrations.lancedb.client import index_screenshot
      index_screenshot(str(img_path), analysis.description, analysis.ocr)
  except ImportError:
      pass
  ```
- [ ] Tool `sinapse_visual_search` no MCP — **registrar em `TOOLS` + `tools/list` do `sinapse-mcp.py`** (senão fica invisível aos clientes); **NÃO entra em `_READ_BACKENDS`** (store visual separado, não backend de fusão):
  ```python
  def _visual_search(query: str = "", image_path: str = "", top_k: int = 10) -> dict:
      """Busca visual: screenshots parecidos com texto ou imagem de referência."""
      from integrations.lancedb.client import search_visual
      results = search_visual(query_image_path=image_path or None,
                              query_text=query or None, top_k=top_k)
      return {"results": results, "count": len(results)}
  ```
- [ ] `pyproject.toml`: `lancedb>=0.5`, `open-clip-torch>=2.20`, `torch>=2.0` (pinar wheel CPU; `torch` é dep pesado ~2GB — decidir CPU/CUDA)
- [ ] `tests/integration/test_lancedb.py` — 4 testes (index, search visual, search text, empty)

**Critério de pronto:**
- Screenshots do Screenpipe indexados com embedding CLIP
- Busca visual ("screenshots parecidos com X") retorna top-K relevante
- Busca por texto ("tela com terminal") retorna screenshots correspondentes
- `tests/integration/test_lancedb.py` passa
- Storage em `claude-mem/data/lancedb/` (anatomia: occipital storage)

**Modelo CLIP:** `ViT-B-32` (open_clip, ~600MB) — **adicionar download ao `install.sh` (opt-in)** ou baixar on-first-use via `open_clip.create_model_and_transforms`. Não deixar só em nota de risco.

**Tier de máquina (§0.3.1):** CLIP só roda em `HIVE_VISION_TIER=lite|full`. Em `none` (máquina simples) a busca visual cai no Vision LLM Ollama (descrição) + `bge-m3` no store atual — **sem CLIP, sem torch**. Modelo dedicado é opt-in por capacidade de hardware.

**Nota de dimensão:** embeddings visuais CLIP são **512d** e vivem num store LanceDB **separado** — **NÃO** usam o índice HNSW 1024d (bge-m3) do cérebro. Sem conflito de dimensão.

### Fase P13 — OmniParser v2 (UI screenshot parsing, pré-processador) 🔜

**Origem:** `09` §8 — OmniParser v2 (Microsoft).
**Lobo:** Córtex occipital (UI parsing estruturado). Pré-processador que extrai elementos UI (bounding boxes, tipos) antes do LLM Vision — reduz tokens.
**ROI:** Médio | **Esforço:** Alto | **Status:** 🔜 Pendente

**Estado atual (verificado):**
- `scripts/dream/dream_cycle.py:448` chama `call_llm_with_fallback("vision", ..., vision_prompt, VisionAnalysis, image_path=...)` — LLM Vision processa screenshot **direto** (sem pré-parser estruturado)
- `core/schemas/vision_models.py` define `VisionAnalysis` (description, ocr, inferred_topics, importance_score)
- OmniParser ausente — gap real (pré-processador)

**Tarefas:**
- [ ] Clonar `https://github.com/microsoft/OmniParser` (**pinar tag/commit**) em `integrations/omniparser/` e **registrar em `pyproject.toml` `[tool.uv.sources]`** (como `graphifyy` e `neural-memory`) — não deixar clone manual avulso
- [ ] `integrations/omniparser/client.py`:
  ```python
  """OmniParser v2 — pré-processador de screenshots para elementos UI estruturados.
  Extrai bounding boxes + tipos de elemento antes do LLM Vision. Reduz tokens.
  """
  from pathlib import Path

  def parse_ui_elements(image_path: str) -> dict:
      """Extrai elementos UI estruturados de um screenshot.
      Returns: {elements: [{bbox, type, text}], annotated_image_path}
      """
      # Chama OmniParser (peso ~1.3GB, roda local)
      ...

  def elements_to_prompt(elements: list[dict]) -> str:
      """Converte elementos estruturados em prompt compacto para o LLM Vision."""
      return "\n".join(f"[{e['type']}] {e['text']}" for e in elements)
  ```
- [ ] Modificar `scripts/dream/dream_cycle.py:run_visual_dream_stage()` — pré-processar antes do LLM Vision:
  ```python
  # ANTES (atual):
  analysis: VisionAnalysis = call_llm_with_fallback(
      "vision", "Analise esta imagem.", vision_prompt, VisionAnalysis, image_path=str(img_path)
  )

  # DEPOIS:
  try:
      from integrations.omniparser.client import parse_ui_elements, elements_to_prompt
      ui = parse_ui_elements(str(img_path))
      structured_prompt = elements_to_prompt(ui["elements"])
      analysis: VisionAnalysis = call_llm_with_fallback(
          "vision", structured_prompt, vision_prompt, VisionAnalysis,
          image_path=ui.get("annotated_image_path", str(img_path))
      )
  except ImportError:
      # Fallback: LLM Vision puro (atual)
      analysis: VisionAnalysis = call_llm_with_fallback(...)
  ```
- [ ] Medir redução de tokens: antes/depois (benchmark em `tests/integration/test_omniparser.py`)
- [ ] **Resolver deps reais do OmniParser ANTES de implementar** (upstream usa `torch`, `transformers`, `ultralytics`/YOLO, `easyocr`) — pinar versões + wheel CPU/CUDA. ⚠️ **Fase NÃO é implementável enquanto as deps forem "provavelmente"**
- [ ] **Pesos (~1.3GB):** adicionar step de download ao `install.sh` (`huggingface-cli download microsoft/OmniParser-v2.0`), não deixar só em comentário de código
- [ ] **Tier de máquina (§0.3.1):** OmniParser (YOLO, ~1.3GB) só ativo em `HIVE_VISION_TIER=full` (ou `HIVE_OMNIPARSER_ENABLED=true`); default off → fallback Vision LLM Ollama puro. **Pesos pesados não podem quebrar máquina simples** — por isso é dedicado e opt-in, não Ollama (que é pesado p/ visão e não faz detecção estruturada)
- [ ] `tests/integration/test_omniparser.py` — 4 testes (parse, prompt generation, fallback quando offline, redução de tokens)

**Critério de pronto:**
- Screenshots processados em ≤ 70% do tempo do LLM Vision puro
- Tokens enviados ao LLM Vision reduzidos em ≥ 40%
- Qualidade de extração (description, ocr) comparável ou melhor que LLM Vision puro
- `tests/integration/test_omniparser.py` passa
- Fallback funciona quando OmniParser offline (volta para LLM Vision puro)

**Risco:** OmniParser tem 39.5% no ScreenSpot Pro — viável mas não perfeito. Avaliar qualidade real contra o corpus do Hive-Mind antes de adotar como padrão.

---

## 5. Rejeitados com razão

Projetos do `09-integration-study.md` que NÃO são fases do roadmap, com justificativa verificada contra código.

| Projeto | Onde no `09` | Razão da rejeição | Verificado |
|---|---|---|---|
| **Letta (ex-MemGPT)** | §1 | As 3 camadas (Core/Recall/Archival) já mapeiam para o cérebro: sessão ativa (Core), `cortex/parietal/inbox/` (Recall), `cortex/temporal/` (Archival). Letta é runtime de agente externo, não órgão — integrar = acoplar a runtime externo. | ✅ `cerebro/cortex/{temporal,parietal/inbox}` existem |
| **Zep** | §1 | Não é fase separada: o componente open-source do Zep **é o Graphiti** (citado no próprio `09 §1`), já entregue no **P2**. | ✅ ver §2 P2 |
| **sqlite-lembed (GGUF)** | §3 | Embeddings rodam no **Ollama `bge-m3`** (P0, 100% local). sqlite-lembed exigiria modelo **GGUF/llama.cpp avulso** (contra a política de modelos §0.3.1) e está bloqueado upstream (Python 3.12+). Sem ganho real: Ollama já é local e continua sendo dependência (LightRAG/Graphiti/Vision), então não remove nada — só economiza ~40ms. | ✅ P0 cobre |
| **MCP server oficial (memory)** | §2 | Schema inferior (JSONL) vs `sinapse_query` (7 backends, SQLite+FTS5+HNSW+grafo). | ✅ `plugins/hermes/sinapse-memory.py` tem 7 backends |
| **sqlite-memory-mcp** | §2 | Drop-in replacement do oficial, mas `hive_mind.db` já é superior (FTS5 + sqlite-vec + HNSW + WAL). | ✅ `core/umc_schema.sql` tem 9 tabelas |
| **Microsoft GraphRAG** | §4 | RAPTOR (P10) cobre recursão; PPR do neural-memory (`engine/ppr_activation.py`) cobre community detection-like. GraphRAG tem "custo de indexação inviável para uso diário" (citado no `09`). Só faria sentido como batch mensal — mas RAPTOR nível mensal já faz síntese hierárquica. | ✅ RAPTOR P10 + PPR existente |
| **AgentOps** | §5 | Cloud-first (sem self-hosting gratuito). Langfuse self-hosted (P9) cobre observabilidade sem vendor lock-in. | ✅ P9 cobre |
| **Arize Phoenix** | §5 | Drift detection é feature do Langfuse quando configurado. Ferramenta separada = redundante. | ✅ P9 cobre |
| **W&B Weave** | §5 | Auto-logging de traces MCP — Langfuse (P9) já faz via OTLP. Duplicado. | ✅ P9 cobre |
| **MemCoT** | §6 | "Ainda paper sem implementação madura" (citado no `09` §6). Sem código para integrar. | ✅ só paper |
| **Automerge** | §7 | CR-SQLite (P8) resolve sync do `hive_mind.db`. Para vault `.md`, Syncthing/Obsidian Sync são soluções externas válidas já usadas. Automerge adiciona complexidade para `.md` que Syncthing já cobre. | ✅ P8 + Syncthing (`scripts/services/syncthing_watcher.py` existe) |
| **Yjs** | §7 | CRDT para edição colaborativa em tempo real. Cérebro é single-writer (Dream Cycle) — edição simultânea não é caso de uso. | ✅ Dream Cycle é single-writer |
| **Cognee** (rejeitado como fase, mas já integrado) | §1 | Já no neural-memory (`mcp/cognitive_handler.py`, `recall_handler.py`). Não é fase pendente. | ✅ ver §3 |
| **HippoRAG 2** (rejeitado como fase, mas já integrado) | §4 | PPR já no neural-memory (`engine/ppr_activation.py`). Não é fase pendente. | ✅ ver §3 |

---

## 6. Critério geral de "pronto"

Cada fase, ao concluir, entrega:

1. **Código** em path correto (anatomia — `core/`, `integrations/<nome>/`, `scripts/...`)
2. **Dependências** em `pyproject.toml` (Python) ou `install.sh` (sistema)
3. **Testes** mínimo 4 (smoke + 2 unit + 1 integration)
4. **Health check** se for órgão novo — `assert_health()` no `install.sh`
5. **Documentação** README no `integrations/<nome>/` (se vendor) ou seção no `docs/`
6. **Fusão no cérebro** se for órgão — registrado no `_READ_BACKENDS` (faz parte do `sinapse_query`)
7. **Migration script** se mudar schema (backup antes)

---

## 7. Sprints

### Sprint 1 — P0..P5 ✅ CONCLUÍDO (2026-06-21 → 2026-06-24)
- [x] P0..P5 conforme §2.

### Sprint 2 — P9 (Langfuse instrumentação) 🔜
- [ ] P9: `pyproject.toml` deps + instrumentar Dream Cycle + capture_core + sinapse-mcp (4+ spans)
- [ ] 8 testes novos
- **Esforço:** P9 é o de maior ROI desta sprint (Langfuse self-hosted já tem infra, falta só instrumentação + deps)

### Sprint 3 — P7 (Streamable HTTP) + P8 (CR-SQLite) 🔜
- [ ] P7: criar `sinapse-mcp-http.py` + aiohttp + systemd unit + testes E2E
- [ ] P8: `core/crdt_sync.py` + `sinapse-sync.py` CLI + backup + testes sync entre 2 dirs
- [ ] 8 testes novos

### Sprint 4 — P10 (RAPTOR mensal/anual) + P13 (OmniParser) 🔜
- [ ] P10: `monthly_synthesizer.py` + `yearly_synthesizer.py` + timers + `sinapse_hierarchical_search`
- [ ] P13: clonar OmniParser + pré-processar screenshots + benchmark redução tokens
- [ ] 8 testes novos

### Sprint 5 — P11 (LanceDB multimodal) 🔜
- [ ] P11: `integrations/lancedb/client.py` + CLIP + index screenshots + `sinapse_visual_search`
- [ ] 4 testes novos
- **Risco:** CLIP precisa de modelo (~600MB) — avaliar Ollama CLIP vs local

---

## 8. Mapa de arquivos por fase

| Fase | Arquivo principal | Ação | Status |
|------|---------|------|--------|
| P0 | `core/database.py` | `OllamaEmbedder` HTTP (linha 28-31) | ✅ |
| P0 | `core/hnsw_index.py:25` | `HNSW_DIM=1024` | ✅ |
| P0 | `core/umc_schema.sql:92` | `FLOAT[1024]` | ✅ |
| P0 | `plugins/sqlite-vec-worker/worker.py:54` | `VEC_EMBED_DIM=1024` | ✅ |
| P0 | `scripts/setup/migrate_embed_dim.py` | one-shot 384→1024 | ✅ |
| P1 | `scripts/capture/parsers/screenpipe.py` | **NOVO** | ✅ |
| P1 | `scripts/capture/capture_adapters.py` | `+screenpipe` | ✅ |
| P2 | `integrations/graphiti/client.py` | **NOVO** | ✅ |
| P2 | `integrations/graphiti/__init__.py` | API pública | ✅ |
| P2 | `plugins/hermes/sinapse-memory.py` | `+_backend_graphiti` | ✅ |
| P2 | `docker-compose.falkordb.yml` | FalkorDB | ✅ |
| P2 | `tests/integration/test_graphiti.py` | 14 testes | ✅ |
| P3 | `core/lightrag_index.py` | **NOVO** (granite3-dense:2b) | ✅ |
| P3 | `scripts/dream/dream_cycle.py:372-381` | `+index_memory()` | ✅ |
| P4 | `scripts/services/sinapse-mcp.py` | `sinapse_query` orquestrador | ✅ |
| P5 | `AGENTS.md`, `README.md`, `docs/01-architecture.md` | anatomia em 3 docs | ✅ |
| (DuckDB) | `scripts/analytics/hive_analytics.py` | 4 queries OLAP | ✅ DONE (§3) |
| (neural-memory) | `integrations/neural-memory/` | 7 projetos do 09 | ✅ DONE (§3) |
| P7 | `scripts/services/sinapse-mcp-http.py` | **NOVO** (Streamable HTTP) | 🔜 |
| P7 | `scripts/setup/install_services.py` | `+sinapse-mcp-http.service` | 🔜 |
| P8 | `core/crdt_sync.py` | **NOVO** | 🔜 |
| P8 | `core/database.py:93` | `+enable_crdt()` | 🔜 |
| P8 | `scripts/services/sinapse-sync.py` | **NOVO** CLI | 🔜 |
| P9 | `pyproject.toml` | `+opentelemetry-sdk, +opentelemetry-exporter-otlp-proto-http` | 🔜 |
| P9 | `scripts/dream/dream_cycle.py` | `+span()` em 4 estágios | 🔜 |
| P9 | `scripts/capture/capture_core.py` | `+span()` em `ingest()` | 🔜 |
| P9 | `scripts/services/sinapse-mcp.py` | `+span()` em `handle_request()` | 🔜 |
| P10 | `scripts/dream/monthly_synthesizer.py` | **NOVO** (nível 3) | 🔜 |
| P10 | `scripts/dream/yearly_synthesizer.py` | **NOVO** (nível 4) | 🔜 |
| P10 | `scripts/setup/install_services.py` | `+sinapse-monthly.timer`, `+sinapse-yearly.timer` | 🔜 |
| P11 | `integrations/lancedb/client.py` | **NOVO** (CLIP embeddings) | 🔜 |
| P11 | `scripts/dream/dream_cycle.py:run_visual_dream_stage` | `+index_screenshot()` | 🔜 |
| P13 | `integrations/omniparser/client.py` | **NOVO** (UI parsing) | 🔜 |
| P13 | `scripts/dream/dream_cycle.py:run_visual_dream_stage` | pré-processar antes do LLM Vision | 🔜 |

---

## 9. Gaps conhecidos (2026-06-25)

| Gap | Onde | Workaround | Quando resolve |
|---|---|---|---|
| `core/telemetry.py` existe mas não está instrumentado nem em `pyproject.toml` | P9 Langfuse | — | P9 (deps + instrumentação) |
| `sinapse_temporal_graph_search` ainda existe como tool MCP | `scripts/services/sinapse-mcp.py` | Marcada DEPRECATED; `sinapse_query` é canônico | Próxima release (remover) |
| `_Consciencia.md` e MOCs auto-gerados não estão no gitignore | `generate_mocs.py` | Regenerados a cada Dream Cycle | Considerar `.gitignore` |
| Brain UI (frontend de visualização do grafo) | nenhum | `integrations/neural-memory/dashboard/` tem React dashboard — não integrado ao cérebro | Avaliar em sprint futura |
| Sem sync multi-device | — | Manual rsync | P8 (CR-SQLite) |
| Sem nível mensal/anual de destilação | — | Diário + semanal existem | P10 (RAPTOR) |
| Sem embedding visual CLIP | `visual_memories` table só texto | LLM Vision processa screenshot direto | P11 (LanceDB) + P13 (OmniParser) |
| Sem pré-parser UI de screenshots | LLM Vision puro | — | P13 (OmniParser) |
| Downloads de pesos de visão não estão no `install.sh` (CLIP ~600MB P11, OmniParser ~1.3GB P13) | install.sh | Só em notas/comentários | Wirar como step opt-in por `HIVE_VISION_TIER` |
| Deps reais do OmniParser não resolvidas (são "provavelmente") | P13 | — | **Bloqueia P13** — verificar upstream antes de implementar |
| Pacote/modelo CLIP a fixar (`open-clip-torch` + `torch`, modelo `ViT-B-32`) | P11 | — | P11 (decidir CPU/CUDA) |
| `crsqlite`: confirmar se PyPI traz binário nativo da plataforma | P8 | — | P8 (senão step no install.sh) |
| Tools MCP novas (`sinapse_hierarchical_search` P10, `sinapse_visual_search` P11) precisam registro em `TOOLS`/`tools/list` | `sinapse-mcp.py` | — | P10/P11 (senão invisíveis aos clientes) |
| `integrations/patches/` aplicado sobre clones, antes não documentado | §0.2 | Agora documentado | — |
| Langfuse MCP (`avivsinai/langfuse-mcp`) em limbo (sub-item opcional do P9) | P9 | Deferido | Decidir: sub-fase ou §5 |

---

## 10. Próximo passo imediato

**Sprint 2** (proposto) — confirmar antes de executar:
- [ ] P9 (Langfuse): adicionar deps em `pyproject.toml` + instrumentar 4+ pontos do pipeline (Dream Cycle, capture_core, sinapse-mcp)

Sem confirmação, não mexo.
