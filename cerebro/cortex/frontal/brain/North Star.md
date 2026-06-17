---
date:
description: "Living document of goals, focus areas, and aspirations — read at session start, updated when direction shifts"
tags:
  - brain
  - north-star
aliases:
  - Goals
  - Focus
---

# North Star

A living document of goals, aspirations, and current focus areas. Both you and Claude write to this. Claude reads it at the start of meaningful work sessions and references it when making suggestions.
## Current Focus
_What am I working toward right now?_
-
## Goals
### Short-term (This Quarter)
-
### Medium-term (This Half)
-
### Long-term (This Year+)
-
## Aspirations
_What kind of engineer/person am I becoming?_
-
## Anti-goals
_What am I explicitly NOT optimizing for?_
-
## Shifts Log
Record when focus changes, with date and reason.
| Date | Shift | Reason |
|------|-------|--------|
|      | Created North Star | Initial setup |
---

## About Michel
---
tags: [knowledge, identity, core]
status: active
created: 2026-05-20
updated: 2026-05-20
---

# Quem Sou Eu

## Identidade

- **Nome:** Michel Laurindo
- **Como prefere ser chamado:** Michel
- **Area de atuacao:** IA e aplicacoes autonomas
- **Cargo/papel atual:** Presidente da THOTH AI (empresa de agentes de IA)
- **Tempo na area:** 8 anos em dados, 2 anos com foco em IA

## O Que Faco

- **Descricao em 1 frase:** Construo uma empresa de agentes de IA onde cada cliente recebe agentes especializados como servico.
- **O que me diferencia:** Agentes nao sao features - sao a fundacao. Tudo que e construido pensado para escala: o que funciona para um cliente deve funcionar para dez.
- **O que NAO faco:** Nao sou consultor de marketing digital, nao faco sites, nao pego projetos abaixo de margem minima.

## Habilidades Principais

- **Hard skills:** Python, Go, IA/ML, agentes autonomos, LangGraph, FastAPI, arquitetura de sistemas, Databricks
- **Soft skills:** Visao estrategica, operacao solo com agentes, FinOps integrado, documentacao viva
- **Aprendendo agora:** Go avancado (para o Thoth Agent Runtime)

## Ferramentas e Stack

- **Ferramentas do dia a dia:** VS Code, Obsidian, terminal Linux, WhatsApp, Hermes (agente operacional)
- **Stack tecnico:** Python 3.11+, Go, FastAPI, LangGraph, Anthropic API, Qdrant, Podman, React/Next.js
- **Ferramentas de IA que uso:** Hermes (operacional), Claude Code (CEO), Kilo Code/DeepSeek Pro (implementacao), Codex (code review), Gemini (contexto longo), Copilot (inline), Aider (pair programming)

## Como Prefiro Trabalhar

- **Horario produtivo:** flexivel
- **Estilo de trabalho:** acao direta - prefere instalacao a discussao, comandos a debates
- **Comunicacao preferida:** WhatsApp (texto), direto e sem rodeios
- **O que me trava:** falta de clareza, burocracia, ferramentas quebradas
- **O que me destrava:** acao concreta, resultados visiveis, automacao

## Contexto Pessoal

- **Localizacao:** Brasil
- **Idiomas:** Portugues nativo
- **Fuso horario:** BRT (UTC-3)

## Sobre Mim (aprendido com o tempo)

- Prefere OAuth/login flows a API keys manuais
- Gosta de ter MAXIMO poder de agente - varios coding agents, superpoderes, claude-mem
- Direto e acao-orientado - "instale agora" ao inves de "o que voce acha?"
- Quer migrar toda operacao para uma VPS para nao depender do PC local
- Fala comigo pelo WhatsApp como interface unica e eu orquestro o resto


## Goals
---
tags: [knowledge, goals, core]
status: active
created: 2026-05-20
updated: 2026-05-20
---

# Meus Objetivos

## Curto Prazo (proximo 30 dias)

### Objetivo 1: Migrar o Hermes para VPS
- **O que seria sucesso:** Hermes rodando 24/7 numa VPS, acessivel via WhatsApp sem depender do PC local
- **Metricas:** Zero downtime, cron jobs executando, disponivel sempre que enviar mensagem
- **O que esta me impedindo:** Preciso organizar configs, skills e secrets num repo portavel
- **Proximo passo concreto:** Criar o repo ~/hermes-infra/ com tudo que o Hermes precisa

### Objetivo 2: Baseline tecnico do Thoth
- **O que seria sucesso:** Go instalado, `go test ./...` passando, evidencias registradas
- **Metricas:** Build compilando, testes passando, blockers atualizados
- **O que esta me impedindo:** Go nao esta instalado (bloqueio registrado)
- **Proximo passo concreto:** Instalar Go 1.25+ e executar o baseline

### Objetivo 3: Configurar o Segundo Cerebro no Hermes
- **O que seria sucesso:** Hermes le e escreve no vault do Obsidian como fonte central de conhecimento
- **Metricas:** Vault populado com dados reais, Hermes consulta antes de responder
- **O que esta me impedindo:** Vault recem extraido, ainda vazio de dados (templates)
- **Proximo passo concreto:** Popular os arquivos de knowledge e current-state

## Medio Prazo (proximos 6 meses)

### Objetivo 1: THOTH AI operacional em VPS
- **O que seria sucesso:** Hermes + Thoth Agent Runtime rodando em producao na VPS, com clientes ativos
- **Metricas:** 1+ cliente com agente em producao, receita recorrente, custos rastreaveis
- **O que preciso fazer antes:** Baseline Thoth completo, rename Aurelia-Thoth, contratos internos estaveis
- **Riscos ou bloqueios:** Go toolchain, ambiente de producao, seguranca multi-tenant

### Objetivo 2: Pipeline de clientes ativo
- **O que seria sucesso:** 3+ clientes em pipeline, 1 contratado e em desenvolvimento
- **Metricas:** Pipeline documentado em _pipeline/, propostas enviadas, margem calculada
- **O que preciso fazer antes:** Servicos e precos documentados, posicionamento claro
- **Riscos ou bloqueios:** Foco dividido entre produto interno e clientes

## Longo Prazo (proximo 1 ano)

### Objetivo 1: THOTH AI como plataforma
- **O que seria sucesso:** Runtime Thoth completo com agent packs replicaveis por cliente
- **Metricas:** Multiplos clientes rodando cada um seu agente, custo por tenant rastreado
- **O que precisa acontecer antes:** Todo o roadmap Thoth (M0 a M12) executado
- **Por que isso importa:** Criar um ativo escalavel, nao uma consultoria

### Objetivo 2: Empresa independente do PC local
- **O que seria sucesso:** Zero dependencia de maquina local para operacao da empresa
- **Metricas:** Tudo rodando em VPS, backup automatizado, disaster recovery testado
- **O que precisa acontecer antes:** Hermes na VPS, Thoth na VPS, dados no git + backups
- **Por que isso importa:** Profissionalizacao, escala, confiabilidade

## Antiobjetivos

- Nao quero depender de um unico provider de LLM
- Nao quero clientes que pagam abaixo do custo operacional
- Nao quero virar consultoria de marketing digital
