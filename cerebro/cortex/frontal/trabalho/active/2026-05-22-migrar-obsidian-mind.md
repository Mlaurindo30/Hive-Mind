---
tags: [decision, vault, infrastructure]
status: active
created: 2026-05-22
updated: 2026-05-22
quarter: Q2-2026
project: sinapse-agent
---

# Migrar vault para obsidian-mind template

**Contexto:** O vault `cerebro/` usava uma estrutura própria (`_memory/`, `_knowledge/`, `_decisions/`, `_learnings/`, `_conventions/`, `_projects/`, `_pipeline/`). O [obsidian-mind](https://github.com/breferrari/obsidian-mind) (2.636 estrelas, Brenno Ferrari) oferece uma estrutura superior com 18 slash commands, 9 subagentes, 5 lifecycle hooks, 7 database views, e 6 templates estruturados.

**Decisão:** Adotar obsidian-mind como template base do vault, mantendo nossa stack (Graphify + claude-mem + RTK) como overlay. Estrutura final: `brain/`, `work/`, `org/`, `perf/`, `reference/`, `templates/`, `bases/`.

**Rationale:**
- Estrutura do obsidian-mind é mais granular e acionável (work/active/, work/incidents/, perf/competencies/)
- Lifecycle hooks (SessionStart, UserPromptSubmit, PostToolUse, PreCompact, Stop) preenchem lacuna que tínhamos
- Templates com frontmatter estruturado (Work Note, Decision Record, 1:1, Incident, Competency) são superiores ao nosso YAML genérico
- Bases (database views) permitem queries dinâmicas no Obsidian
- Nossa stack (Graphify + claude-mem + RTK) roda por cima de qualquer estrutura de vault
- Complementar, não competidor: eles são fortes em workflow diário, nós em knowledge graph técnico

**Consequências:**
- AGENTS.md reescrito como guia cross-agent principal
- CLAUDE.md mantido para Claude Code com customizações da nossa stack
- GEMINI.md, .codex/, .gemini/ adicionados para suporte multi-agente
- Sinapse-memory plugin atualizado com novos paths
- Graphify reindexado: 1266 nodes (era 214)
- Backup do vault antigo: `cerebro.backup.20260522-1737/`

**Reversibilidade:** Fácil — backup existe. Restaurar: `rm -rf cerebro/ && mv cerebro.backup.* cerebro/`

**Riscos:**
- QMD (busca semântica do obsidian-mind) não está instalado — fallback para grep + Obsidian CLI funciona
- Hooks são Node/TS, plugin Hermes é Python — bridge necessária na Fase 2
- Templates .claude/commands/ são Claude Code-specific — adaptação pra Hermes na Fase 4
