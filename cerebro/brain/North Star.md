     1|---
     2|date:
     3|description: "Living document of goals, focus areas, and aspirations — read at session start, updated when direction shifts"
     4|tags:
     5|  - brain
     6|  - north-star
     7|aliases:
     8|  - Goals
     9|  - Focus
    10|---
    11|
    12|# North Star
    13|
    14|A living document of goals, aspirations, and current focus areas. Both you and Claude write to this. Claude reads it at the start of meaningful work sessions and references it when making suggestions.
    15|
    16|## Current Focus
    17|
    18|_What am I working toward right now?_
    19|
    20|-
    21|
    22|## Goals
    23|
    24|### Short-term (This Quarter)
    25|
    26|-
    27|
    28|### Medium-term (This Half)
    29|
    30|-
    31|
    32|### Long-term (This Year+)
    33|
    34|-
    35|
    36|## Aspirations
    37|
    38|_What kind of engineer/person am I becoming?_
    39|
    40|-
    41|
    42|## Anti-goals
    43|
    44|_What am I explicitly NOT optimizing for?_
    45|
    46|-
    47|
    48|## Shifts Log
    49|
    50|Record when focus changes, with date and reason.
    51|
    52|| Date | Shift | Reason |
    53||------|-------|--------|
    54||      | Created North Star | Initial setup |
    55|

---

## About Michel

     1|     1|---
     2|     2|tags: [knowledge, identity, core]
     3|     3|status: active
     4|     4|created: 2026-05-20
     5|     5|updated: 2026-05-20
     6|     6|---
     7|     7|
     8|     8|# Quem Sou Eu
     9|     9|
    10|    10|## Identidade
    11|    11|
    12|    12|- **Nome:** Michel Laurindo
    13|    13|- **Como prefere ser chamado:** Michel
    14|    14|- **Area de atuacao:** IA e aplicacoes autonomas
    15|    15|- **Cargo/papel atual:** Presidente da THOTH AI (empresa de agentes de IA)
    16|    16|- **Tempo na area:** 8 anos em dados, 2 anos com foco em IA
    17|    17|
    18|    18|## O Que Faco
    19|    19|
    20|    20|- **Descricao em 1 frase:** Construo uma empresa de agentes de IA onde cada cliente recebe agentes especializados como servico.
    21|    21|- **O que me diferencia:** Agentes nao sao features - sao a fundacao. Tudo que e construido pensado para escala: o que funciona para um cliente deve funcionar para dez.
    22|    22|- **O que NAO faco:** Nao sou consultor de marketing digital, nao faco sites, nao pego projetos abaixo de margem minima.
    23|    23|
    24|    24|## Habilidades Principais
    25|    25|
    26|    26|- **Hard skills:** Python, Go, IA/ML, agentes autonomos, LangGraph, FastAPI, arquitetura de sistemas, Databricks
    27|    27|- **Soft skills:** Visao estrategica, operacao solo com agentes, FinOps integrado, documentacao viva
    28|    28|- **Aprendendo agora:** Go avancado (para o Thoth Agent Runtime)
    29|    29|
    30|    30|## Ferramentas e Stack
    31|    31|
    32|    32|- **Ferramentas do dia a dia:** VS Code, Obsidian, terminal Linux, WhatsApp, Hermes (agente operacional)
    33|    33|- **Stack tecnico:** Python 3.11+, Go, FastAPI, LangGraph, Anthropic API, Qdrant, Podman, React/Next.js
    34|    34|- **Ferramentas de IA que uso:** Hermes (operacional), Claude Code (CEO), Kilo Code/DeepSeek Pro (implementacao), Codex (code review), Gemini (contexto longo), Copilot (inline), Aider (pair programming)
    35|    35|
    36|    36|## Como Prefiro Trabalhar
    37|    37|
    38|    38|- **Horario produtivo:** flexivel
    39|    39|- **Estilo de trabalho:** acao direta - prefere instalacao a discussao, comandos a debates
    40|    40|- **Comunicacao preferida:** WhatsApp (texto), direto e sem rodeios
    41|    41|- **O que me trava:** falta de clareza, burocracia, ferramentas quebradas
    42|    42|- **O que me destrava:** acao concreta, resultados visiveis, automacao
    43|    43|
    44|    44|## Contexto Pessoal
    45|    45|
    46|    46|- **Localizacao:** Brasil
    47|    47|- **Idiomas:** Portugues nativo
    48|    48|- **Fuso horario:** BRT (UTC-3)
    49|    49|
    50|    50|## Sobre Mim (aprendido com o tempo)
    51|    51|
    52|    52|- Prefere OAuth/login flows a API keys manuais
    53|    53|- Gosta de ter MAXIMO poder de agente - varios coding agents, superpoderes, claude-mem
    54|    54|- Direto e acao-orientado - "instale agora" ao inves de "o que voce acha?"
    55|    55|- Quer migrar toda operacao para uma VPS para nao depender do PC local
    56|    56|- Fala comigo pelo WhatsApp como interface unica e eu orquestro o resto
    57|    57|

## Goals

     1|     1|---
     2|     2|tags: [knowledge, goals, core]
     3|     3|status: active
     4|     4|created: 2026-05-20
     5|     5|updated: 2026-05-20
     6|     6|---
     7|     7|
     8|     8|# Meus Objetivos
     9|     9|
    10|    10|## Curto Prazo (proximo 30 dias)
    11|    11|
    12|    12|### Objetivo 1: Migrar o Hermes para VPS
    13|    13|- **O que seria sucesso:** Hermes rodando 24/7 numa VPS, acessivel via WhatsApp sem depender do PC local
    14|    14|- **Metricas:** Zero downtime, cron jobs executando, disponivel sempre que enviar mensagem
    15|    15|- **O que esta me impedindo:** Preciso organizar configs, skills e secrets num repo portavel
    16|    16|- **Proximo passo concreto:** Criar o repo ~/hermes-infra/ com tudo que o Hermes precisa
    17|    17|
    18|    18|### Objetivo 2: Baseline tecnico do Thoth
    19|    19|- **O que seria sucesso:** Go instalado, `go test ./...` passando, evidencias registradas
    20|    20|- **Metricas:** Build compilando, testes passando, blockers atualizados
    21|    21|- **O que esta me impedindo:** Go nao esta instalado (bloqueio registrado)
    22|    22|- **Proximo passo concreto:** Instalar Go 1.25+ e executar o baseline
    23|    23|
    24|    24|### Objetivo 3: Configurar o Segundo Cerebro no Hermes
    25|    25|- **O que seria sucesso:** Hermes le e escreve no vault do Obsidian como fonte central de conhecimento
    26|    26|- **Metricas:** Vault populado com dados reais, Hermes consulta antes de responder
    27|    27|- **O que esta me impedindo:** Vault recem extraido, ainda vazio de dados (templates)
    28|    28|- **Proximo passo concreto:** Popular os arquivos de knowledge e current-state
    29|    29|
    30|    30|## Medio Prazo (proximos 6 meses)
    31|    31|
    32|    32|### Objetivo 1: THOTH AI operacional em VPS
    33|    33|- **O que seria sucesso:** Hermes + Thoth Agent Runtime rodando em producao na VPS, com clientes ativos
    34|    34|- **Metricas:** 1+ cliente com agente em producao, receita recorrente, custos rastreaveis
    35|    35|- **O que preciso fazer antes:** Baseline Thoth completo, rename Aurelia-Thoth, contratos internos estaveis
    36|    36|- **Riscos ou bloqueios:** Go toolchain, ambiente de producao, seguranca multi-tenant
    37|    37|
    38|    38|### Objetivo 2: Pipeline de clientes ativo
    39|    39|- **O que seria sucesso:** 3+ clientes em pipeline, 1 contratado e em desenvolvimento
    40|    40|- **Metricas:** Pipeline documentado em _pipeline/, propostas enviadas, margem calculada
    41|    41|- **O que preciso fazer antes:** Servicos e precos documentados, posicionamento claro
    42|    42|- **Riscos ou bloqueios:** Foco dividido entre produto interno e clientes
    43|    43|
    44|    44|## Longo Prazo (proximo 1 ano)
    45|    45|
    46|    46|### Objetivo 1: THOTH AI como plataforma
    47|    47|- **O que seria sucesso:** Runtime Thoth completo com agent packs replicaveis por cliente
    48|    48|- **Metricas:** Multiplos clientes rodando cada um seu agente, custo por tenant rastreado
    49|    49|- **O que precisa acontecer antes:** Todo o roadmap Thoth (M0 a M12) executado
    50|    50|- **Por que isso importa:** Criar um ativo escalavel, nao uma consultoria
    51|    51|
    52|    52|### Objetivo 2: Empresa independente do PC local
    53|    53|- **O que seria sucesso:** Zero dependencia de maquina local para operacao da empresa
    54|    54|- **Metricas:** Tudo rodando em VPS, backup automatizado, disaster recovery testado
    55|    55|- **O que precisa acontecer antes:** Hermes na VPS, Thoth na VPS, dados no git + backups
    56|    56|- **Por que isso importa:** Profissionalizacao, escala, confiabilidade
    57|    57|
    58|    58|## Antiobjetivos
    59|    59|
    60|    60|- Nao quero depender de um unico provider de LLM
    61|    61|- Nao quero clientes que pagam abaixo do custo operacional
    62|    62|- Nao quero virar consultoria de marketing digital
    63|    63|