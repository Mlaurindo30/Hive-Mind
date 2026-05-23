     1|---
     2|tags: [knowledge, projects, core]
     3|status: active
     4|created: 2026-05-20
     5|updated: 2026-05-20
     6|---
     7|
     8|# Meus Projetos
     9|
    10|### Thoth Agent Runtime
    11|
    12|| Campo | Valor |
    13||-------|-------|
    14|| **Status** | em-andamento |
    15|| **Prioridade** | alta |
    16|| **Inicio** | 2026-05-20 |
    17|| **Deadline** | sem deadline |
    18|| **Proximo passo** | Instalar Go 1.25+ e executar baseline (M1) |
    19|| **Bloqueios** | Go toolchain indisponivel |
    20|
    21|**Descricao:** Runtime modular de agentes autonomos em Go, evolucao do Aurelia limpo. Provider-agnostic, channel-agnostic, multi-tenant. Roadmap de 13 marcos (M0 a M12).
    22|
    23|**Docs:** /home/michel/Documentos/Projects/Thoth/
    24|**Stack:** Go, SQLite, Telegram adapter, providers plugaveis
    25|**Fase atual:** M0 (fundacao documental) COMPLETO, M1 (baseline) bloqueado
    26|
    27|### Hermes na VPS (migracao)
    28|
    29|| Campo | Valor |
    30||-------|-------|
    31|| **Status** | nao-iniciado |
    32|| **Prioridade** | alta |
    33|| **Inicio** | 2026-05-20 |
    34|| **Deadline** | a definir |
    35|| **Proximo passo** | Criar repo ~/hermes-infra/ com configs, skills e deploy script |
    36|| **Bloqueios** | nenhum |
    37|
    38|**Descricao:** Migrar o Hermes (agente operacional via WhatsApp) do PC local para uma VPS, com tudo versionado no git para reproducao.
    39|
    40|### Segundo Cerebro (setup)
    41|
    42|| Campo | Valor |
    43||-------|-------|
    44|| **Status** | em-andamento |
    45|| **Prioridade** | alta |
    46|| **Inicio** | 2026-05-20 |
    47|| **Deadline** | a definir |
    48|| **Proximo passo** | Popular knowledge base e conectar Hermes ao vault |
    49|| **Bloqueios** | nenhum |
    50|
    51|**Descricao:** Configurar o vault Obsidian como fonte central de conhecimento, com Hermes lendo e escrevendo para manter contexto entre sessoes.
    52|
    53|### agency-agents (referencia)
    54|
    55|| Campo | Valor |
    56||-------|-------|
    57|| **Status** | concluido |
    58|| **Prioridade** | baixa |
    59|| **Inicio** | 2026-05-20 |
    60|| **Deadline** | sem deadline |
    61|| **Proximo passo** | Testar com coding agents |
    62|| **Bloqueios** | nenhum |
    63|
    64|**Descricao:** Colecao de 207 agentes especializados em Markdown, 17 divisoes. Clonado para ~/.hermes/agents/.
    65|