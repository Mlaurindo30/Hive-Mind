---
date: "2026-05-22"
description: "Síntese da estrutura de vault: obsidian-mind + Zettelkasten + PARA. Removido perf/incidents/1-1 corporativos. Adicionado atoms/ para notas atômicas."
status: accepted
owner: "Thoth + Michel"
tags:
  - decision
  - vault-structure
  - architecture
quarter: "Q2-2026"
---
# Decision: Síntese obsidian-mind + Zettelkasten + PARA

## Context
Deep research em 8 abordagens de estrutura de vault (obsidian-mind, agent-second-brain, autograph, frozo-vault-mem, PARA, Zettelkasten, Johnny Decimal, oh-my-ontology) + benchmarks de recuperação (Hindsight 91.4% LongMemEval, Letta 74.0% LoCoMo). Kepano (Obsidian CEO) recomenda "folders group by purpose, links group by meaning" sem prescrever estrutura.

## Decision
Adotar síntese: **obsidian-mind como base + Zettelkasten para conhecimento atômico + PARA para clareza operacional**.

Mudanças aplicadas:
- **Adicionado atoms/**: notas Zettelkasten (1 ideia = 1 node no Graphify)
- **Removido perf/**: Brag Doc, competencies, evidence — corporativos demais para founder
- **Removido work/incidents/ + work/1-1/**: corporativos demais
- **Templates tipados**: Atom Note, Work Note (project/quarter/domain), Decision Record (owner/rationale/alternatives/reversibility)

## Rationale
- obsidian-mind é a melhor base (2.6K ⭐, multi-agente, hooks, comandos)
- Zettelkasten alimenta melhor o Graphify: notas atômicas geram nodes mais limpos que notas longas
- PARA traz clareza: work/active vs work/archive é intuitivo
- Remover corporativo: Michel é founder, não dev FAANG

## Alternatives Considered
- **obsidian-mind puro** — rejeitado: perf/ e incidents/ não se aplicam
- **PARA puro** — rejeitado: 4 pastas é muito raso, Areas é vago para agentes
- **Zettelkasten puro** — rejeitado: sem pastas, navegação frágil para agentes
- **Johnny Decimal** — rejeitado: 100 slots limitante, rigidez mata flexibilidade

## Consequences
- Graphify: 1141 nodes, 1210 edges, 100 comunidades (703KB)
- AGENTS.md e CLAUDE.md atualizados
- Sinapse-memory plugin paths validados
- Templates tipados implementados

## Reversibility
easy — estrutura de pastas é superficial. Stack (Graphify + claude-mem + RTK) roda sobre qualquer estrutura.

## Related
- [[work/active/2026-05-22-migrar-obsidian-mind]] — migração inicial
- [[brain/Patterns]] — convenções
- [[brain/North Star]] — objetivos
