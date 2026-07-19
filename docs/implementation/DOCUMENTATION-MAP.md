# Documentation Map

## Matriz alteração → documentação obrigatória

| Alteração | Documentação obrigatória |
|---|---|
| CLI | README.md, docs/cli.md |
| instalação Windows | README.md, docs/install/windows.md |
| instalação Linux | README.md, docs/install/linux.md |
| configuração | docs/configuration.md, config/*.example |
| provider (captura) | docs/capture/providers.md |
| MCP | docs/mcp.md |
| project identity | docs/project-identity.md |
| Dream Cycle | docs/dream-cycle.md |
| banco/schema | docs/data-model.md, notas de migração |
| serviço/runtime | docs/runtime.md, runbook de operações |
| health/doctor | docs/operations.md |
| rollback | docs/install/rollback.md |
| release | CHANGELOG.md, release notes |

Toda entrega que altera comportamento em uma dessas áreas só pode ser
DONE com a documentação correspondente atualizada (regra 7 do README).

## Inventário e classificação (levantado em 2026-07-19, D001)

Classificações: CURRENT / STALE / CONTRADICTORY / MISSING / HISTORICAL.

### Documentos raiz

| Documento | Classificação | Observação |
|---|---|---|
| README.md | STALE (presumido) | descreve instalação por scripts; não menciona CLI nativo `hive-mind`; auditoria linha a linha pendente (P1) |
| AGENTS.md | STALE (presumido) | auditoria pendente |
| CLAUDE.md (worktree) | MISSING | existe apenas no runtime `D:\Hive-Mind` e em backups de `cerebro/`; worktree não tem |
| CHANGELOG.md | MISSING | não existe; criar até P10 |

### docs/

| Documento | Classificação | Observação |
|---|---|---|
| docs/README.md | STALE (presumido) | auditoria pendente |
| docs/01-architecture.md | CONTRADICTORY (presumido) | anterior ao control-plane-redesign-v2; não reflete CLI/daemon nativos |
| docs/02-ai-models.md … docs/14-model-gateway.md | HISTORICAL/STALE | auditoria pendente por arquivo |
| docs/installation.md | STALE (presumido) | descreve fluxo por scripts; será reescrito em P7 |
| docs/reports/POST_AUDIT_FIX_LOG.md | HISTORICAL | manter como registro |
| docs/superpowers/specs/2026-07-17-canonical-project-identity-*.md | CURRENT | design vigente da identidade |
| docs/superpowers/plans/2026-07-17-canonical-project-identity-*.md | CURRENT | plano vigente |
| docs/superpowers/{specs,plans}/2026-07-09..13-*.md | HISTORICAL | ciclos anteriores |

### specs/

| Documento | Classificação | Observação |
|---|---|---|
| specs/control-plane-redesign-v2.md | CURRENT | fonte de verdade arquitetural |
| specs/control-plane-redesign.md (v1, em `D:\Hive-Mind`, untracked) | HISTORICAL | superado pela v2 (Anexo C da v2 documenta os erros da v1) |
| specs/model-gateway.md, model-gateway-unification.md | CURRENT (presumido) | fora do escopo deste plano |
| specs/post-audit-stabilization.md | HISTORICAL | ciclo anterior |

### Documentação MISSING exigida pela matriz

| Documento | Fase responsável | Gatilho |
|---|---|---|
| docs/cli.md | P1+ (cresce com o CLI) | primeiro comando novo documentável |
| docs/project-identity.md | P1 / D002–D003 | identidade canônica em produção |
| docs/dream-cycle.md | P1 / D002 | correção do agrupamento |
| docs/capture/providers.md | P1 / D004 | canários por provider |
| docs/mcp.md | P5 / D009 | registro nativo |
| docs/configuration.md | P2 / D006 | manifesto declarativo |
| docs/runtime.md | P3–P4 / D007–D008 | daemon/supervisor |
| docs/operations.md | P4+ | health/doctor |
| docs/data-model.md | P1+ | primeiro schema alterado |
| docs/install/windows.md | P7 / D011 | installer nativo |
| docs/install/linux.md | P7+ | paridade |
| docs/install/rollback.md | P7 / D011 | lifecycle |
| CHANGELOG.md | P10 / D014 | release |

### Divergências documentais concretas já encontradas

| # | Documento | Afirmação incorreta/desatualizada | Código real | Correção necessária | Fase |
|---|---|---|---|---|---|
| 1 | comentário em `register-mcp.sh` | instala capture hooks como parte do registro (linha 357 ativa) | `.ps1` equivalente já não instala (`b329e84`); ADR-004 define dono único | transformar em wrapper / remover invocação | P5/D009 |
| 2 | `docs/installation.md` | fluxo de instalação por scripts como caminho canônico | spec F10 define installer nativo <100 LOC | reescrever | P7/D011 |
| 3 | `docs/01-architecture.md` | arquitetura pré-redesign | `specs/control-plane-redesign-v2.md` | marcar HISTORICAL ou reescrever | P2+ |
| 4 | frontmatter dos Markdown do cérebro | `project:` label livre (ex.: `project: Hive-Mind`) | ADR-007 exige `project_id` canônico | novo frontmatter em D002; legacy preservado | P1/D002 |

Observação: classificações "presumido" indicam que o documento foi
identificado e categorizado pelo contexto, mas a auditoria linha a
linha ainda não foi feita — ela acontece na fase responsável indicada.
Não atualizar tudo agora; primeiro corrigir o código da fase, depois o
documento, na mesma entrega.
