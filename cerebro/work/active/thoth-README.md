     1|---
     2|tags: [project, thoth, runtime]
     3|status: active
     4|created: 2026-05-20
     5|updated: 2026-05-21
     6|---
     7|
     8|# Thoth Agent Runtime
     9|
    10|## Identidade
    11|
    12|| Campo | Valor |
    13||-------|-------|
    14|| Repo | ~/Documentos/Projects/Thoth |
    15|| Stack | Go, SQLite, Telegram adapter, providers plugáveis |
    16|| Module | github.com/kocar/aurelia (go 1.25.0) |
    17|| Status | M0 concluído, M1 bloqueado |
    18|
    19|## Descrição
    20|
    21|Runtime modular de agentes autônomos em Go. Provider-agnostic, channel-agnostic, multi-tenant. Roadmap de 13 marcos (M0 a M12).
    22|
    23|## Arquitetura
    24|
    25|```
    26|Thoth/
    27|├── docs/          ← documentação (M0 concluído)
    28|├── cmd/           ← entry points
    29|├── internal/      ← runtime core
    30|│   ├── agent/     ← ciclo de vida do agente
    31|│   ├── channel/   ← adapters de canal (Telegram, etc.)
    32|│   └── provider/  ← provedores LLM plugáveis
    33|└── pkg/           ← bibliotecas compartilhadas
    34|```
    35|
    36|## Bloqueios
    37|
    38|- Go toolchain não instalado (M1 bloqueado)
    39|
    40|## Decisões
    41|
    42|- 2026-05-20: Docs-first approach (M0 completo antes de qualquer código)
    43|- 2026-05-20: SQLite como storage inicial (zero infra, trocável depois)
    44|