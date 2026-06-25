# Roadmap de Implementação — Hive-Mind Integrações
**Data:** 2026-06-24 | **Base anatômica:** `docs/01-architecture.md` §2 e `AGENTS.md` §2 | **Base de pesquisa:** `docs/09-integration-study.md`

> Documento de engenharia orientado pela **anatomia do cérebro**: cada fase adiciona
> ou reforça um órgão do cérebro. Clones de projetos externos vivem em
> `integrations/<nome>/` (não em `core/`); deps Python vão no `pyproject.toml`;
> deps de sistema (binários, Docker, Ollama) vão no `install.sh`. Nomes em
> `cerebro/` (projetos, tópicos, setores) são fictícios — projetos reais são
> instalados pelo usuário no diretório `cerebro/cortex/temporal/<projeto>/`.
>
> **Catálogo completo** de 22 fases (sem limite artificial). Cada fase vem do
> estudo `09-integration-study.md` ou foi decidida nesta conversa.
> Não há número fixo de fases — adiciono mais conforme novos projetos
> externos forem estudados ou a anatomia exigir.

---

## Índice de Fases

### Concluídas (P0..P5)
| Fase | Nome | Órgão do cérebro | Status | Commits-chave |
|------|------|------------------|--------|---------------|
| [P0](#fase-p0-embeddings-100-local-ollama-bge-m3-concluído) | Embeddings 100% Local (bge-m3) | Cortex (associação) | ✅ DONE 2026-06-21 | `93db445`, `f087279` |
| [P1](#fase-p1-screenpipe-via-rest-substitui-mss-concluído) | Screenpipe via REST | Cortex occipital (captura) | ✅ DONE 2026-06-21 | `9597ef5`, `2a4cdc8` |
| [P2](#fase-p2-graphiti-falkordb-lóbulo-temporal-concluído) | Graphiti + FalkorDB | **Lóbulo temporal** (causalidade) | ✅ DONE 2026-06-21 → refinado 2026-06-24 | `5d90f51`, `41fac0c`, `b11d6d6`, `16e0387` |
| [P3](#fase-p3-lightrag-no-dream-cycle-concluído) | LightRAG no Dream Cycle | Cortex (RAG híbrido) | ✅ DONE 2026-06-21 → 2026-06-24 | `56f1e98`, `fe68300`, `61c5285`, `dee365b` |
| [P4](#fase-p4-sinapse_query-funciona-como-cérebro-federador-7-órgãos-concluído) | sinapse_query funde 7 órgãos | Tronco (entry point único) | ✅ DONE 2026-06-24 | `16e0387` |
| [P5](#fase-p5-anatomia-canônica-em-3-documentos-concluído) | Anatomia canônica (3 docs) | Tronco (docs) | ✅ DONE 2026-06-23 | `ca1ff96`, `3eb4a35`, `ddf5504` |

### Pendentes (P6..P22) — ordem por ROI
| Fase | Nome | Órgão do cérebro | ROI | Esforço |
|------|------|------------------|-----|---------|
| [P6](#fase-p6-sqlite-lembed-embeddings-nativos-no-sqlite) | sqlite-lembed | Cortex (embeddings nativos) | Alto | Baixo |
| [P7](#fase-p7-megamem-streamable-http-mcp-spec-2025-03-26) | MegaMem Streamable HTTP | Tronco (transporte MCP) | Alto | Médio |
| [P8](#fase-p8-openmemory-mcp-camada-de-memória-compartilhada) | OpenMemory MCP | Diencéfalo (cross-agente) | Alto | Baixo |
| [P9](#fase-p9-langfuse-self-hosted-observabilidade-via-opentelemetry) | Langfuse Self-Hosted | Cerebelo (ritmo) | Alto | Médio |
| [P10](#fase-p10-cr-sqlite-sync-multi-dispositivo) | CR-SQLite | Tronco (infra sync) | Alto | Médio |
| [P11](#fase-p11-a-mem-link-evolution-no-grafo) | A-MEM (link evolution) | Diencéfalo (cross-memória) | Médio | Médio |
| [P12](#fase-p12-cognee-recall-router-multi-hop) | Cognee (recall router) | Cortex (busca semântica) | Médio | Médio |
| [P13](#fase-p13-hipporag-2-retrieval-multi-hop-via-pagerank) | HippoRAG 2 | Cortex (retrieval associativo) | Médio | Alto |
| [P14](#fase-p14-raptor-sumário-recursivo-em-múltiplos-níveis) | RAPTOR (sumário recursivo) | Cortex frontal (síntese) | Médio | Alto |
| [P15](#fase-p15-mem0-camada-de-memória-universal-para-agentes) | Mem0 (memória universal) | Diencéfalo (cross-tool) | Médio | Médio |
| [P16](#fase-p16-lancedb-storage-multimodal-para-captura-visual) | LanceDB (multimodal) | Cortex occipital | Médio | Alto |
| [P17](#fase-p17-duckdb-analytics-olap-sobre-o-corpus) | DuckDB (analytics) | Cerebelo (análise) | Médio | Baixo |
| [P18](#fase-p18-omniparser-v2-ui-screenshot-parsing) | OmniParser v2 | Cortex occipital (UI parsing) | Médio | Alto |
| [P19](#fase-p19-automerge-sync-do-vault-cerebro) | Automerge (vault sync) | Tronco (infra sync) | Baixo | Alto |
| [P20](#fase-p20-microsoft-graphrag-síntese-hierárquica-de-longo-prazo) | Microsoft GraphRAG | Cortex frontal (síntese batch) | Baixo | Alto |
| [P21](#fase-p21-letta-archival-memory-para-agentes-de-longa-duração) | Letta (archival memory) | Cortex ínsula (auto-consciência) | Baixo | Alto |
| [P22](#fase-p22-memoryos-memória-procedural-skill-reuse) | MemoryOS (procedural) | Cerebelo (procedural) | Baixo | Alto |

**Detalhamento por ROI no `09` (matriz original):** SQLite-lembed (P0), Graphiti (P1→P2 aqui), CR-SQLite (P1→P10), Screenpipe (P1→P1), OpenMemory (P1→P8), Langfuse (P2→P9), A-MEM (P2→P11), MegaMem (P2→P7), RAPTOR (P3→P14), Cognee (P3→P12), HippoRAG (P3→P13), LanceDB (P3→P16), DuckDB (P3→P17), Automerge (P4→P19), OmniParser (P4→P18), Letta (P4→P21), MemoryOS (P5→P22), GraphRAG (P5→P20). Mem0 (não estava na matriz, adicionado como P15 por potencial mencionado no `09` §1).

---

## 0. Princípios de Integração

### 0.1 Anatomia canônica (4 lobos irmãos)

O cérebro do Hive-Mind tem **4 lobos irmãos**, não hierárquicos:

- **Cortex** (cognição superior, 5 lóbulos): temporal, frontal, parietal, occipital, ínsula
- **Cerebelo** (ritmo): sessoes, diario, semanal, padroes
- **Diencéfalo** (relay cross-projeto): setores + roteamento
- **Tronco** (infra vital): modelos, paineis, infra, meta

Ver `docs/01-architecture.md` §2 e `AGENTS.md` §2 para o detalhamento. **Nenhuma fase pode violar a anatomia** — projetos vão em **lobos apropriados** ou em **integrations/** (vendors externos, que são órgãos mas não são do cérebro central).

### 0.2 Clones de vendors externos

Cada projeto externo que vira órgão do cérebro vive em `integrations/<nome>/`:

```
integrations/
├── graphify/         # cortex occipital — clustering estrutural
├── graphiti/         # lobo temporal — causalidade com validade (P2)
├── neural-memory/    # cortex — spreading activation
├── rtk/              # tronco — otimização de shell
├── claude-mem-plugins/  # lobo temporal — eventos brutos
├── megamem/          # P7 — MCP Streamable HTTP
├── openmemory/       # P8 — memória compartilhada cross-agente
├── langfuse/         # P9 — observabilidade OTEL
├── crsqlite/         # P10 — CRDT sync
├── amem/             # P11 — link evolution
├── cognee/           # P12 — recall router
├── hipporag/         # P13 — retrieval multi-hop
├── raptor/           # P14 — sumário recursivo
├── mem0/             # P15 — camada universal de memória
├── lancedb/          # P16 — storage multimodal
├── duckdb/           # P17 — analytics
├── omniparser/       # P18 — UI parsing
├── automerge/        # P19 — vault sync CRDT
├── graphrag/         # P20 — síntese hierárquica
├── letta/            # P21 — archival memory
└── memoryos/         # P22 — memória procedural
```

`install.sh` trata cada um como vendor (clone + install, opcional). Novos clones seguem o mesmo template: `<integrations>/<nome>/{__init__.py, client.py, README.md}`.

### 0.3 Dependências

- **Dependências Python** vão em `pyproject.toml` (fonte de verdade única, gerenciada por `uv`)
- **Dependências de sistema** (binários, Docker, Ollama) vão em `install.sh`
- **Variáveis de ambiente** têm default sensato e override via `.env`
- **Nenhuma dependência hardcoded em `core/`** — sempre via env vars ou `pyproject.toml`

### 0.4 Robustez por padrão

Todo órgão novo segue 4 camadas (do P2):

1. **Smoke test** (`assert_health()` ou equivalente)
2. **Circuit breaker** (3 falhas → cooldown)
3. **Persistência degradada** (fallback local se backend externo cai)
4. **Retry com backoff** (1s, 2s, 4s por padrão)

---

## 0.5 Mapa de vendors (estado atual)

| Lobro do cérebro | Vendor | `integrations/` | `pyproject.toml` | `install.sh` | Status |
|---|---|---|---|---|---|
| Cortex occipital | Graphify | `integrations/graphify/` | `graphifyy[watch]` | clone + setup_brain.sh | ✅ |
| **Lobo temporal** | **Graphiti (FalkorDB)** | `integrations/graphiti/` | `graphiti-core`, `falkordb` | clone + Docker FalkorDB | ✅ P2 |
| **Lobo temporal** | claude-mem | `integrations/claude-mem-plugins/` | (indep, npm) | (indep) | ✅ |
| Cortex (associação) | Neural Memory | `integrations/neural-memory/` | `neural-memory[pro]` | clone + setup_brain.sh | ✅ |
| **Cortex** (RAG) | LightRAG | `core/lightrag_index.py` (não vendor) | `lightrag-hku` | `ollama pull granite3-dense:2b` | ✅ P3 |
| Tronco | RTK | `integrations/rtk/` | (indep, cargo) | cargo install | ✅ |
| Cortex | SQLite-vec | (nativo) | `sqlite-vec` | (extensão nativa) | ✅ |
| Cortex (visual) | Screenpipe | (npm) | (indep, npm) | npm install -g @screenpipe/cli | ✅ P1 |
| Cortex | Fastembed | (nativo) | `fastembed` | (fallback P0) | ✅ |

**Padrão de integração:**
- Se é órgão do cérebro (Graphiti, Graphify, Neural Memory, claude-mem) → `integrations/<nome>/`
- Se é utilitário com dep local (LightRAG via pip) → `core/<nome>_index.py` + `pyproject.toml`
- Se é binário de sistema (Screenpipe, RTK) → `install.sh` baixa

---

## 1. Estado atual do cérebro

```
core/                              ← código do cérebro central
├── database.py                    # OllamaEmbedder (bge-m3 1024d) ✅P0
├── indexing.py                    # index_neuron_ids() ✅P0
├── hnsw_index.py                  # HNSW_DIM=1024 ✅P0
├── umc_schema.sql                 # search_vec FLOAT[1024] ✅P0
├── lightrag_index.py             # LightRAG v1.5.4 wrapper ✅P3
├── telemetry.py                   # OTEL → Langfuse (opt-in, P9)
└── paths.py                       # constantes anatômicas (CORTEX, TEMPORAL, etc.)

integrations/
├── graphify/                      # cortex occipital
├── graphiti/                      # lobo temporal (commit b11d6d6) ✅P2
│   ├── client.py                  # 4 camadas: smoke + circuit + retry + persist
│   ├── __init__.py                # API pública + whitebox
│   └── README.md
├── neural-memory/                 # cortex (associação)
├── rtk/                           # tronco (otimização shell)
└── claude-mem-plugins/            # lobo temporal (eventos)

plugins/
├── hermes/
│   └── sinapse-memory.py            # 7 backends federados (UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem)
└── sqlite-vec-worker/worker.py      # VEC_EMBED_DIM=1024 ✅P0

scripts/
├── dream/
│   └── dream_cycle.py             # ETL: Distiller→Validator→Router→Síntese
│                                  # Stage 3.5: push_neuron (Graphiti) + index_memory (LightRAG) best-effort
├── services/
│   ├── sinapse-mcp.py             # MCP stdio, 13 tools sinapse_* + sinapse_query (orquestrador)
│   ├── sinapse-api.py             # REST API (porta 37702)
│   └── sinapse-write.py           # CLI: decision, learning, query, health, session-end
├── capture/
│   ├── capture_core.py            # SeenStore SQLite WAL ✅
│   ├── capture_adapters.py        # ADAPTERS dict (screenpipe, etc.)
│   └── parsers/                   # 11 parsers: antigravity, codex, copilot, hermes, kilo...
└── setup/
    └── migrate_embed_dim.py       # 384 → 1024 one-shot ✅P0
```

---

## 2. Fases concluídas (P0..P5)

### Fase P0 — Embeddings 100% Local (Ollama bge-m3) ✅ CONCLUÍDO

**Objetivo:** eliminar `fastembed + all-MiniLM-L6-v2 (384d)` e usar modelo multilingual PT+EN 1024d rodando 100% local.
**Status:** ✅ | **Commits:** `93db445`, `f087279` | **Data:** 2026-06-21

**Modelo:** `bge-m3:latest` (1024d, MTEB multilingual #1 2024, 91ms warm, EXCELENTE PT-BR)

**Arquivos modificados:**

| Arquivo | Mudança |
|---|---|
| `core/database.py` | `OllamaEmbedder` via HTTP, `EMBED_BACKEND=ollama` default |
| `core/hnsw_index.py:25` | `HNSW_DIM` 384 → 1024 |
| `core/umc_schema.sql:92` | `FLOAT[384]` → `FLOAT[1024]` |
| `plugins/sqlite-vec-worker/worker.py` | `VEC_EMBED_DIM` 384 → 1024 |
| `scripts/setup/migrate_embed_dim.py` | script one-shot (3639/3642 re-indexados em 407s) |
| `tests/unit/test_p0_embedding.py` | 10 testes (backend, determinismo, dim, live) |

**Bloqueio original:** `sqlite-lembed` (plano inicial) é incompatível com Python 3.12+ (`OperationalError: misuse of sqlite3_result_subtype()`). Solução: Ollama HTTP API.

**Rollback:** `EMBED_BACKEND=fastembed` + `HNSW_DIM=384`.

### Fase P1 — Screenpipe via REST substitui mss ✅ CONCLUÍDO

**Objetivo:** deprecar `mss + LLM Vision` e consumir Screenpipe via REST local.
**Status:** ✅ | **Commits:** `9597ef5`, `2a4cdc8` | **Data:** 2026-06-21
**Testes:** 13/13 (10 offline + 3 live, skip se Screenpipe offline)

**Arquivos:**

| Arquivo | Mudança |
|---|---|
| `scripts/capture/parsers/screenpipe.py` (NOVO) | Cliente REST completo |
| `scripts/capture/capture_adapters.py` | entrada `"screenpipe"` em ADAPTERS |
| `scripts/services/sinapse-mcp.py` | `_capture_screen()` tenta Screenpipe primeiro, fallback `visual_capture.py` |
| `scripts/setup/install_services.py` | `_install_screenpipe()` (npm) |

**Env vars:** `SCREENPIPE_BASE` (default `http://localhost:3030`), `SCREENPIPE_TIMEOUT=5`, `SCREENPIPE_API_KEY` (opcional)

### Fase P2 — Graphiti + FalkorDB (lóbulo temporal) ✅ CONCLUÍDO

**Objetivo:** adicionar janelas de validade temporal (`valid_at`/`invalid_at`) ao grafo neurônios/sinapses.
**Status:** ✅ | **Commits:** `5d90f51`, `41fac0c` (robustez), `b11d6d6` (move para integrations), `16e0387` (fusão no cérebro)
**Testes:** 14/14 (11 offline + 3 live)

**Evolução em 3 etapas:**
1. `5d90f51` — Cria `core/graphiti_client.py` + Docker FalkorDB + hook no Dream Cycle
2. `41fac0c` — Adiciona 4 camadas de robustez: smoke test (`assert_health`), circuit breaker, retry com backoff, persistência JSON-lines em `cortex/temporal/_global/grafo.jsonl`
3. `b11d6d6` — Move de `core/` para `integrations/graphiti/` (anatomia: vendors externos ficam em `integrations/`, não no cérebro central)
4. `16e0387` — Funda no `sinapse_query` como 7º backend (`_backend_graphiti` em `plugins/hermes/sinapse-memory.py`)

**Arquivos atuais:**

| Arquivo | Papel |
|---|---|
| `integrations/graphiti/client.py` | Wrapper Graphiti/FalkorDB/Ollama; smoke + circuit + retry + persist |
| `integrations/graphiti/__init__.py` | API pública (`push_neuron`, `search_graph`, `assert_health`, `circuit_state`) |
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
**Testes:** `test_sinapse_mcp.py` + `test_p0_embedding.py` passando

**Decisão arquitetural crítica (commit `dee365b`):** LightRAG LLM fixo em `granite3-dense:2b` (1.5GB, Ollama local). Razões: (1) roda em qualquer máquina, (2) validação live: extrai 4 entities + 3 rels com JSON schema válido, (3) sem fallback Gemini/cloud — `.env` permite override só em dev. Config em `core/lightrag_index.py:25-29`.

**Arquivos:**

| Arquivo | Papel |
|---|---|
| `core/lightrag_index.py` | Wrapper LightRAG v1.5.4 (modelo local fixo) |
| `scripts/dream/dream_cycle.py:372-381` | `index_memory()` best-effort após `push_neuron` Graphiti |
| `scripts/services/sinapse-mcp.py` | tool `sinapse_rag_query` (modos `naive|local|global|hybrid`) |
| `install.sh:686` | nota pós-instalação `ollama pull granite3-dense:2b` |
| `pyproject.toml` | `lightrag-hku>=1.0.0` |

### Fase P4 — sinapse_query funciona como cérebro federador (7 órgãos) ✅ CONCLUÍDO

**Objetivo:** o `sinapse_query` (entry point único do cérebro) funde os 7 órgãos via Context Fusion paralelo.
**Status:** ✅ | **Commit:** `16e0387` | **Data:** 2026-06-24
**Testes:** 14/14 (`test_sinapse_mcp.py`)

**Anatomia:** orquestrador `_query_vault_knowledge` em `plugins/hermes/sinapse-memory.py` itera `_READ_BACKENDS` em paralelo (circuit breaker + timeout 8s):

```
sinapse_query → _query_vault_knowledge (Context Fusion paralelo)
                 ├── _backend_umc            # lobo temporal (índice SQLite consolidado)
                 ├── _backend_neural_memory # cortex (associação)
                 ├── _backend_sqlite_vec     # cortex (semântico local)
                 ├── _backend_claude_mem     # tálamo sensorial (eventos)
                 ├── _backend_graphify       # lobo occipital (estrutural)
                 ├── _backend_graphiti       # lobo temporal (causalidade) ✓ NOVO
                 └── _backend_filesystem     # lobo parietal (leitura)
```

**Bug corrigido:** antes do Passo 2, `sinapse_query` chamava `sm._backend_umc()` (apenas 1 backend) — quebrava a anatomia prometida. Agora chama `sm._query_vault_knowledge()` que funde os 7.

**Verificado end-to-end:** query de teste roda os 7 em paralelo, Graphiti respondeu em ~1.35s (live FalkorDB), tempo total ~1.4s sob `GLOBAL_QUERY_TIMEOUT=8s`.

**Tool `sinapse_temporal_graph_search`** marcada como DEPRECATED no docstring — clientes existentes não quebram, mas o canônico é `sinapse_query`.

### Fase P5 — Anatomia canônica em 3 documentos ✅ CONCLUÍDO

**Objetivo:** documento único de verdade para a anatomia do cérebro.
**Status:** ✅ | **Commits:** `ca1ff96`, `3eb4a35`, `ddf5504` | **Data:** 2026-06-23/24

**3 documentos sincronizados:**
- `AGENTS.md` (root) — seção 2: anatomia resumida (4 lobos + 5 lóbulos do cortex)
- `README.md` — "Anatomia do Cérebro" antes de "Visão Geral"
- `docs/01-architecture.md` — seção 2: anatomia completa (constantes, mapeamento, ferramentas)

**Nomes fictícios** (projeto-A..I, topico-1..N, setor-1..5) — projetos reais instalados pelo usuário. Root do repo limpo: `CLAUDE.md` (Ruflo config), `AGENT_BOOTSTRAP.md` (órfão) removidos em `ddf5504`.

---

## 3. Fases pendentes (P6..P22) — origem no `09-integration-study.md`

Cada fase abaixo lista:
- **Origem:** §n do `09-integration-study.md` ou decisão desta conversa
- **Lobo do cérebro:** onde a fase adiciona/reforça o órgão
- **Critério de pronto:** testes + health check + documentação

### Fase P6 — sqlite-lembed (embeddings nativos no SQLite) 🔜

**Origem:** `09` §3 — sqlite-lembed + sqlite-vec duo nativo.
**Lobo:** Cortex (associação). Substituiria o atual `OllamaEmbedder` (HTTP).
**ROI:** Alto | **Esforço:** Baixo (quando bug for corrigido) | **Status:** ⏸ BLOQUEADO
**Bloqueio:** `OperationalError: misuse of sqlite3_result_subtype()` em Python 3.12+. Issue upstream (`asg017/sqlite-lembed`).
**Tarefas:**
- [ ] Monitorar upstream para fix Python 3.12+
- [ ] Quando corrigido: `pip install sqlite-lembed`
- [ ] `_init_lembed()` em `core/database.py:get_connection()`
- [ ] `EMBED_BACKEND=lembed` no `.env`
- [ ] Migration script 1024→1024 (sem mudança) — só troca backend
**Critério de pronto:** `EMBED_BACKEND=lembed` funciona sem regressão nos 466+ testes existentes. Sem Ollama rodando (embeddings in-process).
**ROI esperado:** elimina OllamaEmbedder → redução de dependência externa no pipeline de indexação.

### Fase P7 — MegaMem (Streamable HTTP, MCP spec 2025-03-26) 🔜

**Origem:** `09` §2 — MegaMem (Obsidian + MCP + SQLite).
**Lobo:** Tronco (transporte MCP). Migra de stdio para Streamable HTTP.
**ROI:** Alto | **Esforço:** Médio | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] Avaliar viabilidade da migração stdio → Streamable HTTP
- [ ] Se viável: criar `scripts/services/sinapse-mcp-http.py` (paralelo ao stdio)
- [ ] `pyproject.toml`: `aiohttp>=3.9`
- [ ] Adicionar systemd unit `sinapse-mcp-http.service` em `install_services.py`
- [ ] Testes: cliente MCP 2025-03-26 rodando contra o server novo
**Critério de pronto:** múltiplos clientes MCP conectados simultaneamente ao mesmo server; testes E2E de Streamable HTTP passam.
**Decisão dependente:** avaliar se a migração é compatível com agentes atuais (Kilo, Hermes, Codex) que falam stdio.

### Fase P8 — OpenMemory MCP (camada de memória compartilhada) 🔜

**Origem:** `09` §1 — OpenMemory (by Mem0).
**Lobo:** Diencéfalo (camada de memória cross-agente). Complementa o cérebro atual: ao invés de interceptar sessões via arquivo/inotify, agentes escrevem direto no OpenMemory.
**ROI:** Alto | **Esforço:** Baixo | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] `pip install openmemory` (ou clone do MCP server)
- [ ] Configurar OpenMemory como endpoint MCP para Claude Code, Codex, Kilo Code
- [ ] Hive-Mind consome via REST API local (`localhost:port/memories`)
- [ ] Adicionar `_backend_openmemory` ao `sinapse_query` (8º backend)
**Critério de pronto:** 2+ agentes diferentes escrevem memórias no OpenMemory; `sinapse_query` retorna memórias cross-agente.
**Anatomia:** o OpenMemory vira um 8º backend do orquestrador. Cache em `cortex/temporal/_global/openmemory_cache.json` para fallback.

### Fase P9 — Langfuse Self-Hosted (observabilidade via OpenTelemetry) 🔜

**Origem:** `09` §5 — Langfuse + OpenTelemetry.
**Lobo:** Cerebelo (ritmo/observabilidade). Captura spans do Dream Cycle, capture pipeline, MCP server.
**ROI:** Alto | **Esforço:** Médio | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] `docker-compose.langfuse.yml` (já existe como draft no `10` original)
- [ ] `core/telemetry.py` (já existe com `init_telemetry()`, `span()` context manager)
- [ ] `pyproject.toml`: `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`
- [ ] Instrumentar `scripts/dream/dream_cycle.py` (spans em cada etapa)
- [ ] Instrumentar `scripts/capture/capture_core.py` (span em `ingest()`)
- [ ] `.env`: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
- [ ] Adicionar Langfuse MCP (`avivsinai/langfuse-mcp`) como ferramenta do cérebro
**Critério de pronto:** Dream Cycle gera traces em `http://localhost:3100`; replay de sessão possível; `sinapse_query` aceita `?trace_id=` para correlacionar com Langfuse.
**Opt-in:** só ativa se `LANGFUSE_PUBLIC_KEY` estiver definido em `.env`. Sem cloud lock-in.

### Fase P10 — CR-SQLite (sync multi-dispositivo) 🔜

**Origem:** `09` §7 — CR-SQLite (vlcn-io).
**Lobo:** Tronco (infra de sincronização).
**ROI:** Alto | **Esforço:** Médio | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] `pip install crsqlite` (extensão loadable)
- [ ] `core/crdt_sync.py` — helpers `enable_crdt()`, `get_changes_since()`, `apply_changes()`, `current_db_version()`
- [ ] Integrar em `core/database.py:get_connection()` (`HIVE_CRDT_SYNC=true`)
- [ ] Tabelas CRR: `neurons`, `synapses`, `observations`, `visual_memories` (NÃO `capture-state.db` — local-only)
- [ ] `scripts/services/sinapse-sync.py` — CLI (`--export`, `--import`, `--push`, `--pull`)
- [ ] `.env`: `HIVE_CRDT_SYNC=true`
**Critério de pronto:** dois diretórios sincronizam alterações sem perda; `tests/integration/test_crdt.py` passa.
**Anatomia:** CR-SQLite é infra do Tronco, não é um órgão cognitivo. Mantém `cortex/temporal/_global/` (vault Obsidian) sincronizado entre workstation + laptop + servidor.

### Fase P11 — A-MEM (link evolution no grafo) 🔜

**Origem:** `09` §1 + §6 — A-MEM (AGI Research, NeurIPS 2025).
**Lobo:** Diencéfalo (relay entre memórias). Links associativos que evoluem dinamicamente.
**ROI:** Médio | **Esforço:** Médio | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] `pip install amem` (ou clone de `agiresearch/A-mem`)
- [ ] `core/amem_linker.py` — `add_and_evolve()` + `_write_links_to_hive()`
- [ ] Conectar ao Dream Cycle: chamar após `index_memory` (LightRAG)
- [ ] Persistir links sugeridos como `synapses` no SQLite com `kind='amem'`
- [ ] `pyproject.toml`: `amem` ou path do clone
**Critério de pronto:** links novos aparecem no grafo após Dream Cycle; `tests/integration/test_amem.py` passa.
**Decisão pendente:** o A-MEM evolui links automaticamente; o Dream Cycle faz isso explicitamente. Avaliar se a evolução implícita do A-MEM substitui ou complementa a etapa de Síntese.

### Fase P12 — Cognee (recall router multi-hop) 🔜

**Origem:** `09` §1 — Cognee (topoteretes).
**Lobo:** Cortex (busca semântica com roteamento automático).
**ROI:** Médio | **Esforço:** Médio | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] `pip install cognee`
- [ ] `integrations/cognee/client.py` — wrapper Python
- [ ] Cognee ingere corpus do Hive-Mind e gera knowledge graph próprio (não conflita com o Graphiti)
- [ ] Adicionar `_backend_cognee` ao `sinapse_query` (9º backend)
- [ ] Quando query multi-hop: roteia para Cognee em vez de sqlite-vec
**Critério de pronto:** query "o que se relaciona com X" retorna top-K com roteamento automático; testes de recall multi-hop passam.
**Risco:** Cognee tem ontologia gerada por LLM — pode divergir do cérebro. Avaliar qualidade das edges geradas vs. Graphiti (que usa FalkorDB).

### Fase P13 — HippoRAG 2 (retrieval multi-hop via PageRank) 🔜

**Origem:** `09` §4 — HippoRAG 2 (OSU NLP Group).
**Lobo:** Cortex (retrieval associativo). Personalizado PageRank sobre knowledge graph.
**ROI:** Médio | **Esforço:** Alto | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] Clone `OSU-NLP-Group/HippoRAG` em `integrations/hipporag/`
- [ ] Ingerir o mesmo grafo do Graphiti/FalkorDB
- [ ] Adicionar tool `sinapse_associative_search` (top-K via PageRank)
- [ ] Comparar qualidade do recall com sqlite-vec (factual) e LightRAG (grafo)
**Critério de pronto:** query "o que se relaciona com X que vi na sessão de Y semanas atrás" retorna resultados úteis; benchmark contra HippoRAG paper.
**Risco:** complexidade alta. Avaliar se sqlite-vec + Graphiti já cobrem o caso.

### Fase P14 — RAPTOR (sumário recursivo em múltiplos níveis) 🔜

**Origem:** `09` §6 — RAPTOR (Stanford 2024).
**Lobo:** Cortex frontal (síntese hierárquica).
**ROI:** Médio | **Esforço:** Alto | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] Clone `parthsarthi03/raptor` em `integrations/raptor/`
- [ ] Scheduler no Dream Cycle:
  - Nível 1: destilação diária cria sumário do dia
  - Nível 2: destilação semanal sobre os diários
  - Nível 3: destilação mensal sobre as semanas
- [ ] Cada nível armazenado como tipo de neurônio diferente no grafo
- [ ] Adicionar tool `sinapse_hierarchical_search` (consulta top-down)
**Critério de pronto:** query "resuma o que aconteceu em 2026-06" retorna sumário do nível 3 (mês); testes de destilação em múltiplos níveis passam.

### Fase P15 — Mem0 (camada de memória universal para agentes) 🔜

**Origem:** `09` §1 — Mem0 (mem0ai).
**Lobo:** Diencéfalo (camada cross-tool). Universalidade: outros agentes (não-Hive-Mind) já falam Mem0 MCP.
**ROI:** Médio | **Esforço:** Médio | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] Avaliar: Mem0 substitui ou complementa o cérebro? Risco de duplicar gestão de memória.
- [ ] Se complementar: criar adapter em `integrations/mem0/client.py` que escreve neurônios no `hive_mind.db` quando Mem0 recebe `remember()`
- [ ] `pyproject.toml`: `mem0ai`
- [ ] Documentar coexistência Mem0 + Hive-Mind (cada um serve um nicho)
**Critério de pronto:** decisão documentada (merge ou coexistência) — `09` recomenda coexistência como camada de adapter.
**Risco:** Mem0 tem sua própria deduplicação e extração. Avaliar se conflita com o Dream Cycle.

### Fase P16 — LanceDB (storage multimodal para captura visual) 🔜

**Origem:** `09` §3 — LanceDB.
**Lobo:** Cortex occipital (storage multimodal). Suporta imagens, vídeos, embeddings de screenshots.
**ROI:** Médio | **Esforço:** Alto | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] `pip install lancedb`
- [ ] `integrations/lancedb/client.py` — storage de embeddings visuais (screenshots do Screenpipe)
- [ ] Integração com captura visual: cada screenshot → embedding (CLIP) → LanceDB
- [ ] Adicionar tool `sinapse_visual_search` (busca por similaridade visual)
**Critério de pronto:** screenshots do Screenpipe indexados; busca visual ("screenshots parecidos com X") retorna resultados relevantes.

### Fase P17 — DuckDB (analytics OLAP sobre o corpus) 🔜

**Origem:** `09` §3 — DuckDB + extensão vetorial `vss`.
**Lobo:** Cerebelo (análise estatística). DuckDB lê `hive_mind.db` via `ATTACH DATABASE` sem migrar dados.
**ROI:** Médio | **Esforço:** Baixo | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] `pip install duckdb`
- [ ] `core/duckdb_analytics.py` — módulo que abre `hive_mind.db` via DuckDB
- [ ] Queries analíticas: distribuição temporal de neurônios, top-k projetos por densidade, etc.
- [ ] Tool `sinapse_analytics` (somente leitura, agregada)
- [ ] `pyproject.toml`: `duckdb>=0.10` (já presente)
**Critério de pronto:** 5+ queries analíticas rodando sem copiar dados; testes de analytics retornam resultados esperados.

### Fase P18 — OmniParser v2 (UI screenshot parsing) 🔜

**Origem:** `09` §8 — OmniParser v2 (Microsoft).
**Lobo:** Cortex occipital (UI parsing estruturado). Extrai elementos UI de screenshots antes do LLM Vision.
**ROI:** Médio | **Esforço:** Alto | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] Clone `microsoft/OmniParser` em `integrations/omniparser/`
- [ ] Pré-processamento: cada screenshot do Screenpipe → OmniParser → elementos estruturados (bounding boxes, tipos)
- [ ] LLM Vision (existente) interpreta apenas elementos relevantes
- [ ] Avaliar redução de tokens: medir antes/depois
**Critério de pronto:** screenshots processados em ~50% do tempo do LLM Vision puro; qualidade de extração comparável ou melhor.
**Risco:** OmniParser tem 39.5% no ScreenSpot Pro — viável mas não perfeito.

### Fase P19 — Automerge (sync do vault `cerebro/`) 🔜

**Origem:** `09` §7 — Automerge.
**Lobo:** Tronco (sync do vault entre máquinas).
**ROI:** Baixo | **Esforço:** Alto | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] Avaliar: o CR-SQLite (P10) já cobre o `hive_mind.db`. Automerge cobre o vault `.md` Obsidian.
- [ ] Se necessário: `npm install @automerge/automerge` + scripts de sync
- [ ] Cada arquivo `.md` vira um documento Automerge
**Critério de pronto:** vault `cerebro/` sincroniza entre 2 instâncias sem perda; merge automático de conflitos.
**Risco:** alto esforço. Avaliar se Yjs (mais simples para edição) não seria melhor. Ver `09` §7.

### Fase P20 — Microsoft GraphRAG (síntese hierárquica de longo prazo) 🔜

**Origem:** `09` §4 — Microsoft GraphRAG.
**Lobo:** Cortex frontal (síntese batch).
**ROI:** Baixo | **Esforço:** Alto | **Status:** 🔜 Pendente (custo alto)
**Tarefas:**
- [ ] Clone `microsoft/graphrag` em `integrations/graphrag/`
- [ ] Batch mode no Dream Cycle: a cada mês, roda GraphRAG sobre o corpus do mês para gerar sumários hierárquicos (community detection + Leiden algorithm)
- [ ] Avaliar se RAPTOR (P14) já cobre; se sim, marcar P20 como redundante e documentar
**Critério de pronto:** run mensal de GraphRAG sobre corpus real retorna sumários úteis em tempo aceitável.
**Risco:** `09` cita "custo de indexação inviável para uso diário" — só faz sentido como batch mensal.

### Fase P21 — Letta (archival memory para agentes de longa duração) 🔜

**Origem:** `09` §1 — Letta (ex-MemGPT).
**Lobo:** Cortex ínsula (auto-consciência de agente). Memória de agente em 3 camadas (Core/Recall/Archival).
**ROI:** Baixo | **Esforço:** Alto | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] Avaliar viabilidade: o cérebro já cobre as 3 camadas (inbox sensorial = Recall, neurônios consolidados = Archival, sessão ativa = Core).
- [ ] Se Letta trouxer valor: usar REST API para injetar Archival Memory do Dream Cycle em agentes Letta externos
- [ ] Documentar coexistência (cérebro + Letta)
**Critério de pronto:** decisão documentada (merge, coexistência ou rejeição).

### Fase P22 — MemoryOS (memória procedural, skill reuse) 🔜

**Origem:** `09` §1 — MemoryOS (BAI-LAB).
**Lobo:** Cerebelo (procedural). Skill reuse cross-task.
**ROI:** Baixo | **Esforço:** Alto | **Status:** 🔜 Pendente
**Tarefas:**
- [ ] Avaliar se o cérebro tem lacuna em memória procedural
- [ ] Se sim: integrar módulo tool-memory do MemoryOS
- [ ] Classificar memórias como factuais vs. procedurais (roteamento no Dream Cycle)
**Critério de pronto:** memórias procedurais ("como fazer X") separadas das factuais ("o que é X"); tool memory do MemoryOS persiste.

---

## 4. Critério geral de "pronto" por fase

Cada fase, ao concluir, deve entregar:

1. **Código:** arquivos no path correto (anatomia)
2. **Dependências:** em `pyproject.toml` (Python) ou `install.sh` (sistema)
3. **Testes:** mínimo 4 (smoke + 2 unit + 1 integration)
4. **Health check:** se for órgão novo, `assert_health()` no install.sh
5. **Documentação:** README no `integrations/<nome>/` (se vendor) ou seção no `docs/`
6. **Fusão no cérebro:** se for órgão, registrado no `_READ_BACKENDS` (faz parte do `sinapse_query`)
7. **Migration script** (se mudar schema)

---

## 5. Checklist por sprint (rolling)

### Sprint 1 — P0..P5 ✅ CONCLUÍDO (2026-06-21 → 2026-06-24)
- [x] P0..P5 conforme detalhado em §2.

### Sprint 2 — P6 (sqlite-lembed quando desbloqueado) + P8 (OpenMemory) 🔜
- [ ] P6: monitorar upstream; se corrigido, implementar
- [ ] P8: configurar OpenMemory + 8º backend
- [ ] 8 testes novos

### Sprint 3 — P7 (MegaMem) + P9 (Langfuse) 🔜
- [ ] P7: avaliar viabilidade Streamable HTTP
- [ ] P9: Langfuse self-hosted + instrumentação OTEL
- [ ] 8 testes novos

### Sprint 4 — P10 (CR-SQLite) + P11 (A-MEM) 🔜
- [ ] P10: `core/crdt_sync.py` + sync CLI
- [ ] P11: `core/amem_linker.py` + Dream Cycle hook
- [ ] 8 testes novos

### Sprint 5 — P12 (Cognee) + P13 (HippoRAG 2) 🔜
- [ ] P12: 9º backend (cognee)
- [ ] P13: tool `sinapse_associative_search`
- [ ] 8 testes novos

### Sprint 6 — P14 (RAPTOR) + P15 (Mem0 coexistência) 🔜
- [ ] P14: scheduler recursivo no Dream Cycle
- [ ] P15: decisão de coexistência documentada
- [ ] 8 testes novos

### Sprint 7 — P16 (LanceDB) + P17 (DuckDB) + P18 (OmniParser) 🔜
- [ ] P16: storage multimodal
- [ ] P17: analytics
- [ ] P18: pré-processamento visual

### Sprint 8 — P19 (Automerge) + P20 (Microsoft GraphRAG) + P21 (Letta) + P22 (MemoryOS) 🔜
- [ ] P19..P22: decisões de coexistência (alguns marcados como "não fazer" se redundantes)

---

## 6. Resumo: Mapa de Arquivos por Fase

| Fase | Arquivo principal | Ação | Status |
|------|---------|------|--------|
| P0 | `core/database.py` | `OllamaEmbedder` HTTP | ✅ |
| P0 | `core/hnsw_index.py` | `HNSW_DIM=1024` | ✅ |
| P0 | `core/umc_schema.sql` | `FLOAT[1024]` | ✅ |
| P0 | `plugins/sqlite-vec-worker/worker.py` | `VEC_EMBED_DIM=1024` | ✅ |
| P0 | `scripts/setup/migrate_embed_dim.py` | one-shot 384→1024 | ✅ |
| P1 | `scripts/capture/parsers/screenpipe.py` | **NOVO** | ✅ |
| P1 | `scripts/capture/capture_adapters.py` | `+screenpipe` | ✅ |
| P2 | `integrations/graphiti/client.py` | **NOVO** | ✅ |
| P2 | `plugins/hermes/sinapse-memory.py` | `+_backend_graphiti` | ✅ |
| P2 | `docker-compose.falkordb.yml` | FalkorDB | ✅ |
| P2 | `tests/integration/test_graphiti.py` | 14 testes | ✅ |
| P3 | `core/lightrag_index.py` | **NOVO** (granite3-dense:2b) | ✅ |
| P3 | `scripts/dream/dream_cycle.py` | `+index_memory()` | ✅ |
| P4 | `scripts/services/sinapse-mcp.py` | `sinapse_query` orquestrador | ✅ |
| P5 | `AGENTS.md`, `README.md`, `docs/01-architecture.md` | anatomia em 3 docs | ✅ |
| P6 | `core/database.py` | `+_init_lembed()` | ⏸ |
| P7 | `scripts/services/sinapse-mcp-http.py` | **NOVO** (Streamable HTTP) | 🔜 |
| P8 | `integrations/openmemory/client.py` | **NOVO** | 🔜 |
| P8 | `plugins/hermes/sinapse-memory.py` | `+_backend_openmemory` | 🔜 |
| P9 | `core/telemetry.py` | OTEL → Langfuse (opt-in) | 🔜 |
| P9 | `scripts/dream/dream_cycle.py` | spans | 🔜 |
| P10 | `core/crdt_sync.py` | **NOVO** | 🔜 |
| P10 | `scripts/services/sinapse-sync.py` | **NOVO** CLI | 🔜 |
| P11 | `core/amem_linker.py` | **NOVO** | 🔜 |
| P12 | `integrations/cognee/client.py` | **NOVO** | 🔜 |
| P13 | `integrations/hipporag/client.py` | **NOVO** | 🔜 |
| P14 | `integrations/raptor/client.py` | **NOVO** | 🔜 |
| P15 | `integrations/mem0/client.py` | **NOVO** | 🔜 |
| P16 | `integrations/lancedb/client.py` | **NOVO** | 🔜 |
| P17 | `core/duckdb_analytics.py` | **NOVO** | 🔜 |
| P18 | `integrations/omniparser/client.py` | **NOVO** | 🔜 |
| P19 | `integrations/automerge/client.py` | **NOVO** | 🔜 |
| P20 | `integrations/graphrag/client.py` | **NOVO** | 🔜 |
| P21 | `integrations/letta/client.py` | **NOVO** | 🔜 |
| P22 | `integrations/memoryos/client.py` | **NOVO** | 🔜 |

---

## 7. Gaps conhecidos (2026-06-24)

| Gap | Onde | Workaround | Quando resolve |
|---|---|---|---|
| sqlite-lembed incompatível Python 3.12+ | P0 embeddings | `EMBED_BACKEND=ollama` (atual) | Quando upstream corrigir (P6) |
| LightRAG cobre sub-região do occipital junto com Graphify | P3 RAG | LightRAG é `core/` (não `integrations/`) por ser wrapper Python | P12 (Cognee) pode consolidar |
| `sinapse_temporal_graph_search` ainda existe como tool MCP | `scripts/services/sinapse-mcp.py` | Marcada como DEPRECATED; `sinapse_query` é o canônico | Próxima release (remover) |
| `_Consciencia.md` e MOCs auto-gerados não estão no gitignore | `generate_mocs.py` | Regenerados a cada Dream Cycle | Considerar `.gitignore` |
| Brain UI (frontend de visualização do grafo) | nenhum | Não há skill de canvas/web design no projeto | Avaliar em sprint futura |
| 17 fases pendentes (P6..P22) ainda não implementadas | `09-integration-study.md` | Roadmap priorizado por ROI | Conforme sprints |

---

## 8. Próximo passo imediato

**Sprint 2** (proposto) — confirmar antes de executar:
- [ ] P6 (sqlite-lembed): monitorar upstream + implementar assim que corrigido
- [ ] P8 (OpenMemory): configurar + 8º backend
- [ ] P9 (Langfuse): self-hosted + instrumentação OTEL

Sem confirmação, não mexo.