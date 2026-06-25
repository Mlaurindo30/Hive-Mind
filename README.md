# Hive-Mind

> **Camada de memória universal, persistente e local-first para enxames de agentes de IA.**

[![Status](https://img.shields.io/badge/status-Fase%20HM--12%20(Federated%20Swarm)-blue)]()
[![Python](https://img.shields.io/badge/python-3.12-green)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-lightgrey)]()
[![Tests](https://img.shields.io/badge/tests-211%20unitários-brightgreen)]()

O **Hive-Mind** resolve a amnésia entre sessões dos agentes de IA. Tudo o que os agentes **fazem** (logs), **veem** (capturas de tela), **leem** (PDF/DOCX) e **decidem** é consolidado em um único cérebro persistente — o **Unified Memory Core (UMC)** — e materializado em linguagem natural num vault Obsidian (`cerebro/`), a fonte única de verdade legível por humanos e agentes.

Múltiplos agentes (Claude Code, Codex CLI, Cursor, Gemini CLI, Hermes, OpenClaw) compartilham esse cérebro via MCP, plugin nativo, CLI ou API REST — em uma ou em múltiplas máquinas sincronizadas por P2P.

---

## Início Rápido — Configure com seu Agente de IA

Copie o prompt abaixo e cole no seu agente (Claude Code, Codex CLI, Gemini CLI, Cursor, etc.).

### Prompt de Instalação Inicial

```
Clone e instale o Hive-Mind nesta máquina.

  git clone https://github.com/Mlaurindo30/sinapse_agent.git ~/hive-mind
  cd ~/hive-mind
  ./install.sh --with-tests

Pré-requisitos: Linux com systemd de usuário, Git, curl, uv, Node 18+, Bun e
acesso à internet. O instalador cria o Python 3.12 gerenciado por uv, `.venv`,
Graphify, claude-mem, NeuralMemory, RTK, serviços, índices e registros MCP.

Ao terminar, o próprio instalador pergunta se deseja configurar o provedor LLM
(Gemini, OpenAI, Anthropic, Ollama...) via setup-brain.sh. Responda S e siga
o menu para escolher provedor, modelo e chaves de API.

Se estiver rodando em modo headless/CI (sem terminal interativo):
  HIVE_DREAMER_PROVIDER=google HIVE_DREAMER_MODEL=gemini-2.0-flash \
  GOOGLE_API_KEY=<sua_chave> ./install.sh --non-interactive

Após a instalação, reinicie este agente. No Codex serão registrados:
sinapse-memory, claude-mem-local e neural-memory-local. O primeiro expõe as
11 tools unificadas do Hive-Mind; o claude-mem usa o runtime temporal global
oficial em `~/.claude-mem`.
```

### Prompt de Registro do MCP (projeto já instalado)

```
Configure o Hive-Mind como servidor MCP PARA VOCÊ MESMO — o agente que está
lendo este prompt. Registre apenas a SUA configuração, não a dos outros.

  cd ~/hive-mind
  ./scripts/setup/register-mcp.sh --only <seu-agente>

Substitua <seu-agente> pela sua identidade. Chaves válidas:
  claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode openclaw

Exemplos: Claude Code → `--only claude` · Codex CLI → `--only codex`
          Gemini CLI → `--only gemini` · Cursor → `--only cursor`

Faz merge seguro dos três MCPs gerenciados pelo projeto na SUA config e nunca
remove servidores alheios. Em dúvida sobre a chave: ./scripts/setup/register-mcp.sh --list

Para verificar o seu status sem modificar nada:
  ./scripts/setup/register-mcp.sh --only <seu-agente> --check

(Avançado / administrador) Registrar TODOS os agentes detectados de uma vez —
normalmente só o instalador faz isso:
  ./scripts/setup/register-mcp.sh

Após registrar, reinicie-se e confirme com: "use a tool sinapse_health"

Tools disponíveis:
  sinapse_query              — busca híbrida na memória (vetorial + FTS + grafo)
  sinapse_save_decision      — salva decisão permanente no vault
  sinapse_save_learning      — salva aprendizado/insight
  sinapse_temporal_search    — busca por período de tempo
  sinapse_temporal_save      — salva observação com timestamp
  sinapse_health             — verifica saúde de todos os backends
  sinapse_session_end        — consolida e encerra sessão
  sinapse_zettelkasten_split — fragmenta nota longa em átomos linkados
  sinapse_capture_screen     — captura screenshot e salva em visual_memories
```

---

## Sumário

- [Início Rápido — Configure com seu Agente de IA](#início-rápido--configure-com-seu-agente-de-ia)
- [Visão Geral da Arquitetura](#visão-geral-da-arquitetura)
- [Componentes](#componentes)
- [O Ciclo de Sonho (Hive-Dreamer)](#o-ciclo-de-sonho-hive-dreamer)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Operação](#operação)
- [Integração com Agentes](#integração-com-agentes)
- [Cloud Memory API](#cloud-memory-api)
- [Sincronização P2P](#sincronização-p2p)
- [Testes](#testes)
- [Segurança](#segurança)
- [Solução de Problemas](#solução-de-problemas)
- [Roadmap](#roadmap)

---

## Anatomia do Cérebro

O Hive-Mind é organizado como um cérebro. O vault `cerebro/` espelha a anatomia — cada lobo tem uma função, cada projeto consumidor é um neurônio no lobo temporal. As dimensões de memória abaixo correspondem a órgãos do cérebro, não a bancos paralelos.

```
                  ┌─────────────────────────────────────┐
                  │   🧠 Consciência (Home)             │
                  │   "eu" que integra os lobos         │
                  └──────────────┬──────────────────────┘
                                 │
        ┌─────────────┬──────────┴───────────┬──────────────┐
        │             │                      │              │
   ┌────▼────┐   ┌────▼────┐         ┌───────▼──────┐  ┌────▼────┐
   │ CÓRTEX  │   │CEREBELO │         │ DIENCÉFALO  │  │ TRONCO  │
   │ (cogn.) │   │ (ritmo) │         │  (relay     │  │ (infra) │
   │ • frontal  │ • diário  │         │             │  │ • modelos
   │ • parietal │ • semanal│         │ • ai-infra  │  │ • paineis
   │ • occipital│ • sessões│        │ • dev-tools │  │ • meta
   │ • temporal │ • padroes│         │ • finance   │  │ • infra
   │ • ínsula   │          │         │ • infra/pkm │  │
   └────┬─────┴────────────┘         └──────┬──────┘  └────┬────┘
        │                                  │             │
        └──────────────┬───────────────────┘             │
                       │                                 │
                  ┌────▼──────────────────┐              │
                  │   Lobo Temporal        │◄─────────────┘
                  │   (memória por projeto) │
                  └────────────────────────┘
```

| Lobo | Função | Onde mora |
|---|---|---|
| Córtex frontal | Decisão, planejamento, trabalho | `core/`, `scripts/dream/dream_cycle.py`, `cortex/frontal/` |
| Córtex parietal | Sensorial — inbox, referências | `scripts/capture/`, `cortex/parietal/` |
| Córtex occipital | Visão — capturas + **grafo** | `graphify-out/graph.json` (Graphify, em `cortex/occipital/grafo/`) |
| Córtex temporal | Memória de longo prazo por projeto | `cortex/temporal/<projeto>/<tópico>/neuronio-*.md` + UMC `hive_mind.db` |
| Córtex ínsula | Saúde, autoconsciência | `scripts/health/`, health dashboard |
| Cerebelo | Ritmo — diário, semanal, sessões, padrões | `cerebelo/{diario,semanal,sessoes,padroes}/`, `brain/Patterns.md` |
| Diencéfalo | Relay cross-projeto | `diencefalo/setores/` (ai-infra, dev-tools, finance, infra, pkm) |
| Tronco | Infra vital | `tronco/{modelos,paineis,infra,meta}/` |

As ferramentas externas são **órgãos do cérebro**, não bancos paralelos: Graphify (occipital), claude-mem (temporal), RTK (tronco), NeuralMemory (associação), filesystem scan (parietal). Anatomia completa em [`AGENTS.md`](AGENTS.md) e [`docs/01-architecture.md`](docs/01-architecture.md).

---

```
  ┌────────────────────────────────────────────────────────────────┐
  │                       AGENTES DE IA                            │
  │  ┌────────────┐ ┌──────────┐ ┌────────┐ ┌─────────────────┐  │
  │  │ Claude Code│ │Codex CLI │ │Cursor  │ │Gemini/OpenClaw/ │  │
  │  │ Kilo Code  │ │          │ │ Aider  │ │Copilot/ZooCode  │  │
  │  └─────┬──────┘ └────┬─────┘ └───┬────┘ └───────┬─────────┘  │
  └────────┼─────────────┼───────────┼───────────────┼────────────┘
           │             │           │               │
           └──────────┬──┴───────────┘               │
                      │                              │ (hooks nativos)
                      ▼                              ▼
  ┌───────────────────────────────┐   ┌─────────────────────────────┐
  │   sinapse-mcp.py              │   │   sinapse-memory.py          │
  │   MCP Server · stdio          │   │   Plugin Hermes/Thoth        │
  │   10 tools · JSON-RPC          │   │   pre_gateway_dispatch       │
  │                               │   │   post_tool_call             │
  │   sinapse-write.py (CLI)      │   │   on_session_end             │
  │   sinapse-api.py (REST :37702)│   │                              │
  └────────────┬──────────────────┘   └─────────────┬───────────────┘
               └────────────────────┬────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │            UNIFIED MEMORY CORE — hive_mind.db (SQLite)          │
  │                                                                 │
  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
  │  │  neurons    │  │ observations │  │   visual_memories      │ │
  │  │  synapses   │  │ (temporal)   │  │   document_memories    │ │
  │  │  (grafo)    │  │ archived 0/1/2   │   (multimodal)         │ │
  │  └──────┬──────┘  └──────┬───────┘  └────────────────────────┘ │
  │         │                │                                       │
  │  ┌──────▼──────┐  ┌──────▼──────┐  ┌────────────────────────┐  │
  │  │ search_vec  │  │ search_fts  │  │   ambiguities          │  │
  │  │ sqlite-vec  │  │ FTS5        │  │   vault (cifrado)      │  │
  │  │ 384d HNSW   │  │ unicode61   │  │   (P2P / segredos)     │  │
  │  └─────────────┘  └─────────────┘  └────────────────────────┘  │
  └───────────────────────────┬────────────────────────────────────┘
                              │                     ▲
              ┌───────────────┼───────────┐         │ reindexação ~2s
              │               │           │         │
              ▼               ▼           │         │
  ┌────────────────┐  ┌──────────────┐   │  ┌──────────────────────┐
  │  Hive-Dreamer  │  │  REST API    │   │  │  Watcher (watchdog)  │
  │  dream_cycle.py│  │  FastAPI     │   │  │  + Graphify          │
  │  (consolidação │  │  :37702      │   │  │  (indexação do vault)│
  │   noturna)     │  └──────────────┘   │  └──────────────────────┘
  └───────┬────────┘                     │            ▲
          │                              │            │ edição
          ▼                              │            │ humana/agente
  ┌───────────────────────────────────┐  │            │
  │  Vault Obsidian — cerebro/        │──┘────────────┘
  │  atlas/  brain/  work/  atoms/    │
  │  org/  reference/  templates/     │◄──── Syncthing (P2P)
  │  portal.canvas  (fonte de verdade)│
  └───────────────────────────────────┘
```

### Dimensões de memória

| Dimensão | Pergunta que responde | Implementação | Latência |
|----------|-----------------------|---------------|----------|
| **Estrutural** | O que existe? Como se conecta? | `neurons`/`synapses` no UMC | < 5 ms |
| **Temporal** | Quem fez o quê? Quando? | `observations` via claude-mem | < 500 ms |
| **Vetorial** | O que é semanticamente parecido? | `sqlite-vec` (384d, fastembed) | < 100 ms |
| **Textual** | Onde aparece esse termo? | FTS5 `unicode61` com triggers | < 50 ms |
| **Visual** | O que o agente viu? | `visual_memories` + LLM Vision | offline (Dreamer) |
| **Documental** | O que o agente leu? | `document_memories` (PDF/DOCX) | offline (Dreamer) |
| **Execução** | Como otimizar este comando shell? | RTK (Rust), hook `pre_tool_call` | < 2 s |

---

## Componentes

| Componente | Caminho | Linguagem | Papel |
|------------|---------|-----------|-------|
| Unified Memory Core | `hive_mind.db` + `core/umc_schema.sql` | SQLite | Banco único: grafo, logs, vetores, FTS, multimodal, segredos |
| Conexão/Schema | `core/database.py` | Python | Conexões com sqlite-vec, WAL, busy_timeout |
| Autenticação LLM | `core/auth.py` | Python | 10 provedores (API key + OAuth), refresh, descoberta de modelos |
| Schemas Pydantic | `core/schemas/` | Python | Saída estruturada: Distiller, Validator, Router, Synthesis, Vision |
| Hive-Dreamer | `scripts/dream/dream_cycle.py` | Python | Consolidação: observações → fatos validados → Atlas |
| Brain Selector | `scripts/setup/setup-brain.sh` | Python | UI terminal: configura provedor/modelo/auth de TODOS os papéis + fallback |
| Watcher | `scripts/services/start-watcher.sh` | Python/watchdog | Sync em tempo real Obsidian → SQLite (~2s) |
| Auditor P2P | `scripts/health/audit_memory.py` | Python | Integridade vault ↔ SQLite |
| Diff Semântico | `scripts/dream/semantic_diff.py` | Python | Classifica conflitos P2P (vetorial + LLM) |
| Ingestão de Docs | `scripts/knowledge/document_ingest.py` | Python | PDF/DOCX → fila de observações |
| Captura Visual | `scripts/capture/visual_capture.py` | Python/mss | Screenshots → `visual_memories` |
| Portal Visual | `scripts/knowledge/generate_portal.py` | Python | Gera `portal.canvas` (Obsidian Canvas) |
| REST API | `scripts/services/sinapse-api.py` | FastAPI | Acesso remoto autenticado ao UMC (porta 37702) |
| MCP Server | `scripts/services/sinapse-mcp.py` | Python | 11 tools via stdio JSON-RPC |
| CLI | `scripts/services/sinapse-write.py` | Python | Subcomandos: decision, learning, query, health, session-end |
| Graphify | `graphify/` | Python | Indexador estrutural do vault |
| claude-mem | `~/.claude-mem` + plugin upstream | TypeScript/Bun | Tracking global multi-projeto de eventos (porta 37700) |
| RTK | `rtk/` | Rust | Otimização de comandos shell |
| NeuralMemory | `integrations/neural-memory/` | Python | Recall associativo (spreading activation) |
| Plugin Hermes | `plugins/hermes/sinapse-memory.py` | Python | Leitura/escrita automática via hooks |
| Vault | `cerebro/` | Markdown | Fonte única de verdade (Obsidian) |

---

## O Ciclo de Sonho (Hive-Dreamer)

Consolidação offline: o que o agente vive durante o dia (observações brutas) é transformado em conhecimento estruturado e legível.

```
  INGESTÃO                 PIPELINE DE INTELIGÊNCIA          PERSISTÊNCIA
  ─────────                ────────────────────────────      ────────────
  documents/  ─────┐
  PDF, DOCX         │       ┌──────────┐   ┌───────────┐
                    ├──────►│ Distiller│──►│ Validator │──┐
  screenshots ─────┤       │ extrai   │   │ confere   │  │  reprova
  (mss/Vision)      │       │ fatos    │   │ vs. logs  │◄─┘ (loop)
                    │       └──────────┘   └─────┬─────┘
  observations ────┘                             │ aprovado
  (archived=0)                                   ▼
                                          ┌──────────────┐
                                          │    Router    │
                                          │ roteia para  │
                                          │ tópico Atlas │
                                          └──────┬───────┘
                                                 │
                      ┌──────────────────────────┤
                      │                          │
                      ▼                          ▼
               archived=1 (ok)          cerebro/atlas/<tópico>/
               neuron + embedding       <fato>.md (frontmatter)
               no UMC

  SÍNTESE DIALÉTICA (Fase 9)
  ──────────────────────────
  ambiguities (P2P)──► semantic_diff ──► merge | choose | branch
```

- **Agnóstico a provedor, por papel:** cada papel (`dreamer`, `graphify`, `vision`, `synthesis`) escolhe provedor+modelo via `HIVE_{ROLE}_PROVIDER/MODEL` no `.env`, com herança do Dreamer e fallback opt-in (`HIVE_{ROLE}_FALLBACK_*`). Suporte a Google/Gemini, OpenAI, Anthropic, DeepSeek, OpenRouter, NVIDIA, HuggingFace, Qwen, LM Studio e Ollama (local). Detalhes: [`docs/01-architecture.md`](docs/01-architecture.md) §10.1 e ADR-009.
- **Fail-safe:** pipeline que falha envia dados para quarentena (`archived=2`), nunca os descarta. Erros transitórios fazem retry com backoff; falha de validação Pydantic nunca dispara fallback.
- **Multimodal:** screenshots e PDFs/DOCX entram no mesmo pipeline que os logs.

### HM-11 — Deep Reflection

- **`scripts/planner.py`** — decomposição de objetivos em etapas (`decompose_goal`, `save_goal`); exposto como MCP tool `sinapse_plan_goal`.
- **`core/hnsw_index.py`** — índice vetorial incremental HNSW (hnswlib, espaço coseno); coluna `indexed_at` nas neurons atualizada a cada inserção.
- **Grafo de causalidade** — tabela `causal_edges` no UMC + `get_causal_neighbors()` (BFS em `core/database.py`); campos `goal_id` e `why` em observations e `DistillerOutput`.

### HM-12 — Federated Swarm

- **`core/signing.py`** — geração de par Ed25519, `sign_neuron()` / `verify_neuron()`; chaves persistidas em `config/keys/` (gitignored).
- **`core/redactor.py`** — `redact_for_export()` / `redact_neuron()`; cobre 8 categorias de PII antes de qualquer exportação.
- **`POST /api/v1/neurons/export`** — exporta neurons por visibilidade (`private`/`shared`/`public`), com filtros de tipo/data, assinatura Ed25519 e redação automática de PII.
- **`scripts/syncthing_watcher.py`** — detecção de conflitos Syncthing em tempo real via REST API (`.sync-conflict-*`).
- **`scripts/hive_analytics.py`** — camada analítica DuckDB; queries `growth`, `top_topics`, `quarantine_rate`, `intent_by_goal`.
- **`core/memory/`** — pacote de 13 módulos resultante do refactor do monólito `sinapse-memory.py`.

```bash
./scripts/setup/setup-brain.sh        # configurar LLM por papel (+ fallback opcional)
python3 scripts/dream/dream_cycle.py  # disparar consolidação
```

---

## Instalação

### Pré-requisitos

| Dependência | Obrigatório? | Usado por |
|-------------|--------------|-----------|
| Python 3.10+ | Sim | UMC, Dream Cycle, MCP, API |
| SQLite 3 + sqlite-vec | Sim (instalado via pip) | UMC |
| hnswlib | Sim (pip) | Índice HNSW incremental (HM-11) |
| duckdb | Sim (pip) | Analytics layer (HM-12) |
| Node.js 18+ / Bun 1.0+ | Para claude-mem | Camada temporal |
| Rust (cargo) | Para RTK | Camada de execução |
| Ollama | Opcional | LLM/embeddings locais |
| Obsidian | Opcional | Interface visual do vault |
| Syncthing | Opcional | Sincronização P2P |

### Instalação rápida

```bash
git clone <repo-url> ~/Documentos/Projects/Hive-Mind
cd ~/Documentos/Projects/Hive-Mind
./install.sh
```

### Instalação no Windows (via WSL2)

O **Hive-Mind** é totalmente suportado no Windows através do **WSL2** (Windows Subsystem for Linux). Isso garante que dependências nativas e compilações complexas de C e Rust (`sqlite-vec`, `RTK`) funcionem com máxima performance e sem atritos de compiladores.

1. **Instale e inicie o WSL2** (preferencialmente Ubuntu 22.04 LTS ou superior).
2. **Clone o repositório no sistema de arquivos do Windows** (para que você possa abrir o vault no Obsidian do Windows). No terminal do WSL2, navegue até a sua pasta de projetos e clone (exemplo):
   ```bash
   mkdir -p /mnt/c/Projects
   cd /mnt/c/Projects
   git clone <repo-url> Hive-Mind
   cd Hive-Mind
   ```
3. **Execute o instalador**:
   ```bash
   ./install.sh
   ```
4. **Onboarding Multimodal (Visão/Captura de Tela)**: O utilitário de visão (`visual_capture.py`) detecta nativamente o ambiente WSL2 e invoca o `powershell.exe` do Windows host de forma transparente para realizar capturas de tela físicas do Windows, sem necessidade de servidores de imagem adicionais ou servidores X11.
5. **Abertura do Vault**: Abra o Obsidian no seu Windows host e selecione a pasta física `C:\Projects\Hive-Mind\cerebro` como um novo vault. Qualquer edição feita no Obsidian do Windows é sincronizada em tempo real com o SQLite/UMC no WSL2 em menos de 2 segundos.

---

O `install.sh` executa 12 etapas:

```
  [1/12] Pré-requisitos e Python 3.12 gerenciado por uv
  [2/12] Ambiente Python reproduzível (.venv + uv.lock)
  [3/12] Graphify local e índices FTS/sqlite-vec/HNSW
  [4/12] Skills nos agentes detectados
  [5/12] Claude-Mem global via npx/marketplace
  [6/12] NeuralMemory local
  [7/12] RTK fixado e compilado
  [8/12] MCP do Hermes
  [9/12] Cron único de sincronização
  [10/12] Plugin sinapse-memory do Hermes
  [11/12] Configuração de inteligência
  [12/12] Três MCPs gerenciados nos agentes externos e serviços
```

---

## Configuração

### Variáveis de ambiente (`.env`)

```bash
cp .env.example .env
```

| Variável | Obrigatória? | Descrição |
|----------|--------------|-----------|
| `HIVE_DREAMER_PROVIDER` | Para o Dream Cycle | Provedor do LLM (`deepseek`, `google`, `ollama`...) |
| `HIVE_DREAMER_MODEL` | Para o Dream Cycle | Modelo (`deepseek-chat`, `gemini-2.0-flash`...) |
| `HIVE_{GRAPHIFY,VISION,SYNTHESIS}_PROVIDER/MODEL` | Não (herdam do Dreamer) | LLM próprio por papel |
| `HIVE_{ROLE}_FALLBACK_PROVIDER/MODEL` | Não (opt-in) | Fallback explícito se o primário falhar |
| `HIVE_MIND_API_KEY` | Para a REST API | Token Bearer — API não inicia sem ela (fail-closed) |
| `HIVE_MIND_API_PORT` | Não (default 37702) | Porta da REST API |
| `HIVE_MIND_MASTER_KEY` | Para vault de segredos | Chave de criptografia em nível de campo |
| `GOOGLE_OAUTH_CLIENT_ID/SECRET` | Para OAuth Google | Credenciais OAuth (nunca hardcoded) |
| `<PROVIDER>_API_KEY` | Por provedor | `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `NVIDIA_API_KEY`... |

> `.env` está no `.gitignore` e nunca deve ser commitado. Use `./scripts/setup/setup-brain.sh` para gerenciar credenciais interativamente.

---

## Operação

```bash
./scripts/services/start-watcher.sh             # Sync em tempo real (Obsidian → SQLite)
python3 scripts/dream/dream_cycle.py            # Ciclo de consolidação
python3 scripts/health/audit_memory.py --fix    # Auditoria vault ↔ SQLite
python3 scripts/knowledge/generate_portal.py    # Portal visual (Obsidian Canvas)
./scripts/graph/build-graph.sh                  # Rebuild manual do grafo
./scripts/utils/recover.sh                      # Disaster recovery
python3 scripts/health/validate_hive_mind.py    # Validação geral do sistema
```

**Obsidian:**
```bash
flatpak run md.obsidian.Obsidian --vault ~/Documentos/Projects/Hive-Mind/cerebro
```

---

## Integração com Agentes

| Método | Agentes | Mecanismo |
|--------|---------|-----------|
| **Plugin nativo** | Hermes/Thoth | hooks `pre_gateway_dispatch`, `post_tool_call`, `on_session_end` |
| **MCP server** | Claude Code, Codex CLI, Cursor, Gemini CLI, Kilo Code, OpenClaw, Copilot, ZooCode, Aider | `scripts/services/sinapse-mcp.py` via stdio JSON-RPC |
| **CLI standalone** | Qualquer agente com shell | `scripts/services/sinapse-write.py <subcomando>` |
| **REST API** | Agentes remotos / VPS | `scripts/services/sinapse-api.py` Bearer auth, porta 37702 |

### Tools MCP

| Tool | Função |
|------|--------|
| `sinapse_query` | Busca híbrida unificada em todos os backends |
| `sinapse_save_decision` | Salva decisão no vault (`work/active/`) |
| `sinapse_save_learning` | Salva aprendizado no `brain/Patterns.md` |
| `sinapse_health` | Health check de todos os backends |
| `sinapse_session_end` | Finaliza sessão, atualiza Current State |
| `sinapse_temporal_search` | Busca direta na camada temporal (FTS5) |
| `sinapse_temporal_save` | Salva observação (com fallback para o vault) |
| `sinapse_zettelkasten_split` | Particiona notas monolíticas em notas atômicas |
| `sinapse_capture_screen` | Captura tela → memória visual |
| `sinapse_plan_goal` | Decompõe objetivo em etapas e persiste no UMC (HM-11) |

**Configuração MCP por agente** (templates em `mcp/`):

| Agente | Arquivo de config |
|--------|------------------|
| Claude Code | `~/.claude/.mcp.json` |
| Codex CLI | `~/.codex/mcp.json` |
| Cursor | `.cursor/mcp.json` |
| Gemini CLI | `~/.gemini/settings.json` |
| Kilo Code | `kilo.json` |
| OpenClaw | `~/.openclaw/openclaw.json` |

---

## Cloud Memory API

FastAPI para acesso remoto ao UMC (VPS), com Bearer auth obrigatório, comparação de token em tempo constante, rate limiting e CORS configurável.

```bash
export HIVE_MIND_API_KEY="<token>"
python3 scripts/services/sinapse-api.py    # porta 37702
```

| Endpoint | Método | Rate | Descrição |
|----------|--------|------|-----------|
| `/api/v1/health` | GET | 60/min | Health check (sem auth) |
| `/api/v1/observations` | POST | 20/min | Registra observação remota |
| `/api/v1/query` | POST | 30/min | Busca híbrida remota |
| `/api/v1/semantic/related` | GET | — | Vizinhos semânticos de um arquivo |
| `/api/v1/vault/{secret_id}` | GET | 10/min | Recupera segredo cifrado |
| `/api/v1/neurons/export` | POST | 20/min | Exporta neurons por visibilidade, com assinatura Ed25519 e redação de PII |

Chaveamento local → cloud no `sinapse.yaml`:
```yaml
cloud:
  enabled: true
  url: "http://<sua-vps>:37702"
  api_key: "${SINAPSE_API_KEY}"
```

---

## Sincronização P2P

```
  Máquina A                 Syncthing                 Máquina B
  ─────────                 ─────────                 ─────────
  edita cerebro/    ──────► sincroniza   ──────►  recebe arquivo
                                                       │
                                                  audit_memory.py
                                                  hash divergente?
                                                       │
                                                  INSERT ambiguities
                                                       │
                                                  dream_cycle.py
                                                  semantic_diff
                                                       │
                                          ┌────────────┴───────────┐
                                          │                        │
                                       merge                    branch
                                   (complemento)          (contradição)
```

- UUIDs v4 em todas as PKs — sem colisão entre máquinas
- SHA-256 de conteúdo em `neurons.hash` — detecção determinística
- `audit_memory.py --fix` — reconcilia vault ↔ SQLite
- Síntese Dialética no Dream Cycle resolve conflitos via LLM

Setup completo: [`docs/07-p2p-sync-setup.md`](docs/07-p2p-sync-setup.md)

---

## Testes

```bash
./tests/run_all.sh    # Smoke → Unit → Integration → E2E
```

| Suíte | Escopo | LLM real? |
|-------|--------|-----------|
| Smoke | Binários e saúde do sistema | Não |
| Unit | Backends (mocks), helpers, fila do Dream Cycle, regressões de auditoria | **Não** |
| Integration | Fluxos leitura/escrita, MCP, API, busca híbrida | Backends reais |
| E2E | Sessão completa, degradação, concorrência, recovery | Backends reais |
| Síntese (`test_synthesis.py`) | `run_synthesis_cycle()` ponta a ponta | **Sim** |

**191 testes passando.** Testes unitários nunca chamam LLM — testam a lógica ao redor do modelo, não o modelo.

---

## Segurança

- **Fail-closed:** API recusa iniciar sem `HIVE_MIND_API_KEY`; comparação de token em tempo constante.
- **Vault cifrado:** segredos detectados são criptografados em nível de campo (Fernet, tabela `vault`).
- **Zero segredos no código:** toda credencial vive no `.env` (gitignored). Auditoria de 10/06 removeu o último resquício hardcoded.
- **Rate limiting** em todos os endpoints sensíveis.
- Bancos de memória pessoal e venvs protegidos no `.gitignore`.

---

## Solução de Problemas

| Problema | Solução |
|----------|---------|
| Dream Cycle não roda | `./scripts/setup/setup-brain.sh` → verificar provedor/modelo/saldo |
| Watcher não sincroniza | `./scripts/services/start-watcher.sh`; checar `watcher.log` |
| API não inicia | Definir `HIVE_MIND_API_KEY` no ambiente |
| MCP não conecta | Verificar config do agente (ex: `~/.claude/.mcp.json`) e path do `scripts/services/sinapse-mcp.py` |
| Observações sumiram da fila | `SELECT * FROM observations WHERE archived=2` (quarentena) |
| Vault ↔ SQLite divergentes | `python3 scripts/health/audit_memory.py --fix` |
| claude-mem worker parou | `systemctl --user restart sinapse-claude-mem.service` |
| Grafo desatualizado | `./scripts/graph/build-graph.sh` |
| Recovery geral | `./scripts/utils/recover.sh` |

---

## Roadmap

| Fase | Tema | Status |
|------|------|--------|
| 1–2 | Fundação + Unified Memory Core (SQLite unificado, busca híbrida) | ✅ Concluído |
| 3 | Unificação temporal (claude-mem → UMC) | ✅ Concluído |
| 4–5 | Interface Obsidian + Auto-Link semântico | ✅ Concluído |
| 6 | Real-time Watcher (elimina gap de 6h) | ✅ Concluído |
| 7 | Ciclo de Sonho — Hive-Dreamer | ✅ Concluído |
| 8 | Enxame multi-máquina (P2P / UUID v4 / Syncthing) | ✅ Concluído |
| 9 | Fusão semântica e consenso (Síntese Dialética) | ✅ Concluído |
| 10 | Deep Portal — memória visual e documental | ✅ Concluído |
| HM-11 | Deep Reflection — Planner + memória de intenção + grafo de causalidade | ✅ Concluído |
| HM-12 | Federated Swarm — compartilhamento seletivo entre enxames + privacidade | ✅ Concluído |

Detalhes: [`PROJECT_STATUS.md`](PROJECT_STATUS.md) · [`IMPLEMENTATION.md`](IMPLEMENTATION.md) · [`docs/01-architecture.md`](docs/01-architecture.md)

---

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [`docs/01-architecture.md`](docs/01-architecture.md) | Referência canônica de arquitetura |
| [`docs/README.md`](docs/README.md) | Índice completo da documentação técnica |
| [`AGENTS.md`](AGENTS.md) | Guia para agentes de IA |
| [`docs/01-architecture.md`](docs/01-architecture.md) | ADRs, fluxos, decisões de design |
| [`docs/02-ai-models.md`](docs/02-ai-models.md) | LLMs, embeddings, provedores, fallback |
| [`docs/03-data-pipeline.md`](docs/03-data-pipeline.md) | Pipeline completo de dados |
| [`docs/04-infrastructure.md`](docs/04-infrastructure.md) | Infraestrutura, portas, serviços, segurança |
| [`docs/05-blueprints.md`](docs/05-blueprints.md) | Diagramas ASCII de todos os fluxos |
| [`docs/06-gap-analysis.md`](docs/06-gap-analysis.md) | Análise do install.sh |
| [`docs/07-p2p-sync-setup.md`](docs/07-p2p-sync-setup.md) | Setup de sincronização P2P |

---

## Licença

Apache 2.0
