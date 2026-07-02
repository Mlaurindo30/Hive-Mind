# Sinapse Agent — Vault (AGENTS.md)

> Formato cross-agent: Thoth (Hermes), Claude Code, Codex, OpenCode, Gemini CLI, Cursor, Copilot.
> Stack: Graphify (knowledge graph) + claude-mem (temporal tracking) + RTK (execution optimization).
> Template base: [obsidian-mind](https://github.com/breferrari/obsidian-mind).
> Última revisão: 2026-05-30.

---

## 0. Idioma

- **Vault:** Português (BR). Todas as notas, templates, documentação.
- **Código e saída técnica:** Inglês.
- **Conversas com Michel:** Português (BR).

---

## 1. O que é este vault

Fonte única de verdade para Thoth (agente pessoal do Michel) e todos os coding agents. **Cinco camadas de memória:**

| Camada | Ferramenta | O que faz | Como acessar | Gap |
|--------|-----------|----------|-------------|-----|
| 1 — Estrutural | **Graphify** | Knowledge graph com Leiden clustering | `cortex/occipital/grafo/graph.json` | ~6h (reindex) |
| 2 — Temporal | **claude-mem** | Tracking de eventos, FTS5, Chroma | Worker HTTP `:37700` | Zero |
| 3 — Execução | **RTK** | Otimização de comandos shell | Plugin Hermes `pre_tool_call` | Zero |
| 4 — Associativa | **Neural Memory** | Busca vetorial HNSW, conceitos relacionados | Plugin Python `sinapse-memory` | ~6h |
| 5 — Híbrida | **Filesystem** | Busca direta real-time nos .md do vault | Plugin Python `sinapse-memory` | **ZERO** |

> **Camada 5 elimina o gap do Graphify:** notas recém-escritas aparecem instantaneamente 
> via scan direto no vault, sem esperar reindexação de 6h. O Context Fusion deduplica 
> automaticamente quando Graphify + filesystem retornam o mesmo arquivo.

**Verificação de saúde (antes de qualquer sessão):**
```bash
ls cortex/occipital/grafo/graph.json                # graph deve existir
curl -s http://127.0.0.1:37700/health               # worker deve responder {"status":"ok"}
systemctl --user is-active sinapse-claude-mem.service
```

---

## 2. Estrutura do vault

| Pasta | Propósito | Arquivos-chave |
|-------|-----------|---------------|
| `cortex/temporal/` | Memória de longo prazo por projeto | `projeto/topico/neuronio-*.md` |
| `cortex/frontal/` | Decisões, planejamento e trabalho ativo | `decisoes/`, `trabalho/`, `brain/`, `org/` |
| `cortex/parietal/` | Inbox, referências e entrada sensorial | `inbox/`, `referencias/`, `analises/` |
| `cortex/occipital/` | Visão e grafo | `capturas-visuais/`, `grafo/graph.json` |
| `cortex/insula/` | Saúde, conflitos e autoconsciência | `saude/`, `conflitos/` |
| `cerebelo/` | Ritmo, sessões, diário, semanal e padrões | `sessoes/`, `diario/`, `semanal/`, `padroes/Patterns.md` |
| `diencefalo/` | Relay cross-projeto | `setores/`, `roteamento/` |
| `tronco/` | Infra vital do vault | `modelos/`, `paineis/`, `infra/`, `meta/` |
| `tronco/infra/agentes/.claude/` | Comandos, hooks, agentes, skills | 18 commands, 9 agents, 5 hooks, obsidian-skills |
| `tronco/infra/agentes/.codex/` | Config Codex CLI | hooks.json |
| `tronco/infra/agentes/.gemini/` | Config Gemini CLI | settings.json |

---

## 3. Como cada agente usa este vault

### O Protocolo de Execução (Agent Loop)
Todo agente DEVE seguir estritamente o protocolo Sinapse injetado em `AGENTS.md` e nos clientes MCP. Este protocolo unifica a disciplina de pensamento do Manus com a soberania do usuário e a prioridade de memória do Sinapse.

### Thoth (Hermes Agent — agente principal do Michel)

- Lê `cortex/frontal/brain/Current State.md` via sinapse-memory plugin (pre_prompt_build)
- Consulta `cortex/frontal/brain/` e `cerebelo/padroes/Patterns.md` para contexto
- Escreve decisões em `cortex/frontal/trabalho/ativo/`
- Apenda aprendizados em `cerebelo/padroes/Patterns.md`
- Atualiza `cortex/frontal/brain/Current State.md` ao final da sessão
- Interface: WhatsApp

### Claude Code

- Lê `CLAUDE.md` como manual de operações (automático)
- Lê `AGENTS.md` como guia complementar
- Hooks em `tronco/infra/agentes/.claude/settings.json` — SessionStart, UserPromptSubmit, PostToolUse, PreCompact, Stop
- Comandos: `/om-standup`, `/om-dump`, `/om-wrap-up`, etc.
- Skills: obsidian-markdown, obsidian-cli, obsidian-bases, json-canvas, defuddle, qmd

### Codex CLI

- Lê `AGENTS.md` nativamente
- Para ler `CLAUDE.md` também, adicionar ao `~/.codex/config.toml`:
  ```toml
  project_doc_fallback_filenames = ["CLAUDE.md"]
  ```
- Hooks em `tronco/infra/agentes/.codex/hooks.json` (mesmos scripts do Claude Code)
- Comandos: digitar `om-standup` (sem `/`)

### Gemini CLI

- Lê `GEMINI.md` nativamente
- Para ler `CLAUDE.md` também, adicionar ao `~/.gemini/settings.json`:
  ```json
  { "context": { "fileName": ["GEMINI.md", "CLAUDE.md"] } }
  ```
- Hooks em `tronco/infra/agentes/.gemini/settings.json` (mesmos scripts do Claude Code)

### Outros agentes (Cursor, Windsurf, Copilot, OpenCode)

- Leem `AGENTS.md` para convenções do vault
- Suporte a hooks varia por agente
- Podem usar a stack Graphify + claude-mem + RTK via scripts

---

## 4. Hooks (5 lifecycle hooks)

Scripts em `tronco/infra/agentes/.claude/scripts/` — TypeScript puro, sem build step, sem dependências de SDK.

| Hook | Quando | O que faz |
|------|--------|----------|
| SessionStart | Startup/resume | QMD re-index, injeta North Star, active work, recent changes, tasks, file listing |
| UserPromptSubmit | Toda mensagem | Classifica conteúdo (decision, incident, win, 1:1, architecture, person, project update) e injeta routing hints |
| PostToolUse | Após escrever `.md` | Valida frontmatter, verifica wikilinks |
| PreCompact | Antes de compactar contexto | Backup do transcript em `thinking/session-logs/` |
| Stop | Fim da sessão | Checklist: arquivar projetos, atualizar indexes, verificar orphans |

---

## 5. Comandos (18 slash commands)

Definidos em `tronco/infra/agentes/.claude/commands/`. Agent-agnostic markdown com YAML frontmatter.

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

Definidos em `tronco/infra/agentes/.claude/agents/`. Rodam em contextos isolados.

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

O vault é a fonte única de verdade. A memória do agente opera em **5 camadas:**

### Camada 1 — Structural Memory (Graphify)
- `graphify update cerebro/` → `cerebro/cortex/occipital/grafo/graph.json`
- 1266+ nodes, 1319+ edges, 117 comunidades (Leiden clustering)
- Query via: `graphify query`, MCP server, ou sinapse-memory plugin
- **Gap:** ~6h entre reindexações automáticas

### Camada 2 — Temporal Memory (claude-mem)
- Worker em `:37700` (systemd user service)
- FTS5 full-text search + Chroma embeddings
- Query via: `search()` → `timeline(anchor=ID)` → `get_observations([IDs])`
- **Gap:** Zero (eventos em tempo real)

### Camada 3 — Execution Memory (RTK)
- Plugin Hermes: `~/.hermes/plugins/rtk-rewrite/`
- Otimiza comandos shell automaticamente (pre_tool_call hook)
- **Gap:** Zero (hook síncrono)

### Camada 4 — Associative Memory (Neural Memory)
- Plugin Python: `neural-memory/` (busca vetorial HNSW)
- Retorna conceitos semelhantes, clusters dinâmicos
- Query via: sinapse-memory plugin (recall_timeout: 5s)
- **Gap:** ~6h (sincroniza com graph.json)

### Camada 5 — Hybrid Memory (Filesystem — busca direta real-time)
- Plugin Python: `sinapse-memory` → `_backend_filesystem()`
- Scan recursivo direto em `.md` do vault, sem depender de indexação
- Busca case-insensitive, extrai título H1, YAML frontmatter, conteúdo
- Cache TTL 30s — performance sem stale data
- **Gap: ZERO** — lê o arquivo no momento exato da query
- **Deduplicação cross-backend** elimina duplicados quando Graphify + filesystem
  retornam o mesmo arquivo (chaves: source_file, title, conteúdo)

### Write path
```
Decisão → vault (cortex/frontal/trabalho/ativo/) ← Graphify reindex
        → claude-mem (memory_add) ← temporal tracking
        → comandos passam pelo RTK ← otimização
        → hybrid search encontra INSTANTANEAMENTE ← camada 5 filesystem
```

---

## 8. Regras de filing (onde cada coisa vai)

- **Projeto ativo** → `cortex/frontal/trabalho/ativo/`
- **Projeto concluído** → `cortex/frontal/trabalho/arquivo/`
- **Decisão** → `cortex/frontal/decisoes/` ou `cortex/frontal/trabalho/ativo/` conforme escopo
- **Ideia/conceito atômico** → `cortex/temporal/<projeto>/<topico>/neuronio-*.md`
- **Pessoa** → `cortex/frontal/org/people/`
- **Time** → `cortex/frontal/org/teams/`
- **Brain dump / reflexão** → `cortex/parietal/inbox/` até promover
- **Convenção / padrão** → `cerebelo/padroes/Patterns.md` (append)
- **Aprendizado** → `cerebelo/padroes/Patterns.md` ou neurônio temporal se for fato independente
- **Gotcha** → `cortex/insula/conflitos/` ou `cortex/frontal/brain/`
- **Decisão importante** → `cortex/frontal/decisoes/`
- **Referência técnica** → `cortex/parietal/referencias/`
- **Documento de negócio** → `cortex/parietal/referencias/`
- **Análise de ferramenta/skill/plugin** → `cortex/parietal/analises/`

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

---

## 11. Análises de ferramentas (fluxo Thoth)

Quando Michel enviar uma skill, plugin, ferramenta, integração ou ideia para avaliação,
Thoth gera uma **Análise Fria** usando o template `tronco/modelos/Analise Fria.md` e salva em `cortex/parietal/analises/`.

### Seções obrigatórias
- Veredito (adotar sim/não, com qual escopo)
- O que é / O que faz
- Vantagem prática para o projeto THOTH AI
- Risco principal + riscos específicos
- O que NÃO fazer / NÃO incluir
- Plano de adoção (fases) + rollback
- Decisão sugerida (formato Decision Record)
- Veredito final

### Fluxo
```
Michel envia (PDF, link, ideia) → Thoth analisa → salva em cortex/parietal/analises/ → registra no claude-mem
```

O arquivo serve como registro permanente de avaliação para decisões futuras.

---

## 12. Regras de uso do Sinapse pelo Thoth (OBRIGATÓRIO)

> **Estas regras são não-negociáveis. O Thoth deve segui-las em toda interação com Michel.**

### Consulta obrigatória (antes de responder)

| Gatilho | Ação | Ferramenta |
|---------|------|-----------|
| Qualquer pergunta sobre projeto, ferramenta, decisão passada | Consultar vault primeiro | `session_search()` ou `sinapse-write.py query` |
| Dúvida sobre contexto de conversas anteriores | Buscar no histórico | `session_search(query="...")` |
| Referência a ferramenta/skill/plugin já analisada | Verificar análises existentes | `search_files(pattern="...", path="cerebro/cortex/parietal/analises/")` |
| Decisão técnica ou arquitetural | Verificar decisões | `read_file("cerebro/cortex/frontal/decisoes/")` |
| Padrão ou convenção | Verificar padrões | `read_file("cerebro/cerebelo/padroes/Patterns.md")` |

### Escrita obrigatória (após agir)

| Gatilho | Ação | Destino |
|---------|------|---------|
| Decisão tomada (qualquer) | Registrar | `cortex/frontal/decisoes/` ou `cortex/frontal/trabalho/ativo/` + `claude-mem memory_add` |
| Ferramenta/skill avaliada | Análise Fria completa | `cortex/parietal/analises/` + PDF + `claude-mem` |
| Aprendizado novo | Apendar | `cerebelo/padroes/Patterns.md` |
| Erro cometido ou gotcha | Registrar | `cortex/insula/conflitos/` |
| Fim de tarefa complexa (5+ tool calls) | Atualizar estado | `cortex/frontal/brain/Current State.md` |
| Skill criada ou modificada | Salvar | `skill_manage()` + `claude-mem` |

### Health check (início de sessão)

Antes de qualquer resposta complexa, verificar:
```bash
python3 scripts/services/sinapse-write.py health
```
Se qualquer backend falhar, reportar e oferecer correção imediata.

### Violação

Michel espera que o Sinapse seja usado ativamente. Não consultar o vault antes de responder, ou não escrever decisões após agir, é considerado falha operacional do Thoth.

---

## 13. Regra de resposta por áudio (OBRIGATÓRIO)

> **Se Michel enviar mensagem de voz (áudio), o Thoth DEVE responder também com áudio.**

- Usar `text_to_speech()` para gerar o áudio da resposta
- Incluir `MEDIA:` com o caminho do áudio na resposta
- O áudio deve ser a primeira coisa na resposta
- Pode incluir texto adicional após o áudio, mas o áudio é obrigatório
- Esta regra se aplica a TODAS as respostas a mensagens de voz, sem exceção
