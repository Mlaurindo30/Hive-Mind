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

### 2.2 Independência de Camadas

Cada camada opera independentemente. Se o claude-mem estiver offline, o plugin faz fallback para Graphify. Se o Graphify não estiver indexado, usa NeuralMemory. Se tudo falhar, o agente funciona sem contexto — degrade graceful.

### 2.3 Agente-Agnóstico

O mesmo vault serve Hermes (plugin nativo), Claude Code (MCP + hooks), Codex CLI (MCP + hooks), Kilo Code (MCP) e OpenClaw (MCP). A interface de integração é abstraída em 3 métodos:

| Método | Agentes | Mecanismo |
|--------|---------|-----------|
| Plugin nativo | Hermes | `register(ctx)` → hooks `pre_prompt_build`, `post_tool_use`, `post_session_end` |
| MCP server | Claude Code, Codex, Kilo Code, OpenClaw, Copilot, Gemini CLI, ZooCode | `sinapse-mcp.py` → 5 tools via stdio JSON-RPC |
| CLI standalone | Qualquer agente com shell | `sinapse-write.py` → subcomandos `decision`, `learning`, `query`, `health`, `session-end` |

### 2.4 Indexação Assíncrona

O knowledge graph (graph.json) é rebuildado a cada 6h via cron. Mudanças no vault ficam disponíveis para consulta **imediata** via leitura direta de arquivos (plugin/MCP), mas aparecem como nodes/edges no grafo apenas após reindexação. Este trade-off (consistência eventual) é aceitável para vaults de conhecimento.

---

## 3. Componentes do Sistema

### 3.1 Plugins/hermes/sinapse-memory.py (984 linhas)

**Núcleo do sistema.** Implementa:

- **Sistema de backends plugáveis** (`_READ_BACKENDS`): 3 backends registrados em ordem de prioridade (NeuralMemory → claude-mem → Graphify)
- **Motor de busca unificado** (`_query_vault_knowledge`): orquestra backends com circuit breaker, global timeout e exception logging
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

Servidor MCP que expõe 5 tools via stdio JSON-RPC:

| Tool | Descrição |
|------|-----------|
| `sinapse_query` | Busca unificada em todos os backends |
| `sinapse_save_decision` | Salva decisão no vault com YAML frontmatter |
| `sinapse_save_learning` | Salva aprendizado no Patterns.md (com dedup) |
| `sinapse_health` | Health check completo |
| `sinapse_session_end` | Finaliza sessão, atualiza Current State |

### 3.3 Scripts/sinapse-write.py (CLI Standalone)

CLI para agentes sem MCP. Subcomandos: `decision`, `learning`, `query`, `health`, `session-end`.

### 3.4 cerebro/.claude/scripts/sinapse-hook.py (Hook Script)

Script invocado pelos hooks do Claude Code e Codex CLI (SessionStart, PostToolUse, Stop). Resolve `SINAPSE_HOME` dinamicamente a partir do vault path.

### 3.5 Scripts de Infraestrutura

| Script | Função |
|--------|--------|
| `build-graph.sh` | Indexa vault → graph.json com backup + validação |
| `serve-graph.sh` | MCP server Graphify (stdio) |
| `start-claude-mem.sh` | Worker claude-mem (Bun) |
| `start-rtk.sh` | Plugin RTK no Hermes |
| `recover.sh` | Disaster recovery automático |
| `sync-diario.sh` | Cron diário com rebuild completo + logs |

---

## 4. Fluxo de Memória (Write Path)

```
1. Agente toma decisão → tool memory_add
2. Hermes: post_tool_use hook detecta DECISION_TOOLS
   Claude/Codex: PostToolUse hook executa sinapse-hook.py tool-detect
3. _save_decision(title, content) → atomic write em work/active/YYYY-MM-DD-slug.md
4. Se conteúdo contém LEARNING_SIGNALS → _save_learning() → append em brain/Patterns.md
5. post_session_end / Stop hook → _update_current_state() → brain/Current State.md
6. Cron (6h) → build-graph.sh → graphify update → graph.json atualizado
```

## 5. Fluxo de Consulta (Read Path)

```
1. Usuário faz pergunta
2. Hermes: pre_prompt_build hook → _query_vault_knowledge(user_message)
   Claude/Codex: SessionStart hook → sinapse-hook.py session-start
3. _query_vault_knowledge itera _READ_BACKENDS:
   a. _backend_neural_memory(query) → nmem recall → spreading activation
   b. _backend_claude_mem(query) → HTTP /api/context/semantic → Chroma
      fallback: /api/search?query=X → FTS5
   c. _backend_graphify(query) → busca textual em nodes/edges do graph.json
4. Circuit breaker pula backends com 3+ falhas consecutivas
5. Global timeout (8s) garante resposta rápida
6. Primeiro backend com resultado vence → _format_context() → injetado no prompt
```

## 6. Tratamento de Falhas

| Camada | Falha | Comportamento |
|--------|-------|--------------|
| NeuralMemory | Binário ausente ou timeout | Silently skip → tenta próximo backend |
| claude-mem | Worker offline (HTTP ECONNREFUSED) | Silently skip → tenta FTS5 fallback |
| Graphify | graph.json corrompido ou ausente | Retry 3x com sleep 100ms → log error → skip |
| Escrita | Disco cheio ou permissão | Log stderr → retorna None (não crasha) |
| Backend com bug | KeyError, AttributeError | Log traceback → circuit breaker → skip |
| Cron vs Plugin | Leitura parcial durante rebuild | Retry loop + backup automático no build-graph.sh |

---

## 7. Decisões de Design (ADR)

### ADR-001: Vault Obsidian como fonte única
**Decisão:** Usar vault Obsidian com frontmatter YAML + WikiLinks como storage primário.
**Rationale:** Obsidian é um editor maduro com graph view, backlinks e plugin ecosystem. Formato plain-text Markdown é git-friendly e agnóstico de ferramenta.
**Trade-off:** Dependência de reindexação para sincronizar com graph.json (latência de até 6h).

### ADR-002: Backends plugáveis em ordem de prioridade
**Decisão:** NeuralMemory → claude-mem → Graphify, primeiro resultado vence.
**Rationale:** NeuralMemory é mais rápido (spreading activation local), claude-mem oferece busca semântica (embeddings), Graphify é fallback determinístico (regex em JSON).
**Trade-off:** Não mergeia resultados de múltiplos backends (simplicidade sobre completude).

### ADR-003: MCP como protocolo universal para agentes externos
**Decisão:** Expor tools via MCP stdio em vez de criar plugins específicos por agente.
**Rationale:** MCP é um padrão aberto adotado por Anthropic, OpenAI, GitHub e comunidade. Um único server serve todos os agentes.
**Trade-off:** Menos integração profunda (hooks automáticos) vs. plugins nativos.

### ADR-004: Atomic writes para arquivos do vault
**Decisão:** `tempfile.mkstemp()` + `os.replace()` em vez de `open().write()`.
**Rationale:** Evita arquivos truncados se o processo morrer durante a escrita. `os.replace()` é atômico no Linux.
**Trade-off:** Ligeiramente mais complexo que write direto.

---

## 8. Estrutura de Diretórios

```
sinapse_agent/
├── plugins/hermes/sinapse-memory.py    # Plugin principal (984 linhas)
├── scripts/
│   ├── sinapse-write.py                # CLI standalone (multi-agente)
│   ├── sinapse-mcp.py                  # MCP server (stdio JSON-RPC)
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
