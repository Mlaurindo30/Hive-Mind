# Master Implementation Plan

## Baseline

- branch: `codex/control-plane-redesign`
- HEAD: `ae32195` (docs(implementation): establish living execution plan)
- HEAD anterior a D001: `b329e84`
- base: `d246f0c` (41 commits à frente; ~62 vs `main`)
- versão: 3.10.1 (worktree) / runtime ativo 3.10.0
- data: 2026-07-19
- runtime ativo: `D:\Hive-Mind` (NÃO alterar até P9)
- worktree: `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install`
- spec: `specs/control-plane-redesign-v2.md`
- estado global: F1 (empacotamento) concluída; F2+ não iniciadas;
  cadeia funcional quebrada no Dream Cycle (agrupa por label livre)
- aprovações (2026-07-19): MASTER-PLAN APROVADO; ADR-013 APROVADO

## Princípios obrigatórios

- CLI nativo `hive-mind`;
- daemon nativo `hive-mindd`;
- PowerShell/Bash somente wrappers (ADR-003);
- um owner por serviço/job/provider (ADR-002);
- captura funcional baseada em `capture_core.ingest` (ADR-004);
- captura Claude Mem nativa preservada (ADR-005);
- `project_id` canônico ponta a ponta (ADR-006);
- Dream Cycle agrupado por `project_id` (ADR-007);
- Docker apenas para infraestrutura server-side (ADR-008);
- testes operacionais reais — mock não é evidência de aceite;
- instalação Windows descartável antes da raiz (ADR-010);
- rollback obrigatório em toda entrega.

## Correspondência fases ↔ spec

As fases P0–P10 deste plano sequenciam a execução. As fases F1–F12 da
spec (seção 16) continuam sendo a referência de cutover. Mapa:

| Plano | Spec | Observação |
|---|---|---|
| P0 | — | documentação viva (este conjunto) |
| P1 | pré-F2 | fecha a cadeia funcional existente antes do novo control plane |
| P2 | F2 | manifesto declarativo |
| P3 | F3 | daemon shadow |
| P4 | F4–F8 | supervisor + scheduler + cutovers de serviço/job |
| P5 | F11 (parcial) | registro nativo de agentes/MCP/captura |
| P6 | F4–F8, F11 | cutover de owners legados |
| P7 | F10 | installer e lifecycle |
| P8 | F12 | Windows descartável + reboot |
| P9 | — | atualização controlada de `D:\Hive-Mind` |
| P10 | F11 final | limpeza de shims, release |

## Fases

### P0 — Documentação e baseline

Objetivo: consolidar documentos, estado atual, commits e critérios.

Status: DONE (plano aprovado em 2026-07-19; D001 commitada)

Saída obrigatória:
- documentos deste diretório criados;
- 40 commits mapeados (ver DELIVERY-LEDGER D000);
- arquitetura atual versus desejada (CURRENT-STATE);
- lista de documentação obsoleta (DOCUMENTATION-MAP);
- plano aprovado;
- nenhuma alteração de runtime.

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D001 | Documentação viva e baseline | — | DONE | 8 documentos, +1120 linhas; aprovações de 2026-07-19 | b329e84 | ae32195 + fechamento |

### P1 — Fechar cadeia funcional atual

Objetivo:

```
project identity → captura → Claude Mem → bridge → UMC
→ Dream Cycle → Markdown → índices → consulta
```

Incluir:
- portar `ProjectIdentityResolver` para local canônico (decisão de
  namespace em ADR-013 antes de mover);
- eliminar uso livre de `observations.project`;
- Dream Cycle por `project_id`;
- daily writer por `project_id`;
- frontmatter canônico nos Markdown;
- `workspace_id = project_id` verificado ponta a ponta;
- filtros por projeto (sqlite-vec, Milvus, grafos, LightRAG);
- projetos de teste A/B isolados;
- canários reais de todos os providers instalados;
- saúde semântica (observations_linked_pct, discoveries_pending,
  orphan_vectors, milvus_sync_lag);
- documentação correspondente.

Esta fase TERMINA antes de iniciar o novo control plane (P2+).

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D002 | Dream Cycle + project_id + Markdown | D001 ✅ | NOT_STARTED (**próxima, autorizada**) | — | — | — |
| D003 | Validação real da identidade de projeto | D002 | NOT_STARTED | — | — | — |
| D004 | Canários multiagente completos | D003 | NOT_STARTED | — | — | — |
| D005 | E2E Claude Mem → cérebro → índices → consulta | D004 | NOT_STARTED | — | — | — |

### P2 — Manifesto declarativo e ownership (spec F2)

Objetivo: `config/runtime.yaml` com serviços, external services, jobs,
providers, compose projects, owners, dependencies, readiness,
required_policy e perfis local-min/local-full.
`hive-mind config validate` / `config show` reproduzem `unit_definitions()`.

Não iniciar supervisor real ainda.

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D006 | Manifesto declarativo F2 | D005 | NOT_STARTED | — | — | — |

### P3 — Daemon shadow (spec F3)

Objetivo: `hive-mindd run`, lock de instância única, estado, health,
readiness, shadow totalmente passivo (proibição absoluta de mutação —
spec Anexo D.4), project-root, logs, control socket. Nenhum cutover.

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D007 | Daemon shadow | D006 | NOT_STARTED | — | — | — |

### P4 — Scheduler e supervisor nativos (spec F4–F8)

Objetivo: scheduler único (APScheduler), supervisor, process groups /
Job Objects, restart policy, dependency graph, leases, misfire,
timezone, shutdown, observabilidade.

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D008 | Supervisor e scheduler nativos | D007 | NOT_STARTED | — | — | — |

### P5 — Registro nativo de agentes e MCP (spec F11 parcial)

Objetivo:
- namespace canônico ÚNICO: `hive_mind.agents` (ADR-013 — a spec já
  nomeia `hive_mind.agents.register`; NÃO criar `integrations/`
  concorrente);
- detectar providers; registrar MCP; instalar instruções; instalar
  captura; status; doctor; rollback;
- wrappers PS1/SH mínimos (localizar executável, repassar argumentos,
  repassar exit code — nada mais).

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D009 | Registro MCP/captura nativo | D008 | NOT_STARTED | — | — | — |

### P6 — Cutover dos componentes (spec F4–F8, F11)

Objetivo: shadow → managed com journal transacional (spec Anexo D.3),
rollback automático, remoção de owners legados (Node supervisor, Task
Scheduler, systemd, scripts), um owner de cada vez.

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D010 | Cutover de owners legados | D009 | NOT_STARTED | — | — | — |

### P7 — Installer Windows e lifecycle (spec F10)

Objetivo: install local-min/local-full, repair, update, rollback,
uninstall, reinstall, configuração, logs, serviço/sessão do usuário
(ADR-009), documentação completa.

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D011 | Installer e lifecycle Windows | D010 | NOT_STARTED | — | — | — |

### P8 — Windows descartável e reboot (spec F12)

Objetivo: instalação do zero em ambiente descartável, captura, Dream
Cycle, Markdown, banco, índices, REST, MCP, CLI, reboot, post-reboot,
lifecycle completo. NÃO usar a máquina ativa como primeiro teste.

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D012 | Windows descartável + reboot | D011 | NOT_STARTED | — | — | — |

### P9 — Atualização da raiz

Objetivo: snapshot, backup (config, banco, cerebro, tarefas, logs),
update controlado de `D:\Hive-Mind`, validação, reboot, rollback real,
relatório final. Exige autorização humana explícita.

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D013 | Atualização controlada da raiz | D012 | NOT_STARTED | — | — | — |

### P10 — Finalização e release

Objetivo: remover shims (inclui `b329e84`), remover código morto,
documentação final, changelog, release notes, score 100/100.
Merge/release somente após autorização.

| ID | Entrega | Dependências | Estado | Evidência | Commit inicial | Commit final |
|---|---|---|---|---|---|---|
| D014 | Limpeza de shims e documentação final | D013 | NOT_STARTED | — | — | — |

## Ordem registrada das entregas

```
D001  documentação viva e baseline
D002  Dream Cycle + project_id + Markdown
D003  validação real da identidade de projeto
D004  canários multiagente completos
D005  E2E Claude Mem → cérebro → índices → consulta
D006  manifesto declarativo F2
D007  daemon shadow
D008  supervisor e scheduler nativos
D009  registro MCP/captura nativo
D010  cutover de owners legados
D011  installer e lifecycle Windows
D012  Windows descartável + reboot
D013  atualização controlada da raiz
D014  limpeza de shims e documentação final
```

Não preencher DONE sem evidência real.
