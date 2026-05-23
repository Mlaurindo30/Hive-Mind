# 04 — Infraestrutura e Escopo

> **Sinapse Agent v1.1.0** — Requisitos, portas, serviços, variáveis de ambiente, segurança.

---

## 1. Requisitos de Hardware

### Mínimo (operação básica, sem LLMs locais)

| Recurso | Requisito |
|---------|-----------|
| CPU | 1 core (ARM ou x86_64) |
| RAM | 512 MB |
| Disco | 2 GB (vault + dependências) |
| Rede | Apenas para instalação inicial |
| SO | Linux (Ubuntu 22.04+, Debian 12+), macOS 13+, WSL2 |

### Recomendado (com Ollama local)

| Recurso | Requisito |
|---------|-----------|
| CPU | 4 cores |
| RAM | 8 GB (para Qwen 2.5 Coder 3B + BGE-M3) |
| Disco | 10 GB (modelos Ollama ~5GB) |
| GPU | Opcional (acelera embeddings) |

---

## 2. Dependências de Software

### Runtime

| Dependência | Versão | Uso |
|-------------|--------|-----|
| Python | 3.10+ | Plugin, Graphify, NeuralMemory, MCP server |
| Node.js | 18+ | claude-mem (opcional) |
| Bun | 1.0+ | Worker runtime do claude-mem |
| Rust (cargo) | 1.70+ | Compilação do RTK (opcional) |
| SQLite | 3.35+ | FTS5 do claude-mem |
| uv | 0.4+ | Gerenciador de pacotes Python (preferido) |
| Git | 2.0+ | Clone de repositórios |

### Opcionais

| Dependência | Uso |
|-------------|-----|
| Ollama | LLMs locais (Qwen, BGE-M3, Nomic) |
| Docker | Sandbox para execução isolada |
| systemd | Serviço do worker claude-mem |
| crontab | Agendamento de rebuild do graph.json |

---

## 3. Portas e Serviços

| Serviço | Porta | Protocolo | Descrição |
|---------|-------|-----------|-----------|
| claude-mem worker | `37700` | HTTP REST | API de busca semântica, health check, search |
| Graphify MCP | stdio | JSON-RPC | Tools: query_graph, get_node, get_neighbors |
| Sinapse MCP | stdio | JSON-RPC | Tools: sinapse_query, sinapse_save_decision, etc. |

**Nota:** Nenhuma porta é exposta para a rede externa. O worker claude-mem escuta em `127.0.0.1:37700` (localhost only). Os MCP servers usam stdio (comunicação via stdin/stdout do processo).

---

## 4. Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `SINAPSE_HOME` | Raiz do projeto | `~/Documentos/Projects/sinapse_agent` |
| `SINAPSE_DRY_RUN` | Modo sem side effects no filesystem | `false` |
| `SINAPSE_LOG_JSON` | Logs estruturados em JSON | `false` |
| `SINAPSE_DECISION_TOOLS` | CSV de tool names que disparam escrita | `memory_add,observation_add,mcp_claude_mem_memory_add` |
| `SINAPSE_LEARNING_SIGNALS` | CSV de palavras que disparam aprendizados | Lista pt/en/es |
| `GOOGLE_API_KEY` | API key Gemini (opcional) | — |
| `CLAUDE_MEM_DATA_DIR` | Data directory do claude-mem | `$SINAPSE_HOME/claude-mem/data` |

---

## 5. Serviços Systemd

### sinapse-claude-mem.service

```ini
[Unit]
Description=Sinapse Agent — claude-mem Worker
After=network.target

[Service]
Type=simple
Environment=CLAUDE_MEM_DATA_DIR=/home/user/sinapse_agent/claude-mem/data
ExecStart=/home/user/.bun/bin/bun /home/user/sinapse_agent/claude-mem/plugin/scripts/worker-service.cjs
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

**Comandos:**
```bash
systemctl --user status sinapse-claude-mem.service
systemctl --user restart sinapse-claude-mem.service
journalctl --user -u sinapse-claude-mem.service -f
```

---

## 6. Cron Jobs

```cron
# Rebuild do knowledge graph a cada 6 horas
0 */6 * * * cd /home/user/sinapse_agent && ./scripts/build-graph.sh >> logs/sync.log 2>&1

# Rebuild completo semanal (domingo 2am)
0 2 * * 0 /home/user/sinapse_agent/cron/sync-diario.sh
```

---

## 7. Estrutura de Diretórios de Dados

```
~/Documentos/Projects/sinapse_agent/
├── cerebro/                         # Vault Obsidian (fonte única)
│   ├── graphify-out/
│   │   ├── graph.json               # Knowledge graph (2MB, rebuildado 6h)
│   │   ├── graph.json.bak           # Backup automático
│   │   └── cache/                   # Cache regenerável (SHA256, .gitignore)
│   ├── brain/
│   │   ├── Current State.md         # Estado atual (atualizado por sessão)
│   │   ├── Patterns.md              # Aprendizados acumulados (append-only)
│   │   └── *.md                     # Notas de conhecimento operacional
│   └── work/active/                 # Decisões e projetos ativos
├── claude-mem/data/                 # SQLite + ChromaDB (local, .gitignore)
│   ├── claude-mem.db                # SQLite FTS5
│   └── chroma/                      # ChromaDB embeddings
├── logs/                            # Logs de sync (30 dias retenção)
│   └── sync-YYYYMMDD-HHMMSS.log
└── .env                             # API keys (nunca commitado)
```

---

## 8. Segurança

### 8.1 Princípios

1. **Nenhuma porta exposta à rede externa.** Todos os serviços escutam em localhost ou usam stdio.
2. **API keys no `.env`**, nunca commitadas (`.gitignore`).
3. **Dry-run mode** disponível para testes sem side effects.
4. **Atomic writes** previnem corrupção de arquivos em falhas.

### 8.2 Arquivos Sensíveis

| Arquivo | Conteúdo | Proteção |
|---------|----------|----------|
| `.env` | `GOOGLE_API_KEY`, tokens | `.gitignore`, permissões 600 |
| `.env.example` | Template sem valores reais | Commitado |
| `claude-mem/data/` | Observações, embeddings | `.gitignore` |
| `graphify-out/cache/` | Cache regenerável | `.gitignore` |

### 8.3 Superfície de Ataque

| Vetor | Risco | Mitigação |
|-------|-------|-----------|
| Worker HTTP (37700) | Acesso local não autorizado | `127.0.0.1` only |
| Injeção em queries | MCP/CLI recebe input arbitrário | Regex sanitization, timeouts |
| Path traversal | Escrita de arquivos no vault | `_sanitize_slug()` remove `/`, `..` |
| JSON injection | graph.json parsing | `json.load()` + schema validation |

---

## 9. Escopo do Sistema

### 9.1 O que o Sinapse Agent FAZ

- ✅ Indexa vault Obsidian em knowledge graph queryable
- ✅ Trackeia eventos de agentes com busca temporal (FTS5 + Chroma)
- ✅ Otimiza comandos shell em tempo real (RTK)
- ✅ Fornece busca associativa (spreading activation)
- ✅ Injeta contexto do vault automaticamente no prompt (Hermes, Claude Code, Codex)
- ✅ Salva decisões e aprendizados no vault automaticamente
- ✅ Funciona offline (fallback determinístico sem LLMs)
- ✅ Suporta múltiplos agentes via 3 métodos de integração

### 9.2 O que o Sinapse Agent NÃO FAZ

- ❌ Não substitui o Obsidian como editor de vault
- ❌ Não é um agente de IA (é uma camada de memória para agentes)
- ❌ Não treina modelos próprios
- ❌ Não faz busca na internet
- ❌ Não gerencia autenticação de usuários
- ❌ Não é um banco de dados distribuído

---

## 10. Deploy Típico

```
┌─────────────────────────────────────────────────┐
│                 VPS / Servidor Local              │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Ollama   │  │ claude-  │  │ Graphify       │  │
│  │ (LLMs)   │  │ mem      │  │ (indexador)    │  │
│  │ :11434   │  │ :37700   │  │ stdio MCP      │  │
│  └──────────┘  └──────────┘  └───────────────┘  │
│                                                   │
│  ┌──────────────────────────────────────────┐    │
│  │        sinapse-memory (plugin/MCP)        │    │
│  │  ┌─────────┐  ┌────────┐  ┌───────────┐  │    │
│  │  │ nmem    │  │HTTP API│  │ graph.json │  │    │
│  │  │ recall  │  │ client │  │ reader     │  │    │
│  │  └─────────┘  └────────┘  └───────────┘  │    │
│  └──────────────────────────────────────────┘    │
│                       │                           │
│                       ▼                           │
│  ┌──────────────────────────────────────────┐    │
│  │           Vault Obsidian (cerebro/)       │    │
│  │           ~200 arquivos .md               │    │
│  └──────────────────────────────────────────┘    │
│                                                   │
│  Cron (6h): build-graph.sh                        │
│  Cron (dom): sync-diario.sh                       │
└─────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   ┌──────────┐                  ┌──────────┐
   │ Hermes   │                  │ Claude   │
   │ (plugin) │                  │ Code     │
   └──────────┘                  │ (MCP)    │
                                 └──────────┘
```
