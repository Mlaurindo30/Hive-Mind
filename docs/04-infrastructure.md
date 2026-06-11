# 04 — Infraestrutura e Configuração

> **Hive-Mind v2.0.0** — Requisitos, serviços, portas, variáveis de ambiente e operações.

---

## 1. Requisitos de Software

### 1.1 Runtime

| Dependência | Versão mínima | Uso |
|-------------|--------------|-----|
| Python | 3.10+ | Núcleo — scripts, MCP server, REST API, Dream Cycle |
| SQLite | 3.44+ | UMC com `sqlite-vec` (extensão necessária) |
| Node.js / Bun | 18+ / 1.0+ | claude-mem (TypeScript) |
| Rust / Cargo | 1.70+ | RTK (compilação única; binário pré-compilado opcional) |
| Syncthing | 1.27+ | P2P sync de arquivos Markdown entre máquinas |
| uv | 0.4+ | Gerenciador de pacotes Python |

### 1.2 Dependências Python (requirements.txt)

| Pacote | Versão | Uso |
|--------|--------|-----|
| `fastapi` | ≥0.111 | REST API (sinapse-api.py) |
| `uvicorn` | ≥0.29 | ASGI server para FastAPI |
| `pydantic` | ≥2.7 | Validação de saída LLM + schemas |
| `cryptography` | ≥42 | Fernet encryption (vault de segredos) |
| `fastembed` | ≥0.3 | Embeddings all-MiniLM-L6-v2 384d (local) |
| `watchdog` | ≥4.0 | Watcher de arquivos real-time |
| `pypdf` | ≥4.0 | Extração de texto de PDFs |
| `python-docx` | ≥1.1 | Leitura de documentos Word |
| `PyMuPDF` | ≥1.24 | Extração de imagens de PDFs |
| `mss` | ≥9.0 | Captura de screenshots |
| `pyyaml` | ≥6.0 | Parsing de frontmatter YAML |
| `httpx` | ≥0.27 | Cliente HTTP assíncrono (cloud mode) |

---

## 2. Variáveis de Ambiente

```
# .env na raiz do projeto (nunca commitado)
```

### 2.1 Sistema

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `SINAPSE_HOME` | Caminho raiz do projeto | auto-detectado |
| `SINAPSE_DRY_RUN` | `1` para executar sem side effects | `0` |
| `HIVE_MIND_API_KEY` | Bearer token da REST API (obrigatório) | sem padrão |
| `HIVE_MIND_API_PORT` | Porta da REST API | `37702` |

### 2.2 Hive-Dreamer (Dream Cycle)

| Variável | Descrição | Exemplos |
|----------|-----------|---------|
| `HIVE_DREAMER_PROVIDER` | Provider do LLM de consolidação | `google`, `openai`, `anthropic`, `ollama`, `deepseek` |
| `HIVE_DREAMER_MODEL` | Modelo específico | `gemini-2.0-flash`, `gpt-4o`, `claude-haiku-4-5-20251001` |
| `OLLAMA_LOCAL` | URL base do Ollama | `http://localhost:11434` |

### 2.3 API Keys por Provider

| Variável | Provider |
|----------|---------|
| `GOOGLE_API_KEY` | Google AI Studio (Gemini) |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth Device Flow |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth Device Flow (**⚠️ rotacionar se comprometido**) |
| `OPENAI_API_KEY` | OpenAI / OpenRouter-compatible |
| `ANTHROPIC_API_KEY` | Anthropic |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `HUGGINGFACE_API_KEY` | Hugging Face Inference |
| `QWEN_API_KEY` | Alibaba Qwen (DashScope) |
| `NVIDIA_API_KEY` | NVIDIA NIM |
| `OPENROUTER_API_KEY` | OpenRouter |

---

## 3. Serviços e Portas

| Serviço | Porta | Protocolo | Acesso | Processo |
|---------|-------|-----------|--------|---------|
| REST API (FastAPI) | 37702 | HTTP REST | localhost (VPS: Bearer token) | `sinapse-api.py` |
| claude-mem Worker | 37700 | HTTP REST | localhost only | `bun run serve` |
| Ollama | 11434 | HTTP REST | localhost | `ollama serve` |
| MCP Server (sinapse-mcp) | stdio | JSON-RPC | processo do agente | `sinapse-mcp.py` |
| Syncthing UI | 8384 | HTTP | localhost | `syncthing` |

Nenhuma porta é exposta externamente por padrão. Para deploy em VPS, a REST API (:37702) é exposta atrás de nginx/Caddy com TLS.

---

## 4. Serviços em Background

### 4.1 Real-time Watcher

```bash
# Iniciar watcher em background
./scripts/start-watcher.sh &

# Verificar se está rodando
pgrep -f "start-watcher" && echo "OK"

# Parar
pkill -f "start-watcher"
```

O Watcher usa `watchdog` para monitorar `cerebro/`. Ao detectar mudança em `.md`:
1. Enfileira evento (debounce 500ms para evitar reindex duplo)
2. Chama Graphify para reindexar o arquivo
3. Atualiza `neurons`, `synapses`, `search_fts`, `search_vec`

### 4.2 claude-mem (Tracking Temporal)

```bash
# Na pasta claude-mem/
bun run serve     # start em :37700
bun run build     # compila TypeScript
```

### 4.3 Syncthing P2P

```bash
syncthing &       # inicia daemon
# UI em: http://localhost:8384
```

---

## 5. Cron Jobs

```cron
# Auditoria P2P de integridade + reindexação de arquivos recebidos (a cada hora)
0 * * * * cd $SINAPSE_HOME && python3 scripts/audit_memory.py --fix >> logs/audit.log 2>&1

# Backup do UMC (diário às 3am)
0 3 * * * cp $SINAPSE_HOME/hive_mind.db $SINAPSE_HOME/backups/hive_mind_$(date +\%F).db

# Limpeza de backups antigos (mantém 30 dias)
0 4 * * * find $SINAPSE_HOME/backups/ -name "*.db" -mtime +30 -delete
```

O cron de rebuild a cada 6h da v1.x foi **removido** — o Watcher cobre a atualização em tempo real para mudanças locais.

---

## 6. Estrutura de Diretórios

```
  Hive-Mind/
  ├── cerebro/                       Vault Obsidian (fonte única de verdade)
  │   ├── atlas/                     Fatos consolidados pelo Dream Cycle
  │   ├── brain/
  │   │   ├── Current State.md       Estado atual (atualizado no Stop hook)
  │   │   └── Patterns.md            Aprendizados acumulados
  │   ├── work/
  │   │   └── active/                Decisões ativas (YYYY-MM-DD-slug.md)
  │   ├── inbox/
  │   │   ├── visual/                Screenshots capturados
  │   │   └── documents/             PDFs e DOCXs aguardando ingestão
  │   ├── conflicts/                 Conflitos P2P resolvidos (histórico)
  │   ├── graphify-out/              Saída do Graphify (graph.json, report)
  │   ├── .claude/
  │   │   └── settings.json          Hooks Claude Code (SessionStart, PostToolUse, Stop)
  │   └── .codex/
  │       └── hooks.json             Hooks Codex CLI
  ├── core/
  │   ├── umc_schema.sql             DDL completo do banco
  │   ├── database.py                Pool de conexões (WAL, busy_timeout=5000)
  │   ├── auth.py                    Auth de 10 provedores LLM
  │   └── schemas/                   Modelos Pydantic do Dream Cycle
  ├── scripts/
  │   ├── dream_cycle.py             Pipeline de consolidação offline
  │   ├── sinapse-mcp.py             MCP server (9 tools, stdio)
  │   ├── sinapse-api.py             REST API FastAPI (:37702)
  │   ├── sinapse-write.py           CLI standalone
  │   ├── sinapse-hook.py            Hook universal (Claude Code / Codex)
  │   ├── audit_memory.py            Auditoria P2P (hash check + reindex)
  │   ├── semantic_diff.py           Classificação de conflitos (vetorial + LLM)
  │   ├── document_ingest.py         Ingestão PDF/DOCX → observations
  │   ├── visual_capture.py          Screenshots → visual_memories
  │   ├── generate_portal.py         Gerador de portal.canvas (Obsidian)
  │   ├── setup-dreamer.py           UI de configuração do Hive-Dreamer
  │   ├── setup-dreamer.sh           Wrapper shell do setup-dreamer.py
  │   ├── start-watcher.sh           Inicia Watcher em background
  │   └── recover.sh                 Disaster recovery (rebuild do UMC)
  ├── plugins/
  │   └── hermes/
  │       └── sinapse-memory.py      Plugin nativo para Hermes Agent
  ├── graphify/                      Indexador estrutural (subprojeto)
  ├── claude-mem/                    Tracking temporal TypeScript/Bun
  ├── rtk/                           Shell optimizer Rust
  ├── neural-memory/                 Spreading activation recall
  ├── tests/                         116 testes (smoke/unit/integration/e2e)
  ├── mcp/                           Templates de config MCP por agente
  ├── docs/                          Esta documentação
  ├── hive_mind.db                   Unified Memory Core (SQLite + sqlite-vec)
  ├── sinapse.yaml                   Configuração central
  ├── .env                           Segredos locais (gitignored)
  ├── .env.example                   Template de variáveis (commitado)
  ├── requirements.txt               Dependências Python
  └── install.sh                     Instalador (10 etapas)
```

---

## 7. Segurança

### 7.1 Princípios

1. **Fail-closed**: REST API não inicia sem `HIVE_MIND_API_KEY`
2. **API keys no `.env`**: nunca commitadas (`.gitignore` cobre `.env` e `*.db`)
3. **Tokens em tempo constante**: comparação `hmac.compare_digest` em vez de `==`
4. **Vault de segredos**: segredos detectados nos conteúdos são cifrados com Fernet e substituídos por `[SECRET:uuid]`
5. **Atomic writes**: `os.replace()` previne corrupção de arquivos em falhas

### 7.2 Superfície de Ataque

| Vetor | Risco | Mitigação |
|-------|-------|-----------|
| REST API (:37702) | Token forjado | `hmac.compare_digest` — timing-safe |
| claude-mem Worker (:37700) | Acesso local não autorizado | Bind em `127.0.0.1` only |
| Path traversal (escrita vault) | Arquivo fora de `cerebro/` | `_sanitize_slug()` remove `/` e `..` |
| Injeção de secrets (MCP input) | API key em query | Regex scan → Fernet → vault table |
| Google OAuth client_secret | Comprometido se hardcoded | Apenas via `.env` (`_env("GOOGLE_OAUTH_CLIENT_SECRET")`) |

### 7.3 Arquivos Sensíveis

| Arquivo/Diretório | Conteúdo | Proteção |
|-------------------|----------|----------|
| `.env` | API keys, tokens, OAuth secrets | `.gitignore`, chmod 600 |
| `hive_mind.db` | Toda a memória (inclui vault table) | `.gitignore` |
| `claude-mem/data/` | Observações com timestamps | `.gitignore` |
| `backups/` | Backups do UMC | `.gitignore` |

---

## 8. Deploy

### 8.1 Local (desenvolvimento)

```
  ┌─────────────────────────────────────────────┐
  │                 Máquina Local                 │
  │                                               │
  │  ┌──────────────────────────────────────┐    │
  │  │          hive_mind.db (UMC)          │    │
  │  │   neurons / synapses / FTS5 / vec    │    │
  │  └──────────────────────────────────────┘    │
  │       ▲              ▲              ▲         │
  │  Watcher (~2s)   claude-mem    sinapse-api    │
  │  :watchdog       :37700        :37702         │
  │                                               │
  │  ┌──────────────┐   ┌──────────────────────┐ │
  │  │  Obsidian    │   │  Agentes de IA        │ │
  │  │  (cerebro/)  │   │  MCP / Hooks / Plugin │ │
  │  └──────────────┘   └──────────────────────┘ │
  └─────────────────────────────────────────────┘
              │ Syncthing P2P
              ▼
        Outros dispositivos
```

### 8.2 VPS / Cloud

```
  ┌─────────────────────────────────────────────┐
  │                VPS (cloud)                    │
  │                                               │
  │  nginx/Caddy (TLS) → sinapse-api (:37702)    │
  │  systemd: watcher + claude-mem + api          │
  │  Ollama (:11434) — modelos locais             │
  │  Syncthing — recebe vault de outras máquinas  │
  └─────────────────────────────────────────────┘
              │
              │ HTTPS (Bearer token)
              ▼
  ┌──────────────────┐   ┌──────────────────┐
  │ Máquina local 1  │   │ Máquina local 2  │
  │ (cloud.enabled)  │   │ (cloud.enabled)  │
  └──────────────────┘   └──────────────────┘
```

### 8.3 O que o Hive-Mind FAZ e NÃO FAZ

| FAZ | NÃO FAZ |
|-----|---------|
| Indexa vault Obsidian em UMC queryable | Não substitui o Obsidian como editor |
| Injeta contexto automaticamente nos agentes | Não é um agente de IA |
| Consolida memória offline via Dream Cycle | Não treina modelos próprios |
| Sincroniza vault entre máquinas via Syncthing | Não é um banco de dados distribuído |
| Resolve conflitos P2P via Síntese Dialética | Não faz busca na internet |
| Processa imagens e documentos (Phase 10) | Não gerencia autenticação de usuários |
