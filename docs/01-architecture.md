# 01 — Arquitetura e Abordagem Técnica

> **Hive-Mind v2.0.0** — Camada de memória universal, distribuída e multimodal para agentes de IA.

---

## 1. Visão Geral

O Hive-Mind é a evolução do Sinapse Agent. Ele resolve o problema de **continuidade de memória** e **inteligência coletiva** entre sessões de agentes de IA e múltiplos dispositivos. Sem ele, cada sessão começa "do zero".

A solução organiza a memória em um **Unified Memory Core (UMC)** baseado em SQLite, integrando 5 dimensões do conhecimento:

| Dimensão | Pergunta | Ferramenta | Tecnologia |
|----------|----------|-----------|------------|
| **Estrutural** | O QUE existe? | Graphify | Grafos, Leiden clustering |
| **Temporal** | QUANDO ocorreu? | UMC Logs | SQLite FTS5 |
| **Associativa** | O que é SIMILAR? | UMC Vectors | `sqlite-vec` (all-MiniLM-L6-v2) |
| **Distribuída** | Onde está a VERDADE? | Swarm Layer | Syncthing, UUID v4, SHA-256 |
| **Multimodal** | Como isso PARECE? | Deep Portal | Vision LLM, OCR, Obsidian Canvas |

**Fonte única de verdade:** Vault Obsidian em `cerebro/` sincronizado via P2P.

---

## 2. Princípios de Design

### 2.1 Unified Memory Core (UMC)
Diferente da v1.1.0, o Hive-Mind centraliza tudo em um banco SQLite (`hive_mind.db`). Isso elimina a fragmentação entre Chroma, JSON e arquivos locais, permitindo buscas híbridas complexas em milissegundos.

### 2.2 Soberania de Modelos (Hive-Dreamer)
O usuário tem controle total sobre qual "Cérebro" processa as memórias através das variáveis `HIVE_DREAMER_PROVIDER` e `HIVE_DREAMER_MODEL`. O sistema é agnóstico e não força o uso de modelos específicos.

### 2.3 Sincronização em Enxame (P2P Swarm)
Utiliza o **Syncthing** para mover arquivos Markdown. A integridade entre o banco de dados e os arquivos físicos é garantida por **Hashes de Integridade** e um **Swarm Auditor** que detecta e resolve divergências automaticamente.

### 2.4 Multimodalidade por Design
A memória não é apenas texto. O Hive-Mind captura o estado do sistema (screenshots) e ingere documentos (PDF/DOCX), transformando-os em conhecimento semântico pesquisável.

---

## 3. Componentes do Sistema

### 3.1 Unified Memory Core (UMC) - SQLite
O coração do sistema. Tabelas principais:
- `neurons`: Conceitos, notas e fatos.
- `synapses`: Relações entre neurônios.
- `observations`: Logs temporais brutos.
- `visual_memories`: Metadados de capturas visuais e OCR.
- `ambiguities`: Fila de conflitos semânticos para resolução.

### 3.2 Hive-Dreamer (dream_cycle.py)
O pipeline de consolidação que roda em background:
1.  **Reflexão:** Extrai fatos de observações brutas.
2.  **Visão:** Processa imagens da inbox visual.
3.  **Síntese:** Resolve conflitos semânticos P2P (Dialética).
4.  **Roteamento:** Organiza o conhecimento na taxonomia do Atlas.

### 3.3 Real-time Watcher (scripts/start-watcher.sh)
Monitora o Vault Obsidian e reflete qualquer mudança no SQLite/Vetores em < 2 segundos, eliminando a necessidade de rebuilds periódicos.

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
