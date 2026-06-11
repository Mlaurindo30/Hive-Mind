# Hive-Mind — AGENTS.md
>
> Guia para agentes de IA que trabalham neste projeto.
> Formato cross-agent: Hermes, Claude Code, Codex CLI, Kilo Code, OpenClaw, Copilot.
>
> Última revisão: 10-06-2026

---

## 0. O que é o Hive-Mind v2.0.0

O Hive-Mind é uma infraestrutura de **Inteligência Coletiva e Multimodal**. Ele unifica o que o agente faz, vê e lê em um único cérebro persistente e distribuído.

| Camada | Ferramenta | O que faz | Tecnologia |
|--------|-----------|----------|------------|
| **Cérebro** | **UMC (SQLite)** | Centraliza Grafos, Logs, Vetores e Visão | `sqlite-vec`, `FTS5` |
| **Memória** | **Atlas (Obsidian)** | Fonte única de verdade em Markdown | Obsidian, Syncthing |
| **Visão** | **Deep Portal** | Captura de tela e indexação visual | `mss`, LLM Vision |
| **Consolidação** | **Hive-Dreamer** | Transforma logs e arquivos em conhecimento | `dream_cycle.py` |

---

## 1. Ferramentas Multimodais Disponíveis

Se você é um agente conectado via MCP, você tem acesso às seguintes ferramentas de visão:

- `sinapse_capture_screen`: Tira um print do estado atual do sistema para documentar bugs ou progresso.
- `sinapse_save_visual_memory`: Salva uma imagem específica com descrição e OCR no cérebro.

---

## 2. Arquitetura de fluxo Multimodal

```
CAPTURA (Visão/Texto)          RECONCILIAÇÃO (Sonho)         REDUÇÃO (Atlas)
──────────────────────         ───────────────────────       ───────────────
Agente vê erro/UI    ──┐       Ciclo de Sonho (Noite)  ──┐    Fato Unificado
Agente lê PDF/DOCX   ──┼──►    Dialética Autônoma      ──┼──► Nota no Obsidian
Agente registra Log  ──┘       (Merge de Conflitos)    ──┘    Nó no SQLite
```

---

## 3. Comandos de Operação

```bash
# Iniciar o Watcher (Sincronia em tempo real)
./scripts/start-watcher.sh

# Rodar Auditoria de Integridade (P2P Sync)
python3 scripts/audit_memory.py --fix

# Disparar Ciclo de Consolidação (Dream Cycle)
python3 scripts/dream_cycle.py

# Gerar Portal Visual (Obsidian Canvas)
python3 scripts/generate_portal.py
```

---

## 5. Integração com Agentes Externos

O Sinapse Agent conecta-se a agentes via 3 métodos:

| Método | Agentes | Como funciona |
|--------|---------|--------------|
| **Plugin nativo** | Hermes | `register(ctx)` → hooks `pre_gateway_dispatch`, `post_tool_call`, `on_session_end` |
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
