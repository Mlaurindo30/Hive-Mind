---
tags: [memory, current-state]
status: active
created: 2026-05-22
updated: 2026-05-22
---

# Current State

## Última atualização: 2026-05-22

### O que foi feito
- **Deep research**: Comparativo de estruturas de vault Obsidian para agentes (obsidian-mind, PARA, Zettelkasten, Johnny Decimal, autograph, agent-second-brain, frozo-vault-mem)
- **Síntese aplicada**: obsidian-mind + Zettelkasten + PARA
- **atoms/** criado: notas atômicas Zettelkasten (1 ideia = 1 node no Graphify)
- **perf/ removido**: performance review corporativa não se aplica a founder
- **work/incidents/ + work/1-1/ removidos**: corporativo demais
- **Templates tipados**: Atom Note, Work Note (com project/quarter/domain), Decision Record (com owner/rationale/alternatives/reversibility)
- **AGENTS.md atualizado**: nova estrutura, filing rules com atoms/
- **Graphify reindexado**: 1141 nodes, 1210 edges, 100 comunidades (703KB)
- **Sinapse-memory paths**: validados (DECISIONS_DIR, MEMORY_FILE, PROJECTS_DIR, PATTERNS_FILE)

### Decisões tomadas
- **obsidian-mind como base, não como dogma**: Mantemos brain/work/org/templates/bases/thinking. Removemos perf/incidents/1-1. Adicionamos atoms/.
- **Zettelkasten para conhecimento denso**: atoms/ gera nodes mais limpos no Graphify que notas longas em brain/
- **Templates tipados**: schema validation implícito nos campos obrigatórios dos templates

### Estrutura final do vault
```
cerebro/
├── brain/          ← North Star, Patterns, Key Decisions, Gotchas, Current State
├── atoms/          ← Notas Zettelkasten (1 ideia = 1 node) 🆕
├── work/           ← active/, archive/, meetings/, pipeline/
├── org/            ← people/, teams/
├── reference/      ← business docs
├── templates/      ← Atom Note, Work Note, Decision Record, Thinking Note
├── bases/          ← 7 database views
├── thinking/       ← scratchpad
├── .claude/        ← 18 commands, 9 agents, 5 hooks
├── AGENTS.md       ← cross-agent guide
├── CLAUDE.md       ← Claude Code manual
└── GEMINI.md       ← Gemini CLI guide
```

### Stack
| Camada | Ferramenta | Status |
|--------|-----------|--------|
| Estrutural | Graphify | ✅ 1141 nodes |
| Temporal | claude-mem | ✅ worker ativo |
| Execução | RTK | ✅ plugin ativo |
| Vault | obsidian-mind + Zettelkasten | ✅ integrado |
| Agente | Thoth (Hermes) | ✅ WhatsApp |

### Próximos passos
1. **Fase 2: Hooks** — 5 lifecycle hooks como eventos Hermes
2. **Fase 3: sqlite-vec** — substituir Chroma no claude-mem
3. **Fase 4: Comandos** — adaptar slash commands como skills Hermes
4. **Popular atoms/** — migrar conhecimento do brain/ para átomos
