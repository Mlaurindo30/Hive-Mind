# Roadmap de Implementação — Hive-Mind Integrações
**Data:** 2026-06-24 | **Base anatômica:** `docs/01-architecture.md` §2 e `AGENTS.md` §2 | **Base de pesquisa:** `docs/09-integration-study.md`

> Documento de engenharia orientado pela **anatomia do cérebro**: cada fase adiciona ou
> reforça um órgão do cérebro. Clones de projetos externos vivem em
> `integrations/<nome>/` (não em `core/`); deps Python vão no `pyproject.toml`;
> deps de sistema (binários, Docker, Ollama) vão no `install.sh`. Nomes em
> `cerebro/` (projetos, tópicos, setores) são fictícios — projetos reais são
> instalados pelo usuário no diretório `cerebro/cortex/temporal/<projeto>/`.

---

## Índice de Fases

| Fase | Nome | Órgão do cérebro | Status | Commits-chave |
|------|------|------------------|--------|---------------|
| [P0](#fase-p0-embeddings-100-local-ollama-bge-m3-concluído) | Embeddings 100% Local (bge-m3) | Córtex (associação) | ✅ DONE 2026-06-21 | `93db445`, `f087279` |
| [P1](#fase-p1-screenpipe-via-rest-substitui-mss-concluído) | Screenpipe via REST | Córtex occipital (captura) | ✅ DONE 2026-06-21 | `9597ef5`, `2a4cdc8` |
| [P2](#fase-p2-graphiti-falkordb-lóbulo-temporal-concluído) | Graphiti + FalkorDB | **Lóbulo temporal** (causalidade) | ✅ DONE 2026-06-21 → refinado 2026-06-24 | `5d90f51`, `41fac0c`, `b11d6d6`, `16e0387` |
| [P3](#fase-p3-lightrag-no-dream-cycle-concluído) | LightRAG no Dream Cycle | **Córtex** (RAG híbrido) | ✅ DONE 2026-06-21 → 2026-06-24 | `56f1e98`, `fe68300`, `61c5285`, `dee365b` |
| [P4](#fase-p4-sinapse_query-funciona-como-cérebro-federador-7-órgãos-concluído) | sinapse_query funde 7 órgãos | Tronco (entry point único) | ✅ DONE 2026-06-24 | `16e0387` |
| [P5](#fase-p5-anatomia-canônica-em-3-documentos-concluído) | Anatomia canônica (3 docs) | Tronco (docs) | ✅ DONE 2026-06-23 | `ca1ff96`, `3eb4a35`, `ddf5504` |
| [P6](#fase-p6-raptor-sumário-recursivo-no-grafo) | RAPTOR (sumário recursivo) | Córtex frontal (síntese) | 🔜 Pendente | — |
| [P7](#fase-p7-megamem-obsidian-mcp-sqlite-vault-unificado) | MegaMem (Obsidian + MCP + SQLite) | Diencéfalo (cross-projeto) | 🔜 Pendente | — |
| [P8](#fase-p8-sqlite-lembed-embeddings-nativos-quando-disponível) | sqlite-lembed (nativo) | Córtex (quando Python 3.12+) | ⏸ Bloqueado (bug P0) | — |
| [P9](#fase-p9-cr-sqlite-sync-multi-dispositivo) | CR-SQLite (multi-device) | Tronco (infra) | 🔜 Pendente | — |
| [P10](#fase-p10-a-mem-link-evolution-no-grafo) | A-MEM (links evolutivos) | Diencéfalo (relay) | 🔜 Pendente | — |

---

## 0. Princípios de Integração

### 0.1 Anatomia canônica (4 lobos irmãos)

O cérebro do Hive-Mind tem **4 lobos irmãos**, não hierárquicos:

- **Córtex** (cognição superior, 5 lóbulos): temporal, frontal, parietal, occipital, ínsula
- **Cerebelo** (ritmo): sessoes, diario, semanal, padroes
- **Diencéfalo** (relay cross-projeto): setores + roteamento
- **Tronco** (infra vital): modelos, paineis, infra, meta

Ver `docs/01-architecture.md` §2 e `AGENTS.md` §2 para o detalhamento. **Nenhuma fase pode violar a anatomia** — projetos vão em **lobos apropriados** ou em **integrations/** (vendors externos, que são órgãos mas não são do cérebro central).

### 0.2 Clones de vendors externos

Cada projeto externo que vira órgão do cérebro vive em `integrations/<nome>/`:

```
integrations/
├── graphify/         # lobo occipital — clustering estrutural
├── graphiti/         # lobo temporal — causalidade com validade (commit b11d6d6)
├── neural-memory/    # córtex — spreading activation
├── rtk/              # tronco — otimização de shell
└── claude-mem-plugins/  # lobo temporal — eventos brutos
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
| Córtex occipital | Graphify | `integrations/graphify/` | `graphifyy[watch]` | clone + setup_brain.sh | ✅ |
| **Córtex temporal** | **Graphiti (FalkorDB)** | `integrations/graphiti/` | `graphiti-core`, `falkordb` | clone + Docker FalkorDB | ✅ P2 |
| **Córtex temporal** | claude-mem | `integrations/claude-mem-plugins/` | (indep, npm) | (indep) | ✅ |
| Córtex (associação) | Neural Memory | `integrations/neural-memory/` | `neural-memory[pro]` | clone + setup_brain.sh | ✅ |
| **Córtex** (RAG) | LightRAG | `core/lightrag_index.py` (não vendor) | `lightrag-hku` | `ollama pull granite3-dense:2b` | ✅ P3 |
| Tronco | RTK | `integrations/rtk/` | (indep, cargo) | cargo install | ✅ |
| Córtex | SQLite-vec | (nativo) | `sqlite-vec` | (extensão nativa) | ✅ |
| Córtex (visual) | Screenpipe | (npm) | (indep, npm) | npm install -g @screenpipe/cli | ✅ P1 |
| Córtex | Fastembed | (nativo) | `fastembed` | (fallback P0) | ✅ |

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
├── telemetry.py                   # OTEL → Langfuse (opt-in)
└── paths.py                       # constantes anatômicas (CORTEX, TEMPORAL, etc.)

integrations/
├── graphify/                      # lobo occipital
├── graphiti/                      # lobo temporal (commit b11d6d6) ✅P2
│   ├── client.py                  # 4 camadas: smoke + circuit + retry + persist
│   ├── __init__.py                # API pública + whitebox
│   └── README.md
├── neural-memory/                 # córtex (associação)
├── rtk/                           # tronco (otimização shell)
└── claude-mem-plugins/            # lobo temporal (eventos)

plugins/
├── hermes/
│   └── sinapse-memory.py            # 7 backends federados (UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem)
└── sqlite-vec-worker/worker.py      # VEC_EMBED_DIM=1024 ✅P0

scripts/
├── dream/
│   └── dream_cycle.py             # ETL: Distiller→Validator→Router→Síntese
│   └──                              # Stage 3.5: push_neuron (Graphiti) + index_memory (LightRAG) best-effort
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
                 ├── _backend_umc            # lóbulo temporal (índice SQLite consolidado)
                 ├── _backend_neural_memory # córtex (associação)
                 ├── _backend_sqlite_vec     # córtex (semântico local)
                 ├── _backend_claude_mem     # tálamo sensorial (eventos)
                 ├── _backend_graphify       # lobo occipital (estrutural)
                 ├── _backend_graphiti       # lóbulo temporal (causalidade) ✓ NOVO
                 └── _backend_filesystem     # lobo parietal (leitura)
```

**Bug corrigido:** antes do Passo 2, `sinapse_query` chamava `sm._backend_umc()` (apenas 1 backend) — quebrava a anatomia prometida. Agora chama `sm._query_vault_knowledge()` que funde os 7.

**Verificado end-to-end:** query de teste roda os 7 em paralelo, Graphiti respondeu em ~1.35s (live FalkorDB), tempo total ~1.4s sob `GLOBAL_QUERY_TIMEOUT=8s`.

**Tool `sinapse_temporal_graph_search`** marcada como DEPRECATED no docstring — clientes existentes não quebram, mas o canônico é `sinapse_query`.

### Fase P5 — Anatomia canônica em 3 documentos ✅ CONCLUÍDO

**Objetivo:** documento único de verdade para a anatomia do cérebro.
**Status:** ✅ | **Commits:** `ca1ff96`, `3eb4a35`, `ddf5504` | **Data:** 2026-06-23/24

**3 documentos sincronizados:**
- `AGENTS.md` (root) — seção 2: anatomia resumida (4 lobos + 5 lóbulos do córtex)
- `README.md` — "Anatomia do Cérebro" antes de "Visão Geral"
- `docs/01-architecture.md` — seção 2: anatomia completa (constantes, mapeamento, ferramentas)

**Nomes fictícios** (projeto-A..I, topico-1..N, setor-1..5) — projetos reais instalados pelo usuário. Root do repo limpo: `CLAUDE.md` (Ruflo config), `AGENT_BOOTSTRAP.md` (órfão) removidos em `ddf5504`.

---

## 3. Fases pendentes (P6..P10)

### Fase P6 — RAPTOR (sumário recursivo no grafo) 🔜

**Objetivo:** sumários hierárquicos do corpus — acelera queries multi-hop e melhora grounding em RAGs.

**Anatomia:** Córtex frontal (síntese). Complementa o LightRAG: enquanto LightRAG extrai entidades, RAPTOR constrói árvores de sumário que o cérebro pode consultar como contexto.

**Origem do estudo:** `docs/09-integration-study.md` §4 (RAPTOR paper, Sarthi et al. 2024).

**Tarefas (preliminares):**
- [ ] Clonar RAPTOR oficial em `integrations/raptor/`
- [ ] Criar `integrations/raptor/client.py` (wrapper recursivo)
- [ ] Conectar ao Dream Cycle: chamar `raptor.index()` após `index_memory` (LightRAG)
- [ ] Adicionar tool `sinapse_hierarchical_search` no MCP (consulta top-down)
- [ ] `pyproject.toml`: dependência Python (se houver)

**Critério de pronto:** 5+ testes (offline + live com corpus real). README no `integrations/raptor/`. Funda no `sinapse_query` como 8º backend (`_backend_raptor`).

### Fase P7 — MegaMem (Obsidian + MCP + SQLite vault unificado) 🔜

**Objetivo:** unificar vault Obsidian + MCP + SQLite como única fonte de verdade para o cérebro.
**Anatomia:** Diencéfalo (cross-projeto). MegaMem faz o que o cérebro já faz (vault + busca + MCP), mas com schema externo interoperável.
**Origem do estudo:** `docs/09-integration-study.md` §2 (MegaMem).
**Tarefas:**
- [ ] Avaliar viabilidade: o cérebro já é vault + busca + MCP. MegaMem adiciona interoperabilidade ou duplica?
- [ ] Se viável, clone em `integrations/megamem/`
- [ ] Se não, documentar em `09-integration-study.md` por que não foi adotado
**Critério de pronto:** decisão documentada (ou merge ou rejeição).

### Fase P8 — sqlite-lembed (embeddings nativos quando disponível) ⏸

**Objetivo:** embeddings 100% nativos (sem rede, sem API), quando o bug Python 3.12+ for corrigido.
**Status:** BLOQUEADO — `OperationalError: misuse of sqlite3_result_subtype()` em Python 3.12+.
**Anatomia:** Córtex (associação). Substituiria o atual `OllamaEmbedder` (HTTP).
**Origem do estudo:** `docs/09-integration-study.md` §3 (sqlite-lembed + sqlite-vec duo nativo).
**Tarefas:**
- [ ] Monitorar upstream sqlite-lembed para fix Python 3.12+
- [ ] Quando corrigido: `pip install sqlite-lembed`, `_init_lembed()` em `core/database.py`
- [ ] Migração de volta: `EMBED_BACKEND=lembed`
**Critério de pronto:** `EMBED_BACKEND=lembed` no `.env` funciona sem regressão dos 434 testes existentes.

### Fase P9 — CR-SQLite (sync multi-dispositivo) 🔜

**Objetivo:** `hive_mind.db` replicável entre dispositivos sem conflitos.
**Anatomia:** Tronco (infra vital). Sincronização é infra — não é um órgão cognitivo.
**Origem do estudo:** `docs/09-integration-study.md` §3.
**Tarefas:**
- [ ] `pip install crsqlite`
- [ ] Criar `core/crdt_sync.py` (helpers CR-SQLite)
- [ ] Integrar em `core/database.py:get_connection()` (`HIVE_CRDT_SYNC=true`)
- [ ] Criar `scripts/services/sinapse-sync.py` (CLI export/import/push/pull)
- [ ] Testar sync entre duas instâncias locais
**Critério de pronto:** dois diretórios sincronizam alterações sem perda; `pytest tests/integration/test_crdt.py` passa.
**Risco:** médio (migração de schema). Backup antes.

### Fase P10 — A-MEM (link evolution no grafo) 🔜

**Objetivo:** links entre neurônios evoluem automaticamente quando nova memória é inserida (re-linking baseado em similaridade semântica + LLM).
**Anatomia:** Diencéfalo (relay entre memórias). Complementa o Graphiti: enquanto Graphiti extrai causalidade, A-MEM sugere links associativos.
**Origem do estudo:** `docs/09-integration-study.md` §1 (A-MEM, AGI Research).
**Tarefas:**
- [ ] `pip install amem` (ou clone direto do repo agiresearch/A-mem)
- [ ] Criar `core/amem_linker.py` (wrapper A-MEM)
- [ ] Conectar ao Dream Cycle: chamar `add_and_evolve()` após `index_memory` (LightRAG)
- [ ] Persistir links sugeridos como `synapses` no SQLite
**Critério de pronto:** links novos aparecem no grafo após Dream Cycle; `pytest tests/integration/test_amem.py` passa.

---

## 4. Checklist por sprint

### Sprint 1 — P0+P1+P2+P3+P4+P5 ✅ CONCLUÍDO (2026-06-21 → 2026-06-24)
- [x] P0: bge-m3 1024d via Ollama (commit `93db445`, `f087279`)
- [x] P1: Screenpipe via REST (commit `9597ef5`)
- [x] P2: Graphiti + FalkorDB + 4 camadas robustez (commit `5d90f51`, `41fac0c`)
- [x] P2: move para `integrations/graphiti/` (commit `b11d6d6`)
- [x] P3: LightRAG no Dream Cycle com `granite3-dense:2b` (commit `dee365b`)
- [x] P4: sinapse_query funde 7 órgãos (commit `16e0387`)
- [x] P5: anatomia em 3 docs (commit `ca1ff96`, `3eb4a35`, `ddf5504`)

**Suite:** 466 testes passando, 6 falhas pré-existentes (não relacionadas).

### Sprint 2 — P6 (RAPTOR) + P7 (MegaMem decisão)
- [ ] RAPTOR: clone em `integrations/raptor/`
- [ ] RAPTOR: funde no sinapse_query como 8º backend
- [ ] MegaMem: decisão documentada (merge ou rejeição)
- [ ] 8 testes novos (4 RAPTOR + 4 MegaMem ou rejeição)

### Sprint 3 — P9 (CR-SQLite) + P10 (A-MEM)
- [ ] P9: `core/crdt_sync.py` + sync CLI
- [ ] P9: backup + migração
- [ ] P10: `core/amem_linker.py` + Dream Cycle hook
- [ ] 8 testes novos (4 CRDT + 4 A-MEM)
- [ ] **Suite esperada:** 480+ testes passando

### Sprint 4 — P8 (sqlite-lembed) quando bug for corrigido
- [ ] `pip install sqlite-lembed`
- [ ] Migração de OllamaEmbedder → lembed
- [ ] Sem regressão nos testes existentes

---

## 5. Resumo: Mapa de Arquivos por Fase

| Fase | Arquivo | Ação | Status |
|------|---------|------|--------|
| P0 | `core/database.py` | `OllamaEmbedder` HTTP | ✅ |
| P0 | `core/hnsw_index.py` | `HNSW_DIM=1024` | ✅ |
| P0 | `core/umc_schema.sql` | `FLOAT[1024]` | ✅ |
| P0 | `plugins/sqlite-vec-worker/worker.py` | `VEC_EMBED_DIM=1024` | ✅ |
| P0 | `scripts/setup/migrate_embed_dim.py` | one-shot 384→1024 | ✅ |
| P1 | `scripts/capture/parsers/screenpipe.py` | **NOVO** | ✅ |
| P1 | `scripts/capture/capture_adapters.py` | `+screenpipe` | ✅ |
| P2 | `integrations/graphiti/client.py` | **NOVO** (4 camadas) | ✅ |
| P2 | `integrations/graphiti/__init__.py` | API pública | ✅ |
| P2 | `integrations/graphiti/README.md` | anatomia | ✅ |
| P2 | `plugins/hermes/sinapse-memory.py` | `+_backend_graphiti` | ✅ |
| P2 | `docker-compose.falkordb.yml` | FalkorDB | ✅ |
| P2 | `tests/integration/test_graphiti.py` | 14 testes | ✅ |
| P3 | `core/lightrag_index.py` | **NOVO** (granite3-dense:2b) | ✅ |
| P3 | `scripts/dream/dream_cycle.py` | `+index_memory()` | ✅ |
| P4 | `scripts/services/sinapse-mcp.py` | `sinapse_query` orquestrador | ✅ |
| P5 | `AGENTS.md`, `README.md`, `docs/01-architecture.md` | anatomia em 3 docs | ✅ |
| P6 | `integrations/raptor/client.py` | **NOVO** (RAPTOR) | 🔜 |
| P6 | `plugins/hermes/sinapse-memory.py` | `+_backend_raptor` | 🔜 |
| P7 | `integrations/megamem/` (se viável) | **NOVO** | 🔜 |
| P8 | `core/database.py` | `+_init_lembed()` | ⏸ |
| P9 | `core/crdt_sync.py` | **NOVO** | 🔜 |
| P9 | `scripts/services/sinapse-sync.py` | **NOVO** CLI | 🔜 |
| P10 | `core/amem_linker.py` | **NOVO** | 🔜 |

---

## 6. Gaps conhecidos (2026-06-24)

| Gap | Onde | Workaround | Quando resolve |
|---|---|---|---|
| sqlite-lembed incompatível Python 3.12+ | P0 embeddings | `EMBED_BACKEND=ollama` (atual) | Quando upstream corrigir |
| LightRAG cobre sub-região do occipital junto com Graphify | P3 RAG | LightRAG é `core/` (não `integrations/`) por ser wrapper Python, não vendor | P6 (RAPTOR) pode consolidar |
| `sinapse_temporal_graph_search` ainda existe como tool MCP | `scripts/services/sinapse-mcp.py` | Marcada como DEPRECATED; `sinapse_query` é o canônico | Próxima release (remover) |
| `cerebro/_Consciencia.md` e MOCs auto-gerados não estão no gitignore | `generate_mocs.py` | Regenerados a cada Dream Cycle | Considerar `.gitignore` |
| `_Consciencia.md` reference pode divergir entre docs | 3 docs | Commit único sincroniza | Já resolvido em `ca1ff96` |
| Brain UI (frontend de visualização do grafo) | nenhum | Não há skill de canvas/web design no projeto | Avaliar em sprint futura |

---

## 7. Próximo passo imediato

Executar **Sprint 2** quando você confirmar:
- [ ] P6 (RAPTOR): clone + 4 testes + fundir como 8º backend
- [ ] P7 (MegaMem): decisão de merge ou rejeição (com justificativa)

Sem confirmação, não mexo.