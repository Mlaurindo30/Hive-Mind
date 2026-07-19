# Current Implementation State

Descreve SOMENTE o estado existente no HEAD. Futuro planejado fica no
[MASTER-PLAN.md](MASTER-PLAN.md).

Atualizado em: 2026-07-19 (D001, fechamento).

## Git

- branch: `codex/control-plane-redesign`
- HEAD: `ae32195` (docs(implementation): establish living execution plan)
- HEAD anterior a D001: `b329e84`
- base: `d246f0c`
- commits à frente da base: 41 (≈62 vs `main`) — 40 auditados no D000
  + D001
- staged: nenhum
- unstaged: nenhum
- untracked: 16 arquivos em `.tmp/` — LOCAL TEST ARTIFACT (canário
  Hermes 2026-07-18 + screenshots); não rastreados, não requeridos pelo
  produto, cleanup pendente de aprovação separada
- versão: 3.10.1 (worktree); runtime ativo em `D:\Hive-Mind` = 3.10.0

## Pacote nativo

| Componente | Local | Estado | Evidência |
|---|---|---|---|
| `hive-mind` (CLI) | `src/hive_mind/cli.py` + entry point em `pyproject.toml` | PARTIAL — só `--version` e `projects audit` | `tests/unit/test_f1_package.py`; commit `e215fd6`, `a44540b` |
| `hive-mindd` (daemon) | `src/hive_mind/daemon/main.py` | PARTIAL — stub de F1, sem run loop | `tests/unit/test_f1_package.py`; commit `a44540b` |
| project root | `src/hive_mind/project.py` | DONE (escopo F1) | `tests/unit/test_f1_project_root.py` (151 L); commit `60aa2af` |
| projects audit | `core/projects/audit.py` + `src/hive_mind/cli.py:59-116` | DONE (unit + integração read-only) | `tests/unit/test_projects_audit.py` (127 L); `tests/integration/test_projects_audit_readonly.py`; commit `8a4a41f` |
| build (wheel+sdist) | `pyproject.toml` (hatchling) | DONE (escopo F1) | commits `6ac42f4`, `6f6dc64`; `uv build` < 5s |

## Código ainda legado

| Responsabilidade | Arquivo atual | Dono atual | Destino nativo (spec) | Estado |
|---|---|---|---|---|
| provider detection | `scripts/setup/register-mcp.ps1:423-438` / `.sh` | script | `hive_mind.agents` (F11) | NOT_STARTED |
| MCP registration | `scripts/setup/register-mcp.ps1` (~430 L) / `.sh` (~360 L) | script | `hive_mind.agents.register` (F11) | NOT_STARTED |
| capture install | `scripts/setup/install-capture-hooks.py` | script | `hive_mind.agents` (F11) | PARTIAL — wiring removido do `.ps1` (`b329e84`); **ainda invocado por `register-mcp.sh:357`** |
| supervisor | `npm/lib/supervisor.js` + Task Scheduler | Node/OS | `hive-mindd` (F4–F5) | NOT_STARTED |
| scheduler | `register-windows-jobs.ps1` + systemd timers | scripts/OS | `hive-mindd` + APScheduler (F6–F7) | NOT_STARTED |
| services status | `scripts/setup/install_services.py::unit_definitions` | script | `hive_mind.daemon.manifest` (F2/F11) | NOT_STARTED |
| Dream Cycle | `scripts/dream/dream_cycle.py` | script | job nativo (F7) | NOT_STARTED (e com defeito de agrupamento — ver abaixo) |
| project identity | `scripts/capture/project_identity.py` (765 L) | script | módulo nativo (ADR-013 define destino) | PARTIAL — funciona, mas fora do pacote |

## Pipeline funcional

Legenda de estado: prova unitária ≠ OK operacional. "UNIT" = coberto por
teste unitário/integração; "REAL" = comprovado com evento real pós-HEAD.

| Etapa | Estado | Evidência | Problema |
|---|---|---|---|
| provider source | UNIT | 12 adapters em `scripts/capture/capture_adapters.py:104` (antigravity, codex, copilot, hermes, kilo, kimi, mimo, openclaw, qwen, roo, screenpipe, swarmclaw) | canários reais pós-correção não executados |
| parser | UNIT | `tests/unit/test_provider_parser_identity_contract.py` (264 L); parsers por provider | idem |
| project identity | UNIT | `scripts/capture/project_identity.py`; 82 testes passando (2026-07-19); `config/project-aliases.yaml` com roots raiz+worktree | sem prova real; fora do pacote nativo |
| capture_core.ingest | UNIT | `capture-realtime.py:144`, `capture-tailer.py:130`; dono único após `b329e84` | — |
| Claude Mem | UNIT | `capture_core.py:297,329` usa `project_name` canônico | dropdown com labels legados não migrados |
| bridge | UNIT | `core/knowledge/claude_mem_bridge.py:401-435` grava `workspace_id = project_id` | sem prova real ponta a ponta |
| UMC | PARTIAL | tabelas aceitam `workspace_id`; dados legados sem project_id não migrados | relatório de migração pendente (comando audit existe) |
| Dream Cycle | **QUEBRADO** | `dream_cycle.py:71` `PARTITION BY COALESCE(project,'_sem_projeto')`; `:812` lê `o["project"]` texto livre; 0 ocorrências de `project_id` | ignora o `project_id` que o bridge grava |
| Markdown | **AUSENTE** | 0 ocorrências de `project_id` em `daily_writer.py`; frontmatter atual usa `project:` label livre | diretórios fragmentados por label |
| sqlite-vec | NÃO AUDITADO | — | filtros por project_id não verificados |
| Milvus | NÃO AUDITADO | `milvus_sync_lag=568` em 2026-07-19 | idem |
| Graphify | NÃO AUDITADO | — | idem |
| Graphiti | NÃO AUDITADO | commit `7572756` isolou paths live | idem |
| LightRAG | NÃO AUDITADO | `tests/unit/test_lightrag_schema_selection.py` | vazamento cross-project não verificado |
| REST | NÃO AUDITADO | `scripts/services/sinapse-api.py` | — |
| MCP | UNIT (parcial) | `sinapse_health` respondendo em 2026-07-19 | registro ainda via scripts |
| CLI | PARTIAL | `hive-mind projects audit` existe | demais comandos ausentes |

## Saúde semântica (medição de 2026-07-19, runtime ativo)

| Métrica | Valor | Limiar | Estado |
|---|---:|---:|---|
| neurons_vectorized_pct | 93.61% | — | ok |
| observations_linked_pct | 7.62% | ≥80% | **degraded** |
| discoveries_pending | 942 | ≤500 | **degraded** |
| orphan_vectors | 7 | 0 | **degraded** |
| milvus_sync_lag (total) | 568 | 0 | atrasado |

`sinapse_health.status = degraded`. Não mascarar com "Ready: true".

## Fatos adicionais comprovados

- F1 de empacotamento implementada (commits `e215fd6`…`6f6dc64`);
- manifesto `config/runtime.yaml` AUSENTE (F2 não iniciada);
- caminho experimental outbox (`capture-hook.py` → `CaptureQueue`)
  desabilitado no runtime novo (`cb7e3bd` + `b329e84`); arquivos e
  bancos históricos preservados (ADR-011);
- `D:\Hive-Mind\logs\capture-outbox.db` continua recebendo eventos do
  runtime ANTIGO — esperado; não alterar até P9;
- 2 testes pré-existentes falhando em
  `tests/unit/test_windows_install_contract.py`
  (UnicodeDecodeError lendo stdout PowerShell; reproduzido com e sem o
  diff de `b329e84`);
- 3 testes skipped em `tests/unit/test_register_mcp.py` no Windows
  (exigem POSIX shell);
- instalação Windows descartável NUNCA executada;
- canários anteriores (Antigravity IDE, Kimi, Qwen CLI, Qwen Desktop,
  Hermes) são PRÉ-correção de identidade — precisam ser repetidos.
