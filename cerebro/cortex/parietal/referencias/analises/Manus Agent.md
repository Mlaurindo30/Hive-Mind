---
tags: [analise, agent-loop, orchestration]
domain: agente-autonomo
status: active
created: 2026-05-30
---

# Análise Fria: Manus Agent

## Veredito

**Adotar parcialmente.** O loop de execução do Manus (Analyze → Select → Wait → Iterate → Submit → Standby) já inspirou nosso Agent Loop Protocol. O valor real está nos módulos sistema (Planner, Knowledge, Data API) — especialmente o **event stream tipado** e o **Planner module com pseudocódigo numerado**. As tools em si são equivalentes às que já temos. Ignorar o sandbox Ubuntu e o deploy público — não se aplicam ao Thoth.

---

## O que é / O que faz

Manus é um agente autônomo criado pela equipe Manus (provavelmente Manus AI, china). Opera em sandbox Linux com:

| Componente | Descrição |
|------------|-----------|
| **Agent Loop** | 6 passos: Analyze Events → Select Tools → Wait → Iterate → Submit → Standby |
| **Event Stream** | Stream cronológico de eventos tipados: Message, Action, Observation, Plan, Knowledge, Datasource |
| **Planner Module** | Plano em pseudocódigo numerado, atualizado a cada step, com reflexão |
| **Knowledge Module** | Best practices injetados como eventos, com escopo condicional |
| **Data API Module** | APIs de dados autoritativas via cliente Python pre-instalado |
| **Tools** | 20+ tools: file_r/w, shell_exec, browser, deploy, expose port, message_notify/ask_user |

---

## Vantagem prática para o projeto THOTH AI

1. **Event stream tipado** — Manus separa eventos em 6 categorias (Message, Action, Observation, Plan, Knowledge, Datasource). Nosso fluxo não distingue o tipo de evento injetado. Adotar categorização permitiria priorizar contexto: datasource > knowledge > plan > observation, em vez de tudo misturado no prompt.

2. **Planner com pseudocódigo + reflexão** — O Planner module do Manus não é só um todo list. Ele escreve pseudocódigo numerado, atualiza o step atual, e inclui reflexão ("o que deu errado, o que ajustar"). Nosso `todo` é linear. Um planner que reflete daria feedback loop no meio da execução.

3. **Knowledge module com escopo condicional** — Manus injeta best practices como eventos, mas cada item tem um `scope` — só adota quando as condições batem. Melhor que carregar tudo sempre. Nosso agent-loop-protocol já é sempre-on; um knowledge module condicional reduziria token waste.

4. **Foco único de tool call por iteração** — Já temos isso (Chain-of-Draft + Select Tool), mas Manus explicita: "Choose only one tool call per iteration". Reforça nosso padrão atual.

5. **Submit Results + Enter Standby** — Manus tem um estado explícito de "idle" após completar tarefas. Nosso loop não distingue "aguardando" de "processando". Um estado standby reduziria ciclos ociosos.

---

## Risco principal

O Manus foi projetado para sandbox Ubuntu com deploy público — o loop e os módulos são otimizados para execução única com isolamento total. Adaptar para um agente persistente (Thoth, sempre-on via WhatsApp) pode gerar overhead de estado sem ganho real.

---

## Riscos específicos

| Risco | Impacto |
|-------|---------|
| **Event stream pode crescer sem limite** | Se não podar eventos antigos, o prompt incha. Manus não especifica retention policy |
| **Planner com reflexão = latência extra** | Cada iteração chama planner → reflexão → tool. Aumenta number de calls sem garantir qualidade |
| **Knowledge module = duplicação com o vault** | Nosso vault já serve de knowledge base. Adicionar outra camada de "best practices" conflita |
| **Data API module exige cliente Python** | Preferimos APIs HTTP diretas no nosso stack. Cliente Python é mais uma dependência |
| **message_ask_user = quebra de fluxo** | Thoth é async via WhatsApp. Perguntas síncronas não funcionam |

---

## O que NÃO fazer / NÃO incluir

- **Não adotar sandbox Ubuntu.** Thoth roda no ambiente do Michel, não em sandbox isolado
- **Não adotar deploy público (expose port).** Sem uso pra nós
- **Não adotar cliente Data API Python.** APIs HTTP diretas são suficientes
- **Não adotar message_ask_user síncrono.** WhatsApp não suporta blocking wait
- **Não duplicar conhecimento que já está no vault**

---

## Plano de adoção recomendado

### Fase 1 — Event stream tipado (1h)
- No plugin sinapse-memory, adicionar campo `event_type` no log: message, action, observation, decision, learning
- Priorizar injeção no `pre_gateway_dispatch`: datasource > knowledge > plan > observation
- **Rollback:** reverter pra injeção linear (1 commit)

### Fase 2 — Planner com pseudocódigo (2h)
- Estender `todo` para aceitar `pseudocode` + `reflection` opcionais
- Após cada tool call, gerar reflexão de 1 linha
- **Rollback:** usar TODO simples (desabilitar flag)

### Fase 3 — Knowledge module condicional (1h)
- Cada skill ganha campo `scope: [trigger1, trigger2]`
- Só carregar skill quando trigger bater
- **Rollback:** carregar skills como sempre (flag condicional=false)

### O que NÃO entra em nenhuma fase
- Sandbox, deploy público, Data API Python, message_ask_user síncrono

---

## Decisão sugerida

| Campo | Valor |
|-------|-------|
| **Status** | Adotar parcialmente |
| **Contexto** | Manus tem loop maduro com event stream, planner reflexivo e knowledge condicional |
| **Decisão** | Adotar Fase 1 (event stream) + Fase 2 (planner) + Fase 3 (knowledge condicional). Ignorar sandbox, deploy, data API |
| **Motivo** | Event stream reduz ruído no prompt. Planner com reflexão melhora qualidade. Knowledge condicional economiza tokens |
| **Risco** | Overhead de estado. Planner pode aumentar latência |
| **Rollback** | 1 commit por fase |
| **Responsável** | Thoth |

---

## Veredito final

Manus não é um concorrente direto — é um agente de sandbox para tarefas isoladas, enquanto Thoth é um agente persistente e pessoal. Mas o design do loop, especialmente o **event stream tipado** e o **planner com reflexão**, são melhorias diretas pro nosso Agent Loop Protocol. As 3 fases de adoção são pequenas (4h total) e têm rollback trivial. Vale o custo.

---

## Fontes

- https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools/tree/main/Manus%20Agent%20Tools%20%26%20Prompt
- Prompt.txt — capabilities overview
- Agent loop.txt — loop de 6 passos
- Modules.txt — event stream, planner, knowledge, data API
- tools.json — 20+ ferramentas
