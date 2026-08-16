# Arquitetura — Hive-Mind

> Anatomia do cérebro, Unified Memory Core (UMC), caminhos canônicos, ferramentas
> externas como órgãos, camadas e responsabilidades, fronteiras e controles.
>
> **Versão refletida:** v3.10.1 · **Referência normativa:** [`arquitetura.md`](arquitetura.md)
> (canônico) · **Desenho em uma página:** [`blueprint.md`](blueprint.md) ·
> **Fluxogramas:** [`blueprint.md`](blueprint.md)

---

## 1. Visão macro

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                          AI AGENTS                                   │
  │                                                                      │
  │  ┌────────────┐ ┌──────────┐ ┌────────┐ ┌────────┐ ┌─────────────┐  │
  │  │Claude Code │ │Codex CLI │ │Cursor  │ │Gemini  │ │Hermes/Thoth │  │
  │  │Kilo Code   │ │          │ │Aider   │ │CLI     │ │(native plugin│  │
  │  └──────┬─────┘ └─────┬────┘ └───┬────┘ └───┬────┘ └──────┬──────┘  │
  └─────────┼─────────────┼──────────┼───────────┼─────────────┼─────────┘
            │             │          │           │             │
            └──────────┬──┴──────────┘           │       (native hooks)
                       │                         │             │
                       ▼                         │             ▼
  ┌────────────────────────────────┐             │  ┌──────────────────────┐
  │  sinapse-mcp.py (MCP Server)  │             │  │ sinapse-memory.py    │
  │  16 tools · stdio JSON-RPC    │             │  │ Hermes plugin         │
  │                               │             │  │ pre_gateway_dispatch │
  │  sinapse-write.py (CLI)       │             │  │ post_tool_call       │
  │  sinapse-api.py (REST :37702) │             │  │ on_session_end       │
  └──────────────────┬────────────┘             │  └──────────┬───────────┘
                     └─────────────────────────┬┘             │
                                               │              │
                                               ▼              ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │                 UNIFIED MEMORY CORE — hive_mind.db               │
  │                                                                    │
  │  ┌──────────────┐  ┌────────────────┐  ┌───────────────────────┐  │
  │  │  neurons     │  │  observations  │  │  visual_memories      │  │
  │  │  synapses    │  │  archived: 0   │  │  document_memories    │  │
  │  │  (graph)     │  │  1=ok 2=quarant│  │  (multimodal)         │  │
  │  └──────┬───────┘  └───────┬────────┘  └───────────────────────┘  │
  │         │                  │                                        │
  │  ┌──────▼───────┐  ┌───────▼───────┐  ┌───────────────────────┐  │
  │  │  search_vec  │  │  search_fts   │  │  ambiguities          │  │
  │  │  (sqlite-vec │  │  (FTS5        │  │  (P2P conflicts)      │  │
  │  │   1024d HNSW)│  │   unicode61)  │  │  vault (secrets)      │  │
  │  └──────────────┘  └───────────────┘  └───────────────────────┘  │
  └─────────────────────────────┬──────────────────────────────────────┘
                                │                   ▲
               ┌────────────────┼──────────┐        │ reindex ~2s
               │                │          │        │
               ▼                ▼          │  ┌─────┴──────────────────┐
  ┌────────────────┐  ┌──────────────┐    │  │  Watcher (watchdog)    │
  │  Hive-Dreamer  │  │  REST API    │    │  │  + Graphify            │
  │  dream_cycle.py│  │  FastAPI     │    │  │  vault → neurons +     │
  │  (a cada 4h)   │  │  :37702      │    │  │  embeddings + FTS      │
  └───────┬────────┘  └──────────────┘    │  └────────────────────────┘
          │                               │              ▲
          ▼                               │              │ edits
  ┌───────────────────────────────────┐   │              │
  │  Obsidian Vault — cerebro/        │───┘──────────────┘
  │  cortex/  cerebelo/               │
  │  diencefalo/  tronco/             │ ◄─── Syncthing P2P (optional)
  │  portal.canvas  (source of truth) │
  └───────────────────────────────────┘
```

> **Imagens de referência:**
> ![Diagrama de arquitetura](../assets/image/architecture-diagram.png)
> ![Diagrama de arquitetura completo](../assets/image/architecture-diagram-complet.png)

---

## 2. Anatomia do cérebro

O Hive-Mind é organizado **como um cérebro**. O vault `cerebro/` espelha a anatomia — **quatro lóbulos
irmãos sob a Consciência**, e o Córtex tem **cinco sub-lóbulos próprios**.

```
                          ┌─────────────────────────────────────┐
                          │   🧠 Consciousness (Home)           │
                          │   "self" integrating the lobes      │
                          └──────────────┬──────────────────────┘
                                         │
        ┌──────────────────┬─────────────┼─────────────┬──────────────────┐
        │                  │             │             │                  │
   ┌────▼─────────┐  ┌──────▼─────┐  ┌────▼─────┐  ┌────▼────────┐  ┌────▼────────┐
   │ 🧠 CORTEX    │  │ 🥁 CEREBELLUM│ │ 🔀 DIENCEPHALON│ │ 🌿 STEM  │  │  (cortex    │
   │ (cognition) │  │ (rhythm)   │  │ (cross-   │  │ (vital     │  │   detail)  │
   │             │  │            │  │  project  │  │  infra)    │  │            │
   │ 5 sublobes: │  │ • sessoes/ │  │  relay)   │  │ • modelos/ │  │ (continues │
   │ • Temporal  │  │ • diario/  │  │            │  │ • paineis/ │  │   below)   │
   │ • Frontal   │  │ • semanal/ │  │ • setores/ │  │ • infra/   │  │            │
   │ • Parietal  │  │ • padroes/ │  │   (5)      │  │ • meta/    │  │            │
   │ • Occipital │  │            │  │ • roteamento/  │         │  │            │
   │ • Insula    │  │            │  │            │  │            │  │            │
   └─────────────┘  └────────────┘  └────────────┘  └────────────┘  └────────────┘
```

**Os quatro lóbulos sob a Consciência são pares** (Córtex, Cerebelo, Diencéfalo, Tronco) — não há
hierarquia entre eles. O Tronco **não é descendente** de nenhum outro lóbulo; é irmão.

> **Imagem de referência:** ![Anatomia do cérebro](../assets/image/brain-anatomy.png)

### 2.1 Córtex — cognição superior (5 sub-lóbulos)

```
   🧠 CORTEX
   ├── ⏱ TEMPORAL     — memória de longo prazo, eixo primário por projeto
   │       └── <projeto>/<topico>/neuronio-<hash>.md
   ├── 🎯 FRONTAL     — decisões, planejamento, trabalho ativo
   │       └── decisoes/  trabalho/{active,ativo,arquivo}/
   │           projetos/  brain/  org/{people,teams}/
   ├── 📥 PARIETAL    — sensorial (inbox, referências)
   │       └── inbox/{visual,documents}/  referencias/  analises/
   ├── 👁 OCCIPITAL   — visão (capturas + grafo de conhecimento)
   │       └── capturas-visuais/  grafo/graph.json
   └── 💓 INSULA      — interocepção, autoconsciência
           └── saude/  conflitos/
```

#### 2.1.1 Lóbulo Temporal — detalhe (eixo primário do cérebro)

O lóbulo temporal guarda a **memória de longo prazo organizada por projeto**. É o **eixo primário** do
cérebro. Estrutura genérica (projetos e tópicos são fictícios — `projeto-A`, `topico-1`, etc.):

```
cortex/temporal/
├── projeto-A/                     # project-neuron (exemplo)
│   ├── topico-1/                  # topic-neuron (1 neurônio = 1 fato atômico)
│   ├── topico-2/
│   └── topico-3/
├── projeto-B/                     # project-neuron (exemplo)
│   ├── topico-1/
│   ├── topico-2/
│   ├── topico-3/
│   ├── topico-4/
│   ├── topico-5/
│   └── topico-6/
├── projeto-C/                     # project-neuron (exemplo)
├── projeto-D/                     # project-neuron (exemplo)
├── projeto-E/                     # project-neuron (exemplo)
├── projeto-F/                     # project-neuron (exemplo)
├── projeto-G/                     # project-neuron (exemplo)
├── projeto-H/                     # project-neuron (exemplo)
├── projeto-I/                     # project-neuron (exemplo)
│
├── _global/                        # conhecimento sem projeto (preferências globais)
├── hipocampo/                      # consolidação: staging + quarentena do Dream Cycle
└── arquivo/                        # memória fria (>90d, substância profunda)
```

Cada `neuronio-<hash>.md` tem frontmatter com `integrity_hash` (SHA-256 do conteúdo) e é único por hash —
**neurônios nunca duplicam**. O índice SQLite (UMC `hive_mind.db`) acelera consultas sobre esses neurônios;
o `vault` permanece a fonte única de verdade.

### 2.2 Cerebelo — ritmo e coordenação

```
   🥁 CEREBELO
   ├── sessoes/   → logs de sessão de trabalho (YYYY/MM/YYYY-MM-DD-HHMM-{slug}.md)
   ├── diario/    → reflexões diárias (YYYY/MM/YYYY-MM-DD.md)
   ├── semanal/   → sínteses semanais (YYYY-Wxx.md)
   ├── mensal/    → sínteses mensais (YYYY-MM.md) — modelo forte
   ├── anual/     → sínteses anuais (YYYY.md) — modelo forte/batch
   └── padroes/   → padrões aprendidos (memória procedural)
       └── cerebro/cerebelo/padroes/Patterns.md  (referência canônica humana,
            mas NÃO o único neurônio de aprendizado — cada aprendizado vira um
            átomo em cortex/temporal/)
```

A cadência hierárquica (sessão → diário → semanal → mensal → anual) é o eixo temporal do cérebro
(ver [`arquitetura.md` §29](arquitetura.md)). Cada camada tem
propósito, modelo e regra de promoção próprios.

### 2.3 Diencéfalo — relé entre projetos

```
   🔀 DIENCEFALO
   ├── setores/     → conhecimento que cruza vários projetos
   │   ├── setor-1.md      ← neurônios usados por vários projetos
   │   ├── setor-2.md
   │   ├── setor-3.md
   │   ├── setor-4.md
   │   └── setor-5.md
   └── roteamento/  → regras de roteamento de conhecimento entre projetos
```

### 2.4 Tronco — infraestrutura vital (irmão dos outros 3, não descendente)

```
   🌿 TRONCO
   ├── modelos/   → templates Obsidian tipados (Atom, Work, Decision, Thinking, Cold Analysis)
   ├── paineis/   → bases Obsidian (.base) — Work Dashboard, Incidents, People, Review Evidence
   ├── infra/     → configuração de infraestrutura do vault
   └── meta/      → meta-informação do vault, sub-vaults, links entre vaults
```

### 2.5 Mapeamento lóbulo → função → componente técnico

| Lóbulo | Função | Onde vive em código/vault |
|---|---|---|
| **Córtex frontal** | Decisão, planejamento, trabalho | `core/`, `scripts/dream/dream_cycle.py` (síntese dialética), `cerebro/cortex/frontal/{decisoes,trabalho,brain,projetos,org}`, `core/knowledge/decision_promoter.py`, `core/knowledge/work_tracker.py`, MCP `save_decision`/`plan_goal` |
| **Córtex parietal** | Sensorial — inbox, referências, documentos | `scripts/capture/`, `core/knowledge/document_ingest.py` (→ `DocumentPipeline`), `cerebro/cortex/parietal/{inbox,referencias}`, `cerebro/cortex/parietal/inbox/documents/` |
| **Córtex occipital** | Visão — capturas + **grafo** | `scripts/capture/visual_capture.py`, MCP `sinapse_capture_screen` (→ `visual_memories`, `capturas-visuais/`), `integrations/graphify/` (→ `cerebro/cortex/occipital/grafo/graph.json`), estágio visual no Dream Cycle |
| **Córtex temporal** | Memória de longo prazo por projeto | `cerebro/cortex/temporal/<projeto>/<topico>/neuronio-*.md` + UMC `hive_mind.db` (indexador); `core/knowledge/claude_mem_bridge.py` (→ Dream Cycle), `core/knowledge/drift_detector.py`, `core/knowledge/topic_consolidator.py`, `core/knowledge/alias_miner.py` |
| **Córtex ínsula** | Saúde, autoconsciência, ambiguidades | `scripts/health/{health_dashboard,alert_dispatcher}.py`, `scripts/knowledge/{review_writer,conflict_detector}.py`, `cerebro/cortex/insula/{saude,conflitos}`, `core/knowledge/ambiguities.py` (síntese dialética) |
| **Cerebelo** | Ritmo — sessão, diário, semanal, mensal, anual, padrões | `scripts/dream/{session_consolidator,daily_writer,weekly_synthesizer,monthly_synthesizer,yearly_synthesizer,pattern_distiller}.py`, `cerebro/cerebelo/{sessoes,diario,semanal,mensal,anual,padroes}/` + `cerebro/cerebelo/padroes/Patterns.md` |
| **Diencéfalo** | Relé entre projetos | `core/knowledge/sector_classifier.py`, `core/knowledge/generate_mocs.py`, `cerebro/diencefalo/{setores,roteamento}` |
| **Tronco** | Infraestrutura vital | `cerebro/tronco/{modelos,paineis,infra,meta}/` — templates, bases, config, sub-vaults; mais estático que promovido |

---

## 3. Unified Memory Core (UMC)

Um único banco SQLite (`hive_mind.db`) com `sqlite-vec` carregado em runtime. Schema em
[`core/umc_schema.sql`](../core/umc_schema.sql).

### Diagrama de entidades

```
  neurons (UUID v4)              observations (UUID v4)
  ─────────────────              ──────────────────────
  id          PK                 id            PK
  label                          session_id
  type                           project
  source_file  (vault-relative)  type          decision|learning|event
  content                        title
  hash         SHA-256           content
  metadata     JSON              archived      0=pending 1=ok 2=quarantine
  community    Leiden cluster    neuron_id     FK→neurons (optional)
  visibility   private|shared|   goal_id       FK→goals (HM-11)
               public (HM-12)    why           TEXT (HM-11)
  indexed_at   TIMESTAMP (HM-11)
  created_at
  updated_at                     ambiguities (UUID v4)
       │                         ────────────────────
       │ triggers FTS sync       id            PK
       ▼                         neuron_id     FK→neurons
  search_fts (FTS5)              source_a_hash SHA-256
  ─────────────────              source_b_hash SHA-256
  neuron_id   UNINDEXED          content_a
  label                          content_b
  content                        status   pending|synthesized|branched
  tokenize=unicode61
                                 causal_edges (HM-11)
  search_vec (vec0)              ────────────────────
  ──────────────────             id             PK
  neuron_id   PK                 cause_neuron_id FK→neurons
  embedding   FLOAT[1024]        effect_neuron_id FK→neurons
                                 label, confidence, source
                                 (indexes on cause and effect)

  goals (HM-11)                  visual_memories / document_memories
  ─────────────                  ──────────────────────────────────
  id          PK                 id, path, description/summary
  description                    topics, hash (dedup), neuron_id FK
  steps_json  TEXT (JSON)
  status      active|…           vault (encrypted secrets)
  created_at                     ───────────────────────
                                 id             PK
  synapses (UUID v4)             encrypted_secret  BLOB (Fernet)
  ─────────────────              metadata          JSON
  id          PK
  source_id   FK→neurons
  target_id   FK→neurons
  relation    TEXT
  weight      FLOAT
```

### Garantias técnicas

| Garantia | Implementação |
|---|---|
| Sincronização FTS automática | triggers `AFTER INSERT/UPDATE/DELETE` em `neurons` |
| Colisão P2P impossível | UUID v4 em todas as PKs |
| Detecção de divergência | SHA-256 do conteúdo em `neurons.hash` |
| Fila auditável | `observations.archived` indexado (`idx_observations_archived`) — nunca `LIKE` em JSON |
| Performance | `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000` |

---

## 4. Caminhos canônicos (`core/paths.py`)

A anatomia é codificada em `core/paths.py`. Constantes expostas:

```python
CORTEX     = VAULT_ROOT / "cortex"      # Córtex (5 sub-lóbulos)
TEMPORAL   = CORTEX / "temporal"        # Lóbulo temporal (memória)
FRONTAL    = CORTEX / "frontal"         # Lóbulo frontal (decisão)
PARIETAL   = CORTEX / "parietal"        # Lóbulo parietal (sensorial)
OCCIPITAL  = CORTEX / "occipital"       # Lóbulo occipital (visão/grafo)
INSULA     = CORTEX / "insula"          # Lóbulo ínsula (autoconsciência)
DIENCEFALO = VAULT_ROOT / "diencefalo"  # Diencéfalo (relé)
SECTORS_ROOT = DIENCEFALO / "setores"
CEREBELO   = VAULT_ROOT / "cerebelo"    # Cerebelo (ritmo)
DAILY_ROOT, SESSIONS_ROOT, WEEKLY_ROOT, PADROES_ROOT = cerebelo/...
TRONCO     = VAULT_ROOT / "tronco"      # Tronco (infra)
META_ROOT, MODELOS_ROOT, PAINEIS_ROOT = tronco/...
```

**Regra:** qualquer código novo que crie/modifique um arquivo no vault **deve usar essas constantes**,
não caminhos hardcoded. Detalhe por lóbulo em `cerebro/cortex/cortex.md`, `cerebro/cerebelo/cerebelo.md`,
`cerebro/diencefalo/diencefalo.md`, `cerebro/tronco/tronco.md` e `cerebro/cortex/{frontal,parietal,occipital,temporal,insula}/*.md`.

---

## 5. Ferramentas externas como órgãos do cérebro

As ferramentas que alimentam o cérebro **não são bancos paralelos**. São **órgãos do mesmo cérebro**,
contribuindo para uma única percepção (a resposta de `sinapse_query` e do `RetrievalRouter`). Desde
K0–K2, a lista canônica inclui RAGFlow, Milvus e LlamaIndex como **primeira classe em adapters/contratos**,
sem transformá-los em fontes paralelas de verdade.

| Ferramenta | Órgão do cérebro | Função | Forma de integração |
|---|---|---|---|
| **UMC** (`hive_mind.db`) | Córtex (central) | Grafo + vetores + FTS5 + logs em um SQLite | **Wrapper** (diretório no repo) |
| **NeuralMemory** | Córtex (associação) | Spreading activation, memória associativa | **Clone** em `integrations/neural-memory/` (via `components.lock.json`) |
| **sqlite-vec** | Córtex (vetor local) | Indexação HNSW nativa em SQLite — local-first, offline, cache operacional | Mandatório (extensão de runtime carregada) |
| **claude-mem** | Córtex temporal (hipocampo) | `user_prompts`, `observations`, `discoveries`, `session_summaries` — fonte de evidência temporal | **Wrapper** (worker HTTP `:37700`) |
| **Graphify** | Córtex occipital (grafo estrutural) | Indexa `cerebro/` para `graph.json` com clustering Leiden | **Clone** em `integrations/graphify/` |
| **Graphiti** | Lóbulo temporal (causalidade) | Arestas com validade temporal (`valid_at`/`invalid_at`) | **Wrapper** (`integrations/graphiti/` + `docker-compose.yml` com imagem pinada por digest) |
| **LightRAG/GraphRAG** | Diencéfalo (multi-hop) | Relações multi-hop e perguntas globais | Wrapper ou pip, expansível |
| **RAGFlow** | Córtex parietal (ingestão de documentos) | Adapter para parsing layout-aware, chunking estrutural, citações | **Wrapper** headless (`integrations/ragflow/` + `ragflow-sdk`); **nunca** fonte de verdade — saída flui para `document_vectors` + UMC |
| **Milvus** | Córtex (vetor de produção) | Backend vetorial de produção para coleções grandes (multi-coleção, partição por `workspace_id`) | **Wrapper** (`integrations/milvus/` + `pymilvus`); backend oficial de produção do `VectorBackend` |
| **LlamaIndex** | Córtex (recuperação composta) | Adapter para rerank e workflows de recuperação | **Pip** (`llama-index` em `pyproject.toml`); **não** decide rota nem vira fonte de verdade |
| **Filesystem scan** | Córtex parietal (sentido imediato) | Lê o vault diretamente, sem esperar reindexação | Interno |
| **RTK** | Otimização de shell | Hooks/plugins/instruções por agente/CLI para reescrita de comandos | **Clone** em `integrations/rtk/` — **não** é read backend de `sinapse_query` |

### Os 7 backends de leitura (fused por `sinapse_query`)

O `sinapse_query` dispara os **7 órgãos de leitura** em paralelo (circuit breaker + timeout de 8s por
backend), funde via Context Fusion e devolve **um único pacote de contexto**:

| # | Backend | Papel na fusão |
|---|---|---|
| 1 | **UMC** (`hive_mind.db`) | FTS5 + vetor KNN + grafo + logs |
| 2 | **NeuralMemory** | Spreading activation (associação) |
| 3 | **sqlite-vec** | Semântico local (HNSW) |
| 4 | **claude-mem** | Eventos temporais (hipocampo) |
| 5 | **Graphify** | Estrutural (Leiden) |
| 6 | **Graphiti** | Causalidade temporal (`valid_at`/`invalid_at`) |
| 7 | **Filesystem scan** | Leitura direta do vault (TTL 30s, zero gap) |

> **Regra de vendoring (contrato negativo):** `components.lock.json` rastreia apenas **clones de fonte**
> com commit pinado — hoje `graphify`, `neural-memory`, `rtk`. `crsqlite` é vendored como **binário de
> plataforma baixado** (string de versão, não commit) e fica **fora** do lock. `omniparser` é planejado,
> ainda não implementado. Wrappers (Milvus, RAGFlow, Graphiti) entram por container/SDK; pip cobre apenas
> LlamaIndex e utilitários. Se Milvus, RAGFlow ou LlamaIndex aparecerem em `components.lock.json` nesta
> frente, a implementação está errada (ADR-018).

---

## 6. Camadas e responsabilidades

### Arquitetura em 4 camadas

```
  ┌───────────────────────────────────────────────────────────────────┐
  │                            AI AGENTS                              │
  │   Hermes (plugin) · Claude Code · Codex CLI · Cursor · OpenClaw   │
  └──────────────────────────────┬────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼────────────────────────────────────┐
  │                     INTEGRATION LAYER                             │
  │  sinapse-memory.py (plugin) · sinapse-mcp.py (MCP stdio)          │
  │  sinapse-hook.py (hook universal) · sinapse-api.py (REST :37702)  │
  │  sinapse-write.py (CLI standalone)                                │
  └──────────────────────────────┬────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼────────────────────────────────────┐
  │                       MEMORY BACKENDS                             │
  │  UMC (SQLite) · claude-mem :37700 · NeuralMemory · RTK (Rust)     │
  └──────────────────────────────┬────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼────────────────────────────────────┐
  │                           STORAGE                                 │
  │  hive_mind.db · cerebro/ (Obsidian Vault) · backups/              │
  └───────────────────────────────────────────────────────────────────┘
```

### Matriz de responsabilidades

| Componente | Responsável por | Independente de |
|---|---|---|
| `cerebro/` | Conteúdo canônico | Tudo (vault Obsidian puro funciona sem o sistema) |
| `core/` | Schema UMC, conexões, auth, schemas Pydantic | Agentes específicos |
| `graphify/` | Indexação estrutural → neurons/synapses | claude-mem, RTK |
| `~/.claude-mem` | Captura temporal global de eventos → observations | Graphify, RTK |
| `integrations/rtk/` | Reescrita de comandos de shell por agente/CLI | Tudo (hook isolado) |
| `integrations/neural-memory/` | Recuperação associativa (spreading activation) | Demais camadas |
| `scripts/` | Pipeline, servidores, operações | — |
| `plugins/hermes/` | Ponte bidirecional Hermes ↔ UMC ↔ vault | — |
| `sinapse.yaml` | Config central (paths, portas, agentes) | — |
| `install.sh` / `install.bat` | Instalação universal (12 etapas / Windows nativo) | — |
| `config/runtime.yaml` | Manifesto declarativo de serviços/jobs (control plane) | — |

---

## 7. Fronteiras e controles

| Fronteira/controle | Como é imposta | Fonte |
|---|---|---|
| **Circuit breaker** | backend com 3+ falhas consecutivas entra em cooldown 30s; só exceções/timeouts contam (resultado vazio não é falha) | §5 |
| **Quarentena** | `archived=2` (estrutural) vs `archived=0` (transitório, retry); nada é apagado por falha de promoção | ADR-016 |
| **Isolamento por workspace** | `workspace_id` em toda tabela crítica; Milvus `partition_key=workspace_id`; vazamento entre workspaces é bug de segurança | ADR-015, §30 |
| **Segredos** | detecção por regex → criptografia field-level (`vault` table, Fernet) → placeholder `[SECRET:uuid]` | §6 |
| **Redação de PII** | `core/redactor.py` — 8 categorias (tokens, email, IPv4/6, paths absolutos, chaves SSH/PEM, CPF/CNPJ, telefone), irreversível, antes do export | §19 |
| **Assinatura** | `core/signing.py` — Ed25519, payload canônico exclui campos voláteis; verificação nunca levanta exceção em assinatura inválida | §19 |
| **API fail-closed** | `sinapse-api.py` não inicia sem `HIVE_MIND_API_KEY`; rate limits por endpoint | §10 |
| **Migrations fail-closed** | falha de migração estrutural é fail-closed por default; bypass só via `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` | §30.1 |
| **Fail-closed por papel** | papel sem modelo próprio e sem herança do `dreamer` registra falha auditável e **não inventa** síntese | §29.2 |

---

## 8. Leitura complementar (docs novos)

| Tema | Documento |
|---|---|
| Desenho em uma página e ADRs com consequência | [`blueprint.md`](blueprint.md) |
| Capture → Intake → Promotion → Indexação | [`pipeline-dados.md`](pipeline-dados.md) |
| LLMs, embeddings, papéis, fallback | [`modelos-ia.md`](modelos-ia.md) |
| Control plane e daemon (`hive-mindd`, `runtime.yaml`) | [`runtime.md`](runtime.md) |
| Interface de linha de comando | [`cli.md`](cli.md) |
| Integração de agentes (MCP/plugin/hooks) | [`agentes.md`](agentes.md) |
| Captura universal de providers | [`captura.md`](captura.md) |
| Instalação (incl. Windows nativo) | [`instalacao.md`](instalacao.md) |
| Operação (cron/jobs/backup) | [`operacao.md`](operacao.md) |
| Observabilidade e métricas de saúde (K8) | [`observabilidade.md`](observabilidade.md) |
| Resposta a incidentes e recuperação | [`incidentes.md`](incidentes.md) |
| Segurança (segredos, redação, assinatura) | [`seguranca.md`](seguranca.md) |
| Como desenvolver e estender | [`desenvolvimento.md`](desenvolvimento.md) |
| Handover de estado | [`HANDOVER.md`](HANDOVER.md) |
