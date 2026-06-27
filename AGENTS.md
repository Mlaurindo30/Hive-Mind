# Hive-Mind — AGENTS.md

> Guia para agentes de IA que trabalham **neste repositório**.
> Formato cross-agent: Hermes, Claude Code, Codex CLI, Kilo Code, OpenClaw, Copilot, Gemini CLI.
> Última revisão: 2026-06-12 · Referência canônica de arquitetura: [`docs/01-architecture.md`](docs/01-architecture.md)

---

## 1. O que é o Hive-Mind v3.0.0

Infraestrutura de **inteligência coletiva e multimodal**: unifica o que o agente faz, vê e lê em um único cérebro persistente e distribuído.

| Camada | Ferramenta | O que faz | Tecnologia |
|--------|-----------|-----------|------------|
| **Cérebro** | UMC (`hive_mind.db`) | Centraliza grafo, logs, vetores, FTS e visão | SQLite + `sqlite-vec` + FTS5 |
| **Memória** | Atlas (`cerebro/`) | Fonte única de verdade em Markdown | Obsidian + Syncthing |
| **Visão** | Deep Portal | Captura de tela e indexação visual | `mss` + LLM Vision |
| **Consolidação** | Hive-Dreamer | Logs/arquivos → conhecimento validado | `dream_cycle.py` (Pydantic) |
| **Acesso** | MCP / Plugin / CLI / REST | Conecta qualquer agente ao cérebro | stdio JSON-RPC · FastAPI :37702 |

---

## 2. Anatomia do Cérebro

O Hive-Mind é organizado como um cérebro. O vault `cerebro/` espelha a anatomia — **quatro lobos irmãos sob a Consciência**, e o Córtex tem **cinco lóbulos próprios**. Cada projeto consumidor é um neurônio no lóbulo temporal. Esta seção é **canônica**: o desenho do produto, não o template do vault pessoal de nenhum agente.

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
| **Cerebelo** | Ritmo — diário, semanal, sessões, padrões | `cerebelo/{sessoes,diario,semanal,padroes}/` + `cerebro/cerebelo/padroes/Patterns.md` |
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
> Configure por agente/CLI com `./scripts/services/start-rtk.sh --only <agente>`
> ou diretamente via `rtk init`. Hermes é apenas um dos alvos suportados.

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

Qualquer novo código que criar/modificar arquivo no vault **deve usar essas constantes**, não caminhos hardcoded.

---

## 3. Ferramentas MCP disponíveis

Se você está conectado via MCP (`scripts/services/sinapse-mcp.py`):

| Tool | Quando usar |
|------|-------------|
| `sinapse_query` | Antes de responder sobre algo que pode já estar no cérebro |
| `sinapse_save_decision` | Ao tomar/registrar uma decisão de projeto |
| `sinapse_save_learning` | Ao identificar um padrão ou aprendizado |
| `sinapse_temporal_search` / `sinapse_temporal_timeline` / `sinapse_temporal_get_observations` / `sinapse_temporal_save` | Fluxo temporal claude-mem: índice → janela cronológica → detalhes por ID; escrita temporal bruta |
| `sinapse_health` | Diagnóstico dos backends |
| `sinapse_session_end` | Sempre ao final de uma sessão de trabalho |
| `sinapse_zettelkasten_split` | Nota grande demais → notas atômicas |
| `sinapse_capture_screen` | Documentar bugs/progresso visualmente |
| `sinapse_plan_goal` | Decompor objetivo em passos atômicos |
| `search_memories` | Buscar memórias por HNSW/FTS |

---

## 4. Fluxo multimodal

---

## 5. Comandos de operação

```bash
./scripts/services/start-watcher.sh                 # Sincronia em tempo real (Obsidian → SQLite)
python3 scripts/dream/dream_cycle.py                # Ciclo de consolidação (Dream Cycle)
python3 scripts/health/audit_memory.py --fix        # Auditoria de integridade (P2P)
python3 scripts/knowledge/generate_portal.py        # Portal visual (Obsidian Canvas)
./scripts/setup/setup-brain.sh                      # Configurar LLM por papel
./scripts/utils/recover.sh                          # Disaster recovery
python3 scripts/services/sinapse-api.py             # REST API (requer HIVE_MIND_API_KEY)
```

---

## 6. Instalação em máquina nova (instruções para agente ou humano)

Sequência completa para colocar o Hive-Mind funcionando do zero:

```bash
# 1. Clonar o repositório
git clone <repo-url> ~/Hive-Mind && cd ~/Hive-Mind

# 2. Instalação completa e validação real
./install.sh --with-tests

# 3. Configurar o LLM do Dream Cycle (interativo)
./scripts/setup/setup-brain.sh

# 4. Verificar saúde
python3 scripts/services/sinapse-write.py health
```

**Para registrar o MCP sem reinstalar tudo** (ex.: instalou um agente novo depois):

```bash
./scripts/setup/register-mcp.sh           # detecta e registra em todos os agentes
./scripts/setup/register-mcp.sh --check   # só mostra o status, sem modificar
```

O script é idempotente e registra apenas o orquestrador `sinapse-memory`, sem
apagar MCP servers alheios. Registros legados do próprio Hive-Mind
(`claude-mem-local`, `neural-memory-local`) são removidos porque claude-mem
global (`~/.claude-mem`) e NeuralMemory são federados por dentro do Sinapse.
Agentes suportados na detecção automática: Claude Code, Codex CLI, Gemini CLI,
Qwen Code, Kimi Code, Kiro, Kilo Code, Roo Code, VS Code/Copilot, Cursor,
OpenCode e OpenClaw. Após registrar, **reinicie o agente** e valide pedindo:
"use a tool sinapse_health".

**Para ativar RTK em um agente/CLI**:

```bash
./scripts/services/start-rtk.sh --only codex      # Codex CLI
./scripts/services/start-rtk.sh --only claude     # Claude Code
./scripts/services/start-rtk.sh --only gemini     # Gemini CLI
./scripts/services/start-rtk.sh --only cursor     # Cursor
./scripts/services/start-rtk.sh --only hermes     # Hermes
./scripts/services/start-rtk.sh --all             # todos os alvos RTK conhecidos
```

RTK é independente do MCP: ele instala hooks/plugins/instruções para reescrever
comandos shell antes da execução. Não use RTK para buscar memória; para isso use
`sinapse_query`, `sinapse_temporal_*` ou `search_memories`.

---

## 7. Integração com agentes externos

| Método | Agentes | Como funciona |
|--------|---------|---------------|
| **Plugin nativo** | Hermes | `register(ctx)` → hooks `pre_gateway_dispatch`, `post_tool_call`, `on_session_end` |
| **MCP server** | Claude Code, Codex CLI, Cursor, Kilo Code, OpenClaw, Copilot, Gemini CLI, ZooCode, Aider | `scripts/services/sinapse-mcp.py` → 15 tools via stdio JSON-RPC |
| **CLI standalone** | Qualquer agente com shell | `scripts/services/sinapse-write.py` → `decision`, `learning`, `query`, `health`, `session-end` |
| **REST API** | Agentes remotos / VPS | `scripts/services/sinapse-api.py` → Bearer auth, porta 37702 |

Hooks automáticos para Claude Code e Codex CLI:
- `cerebro/tronco/infra/agentes/.claude/settings.json` — SessionStart, PostToolUse, Stop
- `cerebro/tronco/infra/agentes/.codex/hooks.json` — SessionStart, PostToolUse, Stop
- `cerebro/tronco/infra/agentes/.claude/scripts/sinapse-hook.py` — script invocado pelos hooks

---

## 8. Guardrails

- **Nunca** commite dados sensíveis: `.env`, API keys, tokens, `hive_mind.db` (banco de memória pessoal).
- **Nunca** modifique `cerebro/` sem o Watcher ativo (ou rode `./scripts/graph/build-graph.sh` depois).
- **Nunca** use `graphify cerebro/` sem `--backend` se não tiver API key ou Ollama — use `graphify update cerebro/` (AST-only).
- **Nunca** duplique dados entre vault e ferramentas externas. O vault é a fonte única.
- **Nunca** hardcode modelos de LLM — o sistema obedece estritamente `HIVE_DREAMER_PROVIDER/MODEL` do `.env`.
- **Testes unitários não chamam LLM real.** Lógica ao redor da LLM se testa com dados determinísticos; o modelo real só entra em `tests/test_synthesis.py` e nos fluxos E2E.

---

## 9. Testes

Antes de qualquer commit:

```bash
./tests/run_all.sh                    # suíte completa (Smoke → Unit → Integration → E2E)
bash tests/smoke/test_smoke.sh        # mínimo aceitável se a suíte for longa demais
```

| Nível | Comando | Requisitos |
|-------|---------|------------|
| Smoke | `bash tests/smoke/test_smoke.sh` | Binários no PATH |
| Unit | `python3 -m pytest tests/unit/ -v` | pytest, Python 3.10+ |
| Integration | `python3 -m pytest tests/integration/ -v` | Backends reais |
| E2E | `python3 -m pytest tests/e2e/ -v` | Sistema completo |

**534 funções de teste em 89 arquivos** (contagem de 2026-06-25, 0 skipped) cobrindo todo o pipeline de sinapse (cognitivo, vetorial, grafo, FTS5, temporal).

### Disaster recovery

```bash
./scripts/utils/recover.sh
```

<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.sh — do not edit) -->
# Protocolo Hive-Mind (sinapse-memory) — OBRIGATÓRIO

Você tem as 15 tools `sinapse_*` e `search_memories`. Este é o protocolo de
trabalho; siga sempre, sem exceção. Os backends crus (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) são federados por
dentro do sinapse via `sinapse_query` (Context Fusion com circuit breaker
e timeout 8s) — **nunca os chame diretamente**.

## 0. Pré-checagem (uma vez no início da sessão)
- `sinapse_health()` — confirme que todos os backends estão operacionais
  antes de trabalhar. Se algum falhar, reporte e use `sinapse_temporal_search`
  ou `search_memories` no modo `text` como fallback.

## 1. Recupere antes de agir (no início de cada tarefa)
| Necessidade | Tool |
|-------------|------|
| Estado/histórico do projeto, decisões, padrões, código/vault e contexto geral | `sinapse_query("<tema>")` (busca híbrida canônica: funde UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Atividade recente de conversas, prompts, sessões e observações brutas do claude-mem | `sinapse_temporal_search("<termos curtos e específicos>")` → `sinapse_temporal_timeline(anchor=<id>)` → `sinapse_temporal_get_observations(ids=[...])` |
| Saúde/verificação de backends | `sinapse_health()` |

**Regra:** nunca afirme nada sobre o estado/histórico do projeto sem ter
consultado antes.

**Como pesquisar sem se perder:**
1. Para entender "o que aconteceu no projeto", comece com `sinapse_query`.
   Ele é tolerante a linguagem natural e cruza todos os órgãos do cérebro.
2. Se precisar da conversa/prompt/sessão recente que originou aquilo, use
   `sinapse_temporal_search` como **índice textual do claude-mem**. Pesquise
   com termos curtos que provavelmente estão no texto real. Exemplos bons:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. Se `sinapse_temporal_search` vier vazio, não conclua que não existe memória:
   reduza a consulta para 2-5 termos exatos, tente o título retornado por
   `sinapse_query`, ou volte para `sinapse_query` para recuperar contexto
   consolidado.
4. Não use frases longas, perguntas completas ou muitos filtros misturados em
   `sinapse_temporal_search`; ela é melhor como busca textual/timeline do
   claude-mem, não como orquestrador híbrido.
5. Para memória temporal bruta, siga o fluxo nativo do `claude-mem`:
   `search → timeline → get_observations`.
   - `sinapse_temporal_search` é o índice compacto: encontre IDs/títulos.
   - `sinapse_temporal_timeline` mostra contexto cronológico ao redor de um ID
     ou de uma query-âncora.
   - `sinapse_temporal_get_observations` hidrata o conteúdo completo apenas dos
     IDs filtrados. **Nunca** hidrate detalhes antes de filtrar; isso desperdiça
     tokens e mistura contexto irrelevante.

## 2. Recall sob demanda (durante o trabalho)
| Necessidade | Tool |
|-------------|------|
| Neurônios/notas por similaridade semântica (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Fatos/decisões com validade temporal (arestas valid_at/invalid_at) | `sinapse_temporal_graph_search("<tema>", num_results)` (deprecated — use `sinapse_query`) |
| Busca textual no índice do claude-mem global (`~/.claude-mem`) | `sinapse_temporal_search("<termos curtos>")` |
| Contexto cronológico ao redor de um resultado temporal | `sinapse_temporal_timeline(anchor=<id>)` ou `sinapse_temporal_timeline(query="<termos>")` |
| Detalhe completo de observações temporais já filtradas | `sinapse_temporal_get_observations(ids=[...])` |
| Busca híbrida geral (todas as camadas; padrão para contexto do projeto) | `sinapse_query("<tema>")` |
| Consulta vetorial no grafo LightRAG (P4) | `sinapse_rag_query(question, mode?)` |

### Escolha rápida das tools

| Pergunta do agente | Use | Observação prática |
|--------------------|-----|--------------------|
| "Qual é o estado/histórico do projeto?" | `sinapse_query` | Primeira escolha. Cruza vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec e filesystem. |
| "Qual prompt/sessão recente falou disso?" | `sinapse_temporal_search` → `sinapse_temporal_timeline` → `sinapse_temporal_get_observations` | Use termos curtos/exatos, escolha IDs, leia a janela temporal e só então hidrate detalhes. |
| "Quais neurônios consolidados existem sobre esse tema?" | `search_memories` | Use `project` quando souber o projeto; `mode="text"` para busca literal. |
| "Preciso de relações multi-hop entre entidades já indexadas." | `sinapse_rag_query` | Depende do LightRAG estar populado; se vier vazio, volte para `sinapse_query`. |
| "Preciso de fatos temporais/causais do Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` existe por compatibilidade, mas a consulta canônica é `sinapse_query`. |
| "Tomei uma decisão ou aprendi um padrão reutilizável." | `sinapse_save_decision` / `sinapse_save_learning` | Grave na hora; não deixe só na resposta do chat. |
| "Quero escrever evento temporal bruto." | `sinapse_temporal_save` | Só grava direto no claude-mem em server-beta; no runtime worker atual, trate como fallback/nota, não como caminho principal. |

## 3. Grave na hora (ao decidir, aprender ou decompôr)
| Necessidade | Tool |
|-------------|------|
| Decisão (escolha entre alternativas + razão) | `sinapse_save_decision(title, content)` |
| Padrão/insight/lição reaproveitável | `sinapse_save_learning(title, content)` |
| Objetivo grande → passos atômicos (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Nota monolítica (Patterns.md) → notas atômicas Zettelkasten | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capturar tela de bug/progresso visual (não em loop!) | `sinapse_capture_screen(description, monitor?)` |
| Observação temporal crua (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

## 4. Consolide ao terminar
- `sinapse_session_end(summary)` — atualiza `brain/Current State.md` e
  registra a observação de fechamento no UMC.

## Regras de uso
- **Use SOMENTE as tools `sinapse_*` e `search_memories`.** Nunca chame
  `nmem`, `claude-mem`, `graphify` ou `falkordb` diretamente — o sinapse
  já os federa e deduplica via Context Fusion.
- `sinapse_query` é o orquestrador canônico (7 backends). Use-o em vez de
  tools específicas de um backend sempre que possível.
- `sinapse_temporal_graph_search` está deprecated: mantido para não
  quebrar clientes existentes, mas a consulta cerebral canônica é
  `sinapse_query` (que funde Graphiti junto com os outros 6 órgãos).
- `sinapse_health()` retorna o status de todos os backends; use para
  diagnóstico quando uma query retornar vazio inesperadamente.
- `sinapse_capture_screen` apenas em pedido explícito — nunca em loop ou
  monitoramento. Requer `description` (motivo) e `monitor` em setups
  multi-monitor.
- `sinapse_zettelkasten_split` requer Ollama local rodando (qwen2.5-coder:3b).
- Consultar antes de agir e gravar o que for reaproveitável não é opcional:
  é como o cérebro do projeto evolui entre sessões.
<!-- END HIVE-MIND SINAPSE -->
