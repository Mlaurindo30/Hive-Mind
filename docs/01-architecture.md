# Arquitetura — Hive-Mind v2.0.0

> Referência canônica de arquitetura. Atualizado em 2026-06-24.
> Para uso rápido: [`../README.md`](../README.md)

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
   ├── semanal/   → sínteses semanais
   └── padroes/   → padrões aprendidos (memória procedural)
       + cerebro/cerebelo/padroes/Patterns.md  (Padrões aprendidos — referência canônica)
```

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
| **Córtex frontal** | Decisão, planejamento, trabalho | `core/`, `scripts/dream/dream_cycle.py` (síntese dialética), `cerebro/cortex/frontal/{decisoes,trabalho,brain,projetos,org}` |
| **Córtex parietal** | Sensorial — inbox, referências | `scripts/capture/`, `cerebro/cortex/parietal/{inbox,referencias}` |
| **Córtex occipital** | Visão — capturas + **grafo** | `scripts/capture/visual_capture.py` + `cerebro/cortex/occipital/grafo/graph.json` |
| **Córtex temporal** | Memória de longo prazo por projeto | `cerebro/cortex/temporal/<projeto>/<topico>/neuronio-*.md` + UMC `hive_mind.db` (indexador) |
| **Córtex ínsula** | Saúde, autoconsciência | `scripts/health/`, `cerebro/cortex/insula/{saude,conflitos}` |
| **Cerebelo** | Ritmo — diário, semanal, sessões, padrões | `cerebro/cerebelo/{sessoes,diario,semanal,padroes}/` + `cerebro/cerebelo/padroes/Patterns.md` |
| **Diencéfalo** | Relay cross-projeto | `cerebro/diencefalo/setores/<setor>.md` |
| **Tronco** | Infra vital | `cerebro/tronco/{modelos,paineis,infra,meta}/` — templates, bases, configuração, sub-vaults |

### 2.6 Ferramentas externas como órgãos do cérebro

As 7 ferramentas que alimentam o cérebro **não são bancos paralelos**. São **órgãos do mesmo cérebro** que contribuem para uma única percepção (a resposta do `sinapse_query`).

| Ferramenta | Órgão do cérebro | Função |
|---|---|---|
| **UMC** (`hive_mind.db`) | Córtex (central) | Grafo + vetores + FTS5 + logs em um único SQLite |
| **NeuralMemory** | Córtex (associação) | Spreading activation, memória associativa |
| **sqlite-vec** | Córtex (vetorial) | Indexação HNSW nativa no SQLite |
| **claude-mem** | Córtex temporal (memória de eventos) | Tracking temporal, FTS5, Chroma. Alimenta neurônios em `cortex/temporal/` |
| **Graphify** | Córtex occipital (visão/grafo) | Indexa o `cerebro/` em `graph.json` com Leiden clustering |
| **Graphiti** | Lóbulo temporal (causalidade) | Extrai edges com validade temporal (valid_at/invalid_at) |
| **Filesystem scan** | Córtex parietal (sentido imediato) | Lê o vault direto, sem esperar reindexação |

> **Nota:** RTK não é um read-backend do `sinapse_query` — é otimização de shell, não participa do Context Fusion.
> Ele é instalado por agente/CLI (`codex`, `claude`, `gemini`, `cursor`,
> `hermes`, etc.) via `./scripts/services/start-rtk.sh --only <agente>`.

O `sinapse_query` é o ponto de entrada único do cérebro. Dispara os 7 órgãos em paralelo (circuit breaker + timeout 8s por backend), funde via Context Fusion e devolve **um único pacote de contexto**, não 7 respostas.

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
  │  │   384d HNSW) │  │   unicode61)  │  │  vault (segredos)     │  │
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
  embedding   FLOAT[384]         effect_neuron_id FK→neurons
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
  │  search_vec KNN 384d         │
  │  neurons/synapses            │
  │  observations FTS5           │
  └──────────────────────────────┘
         │                              │
         └──────────────┬───────────────┘
                        │
                        ▼
              merge + dedup + ranking
              (chave: source_file + title + content)
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

`scripts/dream/dream_cycle.py` — consolidação offline com saída Pydantic validada.

```
  ┌────────────────────────────────────────────────────────────────┐
  │                      ESTÁGIO 0 — INGESTÃO                      │
  │                                                                │
  │  document_ingest.py          visual_capture.py                │
  │  PDF/DOCX → resumo/tópicos   mss screenshot → LLM Vision      │
  │       │                           │                           │
  │       └──────────────┬────────────┘                           │
  │                      ▼                                         │
  │  INSERT INTO observations (archived=0)  ←── fila de entrada   │
  └──────────────────────┬─────────────────────────────────────────┘
                         │
  ┌──────────────────────▼─────────────────────────────────────────┐
  │                  ESTÁGIO 1 — PIPELINE DE INTELIGÊNCIA          │
  │                                                                │
  │  SELECT observations WHERE archived=0                          │
  │       │                                                        │
  │       ▼                                                        │
  │  Distiller  (DistillerOutput Pydantic)                         │
  │  "extraia fatos estruturados destas observações"               │
  │       │                                                        │
  │       ▼                                                        │
  │  Validator  (ValidatorOutput Pydantic)                         │
  │  "estes fatos são suportados pelos logs originais?"            │
  │       │                    │                                   │
  │       │ aprovado           │ reprovado → feedback → Distiller  │
  │       ▼                    │                                   │
  │  Router  (RouterOutput Pydantic)                               │
  │  "para qual projeto/tópico do lóbulo temporal cada fato vai?"   │
  │       │                                                        │
  │  falha de pipeline → archived=2 (quarentena, jamais perdido)   │
  └──────────────────────┬─────────────────────────────────────────┘
                         │ roteamento bem-sucedido
  ┌──────────────────────▼─────────────────────────────────────────┐
  │              ESTÁGIO 2 — PERSISTÊNCIA NO CÓRTEX TEMPORAL       │
  │                                                                │
  │  cerebro/cortex/temporal/<projeto>/<topico>/neuronio-*.md      │
  │  escrita atômica via arquivo temporário + os.replace()         │
  │  UPSERT neurons (hash SHA-256, embedding 384d)                 │
  │  archived=1 (consolidado)                                      │
  └──────────────────────┬─────────────────────────────────────────┘
                         │
  ┌──────────────────────▼─────────────────────────────────────────┐
   │  ESTÁGIO 3 — SÍNTESE DIALÉTICA (Fase 9)               │
   │                                                                │
   │  SELECT ambiguities WHERE status='pending'                     │
   │       │                                                        │
   │  semantic_diff (vetorial + LLM)                                │
   │       ├── complemento → merge → conteúdo unificado            │
   │       ├── contradição → choose → versão com evidência         │
   │       └── irreconciliável → branch → preserva ambas           │
   │                                                                │
   │  status='synthesized' | 'branched'                             │
   └──────────────────────┬─────────────────────────────────────────┘
                          │
   ┌──────────────────────▼─────────────────────────────────────────┐
   │     ESTÁGIO 3.5 — PUSH PARA GRAFOS DE CONHECIMENTO (P2 + P4)  │
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
- **Push para grafos** (Estágio 3.5) é best-effort: falha do Graphiti ou LightRAG não impede a síntese dialética de ser marcada como `synthesized`. Logs vão para `[LightRAG]` no stdout.

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

Cada estágio do sistema que chama LLM tem um **papel** com configuração própria. Papéis canônicos atuais (constante `HIVE_LLM_ROLES` em `core/auth.py`): `dreamer`, `graphify`, `vision`, `synthesis`, `claude_mem`, `session_summarizer`, `daily_writer`, `alias_miner`, `topic_router`, `sector_classifier`, `weekly_synthesizer`, `drift_detector`, `decision_promoter`, `project_synthesizer`, `pattern_distiller`, `conflict_detector`. A função aceita qualquer nome de papel (case-insensitive, `-` vira `_`); nome vazio ou não-string levanta `ValueError`.

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
  │   ├── occipital/{capturas-visuais,grafo}/
  │   │   └── grafo/graph.json      ← Graphify canônico
  │   └── insula/{saude,conflitos}/
  ├── cerebelo/{sessoes,diario,semanal,padroes}/
  │   └── padroes/Patterns.md
  ├── diencefalo/{setores,roteamento}/
  └── tronco/{modelos,paineis,infra,meta}/
```

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

  3. mcp/seu-agente.json (template)
     ─────────────────────────────
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

**534 funções em 89 arquivos** cobrindo todo o pipeline de sinapse (cognitivo, vetorial, grafo, FTS5, temporal). Regra: testes unitários nunca chamam LLM — testam a lógica ao redor do modelo, não o modelo.

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

Índice vetorial baseado em `hnswlib` (coseno, 384 dimensões por padrão via `HNSW_DIM`), persistido em `hnsw_neurons.idx` na mesma pasta do `hive_mind.db`. Degrada gracefully se `hnswlib` não estiver instalado (aviso de log, sem crash).

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

## 20. Decisões de Design (ADRs)

Registro das decisões arquiteturais que moldaram o design atual. Cada ADR documenta o contexto, a decisão tomada, o rationale e os trade-offs aceitos.

### ADR-001 — Vault Obsidian como fonte única de verdade

**Decisão:** vault Obsidian com frontmatter YAML + WikiLinks como storage primário.
**Rationale:** formato plain-text Markdown é git-friendly, agnóstico de ferramenta e legível por humanos sem software especial. Obsidian é editor maduro com graph view, backlinks e plugin ecosystem.
**Trade-off:** dependência do Watcher para manter SQLite sincronizado; Obsidian é opcional (vault funciona sem ele).

### ADR-002 — Busca híbrida paralela

**Decisão:** busca paralela em 4 backends (UMC SQL, claude-mem, NeuralMemory, filesystem) com fusão e deduplicação cross-backend.
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

### Status Atual das Fases HM-

| Fase | Nome | Status |
|------|------|--------|
| HM-01 a HM-09 | Fundação (UMC, busca, P2P, síntese) | ✅ Concluída |
| HM-10 | Deep Portal (multimodal) | ✅ Concluída |
| HM-11 | Deep Reflection (raciocínio longo prazo) | ✅ Concluída |
| HM-12 | Federated Swarm (compartilhamento seletivo) | ✅ Concluída |

### Arquivos de Vault com Convenção Antiga

Os seguintes arquivos em `cerebro/cortex/frontal/trabalho/ativo/` usam a numeração antiga sem prefixo e devem ser
renomeados na próxima edição manual do vault (NÃO pelo git — o vault é sincronizado pelo Syncthing):

- `2026-06-01-PHASE-33-TTS-Integration-Closeout-Final.md` (prefixo correto: TH-33)
- `2026-06-02-PHASE-34-Disk-Cache-persistente-para-TTS-design-rationale-e.md` (prefixo correto: TH-34)
- `2026-06-02-PHASE-34-FFmpeg-Transcoding-no-Thoth-Telegram-Voice-Bubble.md` (prefixo correto: TH-34)
- `2026-05-30-Implementacao-das-4-Fases-do-Sinapse-Agent.md` (fases do Sinapse Agent sem prefixo de projeto)
