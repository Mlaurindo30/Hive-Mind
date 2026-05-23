     1|---
     2|tags: [project, hermes, infra, vps]
     3|status: active
     4|created: 2026-05-20
     5|updated: 2026-05-21
     6|---
     7|
     8|# Hermes na VPS (Migração)
     9|
    10|## Identidade
    11|
    12|| Campo | Valor |
    13||-------|-------|
    14|| Objetivo | Hermes 24/7 em VPS, acessível via WhatsApp sem depender do PC local |
    15|| Status | Planejamento |
    16|| Dependência | ~/Documentos/Projects/sinapse_agent/ (memória) |
    17|
    18|## Descrição
    19|
    20|Migrar o Hermes Agent da máquina local para uma VPS com zero downtime. O Sinapse Agent é pré-requisito — a camada de memória precisa estar portável antes do runtime.
    21|
    22|## Requisitos
    23|
    24|- Configs e secrets versionados e portáveis
    25|- Cron jobs executando na VPS
    26|- WhatsApp gateway 24/7
    27|- Mesmo comportamento do ambiente local
    28|
    29|## Decisões
    30|
    31|- 2026-05-20: Criar repo ~/hermes-infra/ com config.yaml, .env.example, deploy.sh
    32|- 2026-05-21: Sinapse Agent como pré-requisito (memória portável)
    33|
    34|## Bloqueios
    35|
    36|- VPS não escolhida (Digital Ocean vs Hetzner vs AWS Lightsail)
    37|- Secrets (.env) precisam de solução segura na VPS
    38|