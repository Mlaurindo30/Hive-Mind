# 01 — Arquitetura e Abordagem Técnica

> **Sinapse Agent v1.1.0** — Camada de memória universal para agentes de IA.

---

## 1. Visão Geral

O Sinapse Agent resolve o problema de **continuidade de memória** entre sessões de agentes de IA. Sem ele, cada sessão começa "do zero" — o agente não lembra decisões passadas, padrões aprendidos ou o estado atual dos projetos.

A solução organiza a memória em **4 camadas complementares**, cada uma respondendo a uma pergunta fundamental sobre o conhecimento:

| Camada | Pergunta | Ferramenta | Tecnologia |
|--------|----------|-----------|-----------|
| **Estrutural** | O QUE existe? Como os conceitos se conectam? | Graphify | Python, tree-sitter, Leiden clustering |
| **Temporal** | QUEM fez o quê? QUANDO? | claude-mem | TypeScript/Bun, SQLite FTS5, Chroma |
| **Execução** | COMO otimizar comandos? | RTK | Rust, regex determinístico |
| **Associativa** | COMO conceitos se relacionam? | NeuralMemory | Python, spreading activation, 24 tipos de relações |

**Fonte única de verdade:** Vault Obsidian em `cerebro/` com frontmatter YAML + WikiLinks.

---

## 2. Princípios de Design

### 2.1 Vault como Fonte Única (Single Source of Truth)

Toda informação converge para o vault Obsidian. As 4 camadas são **indexadores e aumentadores**, não armazenamento primário.

- Graphify **lê** o vault e gera graph.json
- claude-mem **trackeia** eventos e **exporta** para o vault periodicamente
- RTK **intercepta** comandos mas não armazena estado
- NeuralMemory **indexa** relações associativas a partir do vault
- sinapse-memory plugin **lê e escreve** no vault em tempo real

### 2.2 Independência de Camadas & Redirecionamento Cloud

Cada camada opera de forma independente e resiliente. A busca híbrida de contexto (Fase 4.1) consulta todos os backends ativos concorrentemente em paralelo. Se algum backend falhar, os demais cobrem de forma transparente. Adicionalmente, se a configuração `cloud.enabled` estiver ativa (Fase 4.3), o plugin age como um cliente HTTP de alta velocidade, delegando as buscas e gravações diretamente para a API REST na VPS (FastAPI), viabilizando o desacoplamento completo do agente e do vault físico.

### 2.3 Agente-Agnóstico

O mesmo vault serve Hermes (plugin nativo), Claude Code (MCP + hooks), Codex CLI (MCP + hooks), Kilo Code (MCP) e OpenClaw (MCP). A interface de integração é abstraída em 4 métodos:

| Método | Agentes | Mecanismo |
|--------|---------|-----------|
| Plugin nativo | Hermes | `register(ctx)` → hooks `pre_gateway_dispatch`, `post_tool_call`, `on_session_end` |
| MCP server | Claude Code, Codex, Kilo Code, OpenClaw, Copilot, Gemini CLI, ZooCode | `sinapse-mcp.py` → 8 tools via stdio JSON-RPC |
| CLI standalone | Qualquer agente com shell | `sinapse-write.py` → subcomandos `decision`, `learning`, `query`, `health`, `session-end`, `zettelkasten` |
| REST Cloud API | Agentes desacoplados na VPS | `sinapse-api.py` → Endpoints seguros HTTP (SSL + API Key Bearer) |

### 2.4 Indexação Assíncrona

O knowledge graph (graph.json) é rebuildado a cada 6h via cron. Mudanças no vault ficam disponíveis para consulta **imediata** via leitura direta de arquivos (plugin/MCP), mas aparecem como nodes/edges no grafo apenas após reindexação. Este trade-off (consistência eventual) é aceitável para vaults de conhecimento.

---

## 3. Componentes do Sistema

### 3.1 Plugins/hermes/sinapse-memory.py (1138 linhas)

**Núcleo do sistema.** Implementa:

- **Sistema de busca concorrente em paralelo (Fase 4.1):** Consulta todos os backends de leitura (`_READ_BACKENDS`) concorrentemente através de `ThreadPoolExecutor`. Se múltiplos backends retornarem dados ricos, unifica as observações, nós e arestas (Context Fusion), mantendo compatibilidade retroativa para hits isolados.
- **Redirecionamento Cloud API (Fase 4.3):** Intercepta todas as operações locais e delega via requisições HTTP seguras para o microsserviço remoto se `cloud.enabled` for `true`.
- **Prevenção de Recursão:** Implementa a flag `API_SERVER_MODE` para evitar loops de auto-redirecionamento quando rodando dentro da API de nuvem.
- **Escrita atômica** (`_atomic_write`): temp file + `os.replace()` para evitar arquivos truncados
- **Sanitização de slugs** (`_sanitize_slug`): unicode NFKD + regex ASCII-safe + truncamento
- **Deduplicação de aprendizados** (`_save_learning`): verifica existência antes de append
- **Health check unificado** (`health_check`): status de todos os backends + vault
- **Cache TTL** (`_load_graph`): evita releitura do disco a cada consulta (60s TTL)
- **Circuit breaker** (`_is_backend_healthy`): pula backends com 3+ falhas consecutivas (cooldown 30s)
- **Logs estruturados** (`_log`): modo texto ou JSON via `SINAPSE_LOG_JSON`
- **Dry-run mode** (`SINAPSE_DRY_RUN`): sem side effects no filesystem
- **Config centralizada** (`_load_config`): carrega `sinapse.yaml` no startup

### 3.2 Scripts/sinapse-mcp.py (MCP Server)

Servidor MCP que expõe 8 tools via stdio JSON-RPC:

| Tool | Descrição |
|------|-----------|
| `sinapse_query` | Busca unificada concorrente em todos os backends (Context Fusion) |
| `sinapse_save_decision` | Salva decisão no vault com YAML frontmatter |
| `sinapse_save_learning` | Salva aprendizado no Patterns.md (com dedup) |
| `sinapse_health` | Health check completo |
| `sinapse_session_end` | Finaliza sessão, atualiza Current State |
| `sinapse_temporal_search` | Busca direta no claude-mem (FTS5 + Chroma) |
| `sinapse_temporal_save` | Salva observação no claude-mem ou fallback |
| `sinapse_zettelkasten_split` | Particiona notas monolíticas em notas atômicas interligadas |

### 3.3 Scripts/sinapse-write.py (CLI Standalone)

CLI para agentes sem MCP. Subcomandos: `decision`, `learning`, `query`, `health`, `session-end`, `zettelkasten`.

### 3.4 cerebro/.claude/scripts/sinapse-hook.py (Hook Script)

Script invocado pelos hooks do Claude Code e Codex CLI (SessionStart, PostToolUse, Stop). Resolve `SINAPSE_HOME` dinamicamente a partir do vault path.

### 3.5 Scripts de Infraestrutura e Core

| Script | Função |
|--------|--------|
| `build-graph.sh` | Indexa vault → graph.json com backup + validação |
| `serve-graph.sh` | MCP server Graphify (stdio) |
| `start-claude-mem.sh` | Worker claude-mem (Bun) |
| `start-rtk.sh` | Plugin RTK no Hermes |
| `recover.sh` | Disaster recovery automático |
| `sync-diario.sh` | Cron diário com rebuild completo + logs |
| `sinapse-api.py` [NEW] | Microsserviço REST em FastAPI para acesso remoto VPS segura (Fase 4.3) |
| `sinapse-zettelkasten.py` [NEW] | Particionador Zettelkasten conceitual via Ollama local (Fase 4.2) |


---

## 4. Fluxo de Memória (Write Path)

```
1. Agente toma decisão → tool memory_add
2. Hermes: post_tool_call hook detecta DECISION_TOOLS
   Claude/Codex: PostToolUse hook executa sinapse-hook.py tool-detect
3. _save_decision(title, content) → atomic write em work/active/YYYY-MM-DD-slug.md
4. Se conteúdo contém LEARNING_SIGNALS → _save_learning() → append em brain/Patterns.md
5. on_session_end / Stop hook → _update_current_state() → brain/Current State.md
6. Cron (6h) → build-graph.sh → graphify update → graph.json atualizado
```

## 5. Fluxo de Consulta (Read Path)

```
1. Usuário faz pergunta
2. Hermes: pre_gateway_dispatch hook → _query_vault_knowledge(user_message)
   Claude/Codex: SessionStart hook → sinapse-hook.py session-start
3. Se cloud.enabled for True:
   a. O cliente local intercepta e faz requisição HTTP para a API de nuvem (:8000/api/v1/query)
   b. O servidor remoto (com a flag API_SERVER_MODE ativa) processa a consulta localmente na VPS
4. Caso contrário (ou na VPS executando a API):
   a. _query_vault_knowledge orquestra os 3 backends em paralelo assíncrono via ThreadPoolExecutor.
   b. NeuralMemory (spreading activation), claude-mem (ChromaDB/FTS5) e Graphify (graph.json search) executam concorrentemente.
5. Circuit breaker desativa automaticamente por 30s qualquer backend com 3+ falhas consecutivas.
6. Se houver múltiplos hits válidos:
   a. O Query Engine funde as observações, nós e arestas de todas as fontes (Context Fusion).
   b. Se houver apenas um único hit, o Query Engine o retorna diretamente de forma a manter compatibilidade perfeita.
7. O contexto consolidado é formatado e injetado no prompt de forma a respeitar o limite global de caracteres.
```

## 6. Tratamento de Falhas

| Camada | Falha | Comportamento |
|--------|-------|--------------|
| NeuralMemory | Binário ausente ou timeout | Silently skip → os demais backends continuam concorrendo |
| claude-mem | Worker offline (HTTP ECONNREFUSED) | Silently skip → os demais backends continuam concorrendo |
| Graphify | graph.json corrompido ou ausente | Retry 3x com sleep 100ms → log error → skip |
| Escrita | Disco cheio ou permissão | Log stderr → retorna None (não crasha) |
| Backend com bug | KeyError, AttributeError | Log traceback → circuit breaker → skip |
| Cron vs Plugin | Leitura parcial durante rebuild | Retry loop + backup automático no build-graph.sh |
| Cloud API | Rede offline (HTTP Error / Timeout) | Log stderr ➔ Fallback automático para modo local bare-metal se disponível |

---

## 7. Decisões de Design (ADR)

### ADR-001: Vault Obsidian como fonte única
**Decisão:** Usar vault Obsidian com frontmatter YAML + WikiLinks como storage primário.
**Rationale:** Obsidian é um editor maduro com graph view, backlinks e plugin ecosystem. Formato plain-text Markdown é git-friendly e agnóstico de ferramenta.
**Trade-off:** Dependência de reindexação para sincronizar com graph.json (latência de até 6h).

### ADR-002: Fusão de Contexto Paralela Concorrente (Context Fusion)
**Decisão:** Substituir a busca em cadeia sequencial por orquestração assíncrona concorrente via `ThreadPoolExecutor` com fusão híbrida de resultados.
**Rationale:** Aumenta exponencialmente a densidade do contexto injetado unificando busca semântica, relações estruturais Leiden e spreading activation associativa em tempo recorde (<100ms), sem perdas cognitivas.
**Trade-off:** Ligeiramente maior consumo de I/O em paralelo.

### ADR-003: MCP como protocolo universal para agentes externos
**Decisão:** Expor tools via MCP stdio em vez de criar plugins específicos por agente.
**Rationale:** MCP é um padrão aberto adotado por Anthropic, OpenAI, GitHub e comunidade. Um único server serve todos os agentes.
**Trade-off:** Menos integração profunda (hooks automáticos) vs. plugins nativos.

### ADR-004: Atomic writes para arquivos do vault
**Decisão:** `tempfile.mkstemp()` + `os.replace()` em vez de `open().write()`.
**Rationale:** Evita arquivos truncados se o processo morrer durante a escrita. `os.replace()` é atômico no Linux.
**Trade-off:** Ligeiramente mais complexo que write direto.

### ADR-005: Desacoplamento de Memória via Cloud Memory API (FastAPI)
**Decisão:** Criar um microsserviço REST leve em FastAPI protegido por SSL + API Key Bearer Token para permitir deploy agnóstico em nuvem.
**Rationale:** Pavimenta o caminho para VPS hosting (como Thoth AI) de modo que o agente local funcione como um client HTTP extremamente ágil e desacoplado, sem necessidade do vault Obsidian físico local.
**Trade-off:** Requer conexão de rede estável (com fallback determinístico local bare-metal).

---

## 8. Estrutura de Diretórios


```
sinapse_agent/
├── plugins/hermes/sinapse-memory.py    # Plugin principal (1138 linhas, Context Fusion + Cloud)
├── scripts/
│   ├── sinapse-write.py                # CLI standalone (multi-agente)
│   ├── sinapse-mcp.py                  # MCP server (stdio JSON-RPC)
│   ├── sinapse-api.py                  # Microsserviço REST Cloud API (FastAPI)
│   ├── sinapse-zettelkasten.py         # Script utilitário Auto-Zettelkasten via Ollama
│   ├── build-graph.sh                  # Rebuild graph.json
│   ├── serve-graph.sh                  # MCP server Graphify
│   ├── start-claude-mem.sh             # Worker claude-mem
│   ├── start-rtk.sh                    # Plugin RTK
│   └── recover.sh                      # Disaster recovery

├── mcp/
│   ├── graphify.json                   # Config MCP Graphify (template)
│   ├── claude-mem.json                 # Config MCP claude-mem (template)
│   └── sinapse-memory.json             # Config MCP sinapse (template)
├── cerebro/                            # Vault Obsidian (fonte única)
│   ├── brain/                          # Memória operacional do agente
│   ├── work/active/                    # Decisões e projetos ativos
│   ├── graphify-out/graph.json         # Knowledge graph indexado
│   ├── .claude/settings.json           # Hooks Claude Code (5 hooks + 3 sinapse)
│   ├── .claude/scripts/sinapse-hook.py # Script de hook sinapse
│   ├── .codex/hooks.json               # Hooks Codex CLI (5 hooks + 3 sinapse)
│   └── .codex/AGENTS.md               # Template Codex
├── tests/                              # Suite de testes (103 testes)
│   ├── unit/                           # 66 testes unitários
│   ├── integration/                    # 15 testes de integração
│   └── e2e/                            # 22 testes end-to-end
├── cron/sync-diario.sh                 # Cron semanal com rebuild completo
├── sinapse.yaml                        # Configuração central
├── install.sh                          # Instalador universal (10 passos)
├── AGENTS.md                           # Guia para agentes de IA
├── ARCHITECTURE.md                     # Blueprint completo (referência canônica)
└── docs/                               # Esta documentação
```
