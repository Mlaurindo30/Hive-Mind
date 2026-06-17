---
tags: [atom, gotcha, failure-mode]
status: active
created: 2026-05-30
updated: 2026-05-30
---

# Gotchas — Conhecimento Duro

Lições aprendidas na prática com o ecossistema Sinapse.

## Hermes Agent

- **claude-mem offline (silencioso):** sem logs se o worker cai. Verificar: `curl -s http://127.0.0.1:37700/health`
- **graph.json ausente (silencioso):** plugin retorna None sem log. Verificar: `ls cerebro/graphify-out/graph.json`
- **Plugin offline = contexto zero:** sem sinapse-memory, SOUL.md ainda carrega mas vault é perdido. Verificar: `hermes plugins list | grep sinapse`

## Instalação

- **Nunca pip/npm install direto.** Sempre clonar e buildar do source.
- **Graphify output:** `graphify update cerebro/` → `cerebro/graphify-out/`, não `graphify/graphify-out/`.

Links: [[Agent-Loop-Protocol]], [[RESOLVER-Skill-Dispatcher]]
