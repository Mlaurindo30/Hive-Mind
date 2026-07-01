# Arquitetura — Hive-Mind v3.0.0

> Referência canônica de arquitetura. Atualizado em 2026-06-30.
> Para uso rápido: [`../README.md`](../README.md)
> **Esta revisão consolida a Arquitetura de Conhecimento Born-Large (K0–K10)** definida em [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md), com plano de execução em [`12-knowledge-implementation-plan.md`](12-knowledge-implementation-plan.md).

---

## Índice

1. [Princípios de Design](#1-princípios-de-design)
1.1. [Nomenclatura](#11-nomenclatura)
2. [Anatomia do Cérebro](#2-anatomia-do-cérebro)
3. [Visão Macro do Sistema](#3-visão-macro-do-sistema)
4. [Unified Memory Core (UMC)](#4-unified-memory-core-umc)
5. [Fluxo de Leitura](#5-fluxo-de-leitura)
6. [Fluxo de Escrita](#6-fluxo-de-escrita)
7. [O Ciclo de Sonho (Hive-Dreamer)](#7-o-ciclo-de-sonho-hive-dreamer)
8. [Sincronização P2P e Fusão Semântica](#8-sincronização-p2p-e-fusão-semântica)
9. [Camada Multimodal](#9-camada-multimodal)
10. [Camada de Acesso](#10-camada-de-acesso)
11. [Autenticação Multi-Provedor](#11-autenticação-multi-provedor)
12. [Estrutura do Vault](#12-estrutura-do-vault)
13. [Automação e Cron](#13-automação-e-cron)
14. [Como Estender para Novos Agentes](#14-como-estender-para-novos-agentes)
15. [Testes e Qualidade](#15-testes-e-qualidade)
16. [Disaster Recovery](#16-disaster-recovery)
17. [Referência de Configuração](#17-referência-de-configuração)
18. [Fase HM-11: Deep Reflection](#18-fase-hm-11-deep-reflection-raciocínio-de-longo-prazo)
19. [Fase HM-12: Federated Swarm](#19-fase-hm-12-enxame-federado-federated-swarm)
20. [Decisões de Design (ADRs)](#20-decisões-de-design-adrs)
21. [Governança de Fases](#21-governança-de-fases)
22. [Arquitetura de Conhecimento Born-Large](#22-arquitetura-de-conhecimento-born-large)
23. [Fluxo de Captura → Promoção → Recuperação](#23-fluxo-de-captura--promoção--recuperação)
24. [VectorBackend: contrato, coleções canônicas e escala](#24-vectorbackend-contrato-coleções-canônicas-e-escala)
25. [DocumentPipeline (K6) — ingestao born-large](#25-documentpipeline-k6--ingestao-born-large)
26. [RetrievalRouter (K7) — roteamento por intenção](#26-retrievalrouter-k7--roteamento-por-intenção)
27. [Knowledge Promotion Pipeline (K3/K4)](#27-knowledge-promotion-pipeline-k3k4)
28. [Métricas de Saúde do Conhecimento (K8)](#28-métricas-de-saúde-do-conhecimento-k8)
29. [Cadência Hierárquica de Escrita](#29-cadência-hierárquica-de-escrita)
30. [Escala e Isolamento — Workspace e Federação](#30-escala-e-isolamento--workspace-e-federação)
31. [Contratos Pendentes (Reranker, Forget, Eval, Harness)](#31-contratos-pendentes-reranker-forget-eval-harness)
32. [Decisões de Design (ADRs)](#32-decisões-de-design-adrs)

---

## 1. Princípios de Design

1. **Fonte única de verdade legível por humanos.** O vault Obsidian (`cerebro/`) é a camada canônica. O SQLite é o índice; o Markdown é a verdade. Em caso de divergência, o auditor reconcilia a favor do vault.
2. **Local-first.** Funciona completamente offline em uma máquina. Cloud e P2P são opcionais e aditivos.
3. **Um banco, várias dimensões.** Em vez de JSON de grafo + SQLite do claude-mem + Chroma de vetores, o UMC centraliza tudo em um único `hive_mind.db`. Queries entre dimensões viram SQL simples.
4. **Agnosticismo de agente e de LLM.** Qualquer agente se conecta via MCP/CLI/REST. Qualquer LLM serve o Dream Cycle via `HIVE_DREAMER_PROVIDER/MODEL`. Nenhum modelo é hardcoded.
5. **Fail-safe, não fail-silent.** Pipeline que falha envia dados para quarentena (`archived=2`), nunca os descarta. API sem chave não inicia. Backend com 3+ falhas entra em circuit breaker (cooldown 30s).
6. **Sem sufixos de versão em arquivos, código ou schema.** Não usar `v2`, `v3`, `v4` etc. em nomes de arquivos (`umc_schema_v2.sql`), classes, funções ou tabelas. Para evolução de schema, usar sufixo semântico que descreva a propriedade (`umc_schema_crr.sql` para o schema compatível com CRR; `setup_crdt.py` em vez de `migrate_to_v2.py`). Migrações viram scripts `setup_<feature>.py` ou `migrate_<feature>.py`. **Exceção**: referências a upstream (`OmniParser v2`, `MiniLM-L6-v2`, modelos HuggingFace) mantêm o nome que o upstream usa.

---

## 2. Anatomia do Cérebro

O Hive-Mind é organizado como um cérebro. O vault `cerebro/` espelha a anatomia — **quatro lobos irmãos sob a Consciência**, e o Córtex tem **cinco lóbulos próprios**. Esta seção é **canônica** para entender onde cada peça de código mora.

```
                          ┌─────────────────────────────────────┐
                          │   🧠 Consciência (Home)             │
                          │   "eu" que integra os lobos         │
                          └──────────────┬──────────────────────┘
                                         │
        ┌──────────────────┬─────────────┼─────────────┬──────────────────┐
        │                  │             │             │                  │
   ┌────▼─────────┐  ┌──────▼─────┐  ┌────▼─────┐  ┌────▼────────┐  ┌────▼────────┐
   │ 🧠 CÓRTEX    │  │ 🥁 CEREBELO │  │ 🔀 DIENCÉFALO│  │ 🌿 TRONCO │  │  (cortex    │
   │ (cognição)  │  │ (ritmo)    │  │ (relay     │  │ (infra     │  │   detail)  │
   │             │  │            │  │  cross-    │  │  vital)    │  │            │
   │ 5 lóbulos:  │  │ • sessoes/ │  │  projeto)  │  │ • modelos/ │  │ (continua  │
   │ • Temporal  │  │ • diario/  │  │            │  │ • paineis/ │  │   abaixo)  │
   │ • Frontal   │  │ • semanal/ │  │ • setores/ │  │ • infra/   │  │            │
   │ • Parietal  │  │ • padroes/ │  │   (5)      │  │ • meta/    │  │            │
   │ • Occipital │  │            │  │ • roteamento/  │         │  │            │
   │ • Ínsula    │  │            │  │            │  │            │  │            │
   └─────────────┘  └────────────┘  └────────────┘  └────────────┘  └────────────┘
```

**Os quatro lobos sob a Consciência são pares** (Córtex, Cerebelo, Diencéfalo, Tronco) — não há hierarquia entre eles. O Tronco **não é descendente** de nenhum outro lobo; é irmão.

### 2.1 Córtex — cognição superior (5 lóbulos)

```
   🧠 CÓRTEX
   ├── ⏱ TEMPORAL     — memória de longo prazo, eixo primário por projeto
   │       └── <projeto>/<topico>/neuronio-<hash>.md
   ├── 🎯 FRONTAL     — decisões, planejamento, trabalho ativo
   │       └── decisoes/  trabalho/{active,ativo,arquivo}/
   │           projetos/  brain/  org/{people,teams}/
   ├── 📥 PARIETAL    — sensorial (inbox, referências)
   │       └── inbox/{visual,documents}/  referencias/  analises/
   ├── 👁 OCCIPITAL   — visão (capturas + grafo de conhecimento)
   │       └── capturas-visuais/  grafo/graph.json
   └── 💓 ÍNSULA      — interocepção, autoconsciência
           └── saude/  conflitos/
```

#### 2.1.1 Lóbulo Temporal — detalhe (eixo primário do cérebro)

O lóbulo temporal é onde mora a **memória de longo prazo organizada por projeto**. É o **eixo primário** do cérebro. Estrutura genérica (projetos e tópicos são fictícios — `projeto-A`, `topico-1`, etc.):

```
cortex/temporal/
├── projeto-A/                     # neurônio-projeto (exemplo)
│   ├── topico-1/                  # neurônio-tópico (1 neurônio = 1 fato atômico)
│   ├── topico-2/
│   └── topico-3/
├── projeto-B/                     # neurônio-projeto (exemplo)
│   ├── topico-1/
│   ├── topico-2/
│   ├── topico-3/
│   ├── topico-4/
│   ├── topico-5/
│   └── topico-6/
├── projeto-C/                     # neurônio-projeto (exemplo)
├── projeto-D/                     # neurônio-projeto (exemplo)
├── projeto-E/                     # neurônio-projeto (exemplo)
├── projeto-F/                     # neurônio-projeto (exemplo)
├── projeto-G/                     # neurônio-projeto (exemplo)
├── projeto-H/                     # neurônio-projeto (exemplo)
├── projeto-I/                     # neurônio-projeto (exemplo)
│
├── _global/                        # conhecimento sem projeto (preferências globais)
├── hipocampo/                      # consolidação: Dream Cycle staging + quarentena
└── arquivo/                        # memória fria (>90d, substância profunda)
```

Cada `neuronio-<hash>.md` tem frontmatter com `integrity_hash` (SHA-256 do conteúdo) e é único por hash — neurônios nunca duplicam. O índice SQLite (UMC `hive_mind.db`) acelera queries sobre esses neurônios; o `vault` continua sendo a fonte única de verdade.

### 2.2 Cerebelo — ritmo e coordenação

```
   🥁 CEREBELO
   ├── sessoes/   → logs de sessão de trabalho (YYYY/MM/YYYY-MM-DD-HHMM-{slug}.md)
   ├── diario/    → reflexões diárias (YYYY/MM/YYYY-MM-DD.md)
   ├── semanal/   → sínteses semanais (YYYY-Wxx.md)
   ├── mensal/    → sínteses mensais (YYYY-MM.md) — modelo forte
   ├── anual/     → sínteses anuais (YYYY.md) — modelo forte/batch
   └── padroes/   → padrões aprendidos (memória procedural)
       └── cerebro/cerebelo/padroes/Patterns.md  (Patterns é referência canônica humana, mas **não** o único neurônio de aprendizado — cada learning vira átomo em `cortex/temporal/`)
```

A cadência hierárquica (sessão → diário → semanal → mensal → anual) é o eixo temporal do cérebro (ver §29). Cada camada tem objetivo, modelo e regra de promoção próprios.

### 2.3 Diencéfalo — relay cross-projeto

```
   🔀 DIENCÉFALO
   ├── setores/     → conhecimento que cruza múltiplos projetos
   │   ├── setor-1.md      ← neurônios usados em vários projetos
   │   ├── setor-2.md
   │   ├── setor-3.md
   │   ├── setor-4.md
   │   └── setor-5.md
   └── roteamento/  → regras de roteamento de conhecimento entre projetos
```

### 2.4 Tronco — infra vital (irmão dos outros 3, não descendente)

```
   🌿 TRONCO
   ├── modelos/   → templates Obsidian tipados (Atom, Work, Decision, Thinking, Análise Fria)
   ├── paineis/   → bases Obsidian (.base) — Work Dashboard, Incidents, People, Review Evidence
   ├── infra/     → configuração de infraestrutura do vault
   └── meta/      → meta-informação do vault, sub-vaults, links cross-vault
```

### 2.5 Mapeamento lobo → função → componente técnico

| Lobo | Função | Onde mora no código/vault |
|---|---|---|
| **Córtex frontal** | Decisão, planejamento, trabalho | `core/`, `scripts/dream/dream_cycle.py` (síntese dialética), `cerebro/cortex/frontal/{decisoes,trabalho,brain,projetos,org}`, `core/knowledge/decision_promoter.py`, `core/knowledge/work_tracker.py`, MCP `save_decision`/`plan_goal` |
| **Córtex parietal** | Sensorial — inbox, referências, documentos | `scripts/capture/`, `core/knowledge/document_ingest.py` (→ `DocumentPipeline`), `cerebro/cortex/parietal/{inbox,referencias}`, `cerebro/cortex/parietal/inbox/documents/` |
| **Córtex occipital** | Visão — capturas + **grafo** | `scripts/capture/visual_capture.py`, MCP `sinapse_capture_screen` (→ `visual_memories`, `capturas-visuais/`), `integrations/graphify/` (→ `cerebro/cortex/occipital/grafo/graph.json`), estágio visual do Dream Cycle |
| **Córtex temporal** | Memória de longo prazo por projeto | `cerebro/cortex/temporal/<projeto>/<topico>/neuronio-*.md` + UMC `hive_mind.db` (indexador); `core/knowledge/claude_mem_bridge.py` (→ Dream Cycle), `core/knowledge/drift_detector.py`, `core/knowledge/topic_consolidator.py`, `core/knowledge/alias_miner.py` |
| **Córtex ínsula** | Saúde, autoconsciência, ambiguidades | `scripts/health/{health_dashboard,alert_dispatcher,review_writer,conflict_detector}.py`, `cerebro/cortex/insula/{saude,conflitos}`, `core/knowledge/ambiguities.py` (síntese dialética) |
| **Cerebelo** | Ritmo — sessão, diário, semanal, mensal, anual, padrões | `scripts/dream/{session_consolidator,daily_writer,weekly_synthesizer,monthly_synthesizer,yearly_synthesizer,pattern_distiller}.py`, `cerebro/cerebelo/{sessoes,diario,semanal,mensal,anual,padroes}/` + `cerebro/cerebelo/padroes/Patterns.md` |
| **Diencéfalo** | Relay cross-projeto | `core/knowledge/sector_classifier.py`, `core/knowledge/generate_mocs.py`, `cerebro/diencefalo/{setores,roteamento}` |
| **Tronco** | Infra vital | `cerebro/tronco/{modelos,paineis,infra,meta}/` — templates, bases, configuração, sub-vaults; mais estático que promovido |

### 2.6 Ferramentas externas como órgãos do cérebro

As ferramentas que alimentam o cérebro **não são bancos paralelos**. São **órgãos do mesmo cérebro** que contribuem para uma única percepção (a resposta do `sinapse_query` e do `RetrievalRouter`). A partir de K0-K2 (2026-06-30) a lista canônica inclui RAGFlow, Milvus e LlamaIndex como **primeira classe em adapters/contratos**, sem que virem fontes de verdade paralelas.

| Ferramenta | Órgão do cérebro | Função | Forma de integração |
|---|---|---|---|
| **UMC** (`hive_mind.db`) | Córtex (central) | Grafo + vetores + FTS5 + logs em um único SQLite | **Wrapper** (diretório no repo) |
| **NeuralMemory** | Córtex (associação) | Spreading activation, memória associativa | **Clone** em `integrations/neural-memory/` (via `components.lock.json`) |
| **sqlite-vec** | Córtex (vetorial local) | Indexação HNSW nativa no SQLite — local-first, offline e cache operacional | Obrigatório (extensão carregada em runtime) |
| **claude-mem** | Córtex temporal (hipocampo) | `user_prompts`, `observations`, `discoveries`, `session_summaries` — fonte de evidência temporal | **Wrapper** (worker HTTP `:37700`) |
| **Graphify** | Córtex occipital (grafo estrutural) | Indexa o `cerebro/` em `graph.json` com Leiden clustering | **Clone** em `integrations/graphify/` |
| **Graphiti** | Lóbulo temporal (causalidade) | Edges com validade temporal (`valid_at`/`invalid_at`) | **Wrapper** (`integrations/graphiti/` + `docker-compose.yml` com imagem pinada por digest) |
| **LightRAG/GraphRAG** | Diencéfalo (multi-hop) | Relações multi-hop e perguntas globais | Wrapper ou pip, expansível |
| **RAGFlow** | Córtex parietal (ingestão documental) | Adapter para parsing layout-aware, chunking estrutural, citações | **Wrapper** headless (`integrations/ragflow/` + `ragflow-sdk`); **nunca** fonte de verdade — saída flui para `document_vectors` + UMC |
| **Milvus** | Córtex (vetorial produção) | Backend vetorial de produção para coleções grandes (multi-coleção, partition por `workspace_id`) | **Wrapper** (`integrations/milvus/` + `pymilvus`); backend oficial de produção do `VectorBackend` |
| **LlamaIndex** | Córtex (retrieval composto) | Adapter para rerank e workflows de retrieval | **Pip** (`llama-index` em `pyproject.toml`); **não** decide rota nem vira fonte de verdade |
| **Filesystem scan** | Córtex parietal (sentido imediato) | Lê o vault direto, sem esperar reindexação | Interno |
| **RTK** | Otimização de shell | Hooks/plugins/instruções por agente/CLI para reescrita de comandos | **Clone** em `integrations/rtk/` — **não** é read-backend do `sinapse_query` |

> **Regra de vendorização** (contrato negativo): `components.lock.json` aceita apenas clones (`graphify`, `neural-memory`, `rtk`, `omniparser`, `crsqlite`). Wrappers (Milvus, RAGFlow, Graphiti) entram por container/SDK. Pip cobre apenas LlamaIndex e utilitários. Se Milvus, RAGFlow ou LlamaIndex aparecerem em `components.lock.json` nesta frente, a implementação está errada.

O `sinapse_query` é o ponto de entrada único do cérebro. Dispara os órgãos em paralelo (circuit breaker + timeout 8s por backend), funde via Context Fusion e devolve **um único pacote de contexto**. O `RetrievalRouter` K7 (ver §26) acrescenta a ele: classifica a intenção da query, escolhe a rota especializada (temporal, memória, documento, código, grafo, multi-hop, híbrida) e devolve `retrieval_path`, `citations`, `confidence` e `missing_context`.

**RTK** é instalado por agente/CLI (`codex`, `claude`, `gemini`, `cursor`, `hermes`, etc.) via `./scripts/services/start-rtk.sh --only <agente>`. Não é read-backend do `sinapse_query` — é otimização de shell, não participa do Context Fusion.

### 2.7 Constantes canônicas de path

A anatomia é codificada em `core/paths.py`. Constantes expostas:

```python
CORTEX     = VAULT_ROOT / "cortex"      # Córtex (5 lóbulos)
TEMPORAL   = CORTEX / "temporal"        # Lóbulo temporal (memória)
FRONTAL    = CORTEX / "frontal"         # Lóbulo frontal (decisão)
PARIETAL   = CORTEX / "parietal"        # Lóbulo parietal (sensorial)
OCCIPITAL  = CORTEX / "occipital"       # Lóbulo occipital (visão/grafo)
INSULA     = CORTEX / "insula"          # Lóbulo ínsula (autoconsciência)
DIENCEFALO = VAULT_ROOT / "diencefalo"  # Diencéfalo (relay)
SECTORS_ROOT = DIENCEFALO / "setores"
CEREBELO   = VAULT_ROOT / "cerebelo"    # Cerebelo (ritmo)
DAILY_ROOT, SESSIONS_ROOT, WEEKLY_ROOT, PADROES_ROOT = cerebelo/...
TRONCO     = VAULT_ROOT / "tronco"      # Tronco (infra)
META_ROOT, MODELOS_ROOT, PAINEIS_ROOT = tronco/...
```

Qualquer novo código que criar/modificar arquivo no vault **deve usar essas constantes**, não caminhos hardcoded. Detalhamento de cada lobo em `cerebro/cortex/cortex.md`, `cerebro/cerebelo/cerebelo.md`, `cerebro/diencefalo/diencefalo.md`, `cerebro/tronco/tronco.md` e `cerebro/cortex/{frontal,parietal,occipital,temporal,insula}/*.md`.

---

## 3. Visão Macro do Sistema

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                          AGENTES DE IA                               │
  │                                                                      │
  │  ┌────────────┐ ┌──────────┐ ┌────────┐ ┌────────┐ ┌─────────────┐  │
  │  │Claude Code │ │Codex CLI │ │Cursor  │ │Gemini  │ │Hermes/Thoth │  │
  │  │Kilo Code   │ │          │ │Aider   │ │CLI     │ │(plugin nativ│  │
  │  └──────┬─────┘ └─────┬────┘ └───┬────┘ └───┬────┘ └──────┬──────┘  │
  └─────────┼─────────────┼──────────┼───────────┼─────────────┼─────────┘
            │             │          │           │             │
            └──────────┬──┴──────────┘           │       (hooks nativos)
                       │                         │             │
                       ▼                         │             ▼
  ┌────────────────────────────────┐             │  ┌──────────────────────┐
  │  sinapse-mcp.py (MCP Server)  │             │  │ sinapse-memory.py    │
  │  15 tools · stdio JSON-RPC     │             │  │ Plugin Hermes         │
  │                               │             │  │ pre_gateway_dispatch │
  │  sinapse-write.py (CLI)        │             │  │ post_tool_call       │
  │  sinapse-api.py (REST :37702)  │             │  │ on_session_end       │
  └──────────────────┬────────────┘             │  └──────────┬───────────┘
                     └─────────────────────────┬┘             │
                                               │              │
                                               ▼              ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │                 UNIFIED MEMORY CORE — hive_mind.db                  │
  │                                                                    │
  │  ┌──────────────┐  ┌────────────────┐  ┌───────────────────────┐  │
  │  │  neurons     │  │  observations  │  │  visual_memories      │  │
  │  │  synapses    │  │  archived: 0   │  │  document_memories    │  │
  │  │  (grafo)     │  │  1=ok 2=quarent│  │  (multimodal)         │  │
  │  └──────┬───────┘  └───────┬────────┘  └───────────────────────┘  │
  │         │                  │                                        │
  │  ┌──────▼───────┐  ┌───────▼───────┐  ┌───────────────────────┐  │
  │  │  search_vec  │  │  search_fts   │  │  ambiguities          │  │
  │  │  (sqlite-vec │  │  (FTS5        │  │  (conflitos P2P)      │  │
  │  │   1024d HNSW)│  │   unicode61)  │  │  vault (segredos)     │  │
  │  └──────────────┘  └───────────────┘  └───────────────────────┘  │
  └─────────────────────────────┬──────────────────────────────────────┘
                                │                   ▲
               ┌────────────────┼──────────┐        │ reindexação ~2s
               │                │          │        │
               ▼                ▼          │  ┌─────┴──────────────────┐
  ┌────────────────┐  ┌──────────────┐    │  │  Watcher (watchdog)    │
  │  Hive-Dreamer  │  │  REST API    │    │  │  + Graphify            │
  │  dream_cycle.py│  │  FastAPI     │    │  │  vault → neurons +     │
  │  noturno       │  │  :37702      │    │  │  embeddings + FTS      │
  └───────┬────────┘  └──────────────┘    │  └────────────────────────┘
          │                               │              ▲
          ▼                               │              │ edição
  ┌───────────────────────────────────┐   │              │
  │  Vault Obsidian — cerebro/        │───┘──────────────┘
  │  cortex/  cerebelo/               │
  │  diencefalo/  tronco/             │ ◄─── Syncthing P2P (opcional)
  │  portal.canvas  (fonte de verdade)│
  └───────────────────────────────────┘
```

### Responsabilidades

| Componente | Responsável por | Independente de |
|------------|-----------------|-----------------|
| `cerebro/` | Conteúdo canônico | Tudo (vault Obsidian puro funciona sem o sistema) |
| `core/` | Schema UMC, conexões, auth, schemas Pydantic | Agentes específicos |
| `graphify/` | Indexação estrutural → neurons/synapses | claude-mem, RTK |
| `~/.claude-mem` | Captura temporal global de eventos → observations | Graphify, RTK |
| `integrations/rtk/` | Reescrita de comandos shell por agente/CLI | Tudo (hook isolado) |
| `integrations/neural-memory/` | Recall associativo (spreading activation) | Camadas restantes |
| `scripts/` | Pipeline, servidores, operação | — |
| `plugins/hermes/` | Ponte bidirecional Hermes ↔ UMC ↔ vault | — |
| `sinapse.yaml` | Configuração central (paths, portas, agentes) | — |
| `install.sh` | Instalação universal (10 etapas) | — |

---

## 4. Unified Memory Core (UMC)

Banco SQLite único (`hive_mind.db`) com extensão `sqlite-vec` carregada em runtime. Schema em [`core/umc_schema.sql`](../core/umc_schema.sql).

### Diagrama de Entidades

```
  neurons (UUID v4)              observations (UUID v4)
  ─────────────────              ──────────────────────
  id          PK                 id            PK
  label                          session_id
  type                           project
  source_file  (relativo vault)  type          decision|learning|event
  content                        title
  hash         SHA-256           content
  metadata     JSON              archived      0=pendente 1=ok 2=quarentena
  community    Leiden cluster    neuron_id     FK→neurons (opcional)
  visibility   private|shared|   goal_id       FK→goals (HM-11)
               public (HM-12)    why           TEXT (HM-11)
  indexed_at   TIMESTAMP (HM-11)
  created_at
  updated_at                     ambiguities (UUID v4)
       │                         ────────────────────
       │ triggers FTS sync        id            PK
       ▼                          neuron_id     FK→neurons
  search_fts (FTS5)               source_a_hash SHA-256
  ─────────────────               source_b_hash SHA-256
  neuron_id   UNINDEXED           content_a
  label                           content_b
  content                         status   pending|synthesized|branched
  tokenize=unicode61
                                 causal_edges (HM-11)
  search_vec (vec0)              ────────────────────
  ──────────────────             id             PK
  neuron_id   PK                 cause_neuron_id FK→neurons
  embedding   FLOAT[1024]        effect_neuron_id FK→neurons
                                 label, confidence, source
                                 (índices em causa e efeito)

  goals (HM-11)                  visual_memories / document_memories
  ─────────────                  ──────────────────────────────────
  id          PK                 id, path, description/summary
  description                    topics, hash (dedup), neuron_id FK
  steps_json  TEXT (JSON)
  status      active|…           vault (segredos cifrados)
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
|----------|---------------|
| FTS sync automático | Triggers `AFTER INSERT/UPDATE/DELETE` sobre `neurons` |
| Colisão P2P impossível | UUIDs v4 em todas as PKs |
| Detecção de divergência | SHA-256 de conteúdo em `neurons.hash` |
| Fila auditável | `observations.archived` é coluna indexada (`idx_observations_archived`) — nunca LIKE em JSON |
| Performance | `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000` |

---

## 5. Fluxo de Leitura

```
  Usuário faz pergunta
         │
         ▼
  Agente recebe query
         │
         ▼ (hook automático ou tool MCP)
  sinapse_query("pricing decision")
         │
         ├─────────────────────────────────────────────┐
         │                                             │
         ▼                                             ▼
  Busca paralela nos backends de leitura:    Filesystem scan (cerebro/*.md)
  ┌──────────────────────────────┐          cache TTL 30s
  │ UMC SQL                      │          busca direta, zero gap
  │  search_fts MATCH 'pricing'  │
  │  search_vec KNN 1024d        │
  │  neurons/synapses            │
  │  observations FTS5           │
  └──────────────────────────────┘
         │                              │
         └──────────────┬───────────────┘
                        │
                        ▼
              merge + dedup + corte top-N
              (chave: source_file + title + content)
              (rerank por relevância é contrato pendente — docs/11 §17.1)
                        │
                        ▼
              top-N resultados ≤ 3000 chars
                        │
                        ▼
              injetados no system_message
              do agente (pré-prompt)
```

**Acesso por agente:** agentes MCP chamam `sinapse_query` via tool; o plugin
Hermes pode fazer injeção automática via `pre_gateway_dispatch`. Limites:
`MAX_CONTEXT_CHARS=3000`, `MAX_NODES=5`.

**Circuit breaker:** backend com 3+ falhas consecutivas entra em cooldown 30s. Apenas exceções e timeouts contam como falha (não resultados vazios).

---

## 6. Fluxo de Escrita

```
  Agente chama sinapse_save_decision("Migrar VPS", conteúdo)
         │
         ▼
  _sanitize_slug(title)  →  "2026-06-10-migrar-vps"
         │
         ▼
  _atomic_write()
  tempfile.mkstemp() → write → os.replace()  (atômico no Linux)
         │
         ▼
  cerebro/cortex/frontal/trabalho/ativo/2026-06-10-migrar-vps.md
  ─────────────────────────────────────────────
  ---
  tags: [decision]
  status: active
  created: 2026-06-10
  source: hermes-session
  ---
  # Migrar VPS
  conteúdo...
         │
         ▼
  Watcher detecta mudança no filesystem (~2s)
         │
         ▼
  Graphify reindexa → neurons + synapses + embeddings + FTS
         │
         ▼
  Disponível para qualquer agente na próxima consulta

  SINAIS DE APRENDIZADO detectados em paralelo:
  "aprendizado"|"learning"|"insight"|"padrão"|"pattern"|"lição"
         │
         ▼
  append em cerebro/cerebelo/padroes/Patterns.md (com dedup por título)

  ao final da sessão:
  sinapse_session_end() → cerebro/cortex/frontal/brain/Current State.md atualizado
                        → observation de fechamento no UMC
```

**Segredos detectados** (regex API keys, `sk-proj-*`, etc.) → cifrados em nível de campo (tabela `vault`, Fernet) → substituídos por placeholder no conteúdo final.

---

## 7. O Ciclo de Sonho (Hive-Dreamer)

`scripts/dream/dream_cycle.py` — consolidação offline com saída Pydantic validada. **A partir de K3/K4 (2026-06-28/29) o ciclo é estruturado em camadas distintas** (ver §27 e [`11-knowledge-promotion-architecture.md` §3](11-knowledge-promotion-architecture.md#3-preenchimento-por-parte-do-cérebro)):

```
  ┌────────────────────────────────────────────────────────────────┐
  │                      ESTÁGIO 0 — CAPTURA                        │
  │                                                                │
  │  Capture Layer:                                                 │
  │    - hooks (Claude Code, Codex, Kilo, …)                       │
  │    - MCP / CLI / browser / documentos / código / screenshots    │
  │    - runtime events (sessões, tools, métricas)                  │
  │       │                                                       │
  │       ▼                                                       │
  │  ESTÁGIO 0.5 — HIPOCAMPO TEMPORAL (claude-mem)                 │
  │    user_prompts · observations · discoveries · session_summaries│
  │    facts · narrative · concepts · files_read / files_modified   │
  │    prompt_number · generated_by_model                           │
  │       │                                                       │
  │       ▼                                                       │
  │  ESTÁGIO 1 — KNOWLEDGE INTAKE (core/knowledge/intake.py, K3)   │
  │    - normaliza campos (preserva source_id, project, workspace)  │
  │    - extrai evidência / arquivos / timestamps                   │
  │    - classifica knowledge_type                                  │
  │    - deduplica por source_id + hash de conteúdo                 │
  │       │                                                       │
  │       ▼                                                       │
  │  ESTÁGIO 2 — PROMOTION LAYER (core/knowledge/promotion.py, K4) │
  │    Distiller (DistillerOutput Pydantic)                         │
  │      "extraia fatos estruturados destas observações"             │
  │       │                                                       │
  │       ▼                                                       │
  │    Validator (ValidatorOutput Pydantic)                         │
  │      "estes fatos são suportados pelos logs originais?"         │
  │       │ aprovado           │ reprovado → feedback → Distiller  │
  │       ▼                                                       │
  │    Router (RouterOutput Pydantic)                               │
  │      "para qual projeto/tópico do lóbulo temporal cada fato vai?"│
  │       │                                                       │
  │       ▼                                                       │
  │  Arquivo anatômico + UPSERT neuron + vector_backend.upsert()    │
  │  observation.neuron_id = neuron.id;  archived=1                 │
  │  falha estrutural → archived=2 (quarentena, jamais perdido)     │
  └──────────────────────┬─────────────────────────────────────────┘
                          │ roteamento bem-sucedido
  ┌──────────────────────▼─────────────────────────────────────────┐
  │              ESTÁGIO 2.5 — PERSISTÊNCIA ANATÔMICA               │
  │                                                                │
  │  cérebro/cortex/temporal/<projeto>/<topico>/neuronio-*.md      │
  │  cérebro/cortex/frontal/{decisoes,trabalho,brain,projetos,org}  │
  │  cérebro/cortex/{parietal,occipital,insula}/...                │
  │  cérebro/cerebelo/{sessoes,diario,semanal,mensal,anual,padroes} │
  │  cérebro/diencefalo/setores/<setor>.md                          │
  │                                                                │
  │  Escrita atômica via tempfile + os.replace(); SHA-256 do         │
  │  conteúdo; embedding 1024d (snowflake-arctic-embed2);          │
  │  workspace_id obrigatório em tudo; metadata canônica            │
  │  (parent_id, brain_lobe, knowledge_type, source_uri, valid_at).  │
  └──────────────────────┬─────────────────────────────────────────┘
                          │
  ┌──────────────────────▼─────────────────────────────────────────┐
  │      ESTÁGIO 3 — INDEXAÇÃO MULTI-COLEÇÃO (FTS + Vetor + Grafo)  │
  │                                                                │
  │  - FTS5 (search_fts, tokenize=unicode61)                       │
  │  - VectorBackend.upsert() em memory_vectors/observation_vectors │
  │  - Graphiti: push_neuron (causal_edges com valid_at/invalid_at)│
  │  - LightRAG: index_memory (entidades + relações)                │
  │  - Graphify: reindexa o grafo estrutural se algo mudou          │
  └──────────────────────┬─────────────────────────────────────────┘
                          │
  ┌──────────────────────▼─────────────────────────────────────────┐
  │      ESTÁGIO 4 — SÍNTESE DIALÉTICA (Fase 9)                    │
  │                                                                │
  │  SELECT ambiguities WHERE status='pending'                     │
  │       │                                                       │
  │  semantic_diff (vetorial + LLM)                                │
  │       ├── complemento → merge → conteúdo unificado            │
  │       ├── contradição → choose → versão com evidência         │
  │       └── irreconciliável → branch → preserva ambas           │
  │       │                                                       │
  │       ▼                                                       │
  │  status='synthesized' | 'branched'                             │
  └──────────────────────┬─────────────────────────────────────────┘
                          │
  ┌──────────────────────▼─────────────────────────────────────────┐
  │     ESTÁGIO 5 — PUSH PARA GRAFOS DE CONHECIMENTO (P2 + P4)     │
  │                                                                │
  │  Para cada neuron sintetizado:                                 │
  │    1. push_neuron()   → Graphiti/FalkorDB (temporal)           │
  │    2. index_memory()  → LightRAG (entidades + relações)        │
  │                                                                │
  │  Ambos best-effort: try/except, nunca abortam a síntese.       │
  │  Graphiti: grafo temporal causal (queries "quem influenciou X")│
  │  LightRAG: grafo de entidades + busca híbrida (queries multi-  │
  │            hop que FTS5 + KNN não resolvem)                    │
  └────────────────────────────────────────────────────────────────┘
```

**Garantias:**
- Arquivamento somente após roteamento bem-sucedido
- OAuth expirado dispara refresh automático (timeout polling: 300s)
- Determinismo de hash: cada fato persistido carrega SHA-256 do conteúdo
- `call_llm_structured()` valida o JSON retornado pelo LLM com `model_validate_json()`
- **Push para grafos** (Estágio 5) é best-effort: falha do Graphiti ou LightRAG não impede a síntese dialética de ser marcada como `synthesized`. Logs vão para `[LightRAG]` no stdout.
- **Regra de promoção automática** (K3/K4): permitido para `decision`, `learning`, `project_status`, `operational_fact`, `goal/task` e `rationale` — todos com fonte rastreável. Proibido: transformar todo bullet em fact, criar neurônio sem fonte, vetorizar duplicatas sem `parent_id`, promover opinião temporária como decisão arquitetural, sobrescrever decisões anteriores sem criar conflito ou `invalid_at`.
- **Falha de promoção preserva dados**: erro transitório → `archived=0` (retry); erro estrutural → `archived=2` (quarentena com motivo). Nada é deletado por falha de promoção.

**Cadência de writers** (ver §29): sessão/diário usam modelo pequeno; semanal usa modelo médio/forte; mensal/anual usam modelo forte ou batch offline. Cada papel é configurável em `setup-brain` e herda do `dreamer` quando ausente.

---

## 8. Sincronização P2P e Fusão Semântica

```
  Máquina A           Syncthing (P2P)         Máquina B
  ─────────           ───────────────         ─────────
  edita atlas/        ──────────────►          recebe arquivo
  pricing/fato.md                              (mesmo arquivo
                                               editado offline)
                                                    │
                                               audit_memory.py
                                               hash do arquivo ≠
                                               hash do neuron
                                                    │
                                               INSERT ambiguities
                                               (content_a, content_b
                                                source_a_hash,
                                                source_b_hash,
                                                status='pending')
                                                    │
                                               dream_cycle.py
                                               semantic_diff
                                                    │
                             ┌──────────────────────┤
                             │                      │
                        complemento          contradição factual
                             │                      │
                           merge               choose (logic_applied)
                        conteúdo único          versão com evidência
                             │                      │
                             └───────────┬──────────┘
                                         │
                                    status='synthesized'
                                    .md atualizado
                                    neuron atualizado
```

**Pré-requisitos:**

| Mecanismo | Implementação |
|-----------|---------------|
| IDs sem colisão | UUID v4 em todas as PKs |
| Detecção de divergência | SHA-256 de conteúdo em `neurons.hash` |
| Transporte | Syncthing (sem servidor central) |
| Reconciliação vault ↔ SQLite | `audit_memory.py --fix` |
| Classificação de conflitos | `semantic_diff.py` (vetorial + LLM) |
| Resolução autônoma | `dream_cycle.py` estágio de síntese |

Setup completo em [`07-p2p-sync-setup.md`](07-p2p-sync-setup.md).

---

## 9. Camada Multimodal

```
  ENTRADA                    PROCESSAMENTO              SAÍDA
  ───────                    ─────────────              ─────
  visual_capture.py          dream_cycle.py             visual_memories
  tool sinapse_capture_screen  estágio visual           (id, image_path,
  screenshot (mss)      ───►  LLM Vision               description,
                              VisionAnalysis Pydantic    ocr_text,
                              (descrição + OCR)         neuron_id)

  document_ingest.py         dream_cycle.py             document_memories
  PDF (PyMuPDF)         ───►  estágio docs              (id, file_path,
  DOCX (python-docx)          resumo + tópicos          file_hash UNIQUE,
                              → fila observations        summary, topics)

  generate_portal.py         compõe memórias visuais    cerebro/portal.canvas
                             e conceitos do UMC    ───►  (Obsidian Canvas)
```

O estágio multimodal roda **dentro** do Dream Cycle — imagens e documentos entram na mesma fila de consolidação que os logs.

---

## 10. Camada de Acesso

### 9.1 MCP Server (`scripts/services/sinapse-mcp.py`)

stdio JSON-RPC, compatível com qualquer cliente MCP.

| Tool | Assinatura | Função |
|------|-----------|--------|
| `sinapse_query` | `(query, limit?)` | Busca híbrida: FTS5 + vetores + grafo + filesystem |
| `sinapse_save_decision` | `(title, content)` | Decisão → `cerebro/cortex/frontal/trabalho/ativo/YYYY-MM-DD-slug.md` |
| `sinapse_save_learning` | `(title, content)` | Aprendizado → `cerebro/cerebelo/padroes/Patterns.md` |
| `sinapse_health` | `()` | Status de todos os backends |
| `sinapse_session_end` | `(summary?)` | Fecha sessão, atualiza Current State |
| `sinapse_temporal_search` | `(query, limit?, project?)` | Etapa 1 claude-mem: índice compacto com IDs/títulos |
| `sinapse_temporal_timeline` | `(anchor? ou query?, depth_before?, depth_after?, project?)` | Etapa 2 claude-mem: janela cronológica ao redor de um ID/query |
| `sinapse_temporal_get_observations` | `(ids, orderBy?, limit?, project?)` | Etapa 3 claude-mem: detalhes completos só dos IDs filtrados |
| `sinapse_temporal_save` | `(content, type?)` | Observação (fallback: vault) |
| `sinapse_zettelkasten_split` | `(file_path)` | Nota monolítica → notas atômicas Zettelkasten |
| `sinapse_capture_screen` | `(description?)` | Screenshot → `visual_memories` |
| `sinapse_plan_goal` | `(goal, context?)` | Decompõe objetivo em passos atômicos e salva no Intent Memory |
| `sinapse_temporal_graph_search` | `(query, num_results?)` | Grafo temporal Graphiti/FalkorDB — arestas com `valid_at`/`invalid_at` (P2) |
| `sinapse_rag_query` | `(question, mode?)` | Consulta híbrida no grafo LightRAG (entidades + relações) — multi-hop, alimentado pelo Dream Cycle (P4) |
| `search_memories` | `(query, top_k?, project?, mode?)` | Busca HNSW/FTS sobre o vault |

Total: **15 tools**. Registro/instructions automáticos via `register-mcp.sh`.

**Fonte única de instruções operacionais:** `config/sinapse-agent-prompt.md`.
- Carregado por `scripts/services/sinapse-mcp.py:_load_instructions()` (L38–53) e exposto como `instructions` no `initialize` do MCP.
- Injetado em `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `.github/copilot-instructions.md` / `.cursor/rules/hive-mind.md` via `register-mcp.sh:inject_instructions()` (L325–351), entre marcadores `<!-- BEGIN HIVE-MIND SINAPSE -->` / `<!-- END HIVE-MIND SINAPSE -->`.
- Corrigir o prompt é a única ação necessária para propagar a política operacional para todas as instalações limpas futuras.

**Configs MCP por agente** (registro via `scripts/setup/register-mcp.sh`):
Claude Code: `<projeto>/.mcp.json` (escopo project, `claude mcp add -s project` — **não** `~/.claude/.mcp.json`) · Codex: `~/.codex/config.toml` + `~/.codex/mcp.json` · Cursor: `~/.cursor/mcp.json` · Gemini: `~/.gemini/settings.json`

### 9.2 Plugin Hermes (`plugins/hermes/sinapse-memory.py`)

```python
def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", _pre_prompt_build)   # leitura automática
    ctx.register_hook("post_tool_call",       _post_tool_use)      # escrita automática
    ctx.register_hook("on_session_end",       _post_session_end)   # fechamento
```

Único componente que conhece todas as camadas. Circuit breaker embutido (3 falhas → cooldown 30s). `health_check()` retorna status de todos os backends.

### 9.3 CLI standalone (`scripts/services/sinapse-write.py`)

`decision` · `learning` · `query` · `health` · `session-end` — para agentes sem MCP.

### 9.4 REST API (`scripts/services/sinapse-api.py`)

FastAPI, porta `HIVE_MIND_API_PORT` (default **37702**). Fail-closed sem `HIVE_MIND_API_KEY`.

```
  ┌────────────────────────┬────────┬────────┬──────────┬────────────────────────────────────────────┐
  │ Endpoint               │ Método │ Auth   │ Rate     │ Descrição                                  │
  ├────────────────────────┼────────┼────────┼──────────┼────────────────────────────────────────────┤
  │ /api/v1/health         │ GET    │ —      │ 60/min   │ Health check                               │
  │ /api/v1/observations   │ POST   │ Bearer │ 20/min   │ Nova observação                            │
  │ /api/v1/query          │ POST   │ Bearer │ 30/min   │ Busca híbrida                              │
  │ /api/v1/semantic/…     │ GET    │ Bearer │ —        │ Vizinhos semânticos                        │
  │ /api/v1/vault/{id}     │ GET    │ Bearer │ 10/min   │ Segredo cifrado                            │
  │ /api/v1/neurons/export │ POST   │ Bearer │ 10/min   │ Export neurônios shared/public (HM-12)     │
  └────────────────────────┴────────┴────────┴──────────┴────────────────────────────────────────────┘
```

---

## 11. Autenticação Multi-Provedor

`PROVIDERS_CONFIG` em `core/auth.py` é o registro mestre de provedores. A lista ativa é definida no código e inclui provedores de API, provedores locais e pontes CLI/OpenAI-compatible.

| Provedor | Auth | Env var |
|----------|------|---------|
| google | API key + OAuth loopback | `GOOGLE_API_KEY` / `GOOGLE_OAUTH_CLIENT_*` |
| antigravity | CLI OAuth reaproveitado | `ANTIGRAVITY_UNUSED` |
| gemini-cli | CLI OAuth reaproveitado | `GEMINI_CLI_UNUSED` |
| omniroute | gateway local OpenAI-compatible | `OMNIROUTE_API_KEY` |
| openai | API key + OAuth Codex-handshake | `OPENAI_API_KEY` |
| anthropic | API key | `ANTHROPIC_API_KEY` |
| deepseek | API key | `DEEPSEEK_API_KEY` |
| openrouter | API key | `OPENROUTER_API_KEY` |
| nvidia | API key | `NVIDIA_API_KEY` |
| huggingface | API key | `HF_TOKEN` |
| qwen | API key | `DASHSCOPE_API_KEY` |
| lmstudio | local (sem chave) | — |
| ollama | local (sem chave) | — |

**Capacidades comuns:** refresh automático de token OAuth, timeout de polling 300s, descoberta de modelos em tempo real (`discover_models_realtime()`), nenhuma credencial hardcoded.

### 11.1 Resolução de LLM por papel (`get_role_config`)

Cada estágio do sistema que chama LLM tem um **papel** com configuração própria. Papéis canônicos atuais (constante `HIVE_LLM_ROLES` em `core/auth.py`): `dreamer`, `graphify`, `vision`, `synthesis`, `claude_mem`, `session_summarizer`, `daily_writer`, `alias_miner`, `topic_router`, `sector_classifier`, `weekly_synthesizer`, `monthly_synthesizer`, `yearly_synthesizer`, `drift_detector`, `decision_promoter`, `project_synthesizer`, `pattern_distiller`, `conflict_detector`, `graphiti`, `lightrag`. A função aceita qualquer nome de papel (case-insensitive, `-` vira `_`); nome vazio ou não-string levanta `ValueError`.

```python
get_role_config(role: str) -> Optional[Dict[str, Optional[str]]]
# retorna {"provider", "model", "fallback_provider", "fallback_model"}
# ou None se nem o papel nem o Dreamer estiverem configurados
```

**Variáveis de ambiente por papel** (lidas exclusivamente de `os.environ` — o `.env` é carregado por dotenv no `dream_cycle.py`):

| Papel | Primário | Fallback (opcional) |
|-------|----------|---------------------|
| Dreamer (base de herança) | `HIVE_DREAMER_PROVIDER` / `HIVE_DREAMER_MODEL` | `HIVE_DREAMER_FALLBACK_PROVIDER` / `HIVE_DREAMER_FALLBACK_MODEL` |
| Graphify | `HIVE_GRAPHIFY_PROVIDER` / `HIVE_GRAPHIFY_MODEL` | `HIVE_GRAPHIFY_FALLBACK_PROVIDER` / `HIVE_GRAPHIFY_FALLBACK_MODEL` |
| Vision | `HIVE_VISION_PROVIDER` / `HIVE_VISION_MODEL` | `HIVE_VISION_FALLBACK_PROVIDER` / `HIVE_VISION_FALLBACK_MODEL` |
| Síntese P2P | `HIVE_SYNTHESIS_PROVIDER` / `HIVE_SYNTHESIS_MODEL` | `HIVE_SYNTHESIS_FALLBACK_PROVIDER` / `HIVE_SYNTHESIS_FALLBACK_MODEL` |
| Claude Mem | `HIVE_CLAUDE_MEM_PROVIDER` / `HIVE_CLAUDE_MEM_MODEL` | `HIVE_CLAUDE_MEM_FALLBACK_PROVIDER` / `HIVE_CLAUDE_MEM_FALLBACK_MODEL` |
| Memória viva/inteligente | `HIVE_{ROLE}_PROVIDER` / `HIVE_{ROLE}_MODEL` | `HIVE_{ROLE}_FALLBACK_PROVIDER` / `HIVE_{ROLE}_FALLBACK_MODEL` |

**Regras de resolução:**

```
  HIVE_{ROLE}_PROVIDER + HIVE_{ROLE}_MODEL definidos (par COMPLETO)?
       │
       ├── Sim → usa o primário do próprio papel
       │          fallback: apenas o HIVE_{ROLE}_FALLBACK_* explícito
       │          (NUNCA herda o fallback do Dreamer) — sem ele, fallback=None
       │
       └── Não (par incompleto ou ausente)
             → herda HIVE_DREAMER_PROVIDER/MODEL
             → sem HIVE_{ROLE}_FALLBACK_* próprio, herda também
               HIVE_DREAMER_FALLBACK_PROVIDER/MODEL
```

- O fallback só vale como **par completo** PROVIDER+MODEL; par incompleto é tratado como ausente (`None`).
- **Chaves de API nunca são duplicadas por papel:** são sempre resolvidas via `PROVIDERS_CONFIG` pelo nome do provedor (`GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, ...).

### 11.2 Cliente LLM unificado (`core/llm_client.py`)

Módulo que centraliza as chamadas estruturadas (antes embutidas no `dream_cycle.py`):

| Função/Classe | Papel |
|---------------|-------|
| `call_llm_structured(...)` | Chamada com JSON Schema + validação Pydantic (movida do `dream_cycle.py`) |
| `classify_llm_error(exc)` | Classifica exceção em `"validation"` \| `"auth"` \| `"transient"` |
| `call_llm_with_fallback(role, ...)` | Aplica a política de retry/fallback do papel |
| `LLMValidationError` | Saída da LLM reprovada pela validação Pydantic |

Política de retry/fallback por classe de erro: ver tabela em [`02-ai-models.md`](02-ai-models.md). Ao alternar de modelo, o log registra: `[Fallback] Papel 'X': alternando de A/B para C/D`.

---

## 12. Estrutura do Vault

```
  cerebro/
  ├── _Consciencia.md
  ├── cortex/
  │   ├── temporal/<projeto>/<topico>/neuronio-*.md
  │   ├── frontal/{decisoes,projetos,trabalho,brain,org}/
  │   ├── parietal/{inbox,referencias,analises}/
  │   │   └── inbox/documents/        ← pais de document_chunks (K6)
  │   ├── occipital/{capturas-visuais,grafo}/
  │   │   └── grafo/graph.json      ← Graphify canônico
  │   └── insula/{saude,conflitos}/
  ├── cerebelo/{sessoes,diario,semanal,mensal,anual,padroes}/
  │   └── padroes/Patterns.md
  ├── diencefalo/{setores,roteamento}/
  └── tronco/{modelos,paineis,infra,meta}/
```

**Convenção crítica (K3/K4):** arquivo grande pode existir para leitura humana, mas a unidade de busca é atômica. `Patterns.md` é referência humana consolidada; cada aprendizado real precisa virar `type=learning` individual em `cortex/temporal/`. Da mesma forma, `document_chunks` no UMC é a unidade atômica; o documento-pai (em `inbox/documents/`) é o contexto recuperável.

Convenções: frontmatter YAML obrigatório (`tags`, `status`, `created`); WikiLinks criam `synapses` no grafo; decisões ficam em `cerebro/cortex/frontal/trabalho/ativo/`; padrões em `cerebro/cerebelo/padroes/`; capturas explícitas em `cerebro/cortex/parietal/inbox/visual/`. Diretórios de agente e lixeira migrada ficam sob `cerebro/tronco/infra/` e são excluídos da indexação por `.graphifyignore` e pelas exclusões compartilhadas em `core/vault_excludes.py`. Diretórios de UI/artefatos ainda permitidos no topo (`.obsidian/`, `.smart-env/`) também são excluídos da indexação.

---

## 13. Automação e Cron

| Processo | Trigger | Ação |
|----------|---------|------|
| Watcher (`start-watcher.sh`) | daemon contínuo | Obsidian → SQLite em ~2s |
| `build-graph.sh` | `0 */6 * * *` | Reindexação de segurança (cache SHA-256) |
| `cron/sync-diario.sh` | `0 2 * * 0` | Rebuild completo `--force` (logs rotacionados, últimos 30) |
| `dream_cycle.py` | noturno (recomendado) | Consolidação de memória |
| `audit_memory.py` | pós-sync P2P | Reconciliação vault ↔ SQLite |
| `alias_miner.py` | ciclo de memória | Mineração de aliases (slugs) para neurônios |

---

## 14. Como Estender para Novos Agentes

```
  1. sinapse.yaml
     ─────────────
     agents:
       supported:
         - seu-agente           ← adicionar aqui
       install_methods:
         seu-agente: "..."

  2. install.sh
     ─────────────
     AGENT_DETECTORS+=([seu-agente]="seu-agente")
     # no case "$agent":
     seu-agente)
         cp skills/sinapse-consulta.md ~/.seu-agente/skills/

  3. config/mcp/seu-agente.json (template)
     ───────────────────────────────────
     {
       "mcpServers": {
         "sinapse-memory": {
           "command": "python3",
          "args": ["<SINAPSE_HOME>/scripts/services/sinapse-mcp.py"]
         }
       }
     }

  4. Teste mínimo
     ─────────────
     Agente consegue chamar sinapse_query + sinapse_save_decision?
     → Integração completa.
```

---

## 15. Testes e Qualidade

```bash
./tests/run_all.sh   # Smoke → Unit → Integration → E2E
```

| Suíte | Local | LLM real? | O que cobre |
|-------|-------|-----------|-------------|
| Smoke | `tests/smoke/` | Não | Binários, health do sistema |
| Unit | `tests/unit/` | **Não** | Backends (mocks HTTP/subprocess), helpers de escrita, fila Dream Cycle, regressões auditoria |
| Integration | `tests/integration/` | Backends reais | Fluxos leitura/escrita, MCP, API, busca híbrida |
| E2E | `tests/e2e/` | Backends reais | Sessão completa, degradação graceful, concorrência, recovery, edge cases |
| Síntese | `tests/test_synthesis.py` | **Sim** | `run_synthesis_cycle()` com modelo real do `.env` |

O conjunto de testes é dinâmico; em 2026-07-01 havia **706 funções `test_`
em 123 arquivos com testes**. Use `rg -n "^\s*(async\s+def|def)\s+test_"
tests | wc -l` e `rg -l "^\s*(async\s+def|def)\s+test_" tests | wc -l`
para medir o estado atual. Regra: testes unitários nunca chamam LLM —
testam a lógica ao redor do modelo, não o modelo.

---

## 16. Disaster Recovery

```bash
./scripts/utils/recover.sh
```

1. Verifica/reconstrói índice do grafo
2. Verifica integridade do backup (`hive_mind.db.bak`)
3. Reinicia worker claude-mem
4. Health check HTTP (:37700)
5. Verifica carregamento do plugin

**Variáveis operacionais:**

| Variável | Descrição | Default |
|----------|-----------|---------|
| `SINAPSE_HOME` | Raiz do projeto | `~/Documentos/Projects/Hive-Mind` |
| `SINAPSE_DRY_RUN` | Sem side effects | `false` |
| `SINAPSE_LOG_JSON` | Logs em JSON | `false` |
| `SINAPSE_DECISION_TOOLS` | Tools que disparam escrita (csv) | `memory_add,observation_add,...` |
| `SINAPSE_LEARNING_SIGNALS` | Sinais de aprendizado (csv) | padrão pt/en/es |

---

## 17. Referência de Configuração

`sinapse.yaml` — schema resumido com comentários no próprio arquivo:

```yaml
project:        # nome, versão, descrição
vault:          # path (cerebro/), format (obsidian), language, indexer, watch
graphify:       # package, install_method, extras, output_dir=cerebro/cortex/occipital/grafo, mcp_port
claude_mem:     # port (37700), install_method, worker_autostart
neural_memory:  # package, src_dir, recall_timeout
rtk:            # source_dir, binary, wrapper, targets global/project
sinapse_mcp:    # command, transport (stdio), tools (lista de 15)
agents:         # supported[], integration_methods, install_methods
mcp_servers:    # graphify, claude_mem, sinapse_memory
cloud:          # enabled, url, api_key  ← chaveamento local→VPS
hybrid_search:  # backends[], filesystem (categories, cache_ttl=30s), dedup
cron:           # sync_schedule ("0 */6 * * *"), rebuild_schedule ("0 2 * * 0")
```

---

*Histórico de fases e entregas: [`PROJECT_STATUS.md`](../PROJECT_STATUS.md) · [`IMPLEMENTATION.md`](../IMPLEMENTATION.md) · [`docs/plans/`](plans/)*

---

## 18. Fase HM-11: Deep Reflection (Raciocínio de Longo Prazo)

### Intent Memory (goal_id / why)

Cada observação pode agora carregar as colunas `goal_id` (FK para a tabela `goals`) e `why` (motivo textual). O `DistillerOutput` (`core/schemas/dream_models.py`) também expõe esses dois campos opcionais, de modo que cada conjunto de fatos extraídos numa sessão do Dream Cycle fica vinculado ao objetivo ativo que os motivou.

### Agente Planner (`scripts/planner.py`)

Decomposição de objetivos em passos atômicos via LLM com saída Pydantic validada.

| Função | Assinatura | O que faz |
|--------|-----------|-----------|
| `decompose_goal` | `(goal, context?) → list[dict]` | Chama o LLM com prompt estruturado; retorna lista de passos `{id, action, why, depends_on}`; em caso de falha retorna passo fallback com o objetivo original |
| `save_goal` | `(goal, steps, db_conn?) → goal_id` | Persiste objetivo e JSON dos passos na tabela `goals`; cria a tabela se não existir (idempotente) |

Schemas: `GoalStep` (id, action, why, depends_on) e `GoalPlan` (lista de GoalStep). O tool MCP `sinapse_plan_goal` expõe os dois numa chamada só (`goal` obrigatório, `context` opcional).

### Grafo de Causalidade (`core/database.py`)

Tabela `causal_edges` registra relações causa→efeito entre neurônios. A função `get_causal_neighbors(conn, neuron_id, hops=2)` faz BFS multi-hop retornando `[{neuron_id, label, confidence}]`. Índices em `cause_neuron_id` e `effect_neuron_id` para queries eficientes. Migração aplicada automaticamente via `ensure_migrations()`.

### Índice HNSW Incremental (`core/hnsw_index.py`)

Índice vetorial baseado em `hnswlib` (coseno, 1024 dimensões por padrão via `HNSW_DIM`), persistido em `hnsw_neurons.idx` na mesma pasta do `hive_mind.db`. Degrada gracefully se `hnswlib` não estiver instalado (aviso de log, sem crash).

| Função | O que faz |
|--------|-----------|
| `load_or_create(dim?)` | Carrega índice do disco ou cria novo (max_elements=10 000, M=16, ef_construction=200) |
| `add_neuron(neuron_id, vector, conn?)` | Adiciona/atualiza vetor; marca `indexed_at` no DB se conn fornecido; expande o índice automaticamente quando cheio |
| `search(query_vector, k=10)` | Retorna top-k vizinhos `[{neuron_id, distance}]` |
| `rebuild_from_db(conn, embed_fn)` | Reconstrói índice completo a partir de todos os neurônios com conteúdo |
| `incremental_update(conn, embed_fn)` | Indexa apenas neurônios com `indexed_at IS NULL`; persiste ao disco se indexou ao menos um |

---

## 19. Fase HM-12: Enxame Federado (Federated Swarm)

### Modelo de Visibilidade

Coluna `visibility TEXT DEFAULT 'private'` em `neurons`. Três valores possíveis:

| Valor | Significado |
|-------|-------------|
| `private` | Exclusivo da máquina local — nunca exportado |
| `shared` | Pode ser exportado para outros nós confiáveis |
| `public` | Pode ser exportado irrestritamente |

O endpoint de export filtra automaticamente para `visibility IN ('shared', 'public')`.

### Endpoint de Export (`POST /api/v1/neurons/export`)

Requer Bearer token + rate-limit 10/min. Corpo da requisição:

```json
{
  "filters": { "type": "fact", "created_after": "2026-01-01" },
  "sign": false,
  "redact": true
}
```

Retorna `{ neurons, count, exported_at, schema_version: "1.0" }`. Redação ativada por padrão (`redact=true`). Assinatura desativada por padrão (`sign=false`).

### Assinatura Ed25519 (`core/signing.py`)

Chaves PEM armazenadas em `config/keys/` (`SINAPSE_HOME/config/keys/`). Chave privada criada com `chmod 0600`.

| Função | O que faz |
|--------|-----------|
| `generate_keypair(name="default")` | Gera par Ed25519 e persiste como `{name}_privkey.pem` / `{name}_pubkey.pem`; retorna `{name, fingerprint, pubkey_path}` |
| `load_private_key(name)` / `load_public_key(name)` | Carrega PEM do disco |
| `sign_neuron(neuron, key_name)` | Retorna cópia do neurônio com `_signature` (base64 Ed25519) e `_pubkey_fingerprint` (SHA-256 hex do DER público) |
| `verify_neuron(neuron, pubkey)` | Verifica assinatura; retorna `True`/`False`; nunca levanta em assinatura inválida |
| `fingerprint(pubkey)` | SHA-256 hex do DER da chave pública |

O payload canônico exclui campos voláteis (`created_at`, `updated_at`, `indexed_at`) e campos de assinatura para garantir determinismo entre nós.

### Redação de PII (`core/redactor.py`)

Redação irreversível aplicada ao `content` e `label` dos neurônios antes do export. Neurônios locais nunca são modificados.

| Função | O que faz |
|--------|-----------|
| `redact_for_export(text)` | Aplica todas as regras em sequência; retorna novo string sem PII |
| `redact_neuron(neuron)` | Deep-copy do dict; redige `content` e `label`; demais campos passam intactos |

8 categorias de regras (ordem importa — mais específicas antes):
1. Tokens de API (`sk-*`, `GOCSPX-*`, `ghp_*`, JWTs, `Bearer …`)
2. E-mails
3. IPv4
4. IPv6
5. Paths absolutos (`/home/`, `/root/`, `/Users/`, `/var/`)
6. Blocos de chave privada SSH/PEM
7. CPF / CNPJ (antes de telefone para evitar sobreposição)
8. Telefones (broad pattern, roda por último)

---

## 20. Decisões de Design (ADRs) — placeholder

> O conteúdo dos ADRs foi movido para [§32](#32-decisões-de-design-adrs) (a numeração cresceu após a integração da Arquitetura de Conhecimento Born-Large). As seções §21 e §22 abaixo foram preservadas.

---

### ADR-001 — Vault Obsidian como fonte única de verdade

**Decisão:** vault Obsidian com frontmatter YAML + WikiLinks como storage primário.
**Rationale:** formato plain-text Markdown é git-friendly, agnóstico de ferramenta e legível por humanos sem software especial. Obsidian é editor maduro com graph view, backlinks e plugin ecosystem.
**Trade-off:** dependência do Watcher para manter SQLite sincronizado; Obsidian é opcional (vault funciona sem ele).

### ADR-002 — Busca híbrida paralela

**Decisão:** busca paralela em 7 backends/órgãos (UMC, NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem — ver §2.6) com fusão e deduplicação cross-backend.
**Rationale:** FTS5 encontra termos exatos; vetores encontram conceitos similares; grafo encontra conexões; filesystem garante dados recém-escritos (zero gap). Nenhum backend sozinho cobre todos os casos.
**Trade-off:** ligeiramente maior consumo de I/O; mitigado por circuit breaker (cooldown 30s após 3+ falhas).

### ADR-003 — MCP como protocolo universal de integração

**Decisão:** expor tools via MCP stdio em vez de criar plugins específicos por agente.
**Rationale:** MCP é padrão aberto adotado por Anthropic, OpenAI, GitHub e comunidade. Um único server (`sinapse-mcp.py`) serve todos os agentes sem adaptação.
**Trade-off:** menos integração automática (hooks) que plugins nativos; compensado por CLI e hooks externos (SessionStart, PostToolUse, Stop).

### ADR-004 — Atomic writes via os.replace()

**Decisão:** `tempfile.mkstemp()` + `os.replace()` em vez de `open().write()`.
**Rationale:** `os.replace()` é atômico no Linux (rename(2) syscall) — se o processo morrer durante a escrita, o arquivo destino permanece íntegro (o tmp fica orphan, não o destino).
**Trade-off:** ligeiramente mais complexo; complexidade justificada para dados de memória persistente.

### ADR-005 — Cloud Memory API (FastAPI :37702)

**Decisão:** microsserviço REST leve em FastAPI protegido por Bearer token para deploy em VPS.
**Rationale:** permite que agentes locais usem memória hospedada num VPS sem precisar do vault físico local. Fail-closed: não inicia sem `HIVE_MIND_API_KEY`.
**Trade-off:** requer rede estável; fallback automático para modo local quando `cloud.enabled=false`.

### ADR-006 — Saída estruturada Pydantic no Dream Cycle

**Decisão:** todas as chamadas LLM usam JSON Schema derivado dos modelos Pydantic; a resposta é validada com `model_validate_json()`.
**Rationale:** garante que qualquer provider (Ollama local ou Anthropic cloud) produza estrutura processável; loop de feedback (Validator reprova → Distiller reprocessa) aumenta qualidade sem intervenção humana.
**Trade-off:** adiciona uma chamada LLM de validação por execução do pipeline.

### ADR-007 — UUID v4 em todas as PKs

**Decisão:** migração de IDs sequenciais para UUID v4 em todas as tabelas do UMC.
**Rationale:** IDs sequenciais colidem entre máquinas distintas no cenário P2P (máquina A e B ambas criam `id=1`). UUID v4 tem probabilidade de colisão de 1 em 10^36.
**Trade-off:** IDs menos legíveis em logs; irrelevante para uso programático.

### ADR-008 — Quarentena em vez de descarte

**Decisão:** pipeline que falha seta `archived=2` em vez de deletar ou ignorar a observação.
**Rationale:** dados de memória são valiosos; falhas temporárias (rede indisponível, saldo de API zerado) não devem causar perda permanente de contexto.
**Trade-off:** acúmulo de dados em quarentena requer limpeza periódica manual ou automatizada.

### ADR-009 — Configuração de LLM por papel com herança e fallback explícito

**Decisão:** cada papel que consome LLM (`dreamer`, `graphify`, `vision`, `synthesis`) tem configuração própria via `HIVE_{ROLE}_PROVIDER/MODEL`, com herança do Dreamer quando ausente e fallback **opt-in** via `HIVE_{ROLE}_FALLBACK_PROVIDER/MODEL`. Resolução centralizada em `get_role_config()` (`core/auth.py`); chamadas e política de retry/fallback centralizadas em `core/llm_client.py`.
**Rationale:** os papéis têm perfis opostos — extração de entidades (milhares de chamadas baratas e frequentes) e síntese dialética (poucas chamadas que exigem raciocínio forte) não podem ser servidos pelo mesmo modelo sem desperdício ou perda de qualidade. A **cascata automática de provedores foi rejeitada** por violar a soberania do usuário: a Síntese Dialética decide qual versão da memória é a verdade e não pode trocar de modelo silenciosamente. O fallback existe apenas quando o usuário o define explicitamente. Falha de **validação Pydantic nunca dispara fallback** — é problema de qualidade da saída, não de disponibilidade; trocar de modelo às cegas mascararia o problema. Chaves de API permanecem uma por provedor (nunca por papel), evitando duplicação de segredos.
**Trade-off:** mais variáveis de ambiente (até 16 com fallbacks); mitigado pela herança — o caso mínimo continua sendo 2 variáveis (`HIVE_DREAMER_PROVIDER/MODEL`).

### ADR-010 — Pipeline de Promoção de Conhecimento em camadas (K3/K4)

**Decisão:** separar o pipeline de promoção em **Knowledge Intake** (normalização/classificação/deduplicação) e **Promotion Layer** (Distiller → Validator → Router → Persistência → Indexação), implementados em `core/knowledge/intake.py` e `core/knowledge/promotion.py`. A bridge do claude-mem é canônica em `core/knowledge/claude_mem_bridge.py` (caminho SQL read-only que aceita `source_id` e janela temporal).

**Rationale:** a versão anterior do Dream Cycle fazia tudo num único estágio; separar intake e promotion torna a promoção **idempotente**, **testável** sem LLM real, e expõe o modo `candidate-only` (saída `candidate` sem persistência) para orquestração. A promoção nunca é 1-a-1 — é em batch com fila e prioridade por workspace (§30.5). Tipos canônicos de conhecimento (§27.2) e regras de promoção automática/proibida (§27.3) viram contrato, não heurística.

**Trade-off:** mais código upfront; mitigado pelo retorno de `KnowledgePromotionPipeline` em modo `candidate-only` para callers que não querem persistir.

### ADR-011 — Coleções vetoriais canônicas separadas (K1)

**Decisão:** o `VectorBackend` opera sobre **sete coleções canônicas** — `memory_vectors`, `observation_vectors`, `document_vectors`, `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors` — cada uma com metadata canônica (`parent_id`, `parent_type`, `brain_lobe`, `knowledge_type`, `project`, `source_uri`, `hash`, `valid_at`, `workspace_id`). Backends oficiais: `sqlite_vec` (local/dev/offline) e `milvus` (produção).

**Rationale:** uma única coleção "tudo" polui ranking e torna impossível medir cobertura por tipo. A separação permite gate de produção por coleção (§28), poda seletiva (esquecer `document_chunks` órfãos não mexe em `memory_vectors`) e versionamento de modelo de embedding por coleção (§30.4).

**Trade-off:** mais tabelas UMC; mitigado por `vector_metadata` auxiliar e identidade de coleção `(name, embedding_model, dim)`.

### ADR-012 — VectorBackend: contrato único, múltiplos backends

**Decisão:** toda a aplicação acessa o vetorial via contrato `upsert/delete/query/hybrid_query/count/health`, independente do backend. Milvus, sqlite-vec, e qualquer futuro backend obedecem o mesmo contrato. **A aplicação nunca chama Milvus diretamente fora do contrato.**

**Rationale:** trocar `sqlite_vec` por `milvus` (e vice-versa) passa a ser mudança de configuração, não de código. Permite que o mesmo `DocumentPipeline`, `RetrievalRouter` e `KnowledgePromotionPipeline` rodem em dev (sqlite-vec) e produção (Milvus) sem分支.

**Trade-off:** o contrato precisa ser estável; mudanças de schema em Milvus exigem migração versionada de embedding (§30.4).

### ADR-013 — DocumentPipeline com parent/chunk/citation obrigatório (K6)

**Decisão:** todo documento ingerido vira um `document_memories` (pai) com `document_chunks` (átomos) e entradas em `document_vectors` (vetores com metadata canônica). Consulta devolve **citações auditáveis** (`source_uri`, offsets, parent), não apenas "melhor trecho".

**Rationale:** sem parent, chunk é texto solto — não tem como auditar nem deduplicar nem reingerir. A separação `documento / chunk / vetor` é o que torna o K6 born-large. RAGFlow entra como adapter/headless, nunca como fonte de verdade; o store dele é cache de ingestão.

**Trade-off:** mais metadados por vetor; mitigado pelo índice auxiliar `vector_metadata` e schema fixo do Milvus.

### ADR-014 — RetrievalRouter classifica intent antes de buscar (K7)

**Decisão:** o `RetrievalRouter` (`core/retrieval/router.py`) é a porta de entrada para queries; ele classifica a intenção, escolhe a rota especializada (temporal, memória, documento, código, grafo, multi-hop, híbrida) e devolve `retrieval_path`, `citations`, `confidence` e `missing_context`. LlamaIndex entra apenas como adapter opcional de rerank; não decide rota nem vira fonte de verdade.

**Rationale:** o `sinapse_query` funde 7 órgãos sem entender a intenção — bom para busca ampla, ruim para precisão. O router explicitamente roteia "decisão" para `memory_vectors`, "documento" para `document_vectors`+parent, "código" para `code_vectors`+Graphify, etc. A telemetria `query_route_distribution` (hash da query, não texto) alimenta a métrica de saúde K8.

**Trade-off:** classificadores de intenção podem errar; mitigado por fallback para `sinapse_query`/Context Fusion quando a confiança é baixa, e por métrica `intent_accuracy` no golden set (§31.3).

### ADR-015 — Workspace como fronteira de isolamento (K8/§30)

**Decisão:** toda tabela crítica do UMC (`neurons`, `observations`, `synapses`, `goals`, `document_memories`, `visual_memories`, `ambiguities`, `causal_edges`, `vault`) carrega `workspace_id` (default `'default'`). Toda query do `RetrievalRouter` e da promoção filtra por `workspace_id`. Milvus usa `partition_key=workspace_id` para isolamento por partição.

**Rationale:** o Hive-Mind nasce single-user local-first, mas o produto é open-source com vetor de escala per-install, multi-usuário por instância e federação entre instâncias. Adicionar `workspace_id` depois custaria migração estrutural — agora é uma coluna. Vazamento cross-workspace é bug de segurança, não de ranking.

**Trade-off:** toda query precisa carregar `workspace_id`; mitigado por `(workspace_id, ...)` nos índices quentes e por default `'default'` (não atrapalha single-user).

### ADR-016 — Falha de promoção preserva dados, nunca descarta

**Decisão:** o contrato de promoção distingue explicitamente erro transitório (`archived=0`, retry futuro) e erro estrutural (`archived=2`, quarentena com motivo). Nada é deletado por falha de promoção. O `Knowledge Intake` (K3) é a primeira camada a usar esse contrato; o `Promotion Layer` (K4) o enforça.

**Rationale:** dados de memória são valiosos; falhas temporárias (rede indisponível, saldo de API zerado, schema novo) não devem causar perda permanente. O contract normativo é fail-safe, não fail-silent.

**Trade-off:** acumula quarentena; mitigado por `K8 knowledge_health` expondo `observations_pending` e `discoveries_pending` como gate, e por pipeline de reprocessamento manual/automático.

### ADR-017 — Cadência hierárquica sessão→anual com papéis de LLM próprios

**Decisão:** a memória temporal é organizada em **cinco cadências** (sessão, diário, semanal, mensal, anual) com writers, entradas, saídas, modelos e regras de promoção próprios. Cada cadência tem um papel de LLM configurável (`session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer`, `yearly_synthesizer`) e herda do `dreamer` se não houver override. Fail-closed: papel sem modelo próprio nem herança registra falha auditável e não inventa síntese.

**Rationale:** mensal e anual produzem memória estratégica (metas, drift, princípios) que não pode ser gerada por modelo pequeno sem rebaixar qualidade. Sessão e diário podem usar modelo pequeno porque a tarefa é compressão local. Custo/qualidade por cadência é o desenho correto.

**Trade-off:** mais papéis para configurar; mitigado pelo `setup-brain` que aceita herança do `dreamer` para o caso mínimo.

### ADR-018 — Contrato negativo de vendorização via `components.lock.json`

**Decisão:** o `components.lock.json` aceita apenas **clones** do source que o `install.sh` builda/patcha (`graphify`, `neural-memory`, `rtk`, `omniparser`, binário `crsqlite`). Wrappers (Milvus, RAGFlow, Graphiti) entram por container/SDK; pip cobre apenas LlamaIndex e utilitários. Se Milvus, RAGFlow ou LlamaIndex aparecerem em `components.lock.json` nesta frente, a implementação está errada.

**Rationale:** regras claras de quem é clone e quem é wrapper reduzem ambiguidade operacional. O contrato é também negativo (declara o que **não** pertence ali) para evitar regressão.

**Trade-off:** manutenção do lock file; mitigado por ser gerado por `install.sh` e revisado em PR.

---

## 21. Governança de Fases

### Namespace de Fases

Cada projeto usa um prefixo único para evitar colisão de numeração:

| Projeto | Prefixo | Exemplo |
|---------|---------|---------|
| Hive-Mind | `HM-` | HM-10, HM-11, HM-12 |
| Thoth | `TH-` | TH-33, TH-34 |
| Ruflo | `RF-` | RF-01, RF-02 |

### Regra de Conclusão de Fase

Nenhuma fase pode ser marcada como `✅ Concluída` sem:

1. **Commit** — todos os arquivos da entrega versionados no git
2. **Teste** — pelo menos um teste cobrindo o caminho principal da entrega
3. **CI verde** — suíte de testes passando no momento do merge

Violações desta regra foram a causa da divergência entre estado declarado e estado real identificada na auditoria de 2026-06-10.

### Status Atual das Fases HM- e K-

| Fase | Nome | Status | Ref. |
|------|------|--------|------|
| HM-01 a HM-09 | Fundação (UMC, busca, P2P, síntese) | ✅ Concluída | — |
| HM-10 | Deep Portal (multimodal) | ✅ Concluída | — |
| HM-11 | Deep Reflection (raciocínio longo prazo) | ✅ Concluída | — |
| HM-12 | Federated Swarm (compartilhamento seletivo) | ✅ Concluída | — |
| K0 | `VectorBackend` contrato (sqlite-vec + adapter Milvus) | ✅ Concluída | §24, [11-§9](../11-knowledge-promotion-architecture.md#9-contrato-vectorbackend) |
| K1 | Separação de coleções canônicas + metadata canônica | ✅ Concluída | §24, [11-§8](../11-knowledge-promotion-architecture.md#8-estrategia-de-vector-search) |
| K2 | `DocumentPipeline` (K6) parent/chunk/citation | ✅ Concluída | §25, [11-§10](../11-knowledge-promotion-architecture.md#10-documentpipeline-born-large) |
| K3 | Knowledge Intake (intake.py) | ✅ Concluída | §27, [11-§5](../11-knowledge-promotion-architecture.md#5-fluxo-ideal-de-promocao) |
| K4 | Promotion Layer (promotion.py) + bridge claude-mem | ✅ Concluída | §27, [11-§6](../11-knowledge-promotion-architecture.md#6-claude-mem-nao-e-apenas-dado-bruto) |
| K5 | Cadência hierárquica sessão→anual | ✅ Concluída | §29, [11-§14](../11-knowledge-promotion-architecture.md#14-cadencia-hierarquica-de-escrita) |
| K6 | `DocumentPipeline` parent/chunk/citation | ✅ Concluída | §25 |
| K7 | `RetrievalRouter` (router.py) | ✅ Concluída (v3.5.0, 2026-06-30) | §26, [11-§11](../11-knowledge-promotion-architecture.md#11-retrievalrouter-born-large) |
| K8 | Métricas de saúde (knowledge_health.py) | ✅ Concluída (v3.6.0, 2026-06-30) | §28, [11-§13](../11-knowledge-promotion-architecture.md#13-metricas-de-saude) |
| K9 | Harness real de aceite (`tests/real/`) | ✅ Contrato (implementação em [12-§17.4](../11-knowledge-promotion-architecture.md#174-harness-real-e-skip-de-servicos)) | §31.4 |
| K10 | Born-large (workspace, federação, embedding versionado) | ✅ Contrato | §30 |

### Arquivos de Vault com Convenção Antiga

Os seguintes arquivos em `cerebro/cortex/frontal/trabalho/ativo/` usam a numeração antiga sem prefixo e devem ser
renomeados na próxima edição manual do vault (NÃO pelo git — o vault é sincronizado pelo Syncthing):

- `2026-06-01-PHASE-33-TTS-Integration-Closeout-Final.md` (prefixo correto: TH-33)
- `2026-06-02-PHASE-34-Disk-Cache-persistente-para-TTS-design-rationale-e.md` (prefixo correto: TH-34)
- `2026-06-02-PHASE-34-FFmpeg-Transcoding-no-Thoth-Telegram-Voice-Bubble.md` (prefixo correto: TH-34)
- `2026-05-30-Implementacao-das-4-Fases-do-Sinapse-Agent.md` (fases do Sinapse Agent sem prefixo de projeto)

---

## 22. Arquitetura de Conhecimento Born-Large

O Hive-Mind não é apenas um RAG local — é um **cérebro persistente** com captura temporal, memória consolidada, documentos, código, visão, grafo estrutural, causalidade temporal e busca híbrida/ vetorial. A arquitetura de conhecimento deve **separar captura, promoção, armazenamento, indexação e recuperação desde o início** — sem depender de refatoração estrutural posterior para suportar Milvus, pipelines documentais avançados ou roteadores compostos.

A referência normativa detalhada vive em [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md), e o plano de execução detalhado por fases (K0–K10) vive em [`12-knowledge-implementation-plan.md`](12-knowledge-implementation-plan.md). As seções §23–§31 deste documento **destilam** aquela referência canônica no nível arquitetural.

### 22.1 Decisão de produto

| Ferramenta | Papel no Hive-Mind | Status arquitetural |
|---|---|---|
| RAGFlow | Adapter/headless para ingestão documental, parsing layout-aware, chunking, citações | primeira classe no `DocumentPipeline` |
| Milvus | Backend vetorial de produção para coleções grandes (multi-coleção, partition por `workspace_id`) | primeira classe no `VectorBackend` |
| LlamaIndex | Adapter para rerank e workflows de retrieval composto | primeira classe no `RetrievalRouter` |
| sqlite-vec | Backend local/dev/offline e cache operacional | obrigatório para local-first |
| claude-mem | Hipocampo temporal: `user_prompts`, `observations`, `discoveries`, `session_summaries` | obrigatório |
| Graphify | Grafo estrutural de vault/código | obrigatório |
| Graphiti | Causalidade e validade temporal (`valid_at`/`invalid_at`) | obrigatório |
| LightRAG/GraphRAG | Relações multi-hop e perguntas globais | obrigatório/expandível |

### 22.2 Regra final

O Hive-Mind deve ser:

```text
local-first por operação
born-large por arquitetura
plugavel por contrato
anatomico por fonte de verdade
auditable por evidência
```

Nenhum backend externo pode substituir o cérebro. Backends externos **aceleram, escalam ou especializam índices**. A verdade continua no vault anatômico (`cerebro/`) e no UMC. O `components.lock.json` é também um **contrato negativo**: se Milvus, RAGFlow ou LlamaIndex aparecerem ali nesta frente, a implementação está errada — eles entram por wrapper/compose+SDK e pip, respectivamente.

### 22.3 Vendorização: clone vs wrapper vs pip

- **Clone** (`integrations/<nome>/` via `components.lock.json`): só o que o `install.sh` builda/patcha do source — `graphify`, `neural-memory`, `rtk`, `omniparser`, binário `crsqlite`.
- **Wrapper** (`client.py` + `docker-compose.yml` com imagem pinada por digest): serviço rodado via container/SDK — `graphiti`, **Milvus** (`pymilvus`), **RAGFlow** (`ragflow-sdk`, headless).
- **Pip**: **LlamaIndex** (`llama-index` em `pyproject.toml`).

Milvus e RAGFlow **não são clonados**. RAGFlow roda headless: resultado flui para `document_vectors` + UMC; o store dele é cache de ingestão, não fonte de verdade.

### 22.4 Resumo das seções derivadas

| Seção | Conteúdo |
|---|---|
| [§23](#23-fluxo-de-captura--promoção--recuperação) | Fluxo de 9 etapas (Capture → Temporal → Intake → Promotion → Anatomical → Index → Retrieval → Answer+Citation → Feedback) |
| [§24](#24-vectorbackend-contrato-coleções-canônicas-e-escala) | Contrato `VectorBackend` e 7 coleções canônicas |
| [§25](#25-documentpipeline-k6--ingestao-born-large) | `DocumentPipeline` (K6): `document_memories` + `document_chunks` + `document_vectors` |
| [§26](#26-retrievalrouter-k7--roteamento-por-intenção) | `RetrievalRouter` (K7): rotas por intenção, contrato de retorno |
| [§27](#27-knowledge-promotion-pipeline-k3k4) | `Knowledge Intake` + `Promotion Layer` (K3/K4) |
| [§28](#28-métricas-de-saúde-do-conhecimento-k8) | Métricas de saúde K8 e gate de produção |
| [§29](#29-cadência-hierárquica-de-escrita) | Cadência sessão → anual com papéis e modelos por cadência |
| [§30](#30-escala-e-isolamento--workspace-e-federação) | `workspace_id`, partição de coleções, federação inter-instância, migração de embedding |
| [§31](#31-contratos-pendentes-reranker-forget-eval-harness) | Reranker, Esquecimento intencional, Avaliação de retrieval, Harness real |

---

## 23. Fluxo de Captura → Promoção → Recuperação

O fluxo canônico de 9 etapas (extraído de [`11-knowledge-promotion-architecture.md` §2](11-knowledge-promotion-architecture.md#2-fluxo-completo)):

```text
Agente / Humano / Sistema
        |
        v
[1] Capture Layer
    hooks, MCP, CLI, browser, documentos, codigo, screenshots, runtime
        |
        v
[2] Temporal Hippocampus (claude-mem)
    user_prompts · observations · discoveries · session_summaries
    facts / narrative / concepts · files_read / files_modified
        |
        v
[3] Knowledge Intake (core/knowledge/intake.py — K3)
    normaliza · classifica · deduplica · preserva evidência
        |
        v
[4] Promotion Layer (core/knowledge/promotion.py — K4)
    raw -> summary -> fact / learning / decision / preference / task / rationale
        |
        v
[5] Anatomical Memory
    cerebro/ + UMC:
      cortex temporal · frontal · parietal · occipital · insula
      cerebelo · diencefalo · tronco
        |
        v
[6] Index Layer
    FTS · sqlite-vec · Milvus · vec_observations · Graphify · Graphiti · LightRAG
        |
        v
[7] Retrieval Router (core/retrieval/router.py — K7)
    escolhe temporal · memoria · documento · codigo · grafo · chunk · hibrido
        |
        v
[8] Answer + Citation
    resposta com fonte, evidência, caminho e data
        |
        v
[9] Feedback
    nova observação, decisão, aprendizado ou tarefa
```

**Regras de borda** (normativas):

1. Cada etapa é fracamente acoplada: falha na [4] não bloqueia [1]–[3] (a observação volta com `archived=0` ou `archived=2`).
2. Cada writer declara contrato de escrita explícito (§27.3): cria observação? arquivo anatômico? neurônio? vetor? edge? task/goal? evidência? idempotency key?
3. Nada é deletado por falha de promoção: erro transitório → `archived=0` (retry); erro estrutural → `archived=2` (quarentena com motivo).

---

## 24. VectorBackend: contrato, coleções canônicas e escala

### 24.1 Contrato

Todo backend vetorial implementa o mesmo contrato (`core/vector_backend.py`):

```text
upsert(collection, id, vector, metadata)
delete(collection, id)
query(collection, vector, top_k, filters)
hybrid_query(collection, text, vector, filters)
count(collection, filters)
health()
```

A aplicação **nunca** chama Milvus diretamente fora do contrato. Isso evita trocar a anatomia do cérebro por detalhe de infraestrutura.

### 24.2 Coleções canônicas

O Hive-Mind **separa coleções por tipo de conteúdo** — não coloca tudo no mesmo ranking:

| Coleção | Conteúdo | Backend local | Backend produção |
|---|---|---|---|
| `memory_vectors` | facts, decisions, learnings, preferences | UMC `hive_mind.db/search_vec` | Milvus |
| `observation_vectors` | claude-mem observations/discoveries | `~/.claude-mem/claude-mem.db/vec_observations` (sqlite-vec, read-only) | Milvus |
| `document_vectors` | document chunks/vault docs | UMC `vec_documents` + `vector_metadata` | Milvus |
| `code_vectors` | code symbols/files | UMC `vec_code` + `vector_metadata` | Milvus |
| `visual_vectors` | screenshots/visual descriptions | UMC `vec_visual` + `vector_metadata` | Milvus |
| `graph_vectors` | entity/relation summaries | UMC `vec_graph` + `vector_metadata` | Milvus + graph |
| `summary_vectors` | resumos de cadência (sessão→anual) | UMC `vec_summary` + `vector_metadata` | Milvus |

`sqlite-vec` é obrigatório para local-first/offline. Milvus é backend de produção, **não substitui a fonte de verdade** — apenas escala o índice vetorial.

### 24.3 Metadata canônica por item vetorial

Cada item carrega: `parent_id`, `parent_type`, `brain_lobe`, `knowledge_type`, `project`, `source_uri`, `hash`, `valid_at`, `workspace_id`. No UMC, coleções auxiliares guardam esses campos em `vector_metadata`; no Milvus, viram campos obrigatórios do schema. O modelo e a dimensão do embedding são controlados pelo contrato global: `snowflake-arctic-embed2:latest`, **1024d**, salvo override explícito por env.

### 24.4 Backends oficiais

| Backend | Papel |
|---|---|
| `sqlite_vec` | local/dev/offline/cache — obrigatório |
| `milvus` | produção/escala/multi-coleção — primeira classe |

---

## 25. DocumentPipeline (K6) — ingestao born-large

Inspirado em RAGFlow, mas **preservando a anatomia do Hive-Mind** (K6 implementado em `core/knowledge/document_pipeline.py`):

```text
document input
        |
        v
parse layout-aware
        |
        v
normalize
        |
        v
chunk by structure
        |
        v
metadata + citations
        |
        v
embedding
        |
        v
document_vectors + parent document
        |
        v
optional promotion to facts/learnings (via KnowledgePromotionPipeline)
```

### 25.1 Três níveis para evitar "texto solto"

| Nível | Tabela/coleção | Conteúdo | Por que existe |
|---|---|---|---|
| Documento-pai | `document_memories` | `document_id`, `source_uri`, `file_hash`, `project`, `workspace_id`, metadata | Prova de origem e unidade de reingestão |
| Chunk | `document_chunks` | `parent_id`, `parent_type=document`, `chunk_index`, `heading`, offsets, `hash`, metadata | Unidade atômica recuperável |
| Vetor | `document_vectors` | embedding do chunk + metadata canônica | Busca semântica local/Milvus sem perder parent context |

Metadados obrigatórios em `document_vectors`: `parent_id`, `parent_type=document`, `brain_lobe=parietal`, `knowledge_type=document_chunk`, `project`, `source_uri`, `hash`, `valid_at`, `workspace_id`. Sem esses campos, o vetor é considerado incompleto para o desenho K6.

### 25.2 Consulta com parent context

```text
query
  -> document_vectors
  -> document_chunks
  -> document_memories
  -> citations[{source_uri, offset_start, offset_end, score, parent}]
```

O retorno **não pode** ser apenas "melhor trecho": precisa carregar o trecho, score, `source_uri`, offsets e parent completo o suficiente para auditoria.

### 25.3 RAGFlow: papel e fronteiras

RAGFlow é permitido como **parser/headless** para documentos complexos, com fronteiras explícitas:

- **não** é fonte de verdade;
- **não** substitui `document_memories`, `document_chunks` ou `document_vectors`;
- cache/store próprio **não** entra no contrato de recuperação;
- indisponibilidade do RAGFlow **não** pode quebrar o caminho local-first;
- qualquer saída aproveitada precisa ser normalizada para UMC antes de ser recuperável pelo cérebro.

A promoção de documento para conhecimento durável (fact/decision/learning) é feita pelo `KnowledgePromotionPipeline` (ver §27), **não** pelo `DocumentPipeline` sozinho. Esta separação evita poluir memória durável com todo chunk de documento e preserva a diferença entre evidência recuperável e conhecimento promovido.

---

## 26. RetrievalRouter (K7) — roteamento por intenção

Inspirado em LlamaIndex, mas implementado como **contrato próprio** (entregue em `core/retrieval/router.py` na v3.5.0, 2026-06-30). O router classifica intent, executa rotas especializadas, preserva fallback para `sinapse_query`/Context Fusion e retorna `retrieval_path`, `citations`, `confidence` e `missing_context` em todas as consultas. `core/search.py` expõe `route_retrieval()` como adaptador interno.

**LlamaIndex entra apenas como adapter opcional de rerank**; não decide rota nem vira fonte de verdade.

```text
query
  |
  +-- recente / "o que aconteceu"       -> claude-mem temporal
  +-- decisao / preferencia             -> memory_vectors + FTS
  +-- aprendizado                       -> learning atoms + Patterns parent
  +-- documento                         -> document_vectors + parent context
  +-- codigo                            -> code_vectors + Graphify
  +-- causalidade / quando era verdade  -> Graphiti
  +-- pergunta global / multi-hop       -> LightRAG/GraphRAG
  +-- saude / autoconsciencia           -> insula (saude/conflitos)
  +-- config / operacional / modelo     -> tronco (operational_fact)
  +-- setor / cross-projeto             -> diencefalo + Graphiti
  +-- ambigua                           -> hybrid + reranker
```

**Contrato de retorno** (toda consulta K7 devolve):

```json
{
  "answer_context": [],
  "citations": [],
  "retrieval_path": [],
  "confidence": 0.0,
  "missing_context": []
}
```

`query_route_distribution` (métrica §28) é preenchida a partir do `query_route_log` em modo best-effort. A query gravada é sempre hash — o texto bruto da pergunta não entra na telemetria.

---

## 27. Knowledge Promotion Pipeline (K3/K4)

### 27.1 Knowledge Intake (K3) — `core/knowledge/intake.py`

Camada [3] do fluxo (ver §23). Responsabilidades:

- normaliza campos de observações do claude-mem (`observations`, `discoveries`, `session_summaries`, `facts`, `narrative`, `concepts`, `files_read/files_modified`, `prompt_number`, `generated_by_model`);
- preserva `source_id` estável (`claude-mem:<table>:<id>`);
- extrai evidência / arquivos / timestamps;
- classifica `knowledge_type` (§27.2);
- deduplica por `source_id` + hash de conteúdo.

### 27.2 Tipos canônicos de conhecimento

| Tipo | Origem comum | Promove para | Observação |
|---|---|---|---|
| `event_raw` | hook/claude-mem/runtime | temporal apenas ou investigation | nunca apagar |
| `user_prompt` | claude-mem | evidência/intenção | preserva pergunta original |
| `session_summary` | claude-mem | cerebelo/sessão | contém investigado, feito, pendente |
| `discovery` | claude-mem | fact/learning/rationale/task | não é bruto descartável |
| `fact` | Dream Cycle/discovery | cortex temporal | fato atômico validado |
| `preference` | conversa/decisão | cortex temporal/_global | preferência do usuário/projeto |
| `decision` | MCP/summary/discovery | cortex frontal + temporal | decisão com razão |
| `learning` | discovery/Patterns | cerebelo + temporal | aprendizado atômico |
| `rationale` | código/decisão | temporal/frontal | por que algo existe |
| `operational_fact` | health/runtime/audit | tronco/ínsula | estado real verificável |
| `document_chunk` | docs/PDF/vault | parietal | chunk pequeno + parent |
| `code_symbol` | Graphify/code scan | occipital/structural | função/classe/módulo |
| `visual_observation` | screenshot | occipital/parietal | imagem + descrição |
| `next_step` | session summary/discovery | goal/task | vira trabalho rastreável |

### 27.3 Promotion Layer (K4) — `core/knowledge/promotion.py`

Camada [4] do fluxo. Regras de promoção automática:

- **Permitida**: `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` — todos com fonte rastreável.
- **Proibida**: transformar todo bullet em fact; criar neurônio sem fonte; vetorizar duplicatas sem `parent_id` e hash de conteúdo; promover opinião temporária como decisão arquitetural; sobrescrever decisões anteriores sem criar conflito ou `invalid_at`.

### 27.4 Contrato de escrita por writer

Toda tool ou pipeline que escreve memória deve declarar:

| Pergunta | Obrigatório |
|---|---|
| Cria observation? | sim/não |
| Cria arquivo anatômico? | caminho |
| Cria neuron? | tipo |
| Cria vector? | coleção |
| Cria edge? | Graphiti/Graphify/LightRAG |
| Cria task/goal? | sim/não |
| Qual evidência? | source ids/files |
| Como reprocessa? | idempotency key/hash |

Exemplo:

```yaml
writer: sinapse_save_learning
observation: true
file: cerebro/cerebelo/padroes/Patterns.md
neuron: learning
vector_collection: memory_vectors
edges:
  - related_to
promotion_required: false
idempotency: title+content_hash
```

### 27.5 Bridge canônico do claude-mem (K4)

A leitura de claude-mem para promoção/backfill usa `core/knowledge/claude_mem_bridge.py` (SQL read-only em `~/.claude-mem/claude-mem.db`). Este é o caminho que aceita `source_id` e janela temporal sem depender de busca textual. O workflow interativo `search → timeline → get_observations` (via MCP) continua sendo o caminho para recuperar contexto bruto antes de escolher IDs.

Descobertas: `session_summaries` sempre existe; `discoveries` pode não existir — quando ausente, vêm de `observations.type='discovery'` com campos `facts`, `narrative`, `concepts` e `files_*`. `source_id` estável: `claude-mem:<table>:<id>`, preservado em metadata e evidência.

---

## 28. Métricas de Saúde do Conhecimento (K8)

Entregue em `scripts/health/knowledge_health.py` (v3.6.0, 2026-06-30). Este módulo **adiciona** métricas de cobertura de conhecimento; ele **não substitui** `health_dashboard.py`, `alert_dispatcher.py` nem `review_writer.py`, que continuam sendo o health da Ínsula. `sinapse_health` inclui um bloco `knowledge_health` read-only em modo quick, e a REST API expõe `GET /api/v1/knowledge/health` para o gate completo.

| Métrica | Sinal |
|---|---|
| `neurons_total` | tamanho da memória consolidada |
| `neurons_vectorized_pct` | cobertura vetorial |
| `observations_pending` | backlog temporal |
| `observations_linked_pct` | promoção efetiva |
| `discoveries_pending` | risco de perder aprendizado |
| `learnings_atomized` | aprendizado granular |
| `document_chunks_total` | ingestão documental |
| `code_symbols_total` | cobertura estrutural |
| `milvus_sync_lag` | divergência local/produção |
| `orphan_vectors` | índice sujo |
| `query_route_distribution` | quais camadas respondem |
| `*_vectorized_pct` | cobertura por coleção canônica (memory/observation/document/code/visual/graph/summary) |
| `promotion_lag` | backlog de promoção por workspace |
| `promotion_cost` | custo de LLM por workspace |
| `vectors_model_mismatch` | divergência de modelo de embedding dentro de uma coleção |

K8 mede as **sete coleções canônicas** explicitamente — o gate não pode olhar apenas `neurons_vectorized_pct`.

**Gate mínimo de produção:**

```text
neurons_vectorized_pct >= 99%
observations_linked_pct crescente por ciclo
discoveries_pending dentro do SLA
0 orphan vectors
todos os chunks com parent_id
citations presentes nas respostas documentais
```

---

## 29. Cadência Hierárquica de Escrita

A memória do Hive-Mind não depende de um único resumo gigante. Ela sobe em camadas: **sessão → diário → semanal → mensal → anual**. Cada camada tem objetivo, modelo e regra de promoção próprios.

| Cadência | Writer | Entrada | Saída anatômica | Modelo padrão | Promove |
|---|---|---|---|---|---|
| Sessão | `session_consolidator.py` | log bruto, tool calls, notas | `cerebelo/sessoes/YYYY/MM/YYYY-MM-DD-HHMM-{slug}.md` | pequeno/rápido | decisões, perguntas abertas, evidências candidatas |
| Diário | `daily_writer.py` | sessões + resumos | `cerebelo/diario/YYYY/MM/YYYY-MM-DD.md` | pequeno ou médio | aprendizados candidatos, progresso, próximos passos |
| Semanal | `weekly_synthesizer.py` | diários, fatos, decisões, métricas | `cerebelo/semanal/YYYY-Wxx.md` | médio/forte | padrões, decisões estratégicas, prioridades |
| Mensal | `monthly_synthesizer.py` | semanais, projetos, discoveries, métricas | `cerebelo/mensal/YYYY-MM.md` | forte | síntese executiva, drift estratégico, metas, riscos |
| Anual | `yearly_synthesizer.py` | mensais, marcos, padrões duradouros | `cerebelo/anual/YYYY.md` | forte/batch offline | memória histórica, princípios, lessons learned duráveis |

### 29.1 O que vai e o que não vai

| Fonte | Vai para memória de longo prazo | Não vai |
|---|---|---|
| Log bruto de sessão | apenas evidências referenciáveis e eventos importantes | tool call repetitivo, erro temporário, ruído de terminal |
| Resumo de sessão | decisões, perguntas abertas, tarefas, descobertas com fonte | bullets narrativos sem consequência |
| Diário | aprendizados, progresso por projeto, bloqueios recorrentes | lista completa de arquivos lidos/comandos |
| Semanal | padrões, mudanças de direção, status consolidado, prioridades | microdetalhes já cobertos por sessões/diários |
| Mensal | síntese executiva, riscos estruturais, metas, drift de estratégia | progresso operacional sem impacto durável |
| Anual | princípios, retrospectiva de arquitetura, grandes decisões, lessons learned | repetição de semanais/mensais sem abstração nova |

**Regra de ouro:** quanto mais alta a cadência, menos ela copia texto e mais ela consolida causalidade, decisão, padrão e consequência.

### 29.2 Contrato de promoção por cadência

Cada resumo é fonte com `source_id`, `period_start`, `period_end`, `cadence` e `parent_summary_id`. Modelo segue o `setup-brain` e herda do `dreamer` se não houver override. Para máquina zerada: regra fail-closed — se um papel não tiver modelo próprio nem herança do `dreamer`, o writer deve registrar falha auditável e não inventar síntese. Para custo baixo, sessão/diário podem usar modelo pequeno; mensal/anual **não** devem ser rebaixados automaticamente sem aviso.

---

## 30. Escala e Isolamento — Workspace e Federação

Hive-Mind é produto open-source que nasce com escala. Não é SaaS B2B: o eixo de escala é (a) **per-install** (um usuário acumula anos de corpus), (b) **multi-usuário por instância** (um time self-hosta), (c) **federação** entre instâncias. O isolamento nasce no schema — não se enxerta depois — e o single-user local-first não percebe (default `workspace_id='default'`).

### 30.1 Workspace (fronteira de isolamento)

```text
coluna workspace_id em: neurons, observations, synapses, goals, document_memories,
                        visual_memories, ambiguities, causal_edges, vault
  default: 'default'  (single-user não precisa setar; born-large sem custo local)
indice: (workspace_id, ...) nas queries quentes
filtro: TODA leitura/escrita do RetrievalRouter e da promoção carrega workspace_id
vault: cerebro/ pode ser subtree por workspace quando multi-usuário
```

**Regra:** nenhum neurônio/vetor/edge cruza `workspace_id` sem passar pela camada de federação. Vazamento cross-workspace é bug de segurança, não de ranking.

**Migrações estruturais** que criam essa fronteira: falha de migração é fail-closed por padrão. O único bypass é `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` (diagnóstico de DB legado, com log visível e sem marcar a instalação como saudável).

### 30.2 Partição das coleções vetoriais

```text
sqlite-vec (local/dev): filtro por workspace_id no metadata
Milvus (produção):      partition-key = workspace_id (isolamento + poda por partição)
```

### 30.3 Federação entre instâncias (reusa HM-12)

Já existe e não se reimplementa: `visibility` (private|shared|public), assinatura Ed25519 (`core/signing.py`), redação de PII no export (`core/redactor.py`). Contrato born-large:

```text
export inter-instância: só visibility in (shared, public) + redact + sign
import: verifica assinatura; neurônio importado entra com workspace_id do destino
        e proveniência (origin_instance, origin_signature) preservada
nunca: importar raw cross-instância sem redact; sobrescrever local sem invalid_at
```

### 30.4 Migração de embedding versionada

Trocar modelo de embedding em escala não é script one-shot. Espaço vetorial é versionado:

```text
coleção carrega (embedding_model, dim) na identidade
upsert de modelo divergente: rejeitado ou vai pra coleção nova (nunca mistura)
migração: reembed online por workspace, dual-write (modelo antigo+novo) até cutover
métrica: vectors_model_mismatch (§28) = 0 dentro de uma coleção
```

### 30.5 Custo/throughput da promoção por workspace

Cada observação promovida = 1 LLM (classifica) + 1 embedding. Em escala isso é fila com backpressure e teto de custo por workspace:

```text
promoção em batch (não 1-a-1), fila com prioridade
teto por workspace (env HIVE_PROMOTION_BUDGET_*), excedente fica archived=0 (retry)
métrica: promotion_lag e promotion_cost por workspace
```

---

## 31. Contratos Pendentes (Reranker, Forget, Eval, Harness)

Capacidades **já existentes** (não reimplementar): merge/dedup na promoção (Dream Cycle Router `append|create_new|merge` + tabela `ambiguities` + `register_ambiguity` + dedup de learning por título + dedup cross-backend em `context_fusion`); redação de PII/segredo (`core/redactor.py`, no export federado).

As lacunas abaixo são contratos evolutivos. Quando uma primeira fatia já existe,
o texto explicita o que está entregue e o que continua pendente.

### 31.1 Reranker (reordenação por relevância)

Hoje `context_fusion._fuse_contexts` dedupa e **trunca** por ordem de backend.
Dentro do `RetrievalRouter`, o reranker já está entregue:
`HIVE_RETRIEVAL_RERANKER=1` aciona `integrations/llama_index/client.py::rerank`.
Por padrão, ele usa rerank lexical determinístico/fail-open gated por
`assert_health()` do LlamaIndex. Com
`HIVE_RERANKER_PROVIDER=sentence-transformers` + `HIVE_RERANKER_MODEL`, tenta
cross-encoder local opt-in. Contrato:

```text
rerank(query, candidates[]) -> candidates[] reordenados
  entra: top-N bruto da fusão (ex.: 30)
  ativacao atual: HIVE_RETRIEVAL_RERANKER=1 (lexical local deterministico)
  cross-encoder opt-in: env HIVE_RERANKER_PROVIDER/MODEL + extra reranker
  sai: top-K (ex.: 5) ordenado por score de relevância
  fail-open: sem modelo/erro -> ordem atual (dedup+truncate), sem quebrar
```

O hook já está plugado entre a fusão e o retorno do `RetrievalRouter` (§26),
off por padrão em `local-min`. Cobertura real permanente:
`tests/real/test_retrieval_router_real.py` valida reordenação por overlap,
configuração opt-in do cross-encoder e `retrieval_path` com
`reranker/llama_index: hit`.

### 31.2 Esquecimento intencional (forget / retention)

A regra "nunca deletar por falha" (§27) cobre falha, não esquecimento deliberado. Falta apagar segredo vazado, expirar efêmero e podar órfão. Contrato:

```text
forget(target, reason) -> tombstone auditável (nunca delete físico silencioso)
  motivos: secret_leak | expired | superseded | user_request | orphan_vector
  CRDT-safe: delete em CR-SQLite e tombstone; vetor correspondente removido no backend
  audita: registra em ínsula (motivo, quem, quando); raw preservado só se não for segredo
```

K8 implementa a primeira fatia desse contrato para vetores órfãos: `knowledge_health.py` chama `forget_vector()` com motivo `orphan_vector`, remove o item da coleção sqlite-vec local, limpa `vector_metadata` quando aplicável e grava `knowledge_tombstones` com `target_type`, `target_id`, `collection`, `reason`, `actor`, `workspace_id` e metadata auditável. Extensões futuras para `secret_leak`, `expired`, `superseded` e `user_request` devem reaproveitar a mesma tabela de tombstone.

### 31.3 Avaliação de recuperação (eval)

§28 mede **cobertura** (plumbing), não **qualidade** da resposta. Contrato:

```text
golden set: tests/real/golden_retrieval.jsonl
  cada caso: {query, expected_source_ids[], expected_intent}
métricas: precision@k, recall@k, citation_correctness, intent_accuracy
gate: regressão acima de limiar reprova a frente (junto do harness real K9)
```

Pequeno e curado a mão; cresce a cada bug de recuperação reproduzido como caso.

### 31.4 Harness real e skip de serviços

O aceite de fase da frente de conhecimento usa `tests/real/` e não conta mock como fechamento. Contrato do marker `requires_service`:

```text
se o serviço real exigido estiver online: roda e falha se o comportamento falhar
se o serviço real estiver offline: skip explícito com motivo e serviço nomeado
se o teste não depende de serviço externo: roda sempre
```

O skip precisa ser implementado por fixture/hook de serviço, não apenas por comentário no `pytest.ini`. Cada novo backend real (Milvus, FalkorDB, claude-mem, RAGFlow) deve registrar sua própria fixture ou service registry antes de virar gate de fase.

Implementação atual: `tests/real/service_registry.py` + hook em `tests/real/conftest.py`. Serviços conhecidos: `ollama`, `milvus`, `falkordb`, `claude_mem`, `ragflow`. Serviço desconhecido é erro de teste; serviço offline é skip explícito com nome e motivo.

---

## 32. Decisões de Design (ADRs)

Registro das decisões arquiteturais que moldaram o design atual. Cada ADR documenta o contexto, a decisão tomada, o rationale e os trade-offs aceitos. As ADRs **001–009** foram herdadas da arquitetura v2.0.0; as **010–018** foram criadas na frente de Conhecimento Born-Large (K0–K10) e estão espelhadas em [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md). Em caso de divergência, esta seção canônica prevalece.

### ADR-001 — Vault Obsidian como fonte única de verdade

**Decisão:** vault Obsidian com frontmatter YAML + WikiLinks como storage primário.
**Rationale:** formato plain-text Markdown é git-friendly, agnóstico de ferramenta e legível por humanos sem software especial. Obsidian é editor maduro com graph view, backlinks e plugin ecosystem.
**Trade-off:** dependência do Watcher para manter SQLite sincronizado; Obsidian é opcional (vault funciona sem ele).

### ADR-002 — Busca híbrida paralela

**Decisão:** busca paralela em 7+ backends/órgãos (UMC, NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem — ver §2.6) com fusão e deduplicação cross-backend via `sinapse_query`/Context Fusion. O `RetrievalRouter` K7 (§26) acrescenta classificação de intenção antes da fusão.
**Rationale:** FTS5 encontra termos exatos; vetores encontram conceitos similares; grafo encontra conexões; filesystem garante dados recém-escritos (zero gap). Nenhum backend sozinho cobre todos os casos.
**Trade-off:** ligeiramente maior consumo de I/O; mitigado por circuit breaker (cooldown 30s após 3+ falhas) e rerank opcional (§31.1).

### ADR-003 — MCP como protocolo universal de integração

**Decisão:** expor tools via MCP stdio em vez de criar plugins específicos por agente.
**Rationale:** MCP é padrão aberto adotado por Anthropic, OpenAI, GitHub e comunidade. Um único server (`sinapse-mcp.py`) serve todos os agentes sem adaptação.
**Trade-off:** menos integração automática (hooks) que plugins nativos; compensado por CLI e hooks externos (SessionStart, PostToolUse, Stop).

### ADR-004 — Atomic writes via os.replace()

**Decisão:** `tempfile.mkstemp()` + `os.replace()` em vez de `open().write()`.
**Rationale:** `os.replace()` é atômico no Linux (rename(2) syscall) — se o processo morrer durante a escrita, o arquivo destino permanece íntegro (o tmp fica orphan, não o destino).
**Trade-off:** ligeiramente mais complexo; complexidade justificada para dados de memória persistente.

### ADR-005 — Cloud Memory API (FastAPI :37702)

**Decisão:** microsserviço REST leve em FastAPI protegido por Bearer token para deploy em VPS.
**Rationale:** permite que agentes locais usem memória hospedada num VPS sem precisar do vault físico local. Fail-closed: não inicia sem `HIVE_MIND_API_KEY`.
**Trade-off:** requer rede estável; fallback automático para modo local quando `cloud.enabled=false`.

### ADR-006 — Saída estruturada Pydantic no Dream Cycle

**Decisão:** todas as chamadas LLM usam JSON Schema derivado dos modelos Pydantic; a resposta é validada com `model_validate_json()`.
**Rationale:** garante que qualquer provider (Ollama local ou Anthropic cloud) produza estrutura processável; loop de feedback (Validator reprova → Distiller reprocessa) aumenta qualidade sem intervenção humana.
**Trade-off:** adiciona uma chamada LLM de validação por execução do pipeline.

### ADR-007 — UUID v4 em todas as PKs

**Decisão:** migração de IDs sequenciais para UUID v4 em todas as tabelas do UMC.
**Rationale:** IDs sequenciais colidem entre máquinas distintas no cenário P2P (máquina A e B ambas criam `id=1`). UUID v4 tem probabilidade de colisão de 1 em 10^36.
**Trade-off:** IDs menos legíveis em logs; irrelevante para uso programático.

### ADR-008 — Quarentena em vez de descarte

**Decisão:** pipeline que falha seta `archived=2` em vez de deletar ou ignorar a observação. Estendido por ADR-016: erro transitório vira `archived=0` (retry), erro estrutural vira `archived=2` (quarentena com motivo).
**Rationale:** dados de memória são valiosos; falhas temporárias (rede indisponível, saldo de API zerado) não devem causar perda permanente de contexto.
**Trade-off:** acúmulo de dados em quarentena requer limpeza periódica manual ou automatizada via `forget()` (§31.2).

### ADR-009 — Configuração de LLM por papel com herança e fallback explícito

**Decisão:** cada papel que consome LLM (`dreamer`, `graphify`, `vision`, `synthesis`, e os cinco papéis de cadência K5) tem configuração própria via `HIVE_{ROLE}_PROVIDER/MODEL`, com herança do Dreamer quando ausente e fallback **opt-in** via `HIVE_{ROLE}_FALLBACK_PROVIDER/MODEL`. Resolução centralizada em `get_role_config()` (`core/auth.py`); chamadas e política de retry/fallback centralizadas em `core/llm_client.py`.
**Rationale:** os papéis têm perfis opostos — extração de entidades (milhares de chamadas baratas e frequentes) e síntese dialética (poucas chamadas que exigem raciocínio forte) não podem ser servidos pelo mesmo modelo sem desperdício ou perda de qualidade. A **cascata automática de provedores foi rejeitada** por violar a soberania do usuário: a Síntese Dialética decide qual versão da memória é a verdade e não pode trocar de modelo silenciosamente. O fallback existe apenas quando o usuário o define explicitamente. Falha de **validação Pydantic nunca dispara fallback** — é problema de qualidade da saída, não de disponibilidade; trocar de modelo às cegas mascararia o problema. Chaves de API permanecem uma por provedor (nunca por papel), evitando duplicação de segredos.
**Trade-off:** mais variáveis de ambiente (até 16 com fallbacks); mitigado pela herança — o caso mínimo continua sendo 2 variáveis (`HIVE_DREAMER_PROVIDER/MODEL`).

### ADR-010 — Pipeline de Promoção de Conhecimento em camadas (K3/K4)

**Decisão:** separar o pipeline de promoção em **Knowledge Intake** (normalização/classificação/deduplicação) e **Promotion Layer** (Distiller → Validator → Router → Persistência → Indexação), implementados em `core/knowledge/intake.py` e `core/knowledge/promotion.py`. A bridge do claude-mem é canônica em `core/knowledge/claude_mem_bridge.py` (caminho SQL read-only que aceita `source_id` e janela temporal).
**Rationale:** a versão anterior do Dream Cycle fazia tudo num único estágio; separar intake e promotion torna a promoção **idempotente**, **testável** sem LLM real, e expõe o modo `candidate-only` (saída `candidate` sem persistência) para orquestração. A promoção nunca é 1-a-1 — é em batch com fila e prioridade por workspace (§30.5). Tipos canônicos de conhecimento (§27.2) e regras de promoção automática/proibida (§27.3) viram contrato, não heurística.
**Trade-off:** mais código upfront; mitigado pelo retorno de `KnowledgePromotionPipeline` em modo `candidate-only` para callers que não querem persistir.

### ADR-011 — Coleções vetoriais canônicas separadas (K1)

**Decisão:** o `VectorBackend` opera sobre **sete coleções canônicas** — `memory_vectors`, `observation_vectors`, `document_vectors`, `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors` — cada uma com metadata canônica (`parent_id`, `parent_type`, `brain_lobe`, `knowledge_type`, `project`, `source_uri`, `hash`, `valid_at`, `workspace_id`). Backends oficiais: `sqlite_vec` (local/dev/offline) e `milvus` (produção).
**Rationale:** uma única coleção "tudo" polui ranking e torna impossível medir cobertura por tipo. A separação permite gate de produção por coleção (§28), poda seletiva (esquecer `document_chunks` órfãos não mexe em `memory_vectors`) e versionamento de modelo de embedding por coleção (§30.4).
**Trade-off:** mais tabelas UMC; mitigado por `vector_metadata` auxiliar e identidade de coleção `(name, embedding_model, dim)`.

### ADR-012 — VectorBackend: contrato único, múltiplos backends

**Decisão:** toda a aplicação acessa o vetorial via contrato `upsert/delete/query/hybrid_query/count/health`, independente do backend. Milvus, sqlite-vec, e qualquer futuro backend obedecem o mesmo contrato. **A aplicação nunca chama Milvus diretamente fora do contrato.**
**Rationale:** trocar `sqlite_vec` por `milvus` (e vice-versa) passa a ser mudança de configuração, não de código. Permite que o mesmo `DocumentPipeline`, `RetrievalRouter` e `KnowledgePromotionPipeline` rodem em dev (sqlite-vec) e produção (Milvus) sem分支.
**Trade-off:** o contrato precisa ser estável; mudanças de schema em Milvus exigem migração versionada de embedding (§30.4).

### ADR-013 — DocumentPipeline com parent/chunk/citation obrigatório (K6)

**Decisão:** todo documento ingerido vira um `document_memories` (pai) com `document_chunks` (átomos) e entradas em `document_vectors` (vetores com metadata canônica). Consulta devolve **citações auditáveis** (`source_uri`, offsets, parent), não apenas "melhor trecho".
**Rationale:** sem parent, chunk é texto solto — não tem como auditar nem deduplicar nem reingerir. A separação `documento / chunk / vetor` é o que torna o K6 born-large. RAGFlow entra como adapter/headless, nunca como fonte de verdade; o store dele é cache de ingestão.
**Trade-off:** mais metadados por vetor; mitigado pelo índice auxiliar `vector_metadata` e schema fixo do Milvus.

### ADR-014 — RetrievalRouter classifica intent antes de buscar (K7)

**Decisão:** o `RetrievalRouter` (`core/retrieval/router.py`) é a porta de entrada para queries; ele classifica a intenção, escolhe a rota especializada (temporal, memória, documento, código, grafo, multi-hop, híbrida) e devolve `retrieval_path`, `citations`, `confidence` e `missing_context`. LlamaIndex entra apenas como adapter opcional de rerank; não decide rota nem vira fonte de verdade.
**Rationale:** o `sinapse_query` funde 7 órgãos sem entender a intenção — bom para busca ampla, ruim para precisão. O router explicitamente roteia "decisão" para `memory_vectors`, "documento" para `document_vectors`+parent, "código" para `code_vectors`+Graphify, etc. A telemetria `query_route_distribution` (hash da query, não texto) alimenta a métrica de saúde K8.
**Trade-off:** classificadores de intenção podem errar; mitigado por fallback para `sinapse_query`/Context Fusion quando a confiança é baixa, e por métrica `intent_accuracy` no golden set (§31.3).

### ADR-015 — Workspace como fronteira de isolamento (K8/§30)

**Decisão:** toda tabela crítica do UMC (`neurons`, `observations`, `synapses`, `goals`, `document_memories`, `visual_memories`, `ambiguities`, `causal_edges`, `vault`) carrega `workspace_id` (default `'default'`). Toda query do `RetrievalRouter` e da promoção filtra por `workspace_id`. Milvus usa `partition_key=workspace_id` para isolamento por partição.
**Rationale:** o Hive-Mind nasce single-user local-first, mas o produto é open-source com vetor de escala per-install, multi-usuário por instância e federação entre instâncias. Adicionar `workspace_id` depois custaria migração estrutural — agora é uma coluna. Vazamento cross-workspace é bug de segurança, não de ranking.
**Trade-off:** toda query precisa carregar `workspace_id`; mitigado por `(workspace_id, ...)` nos índices quentes e por default `'default'` (não atrapalha single-user).

### ADR-016 — Falha de promoção preserva dados, nunca descarta

**Decisão:** o contrato de promoção distingue explicitamente erro transitório (`archived=0`, retry futuro) e erro estrutural (`archived=2`, quarentena com motivo). Nada é deletado por falha de promoção. O `Knowledge Intake` (K3) é a primeira camada a usar esse contrato; o `Promotion Layer` (K4) o enforça.
**Rationale:** dados de memória são valiosos; falhas temporárias (rede indisponível, saldo de API zerado, schema novo) não devem causar perda permanente. O contract normativo é fail-safe, não fail-silent.
**Trade-off:** acumula quarentena; mitigado por `K8 knowledge_health` expondo `observations_pending` e `discoveries_pending` como gate, e por pipeline de reprocessamento manual/automático.

### ADR-017 — Cadência hierárquica sessão→anual com papéis de LLM próprios

**Decisão:** a memória temporal é organizada em **cinco cadências** (sessão, diário, semanal, mensal, anual) com writers, entradas, saídas, modelos e regras de promoção próprios. Cada cadência tem um papel de LLM configurável (`session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer`, `yearly_synthesizer`) e herda do `dreamer` se não houver override. Fail-closed: papel sem modelo próprio nem herança registra falha auditável e não inventa síntese.
**Rationale:** mensal e anual produzem memória estratégica (metas, drift, princípios) que não pode ser gerada por modelo pequeno sem rebaixar qualidade. Sessão e diário podem usar modelo pequeno porque a tarefa é compressão local. Custo/qualidade por cadência é o desenho correto.
**Trade-off:** mais papéis para configurar; mitigado pelo `setup-brain` que aceita herança do `dreamer` para o caso mínimo.

### ADR-018 — Contrato negativo de vendorização via `components.lock.json`

**Decisão:** o `components.lock.json` aceita apenas **clones** do source que o `install.sh` builda/patcha (`graphify`, `neural-memory`, `rtk`, `omniparser`, binário `crsqlite`). Wrappers (Milvus, RAGFlow, Graphiti) entram por container/SDK; pip cobre apenas LlamaIndex e utilitários. Se Milvus, RAGFlow ou LlamaIndex aparecerem em `components.lock.json` nesta frente, a implementação está errada.
**Rationale:** regras claras de quem é clone e quem é wrapper reduzem ambiguidade operacional. O contrato é também negativo (declara o que **não** pertence ali) para evitar regressão.
**Trade-off:** manutenção do lock file; mitigado por ser gerado por `install.sh` e revisado em PR.

---

*Esta seção consolida as ADRs herdadas da v2.0.0 (001–009) e as ADRs criadas pela frente de Conhecimento Born-Large (010–018). Em caso de divergência, esta seção canônica prevalece sobre [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md).*
