# Hive-Mind — AGENTS.md

> Guia para agentes de IA que trabalham **neste repositório**.
> Formato cross-agent: Hermes, Claude Code, Codex CLI, Kilo Code, OpenClaw, Copilot, Gemini CLI.
> Última revisão: 2026-06-10 · Referência canônica de arquitetura: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## 1. O que é o Hive-Mind v2.0.0

Infraestrutura de **inteligência coletiva e multimodal**: unifica o que o agente faz, vê e lê em um único cérebro persistente e distribuído.

| Camada | Ferramenta | O que faz | Tecnologia |
|--------|-----------|-----------|------------|
| **Cérebro** | UMC (`hive_mind.db`) | Centraliza grafo, logs, vetores, FTS e visão | SQLite + `sqlite-vec` + FTS5 |
| **Memória** | Atlas (`cerebro/`) | Fonte única de verdade em Markdown | Obsidian + Syncthing |
| **Visão** | Deep Portal | Captura de tela e indexação visual | `mss` + LLM Vision |
| **Consolidação** | Hive-Dreamer | Logs/arquivos → conhecimento validado | `dream_cycle.py` (Pydantic) |
| **Acesso** | MCP / Plugin / CLI / REST | Conecta qualquer agente ao cérebro | stdio JSON-RPC · FastAPI :37702 |

---

## 2. Ferramentas MCP disponíveis

Se você está conectado via MCP (`scripts/sinapse-mcp.py`):

| Tool | Quando usar |
|------|-------------|
| `sinapse_query` | Antes de responder sobre algo que pode já estar no cérebro |
| `sinapse_save_decision` | Ao tomar/registrar uma decisão de projeto |
| `sinapse_save_learning` | Ao identificar um padrão ou aprendizado |
| `sinapse_temporal_search` / `sinapse_temporal_save` | Busca/escrita direta na camada temporal |
| `sinapse_health` | Diagnóstico dos backends |
| `sinapse_session_end` | Sempre ao final de uma sessão de trabalho |
| `sinapse_zettelkasten_split` | Nota grande demais → notas atômicas |
| `sinapse_capture_screen` | Documentar bugs/progresso visualmente |

---

## 3. Fluxo multimodal

```
CAPTURA (Visão/Texto)          RECONCILIAÇÃO (Sonho)          REDUÇÃO (Atlas)
──────────────────────         ───────────────────────        ─────────────────
Agente vê erro/UI    ──┐       Dream Cycle (noturno)    ──┐   Fato unificado
Agente lê PDF/DOCX   ──┼──►    Distiller→Validator→     ──┼──► Nota no Obsidian
Agente registra log  ──┘       Router + Síntese Dialética──┘   Neuron no SQLite
```

---

## 4. Comandos de operação

```bash
./scripts/start-watcher.sh              # Sincronia em tempo real (Obsidian → SQLite)
python3 scripts/dream_cycle.py          # Ciclo de consolidação (Dream Cycle)
python3 scripts/audit_memory.py --fix   # Auditoria de integridade (P2P)
python3 scripts/generate_portal.py      # Portal visual (Obsidian Canvas)
./scripts/setup-dreamer.sh              # Configurar provedor/modelo do Dreamer
./scripts/recover.sh                    # Disaster recovery
python3 scripts/sinapse-api.py          # REST API (requer HIVE_MIND_API_KEY)
```

---

## 5. Instalação em máquina nova (instruções para agente ou humano)

Sequência completa para colocar o Hive-Mind funcionando do zero:

```bash
# 1. Clonar o repositório
git clone <repo-url> ~/Hive-Mind && cd ~/Hive-Mind

# 2. Instalação completa (deps, UMC, watcher, cron, MCP nos agentes detectados)
./install.sh

# 3. Configurar o LLM do Dream Cycle (interativo)
./scripts/setup-dreamer.sh

# 4. Verificar saúde
python3 scripts/sinapse-write.py health
```

**Para registrar o MCP sem reinstalar tudo** (ex.: instalou um agente novo depois):

```bash
./scripts/register-mcp.sh           # detecta e registra em todos os agentes
./scripts/register-mcp.sh --check   # só mostra o status, sem modificar
```

O script é idempotente e faz **merge** no JSON de cada agente — nunca apaga outros MCP servers já registrados. Agentes suportados na detecção automática: Claude Code, Codex CLI, Gemini CLI, Qwen Code, Kimi Code, Kiro, Kilo Code, Roo Code, VS Code/Copilot, Cursor, OpenCode, OpenClaw. Após registrar, **reinicie o agente** para ele carregar as 9 tools e valide pedindo: "use a tool sinapse_health".

---

## 6. Integração com agentes externos

| Método | Agentes | Como funciona |
|--------|---------|---------------|
| **Plugin nativo** | Hermes | `register(ctx)` → hooks `pre_gateway_dispatch`, `post_tool_call`, `on_session_end` |
| **MCP server** | Claude Code, Codex CLI, Cursor, Kilo Code, OpenClaw, Copilot, Gemini CLI, ZooCode, Aider | `scripts/sinapse-mcp.py` → 9 tools via stdio JSON-RPC |
| **CLI standalone** | Qualquer agente com shell | `scripts/sinapse-write.py` → `decision`, `learning`, `query`, `health`, `session-end` |
| **REST API** | Agentes remotos / VPS | `scripts/sinapse-api.py` → Bearer auth, porta 37702 |

Hooks automáticos para Claude Code e Codex CLI:
- `cerebro/.claude/settings.json` — SessionStart, PostToolUse, Stop
- `cerebro/.codex/hooks.json` — SessionStart, PostToolUse, Stop
- `cerebro/.claude/scripts/sinapse-hook.py` — script invocado pelos hooks

---

## 7. Guardrails

- **Nunca** commite dados sensíveis: `.env`, API keys, tokens, `hive_mind.db` (banco de memória pessoal).
- **Nunca** modifique `cerebro/` sem o Watcher ativo (ou rode `./scripts/build-graph.sh` depois).
- **Nunca** use `graphify cerebro/` sem `--backend` se não tiver API key ou Ollama — use `graphify update cerebro/` (AST-only).
- **Nunca** duplique dados entre vault e ferramentas externas. O vault é a fonte única.
- **Nunca** hardcode modelos de LLM — o sistema obedece estritamente `HIVE_DREAMER_PROVIDER/MODEL` do `.env`.
- **Testes unitários não chamam LLM real.** Lógica ao redor da LLM se testa com dados determinísticos; o modelo real só entra em `tests/test_synthesis.py` e nos fluxos E2E.

---

## 8. Testes

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

**116 testes coletáveis** (contagem de 2026-06-10).

### Disaster recovery

```bash
./scripts/recover.sh
```
