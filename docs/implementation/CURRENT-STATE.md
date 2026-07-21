# Current Implementation State

> **Auditoria D009-R1 (2026-07-20):** este documento foi revisado contra o
> código. Ver [AUDIT-D001-D009.md](AUDIT-D001-D009.md). Compliance da
> arquitetura nativa: **PARTIAL** — nada de lógica nova entrou em scripts
> de shell desde a D001, mas dívida herdada (4 listas de serviços,
> scheduler paralelo, `register-mcp.sh` religando o outbox) e dois
> desvios do período (canary runner e resolver fora do pacote) seguem
> abertos. D004/D005/D006 foram rebaixadas para PARTIAL.

Descreve SOMENTE o estado existente no HEAD. Futuro planejado fica no
[MASTER-PLAN.md](MASTER-PLAN.md).

Atualizado em: 2026-07-19 (D005, fechamento da Fase P1).

## Git

- branch: `codex/control-plane-redesign`
- HEAD: `f85d8ea` (feat(real): execute multiagent canary pipeline for all providers (D004))
  + D005 (E2E Claude Mem -> Cérebro -> Índices -> Consulta completos)
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
| `hive-mindd` (daemon) | `src/hive_mind/daemon/{main,lock,supervisor}.py` | PARTIAL — `run --shadow` passivo (D007); managed ainda EX_UNAVAILABLE | `tests/unit/test_daemon_lock.py`, `test_shadow_supervisor.py`, `test_shadow_purity.py`, `test_daemon_run_shadow.py`; D007 |
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
| Dream Cycle | `scripts/dream/dream_cycle.py` | script | job nativo (F7) | NOT_STARTED (porte); defeito de agrupamento **corrigido** em D002 |
| project identity | `scripts/capture/project_identity.py` (765 L) | script | módulo nativo (ADR-013 define destino) | PARTIAL — funciona, mas fora do pacote |

## Pipeline funcional

Legenda de estado: prova unitária ≠ OK operational. "UNIT" = coberto por
teste unitário/integração; "REAL" = comprovado com evento real pós-HEAD.

| Etapa | Estado | Evidência | Problema |
|---|---|---|---|
| provider source | REAL (D004) | canários provam cadeia inteira de ponta a ponta | — |
| parser | REAL (D004) | parsers validados nos canários multiagente | — |
| project identity | REAL (D004) | repo Git real + worktree real + registry entregue → `hive-mind`; 10 canários de providers passando; **bug de normalização dupla corrigido** | fora do pacote nativo |
| capture_core.ingest | REAL (D004) | ingestão bem sucedida no Claude Mem isolado dos canários | — |
| Claude Mem | REAL (D004) | `project_identity` gravado nos metadados da observação | dropdown com labels legados não migrados |
| bridge | REAL (D004) | `core/knowledge/claude_mem_bridge.py:401-435` grava `workspace_id = project_id` | — |
| UMC | REAL (D005) | observações no UMC promovidas para neurônios com `workspace_id` canônico e isolamento A/B provado | dados legados sem project_id não migrados |
| Dream Cycle | UNIT (D002) | agrupa por `project_id` via `resolve_observation_project()`; `fetch_balanced_observations` particiona por project_id; 18 unit + 6 integração SQLite real | falta prova operacional (ciclo real com modelos) |
| Markdown | UNIT (D002) | frontmatter com `project_id`, `project_name`, `identity_source`; path `cortex/temporal/<project_id>/<topic>/` | — |
| sqlite-vec | REAL (D005) | vetores e buscas isolados por workspace_id | — |
| Milvus | REAL (D005) | sincronização e expressões de filtro testados | sync_lag=568 em 2026-07-19 |
| Graphify | REAL (D005) | grafos estruturais mapeados e isolados por projeto | — |
| Graphiti | REAL (D005) | commit `7572756` isolou paths live | — |
| LightRAG | REAL (D005) | `test_lightrag_schema_selection.py` e isolamento E2E provados | — |
| REST | REAL (D005) | `scripts/services/sinapse-api.py` endpoints testados | — |
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
- manifesto `config/runtime.yaml` implementado (Fase P2 instalada com D006);
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
  Hermes) foram validados e complementados pelo teste E2E D005 (`test_e2e_memory_to_query_pipeline.py`).
