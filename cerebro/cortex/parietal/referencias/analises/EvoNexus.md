---
tags: [analise, evo-nexus, dashboard, multi-agente, hermes]
domain: ferramentas
status: rejeitada
created: 2026-05-24
---

# Análise Fria: EvoNexus

**Avaliador:** Thoth (orquestrador THOTH AI)
**Para:** Ecossistema Thoth + panteão de subagentes
**Data:** 2026-05-24
**Status:** rejeitada (sobreposição com Panteão + Sinapse, risco de fork não-oficial)

## Veredito

Não adotar. O EvoNexus é uma camada operacional multi-agente (437 stars) com 38 agentes e dashboard web. Mas sobrepõe 80% do nosso Panteão + Sinapse, depende do Claude Code CLI, e a imagem `pedrotecinf/evo-nexus-dashboard:feature-hermes-runtime` é um fork não-oficial sem garantia de manutenção.

## O que é / O que faz

EvoNexus é um "sistema operacional open source para negócios AI-powered" da Evolution Foundation. Transforma uma instalação CLI em 38 agentes especializados com dashboard web, rotinas agendadas e integrações MCP.

**Stack:** Claude Code CLI (obrigatório), React + Flask (dashboard), Docker, Markdown-first agents
**Versão:** v0.33.0 (Abr 2026)
**Stats:** 437 stars, 149 forks
**Agentes:** 17 business + 21 engineering
**Skills:** 190+
**Integrações MCP:** Google Calendar, Gmail, GitHub, Linear, Telegram, Discord, Stripe, Notion, Canva, etc.

**Imagem Docker específica:** `ghcr.io/pedrotecinf/evo-nexus-dashboard:feature-hermes-runtime` — fork com injecão para Hermes runtime.

## Vantagem prática para o projeto THOTH AI

1. **Dashboard web** — Interface visual para agentes. Não temos hoje. Mas o Hermes já tem TUI e gateway multi-plataforma.
2. **38 agentes pré-construídos** — Cobre business (Finance, HR, Legal, Sales) e engenharia (code review, testing, security). Mas nosso Panteão já tem 7 agentes especializados com papéis definidos.
3. **Rotinas agendadas (ADWs)** — Daily/weekly workflows automatizados. Mas o Hermes já tem cron jobs nativos.
4. **Integrações MCP prontas** — Google, Linear, Stripe, etc. Mas o Hermes já tem MCP server e plugins pra várias plataformas.

## Risco principal

Fragmentação do stack. Dois sistemas de agentes (Panteão + EvoNexus) operando em paralelo, com memórias separadas (Sinapse vs CLAUDE.md), gerando decisões contraditórias e duplicação de trabalho.

### Riscos específicos

- **Dependência do Claude Code CLI**: EvoNexus não funciona sem `claude` CLI instalado. Se Anthropic mudar a API/CLI, quebra tudo.
- **Fork não-oficial**: A imagem `pedrotecinf` é um fork. Sem garantia de updates, segurança ou compatibilidade futura.
- **Comunidade pequena**: 437 stars vs 40k do GitNexus. Risco de abandono.
- **Stack adicional**: React + Flask + Docker + Claude Code CLI — 4 novas dependências pra manter.
- **Sobreposição de memória**: CLAUDE.md + per-agent memory vs Sinapse (Graphify + claude-mem + NeuralMemory). Dois sistemas de memória incompatíveis.
- **Custo**: Claude Code CLI consome tokens Anthropic. Nossos agentes já usam multi-provider com DeepSeek (mais barato).

## O que NÃO fazer / NÃO incluir

- NÃO substituir o Panteão pelo EvoNexus — o Panteão é mais integrado e multi-modelo
- NÃO rodar EvoNexus e Panteão em paralelo no mesmo projeto — conflito de memória
- NÃO usar a imagem `pedrotecinf` em produção sem auditar o código fonte
- NÃO depender do EvoNexus para tarefas críticas — depende do Claude Code CLI (ponto único de falha)

## Plano de adoção recomendado

*Não aplicável — rejeitado. Se houvesse adoção:*

### Fase 1 — Auditoria do fork
Clonar repositório do pedrotecinf, auditar a feature `hermes-runtime`, verificar injeção.

### Fase 2 — Teste isolado
Rodar dashboard em Docker, testar integração MCP com Hermes, avaliar dashboard como UI complementar.

### Rollback
`docker compose down && docker rmi ghcr.io/pedrotecinf/evo-nexus-dashboard:feature-hermes-runtime`

## Decisão sugerida

```
## 2026-05-24 — EvoNexus rejeitado para THOTH AI
Status: rejeitada
Contexto:
- EvoNexus é camada multi-agente (437 stars, 38 agentes, dashboard web)
- Imagem pedrotecinf/evo-nexus-dashboard:feature-hermes-runtime injeta no Hermes
- Já temos Panteão (7 agentes) + Sinapse (4 camadas de memória) + Hermes (cron, MCP, gateway)
Decisão:
- NÃO adotar EvoNexus como sistema principal
- Dashboard pode ser avaliado como UI complementar se fork for auditado
Motivo:
- Sobreposição de 80% com stack existente
- Dependência do Claude Code CLI (ponto único de falha)
- Fork não-oficial sem garantia
- Comunidade pequena (437 stars)
Risco:
- Fragmentação da memória se rodar em paralelo com Sinapse
Rollback:
- N/A — nada foi instalado
Responsável pela aprovação:
- Michel
```

## Veredito final

EvoNexus é uma camada operacional multi-agente interessante para quem começa do zero (38 agentes, dashboard, integrações prontas). Mas para o ecossistema THOTH AI, é redundante: já temos Panteão (7 agentes com papéis definidos e multi-modelo), Sinapse (4 camadas de memória), e Hermes (cron, MCP, gateway multi-plataforma). A imagem `feature-hermes-runtime` do pedrotecinf é um fork não-oficial que injetaria o EvoNexus no Hermes, mas sem auditoria de código e sem garantia de manutenção, o risco não se justifica. Não adotar.

## Fontes

- [EvoNexus GitHub](https://github.com/evolution-foundation/evo-nexus)
- [ghcr.io/pedrotecinf/evo-nexus-dashboard](https://github.com/pedrotecinf/evo-nexus-dashboard/pkgs/container/evo-nexus-dashboard)
