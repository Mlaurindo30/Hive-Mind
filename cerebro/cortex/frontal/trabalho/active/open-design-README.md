     1|---
     2|tags: [project, open-design, dashboard]
     3|status: active
     4|created: 2026-05-21
     5|updated: 2026-05-21
     6|---
     7|
     8|# Open Design
     9|
    10|## Identidade
    11|
    12|| Campo | Valor |
    13||-------|-------|
    14|| Repo | ~/Documentos/Projects/open-design |
    15|| Stack | TypeScript, Next.js, pnpm (corepack), Node 24 |
    16|| Execução | pnpm tools-dev run web ou node apps/daemon/dist/cli.js |
    17|| Docker | NÃO usar — roda via source |
    18|
    19|## Descrição
    20|
    21|Dashboard/plataforma de design. Daemon expõe APIs e serve web estático em porta única.
    22|
    23|## Arquitetura
    24|
    25|```
    26|open-design/
    27|├── apps/
    28|│   ├── daemon/     ← servidor principal (APIs + static serve)
    29|│   └── web/        ← frontend Next.js
    30|├── packages/       ← libs compartilhadas
    31|└── tools-dev/      ← scripts de dev (pnpm tools-dev run web)
    32|```
    33|
    34|## Decisões
    35|
    36|- 2026-05-21: Rodar via source, não Docker (RTK interfere com pnpm no container)
    37|- 2026-05-21: Node 24 via tarball (~/.local/node24) porque apt do Ubuntu 26.04 tem Node 22
    38|