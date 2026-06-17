---
tags: [atom, resolver, skill-dispatch]
status: active
created: 2026-05-30
updated: 2026-05-30
---

# RESOLVER — Skill Dispatcher

Inspirado no GBrain do Garry Tan. Mapeia triggers → skills. O agente lê antes de agir.

## Thinking Skills (GStack-inspired)

| Trigger | Ação |
|---------|------|
| "Brainstorm", "tenho uma ideia" | 6 forcing questions |
| "Review esse plano", "CEO review" | Desafiar premissas, 4 modos de escopo |
| "Debug", "corrigir", "quebrado" | Investigação sistemática, no fixes without investigation |
| "Retro", "o que shipamos" | Weekly retro com per-person breakdowns |

## Always-On

- Toda mensagem → carregar current-state + brain-first
- Toda decisão de build → Boil the Lake, Search Before Building
- Qualquer decisão registrada → salvar com frontmatter YAML
- Qualquer aprendizado → salvar com tags apropriadas

## Regras de Desambiguação

1. Prefira a mais específica
2. Se menciona pessoa/empresa/projeto → pasta específica
3. Se menciona URL → identificar tipo e rotear

Links: [[Key Decisions]], [[Current State]]
