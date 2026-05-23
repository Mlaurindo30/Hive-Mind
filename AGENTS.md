# Sinapse Agent — AGENTS.md
>
> Guia para agentes de IA que trabalham neste projeto.
> Formato cross-agent: Hermes, Claude Code, Codex CLI, Kilo Code, OpenClaw, Copilot.
>
> Última revisão: 2026-05-23

---

## 0. Idioma

- **Conversas:** Português (BR).
- **Código e saída técnica:** Inglês.
- **Documentação:** Português (BR).

---

## 1. O que é o Sinapse Agent

Camada de memória universal para agentes de IA. Quatro componentes:

| Camada | Ferramenta | O que faz | Source |
|--------|-----------|----------|--------|
| Estrutural | **Graphify** | Knowledge graph do vault (Leiden clustering) | `graphify/` (safishamsi/graphify) |
| Temporal | **claude-mem** | Tracking de eventos e observações (FTS5 + Chroma) | `claude-mem/` (thedotmack/claude-mem) |
| Execução | **RTK** | Otimização de comandos shell | `rtk/` (rtk-ai/rtk) |
| Associativa | **NeuralMemory** | Spreading activation, 24 tipos de relações | `neural-memory/` (nhadaututtheky/neural-memory) |

Vault: `cerebro/` (Obsidian, template obsidian-mind). Fonte única de verdade.

**Documentação técnica completa:** `docs/` — Arquitetura, Modelos IA, Pipeline, Infraestrutura, Blueprints, Gap Analysis.

---

## 2. Como trabalhar neste projeto

### Ao iniciar

1. Leia `cerebro/AGENTS.md`
2. Leia `cerebro/brain/Current State.md`
3. Verifique se o graph.json está atualizado: `cerebro/graphify-out/graph.json`
4. Execute health check: `python3 scripts/sinapse-write.py health`

### Ao modificar código

- **Plugin sinapse-memory**: Python. `plugins/hermes/sinapse-memory.py` (984 linhas).
- **Graphify**: Python. `pip install -e graphify/[all]` para instalar do source.
- **claude-mem**: TypeScript/Node. `cd claude-mem && npm install && npm run build`.
- **RTK**: Rust. `cd rtk && cargo build --release`.
- **NeuralMemory**: Python. `pip install -e neural-memory/` para instalar do source.

### Ao modificar o vault

- Toda nota em `cerebro/` usa frontmatter YAML + WikiLinks.
- Após editar o vault, reindexe: `./scripts/build-graph.sh` (ou aguarde o cron a cada 6h).

### Ao commitar

- Não commite `cerebro/graphify-out/cache/` (cache regenerável).
- Não commite `claude-mem/data/` (dados locais).
- Não commite `rtk/target/` (build Rust).

---

## 3. Arquitetura de fluxo

```
ESCRITA                        INDEXAÇÃO                    LEITURA
───────                        ─────────                    ───────────────
Agente decide                  Cron (6h)                    Usuário pergunta
     │                             │                            │
     ▼                             ▼                            ▼
sinapse-memory                build-graph.sh              sinapse-memory
(post_tool_use)                   │                       (pre_prompt_build)
     │                             ▼                            │
     ├──► work/active/         graphify update             ├──► 1. nmem recall
     ├──► brain/Patterns.md    cerebro/                    │    (spreading activation)
     └──► brain/Current            │                       ├──► 2. claude-mem
          State.md                 ▼                       │    (Chroma semantic)
                              graph.json                       │
                              (1266 nodes,                     └──► 3. graph.json
                              1319 edges,                          (Graphify structural)
                              117 communities)                         │
                                                                     ▼
                                                              Contexto injetado
                                                              no prompt
```

---

## 4. Comandos úteis

```bash
# Health check de todos os backends
python3 scripts/sinapse-write.py health

# Buscar no vault via CLI
python3 scripts/sinapse-write.py query "sua pergunta"

# Salvar decisão via CLI (para agentes sem MCP)
python3 scripts/sinapse-write.py decision --title "Título" --content "Conteúdo"

# Indexar vault (sem LLM)
./scripts/build-graph.sh

# Iniciar MCP server Sinapse (stdio — 5 tools)
python3 scripts/sinapse-mcp.py

# Iniciar MCP server Graphify (modo stdio)
./scripts/serve-graph.sh

# Iniciar claude-mem worker
./scripts/start-claude-mem.sh

# Compilar RTK
cd rtk && cargo build --release

# Instalar tudo
./install.sh

# Disaster recovery
./scripts/recover.sh
```

---

## 5. Integração com Agentes Externos

O Sinapse Agent conecta-se a agentes via 3 métodos:

| Método | Agentes | Como funciona |
|--------|---------|--------------|
| **Plugin nativo** | Hermes | `register(ctx)` → hooks `pre_prompt_build`, `post_tool_use`, `post_session_end` |
| **MCP server** | Claude Code, Codex CLI, Kilo Code, OpenClaw, Copilot, Gemini CLI, ZooCode | `scripts/sinapse-mcp.py` → 5 tools via stdio JSON-RPC |
| **CLI standalone** | Qualquer agente com shell | `scripts/sinapse-write.py` → subcomandos `decision`, `learning`, `query`, `health`, `session-end` |

Hooks automáticos para Claude Code e Codex CLI:
- `cerebro/.claude/settings.json` — SessionStart, PostToolUse, Stop
- `cerebro/.codex/hooks.json` — SessionStart, PostToolUse, Stop
- `cerebro/.claude/scripts/sinapse-hook.py` — script invocado pelos hooks

---

## 6. Guardrails

- **Nunca** modifique `cerebro/` manualmente sem atualizar o graph.json depois.
- **Nunca** use `graphify cerebro/` sem `--backend` se não tiver API key ou Ollama. Use `graphify update cerebro/` para AST-only.
- **Nunca** duplique dados entre vault e ferramentas externas. O vault é a fonte única.
- **Nunca** commite dados sensíveis (API keys, .env, tokens).

---

## 7. Testes

Antes de qualquer commit, execute:

```bash
./tests/run_all.sh
```

Se a suite completa for muito longa, execute ao menos os smoke tests:

```bash
bash tests/smoke/test_smoke.sh
```

### Níveis de teste

| Nível | Comando | Requisitos |
|-------|---------|------------|
| Smoke | `bash tests/smoke/test_smoke.sh` | Binários no PATH |
| Unit | `python3 -m pytest tests/unit/ -v` | pytest, Python 3.10+ |
| Integration | `python3 -m pytest tests/integration/ -v --run-integration` | Backends reais |
| E2E | `python3 -m pytest tests/e2e/ -v --run-e2e` | Sistema completo |

**Total: 103 testes** (66 unitários + 15 integração + 22 E2E).

### Disaster Recovery

```bash
./scripts/recover.sh
```
