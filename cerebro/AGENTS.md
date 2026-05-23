# Sinapse Agent — Vault (AGENTS.md)

> Formato cross-agent: Thoth (Hermes), Claude Code, Codex, OpenCode, Gemini CLI, Cursor, Copilot.
> Stack: Graphify (knowledge graph) + claude-mem (temporal tracking) + RTK (execution optimization).
> Template base: [obsidian-mind](https://github.com/breferrari/obsidian-mind).
> Última revisão: 2026-05-22.

---

## 0. Idioma

- **Vault:** Português (BR). Todas as notas, templates, documentação.
- **Código e saída técnica:** Inglês.
- **Conversas com Michel:** Português (BR).

---

## 1. O que é este vault

Fonte única de verdade para Thoth (agente pessoal do Michel) e todos os coding agents. Três camadas de memória:

| Camada | Ferramenta | O que faz | Como acessar |
|--------|-----------|----------|-------------|
| Estrutural | **Graphify** | Knowledge graph com Leiden clustering (1266 nodes) | `graphify-out/graph.json` |
| Temporal | **claude-mem** | Tracking de eventos, FTS5, Chroma | Worker HTTP `:37700` |
| Execução | **RTK** | Otimização de comandos shell | Plugin Hermes `pre_tool_call` |

**Verificação de saúde (antes de qualquer sessão):**
```bash
ls graphify-out/graph.json                          # graph deve existir
curl -s http://127.0.0.1:37700/health               # worker deve responder {"status":"ok"}
systemctl --user is-active sinapse-claude-mem.service
```

---

## 2. Estrutura do vault

| Pasta | Propósito | Arquivos-chave |
|-------|-----------|---------------|
| `brain/` | Conhecimento operacional do agente | North Star, Patterns, Key Decisions, Gotchas, Memories, Skills, Current State |
| `atoms/` | Notas Zettelkasten atômicas (1 ideia = 1 node) | Notas de 3-10 parágrafos densamente linkadas |
| `work/` | Projetos, decisões, pipeline | `Index.md` (MOC), `active/`, `archive/`, `meetings/` |
| `org/` | Pessoas e times | `People & Context.md` (MOC) |
| `reference/` | Documentação técnica, business docs | ICP, positioning, pricing, services |
| `templates/` | Templates Obsidian tipados | Atom Note, Work Note, Decision Record, Thinking Note |
| `bases/` | Database views dinâmicas | Work Dashboard, Incidents, People, 1-1 History, Review Evidence |
| `thinking/` | Scratchpad temporário | Após promover conteúdo, deletar |
| `.claude/` | Comandos, hooks, agentes, skills | 18 commands, 9 agents, 5 hooks, obsidian-skills |
| `.codex/` | Config Codex CLI | hooks.json |
| `.gemini/` | Config Gemini CLI | settings.json |

---

## 3. Como cada agente usa este vault

### Thoth (Hermes Agent — agente principal do Michel)

- Lê `brain/Current State.md` via sinapse-memory plugin (pre_prompt_build)
- Consulta `brain/North Star.md` e `brain/Patterns.md` para contexto
- Escreve decisões em `work/active/`
- Apenda aprendizados em `brain/Patterns.md`
- Atualiza `brain/Current State.md` ao final da sessão
- Interface: WhatsApp

### Claude Code

- Lê `CLAUDE.md` como manual de operações (automático)
- Lê `AGENTS.md` como guia complementar
- Hooks em `.claude/settings.json` — SessionStart, UserPromptSubmit, PostToolUse, PreCompact, Stop
- Comandos: `/om-standup`, `/om-dump`, `/om-wrap-up`, etc.
- Skills: obsidian-markdown, obsidian-cli, obsidian-bases, json-canvas, defuddle, qmd

### Codex CLI

- Lê `AGENTS.md` nativamente
- Para ler `CLAUDE.md` também, adicionar ao `~/.codex/config.toml`:
  ```toml
  project_doc_fallback_filenames = ["CLAUDE.md"]
  ```
- Hooks em `.codex/hooks.json` (mesmos scripts do Claude Code)
- Comandos: digitar `om-standup` (sem `/`)

### Gemini CLI

- Lê `GEMINI.md` nativamente
- Para ler `CLAUDE.md` também, adicionar ao `~/.gemini/settings.json`:
  ```json
  { "context": { "fileName": ["GEMINI.md", "CLAUDE.md"] } }
  ```
- Hooks em `.gemini/settings.json` (mesmos scripts do Claude Code)

### Outros agentes (Cursor, Windsurf, Copilot, OpenCode)

- Leem `AGENTS.md` para convenções do vault
- Suporte a hooks varia por agente
- Podem usar a stack Graphify + claude-mem + RTK via scripts

---

## 4. Hooks (5 lifecycle hooks)

Scripts em `.claude/scripts/` — TypeScript puro, sem build step, sem dependências de SDK.

| Hook | Quando | O que faz |
|------|--------|----------|
| SessionStart | Startup/resume | QMD re-index, injeta North Star, active work, recent changes, tasks, file listing |
| UserPromptSubmit | Toda mensagem | Classifica conteúdo (decision, incident, win, 1:1, architecture, person, project update) e injeta routing hints |
| PostToolUse | Após escrever `.md` | Valida frontmatter, verifica wikilinks |
| PreCompact | Antes de compactar contexto | Backup do transcript em `thinking/session-logs/` |
| Stop | Fim da sessão | Checklist: arquivar projetos, atualizar indexes, verificar orphans |

---

## 5. Comandos (18 slash commands)

Definidos em `.claude/commands/`. Agent-agnostic markdown com YAML frontmatter.

| Comando | Propósito |
|---------|----------|
| `/om-standup` | Morning kickoff — contexto, prioridades |
| `/om-dump` | Captura freeform — classifica e roteia tudo |
| `/om-wrap-up` | Revisão completa da sessão |
| `/om-humanize` | Edição com calibragem de voz |
| `/om-weekly` | Síntese semanal — padrões, wins |
| `/om-capture-1on1` | Captura reunião 1:1 |
| `/om-incident-capture` | Captura incidente do Slack |
| `/om-slack-scan` | Deep scan Slack channels/DMs |
| `/om-peer-scan` | Deep scan PRs de colega |
| `/om-review-brief` | Gera brief de review |
| `/om-self-review` | Auto-avaliação |
| `/om-review-peer` | Peer review |
| `/om-vault-audit` | Auditoria de links, orphans, indexes |
| `/om-vault-upgrade` | Migração de vault antigo |
| `/om-prep-1on1` | Prep para 1:1 |
| `/om-meeting` | Prep para reunião genérica |
| `/om-intake` | Processa inbox de reuniões |
| `/om-project-archive` | Arquiva projeto concluído |

---

## 6. Subagentes (9 agentes especializados)

Definidos em `.claude/agents/`. Rodam em contextos isolados.

| Agente | Propósito |
|--------|----------|
| `brag-spotter` | Encontra wins não capturados |
| `context-loader` | Carrega todo contexto sobre pessoa/projeto/conceito |
| `cross-linker` | Encontra wikilinks faltantes, orphans, backlinks quebrados |
| `people-profiler` | Cria/atualiza notas de pessoas via Slack profile |
| `review-prep` | Agrega evidências de performance |
| `slack-archaeologist` | Reconstrói conversas do Slack |
| `vault-librarian` | Manutenção profunda do vault |
| `review-fact-checker` | Verifica claims em drafts de review |
| `vault-migrator` | Classifica e migra conteúdo de vault fonte |

---

## 7. Memória — como o agente lembra

O vault é a fonte única de verdade. A memória do agente opera em 3 camadas:

### Structural Memory (Graphify)
- `graphify update cerebro/` → `cerebro/graphify-out/graph.json`
- 1266 nodes, 1319 edges, 117 comunidades (Leiden clustering)
- Query via: `graphify query`, MCP server, ou sinapse-memory plugin

### Temporal Memory (claude-mem)
- Worker em `:37700` (systemd user service)
- FTS5 full-text search + Chroma embeddings
- Query via: `search()` → `timeline(anchor=ID)` → `get_observations([IDs])`

### Execution Memory (RTK)
- Plugin Hermes: `~/.hermes/plugins/rtk-rewrite/`
- Otimiza comandos shell automaticamente (pre_tool_call hook)

### Write path
```
Decisão → vault (work/active/)  ← Graphify reindex (cron 6h)
        → claude-mem (memory_add) ← temporal tracking
        → comandos passam pelo RTK ← otimização
```

---

## 8. Regras de filing (onde cada coisa vai)

- **Projeto ativo** → `work/active/`
- **Projeto concluído** → `work/archive/`
- **Decisão** → `work/active/` (Decision Record template) + link no `work/Index.md`
- **Ideia/conceito atômico** → `atoms/` (Atom Note template, 1 ideia = 1 nota)
- **Pessoa** → `org/people/`
- **Time** → `org/teams/`
- **Brain dump / reflexão** → `thinking/` (depois promover ou deletar)
- **Convenção / padrão** → `brain/Patterns.md` (append)
- **Aprendizado** → `brain/Patterns.md` (append) ou `atoms/` se for uma ideia independente
- **Gotcha** → `brain/Gotchas.md`
- **Decisão importante** → `brain/Key Decisions.md`
- **Referência técnica** → `reference/`
- **Documento de negócio** → `reference/business-*.md`

---

## 9. Regras de linking (crítico)

- **TODO novo arquivo precisa de pelo menos 1 wikilink** — orphans são bugs
- Prefira `[[wikilinks]]` sobre markdown links
- Links bidirecionais: se A linka B, B deve linkar A (exceto concept nodes que recebem backlinks)
- Use aliases: `[[Note Title|texto amigável]]`
- Use deep links: `[[Note Title#seção]]`

---

## 10. Frontmatter obrigatório

```yaml
---
tags: [tipo, contexto]
status: active | completed | archived
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

Campos adicionais por tipo:
- **Work note**: `quarter: Q1-2026`, `project: nome`
- **Incident**: `ticket: TICKET-123`, `severity: high|medium|low`, `role: incident-lead`
- **Person**: `team: Backend`, `role: Eng Manager`
- **Review**: `cycle: h1-2026`, `person: "Nome"`
