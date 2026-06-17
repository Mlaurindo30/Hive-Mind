---
tags: [decision]
status: active
created: 2026-05-30
updated: 2026-05-30
source: hermes-session
---

# Implementação das 4 Fases do Sinapse Agent

Contexto: Michel pediu execução sequencial das 4 fases pendentes do Current State.

Decisões tomadas:

1. **Fase 2 — Hooks (PreCompact)**: Adicionado `on_session_finalize` no plugin sinapse-memory (registrado em register()). Salva snapshot da sessão em `thinking/session-logs/` antes de reset (/new, timeout). Equivalente ao PreCompact do Claude Code. Prune automático: mantém últimos 10 snapshots.

2. **Fase 3 — sqlite-vec**: Substitui Chroma (uvx/Python MCP pesado) por sqlite-vec + fastembed. Worker standalone em http://127.0.0.1:37701, systemd user service (sinapse-sqlite-vec.service) ativo e habilitado. Backfill automático na primeira query. Plugin sinapse-memory já tem `_backend_sqlite_vec` como backend prioritário (antes do Chroma).

3. **Fase 4 — Skills Hermes**: 5 skills criadas em ~/.hermes/skills/: vault-standup, vault-wrap-up, vault-audit, vault-dump, vault-humanize. Mapeamento dos 18 slash commands Claude Code para skills Hermes.

4. **Popular atoms/**: 4 notas atômicas criadas em cerebro/atoms/: RESOLVER-Skill-Dispatcher, Agent-Loop-Protocol, Gotchas-Failure-Modes, Key-Decision-Rename-to-Thoth. Frontmatter YAML + wikilinks + tags.

Impacto: Sinapse Agent agora tem PreCompact (equivalente ao Claude Code), busca semântica mais leve (sqlite-vec nativo), slash commands como skills Hermes, e conhecimento do brain/ em átomos Zettelkasten.
