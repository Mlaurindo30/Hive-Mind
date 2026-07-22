# Project Status Dashboard

- **branch:** `codex/control-plane-redesign`
- **HEAD:** `e86b1fa`
- **active delivery:** D009-R5 (agents doctor/unregister, instruções e captura nativas)
- **last completed delivery:** D009-R4 (writer TOML nativo do Codex)
- **next delivery:** D009-R6 (wrappers PS1/SH mínimos)
- **native control plane compliance:** PARTIAL
- **runtime active root:** `D:\Hive-Mind` (não alterado, exceto DR-001 autorizado)
- **runtime active owner:** Task Scheduler + `npm/lib/supervisor.js` (legado)
- **D010 status:** **BLOCKED** — exige D010-G0 DONE
- **installation status:** instalação limpa NÃO executada
- **reboot status:** reboot NÃO executado
- **real data migration status:** NÃO executada (outbox com 18.579 eventos não entregues; UMC 0% workspace canônico)
- **last full regression:** 1214 passed, 26 skipped, 2 failed
- **known test failures:** 2 pré-existentes em `test_windows_install_contract.py` (UnicodeDecodeError de stdout PowerShell)
- **worktree status:** limpa, exceto 16 untracked em `.tmp/` (LOCAL TEST ARTIFACT)

## Entregas

Qualificadores de status: `DONE` exige prova real. `DONE_SYNTHETIC` /
`DONE_TEMP_CONFIG` indicam prova apenas com dados sintéticos ou cópia
temporária. `IMPLEMENTED_NO_CUTOVER` indica código pronto sem troca de owner.

| Delivery | Objective | Status | Last commit | Real proof | Remaining |
|---|---|---|---|---|---|
| D001 | Documentação viva | **DONE** | `834e405` | 8 docs, aprovado | — |
| D002 | Dream Cycle por project_id | **PARTIAL** | `2ae8558` | unit + SQLite real | ciclo real com modelos |
| D003 | Identidade de projeto validada | **PARTIAL** | `fca4c5a` | repo Git real + registry | canário por provider |
| D004 | Canários multiagente | **PARTIAL** | `e83d260` | canário real: 4 pass, 4 fail | cadeia de entrega quebrada |
| D005 | E2E memória → consulta | **PARTIAL** | `d793353` | testes reais | depende de scripts não portados |
| D006 | Manifesto declarativo | **PARTIAL** | `1db2523` | 10 testes | 4 catálogos concorrentes |
| D007 | Daemon shadow | **IMPLEMENTED_NO_CUTOVER** | `cb4c66d` | run --shadow real, HTTP, socket | cutover |
| D008 | Supervisor e scheduler | **PARTIAL** | `1857869` | processos sintéticos reais | disparo de jobs, cutover |
| D009 | Registro MCP/captura nativo | **PARTIAL** | `e86b1fa` | detect real 9/13, dry-run 11 alvos | doctor, unregister, instruções, captura, wrappers |
| D010 | Cutover de owners legados | **BLOCKED** | — | — | exige D010-G0 |
| D011 | Installer e lifecycle Windows | NOT_STARTED | — | — | — |
| D012 | Windows descartável + reboot | NOT_STARTED | — | — | — |
| D013 | Atualização da raiz | NOT_STARTED | — | — | — |
| D014 | Limpeza de shims e release | NOT_STARTED | — | — | — |

### Subentregas de remediação

| ID | Objetivo | Status | Commit | Prova |
|---|---|---|---|---|
| D009-R1 | Auditoria de propriedade nativa | **DONE** | `6d0eb11` | 6 achados (A-01…A-06) |
| D009-R2 | Testes arquiteturais | **DONE** | `a8f0e59` | 14 testes verdes |
| D009-R3 | Paridade POSIX do capture hook | **DONE** | `fef5383` | ADR-004 restaurado |
| D009-R4 | Writer TOML do Codex | **DONE_TEMP_CONFIG** | `e86b1fa` | cópia do config real (181 L) |
| D009-R5 | doctor, unregister, instruções, captura | **IN_PROGRESS** | — | — |
| D009-R6 | Wrappers PS1/SH mínimos | NOT_STARTED | — | — |
| D003-R1 | Resolver no pacote nativo | **DONE** | `bf60028` | 115 testes; legado é shim |
| D004-R1 | Canary runner nativo | **DONE** | `e83d260` | canário sobre dados reais |
| D006-R1 | Catálogo único | **PARTIAL** | `b9af988` | bloqueado: 4 serviços aspiracionais + post-reboot ausente |
| D008-R1V | Inventário de jobs validado | **DONE** | `33191e3` | 18 jobs vivos; 1 morto removido |
| D008-R1B | Backup nativo verificado | **DONE_SYNTHETIC** | `4f22a3c` | run→verify→restore sintético |
| DR-001 | Restart policy do Docker | **DONE** | `69632bd` | 7/7 containers `unless-stopped` |
| **D010-G0** | **Windows Native Migration Readiness** | **NOT_STARTED** | — | gate obrigatório de D010 |

Inventário completo: [WINDOWS-NATIVE-MIGRATION.md](WINDOWS-NATIVE-MIGRATION.md)
— 15 `LEGACY_OWNER` bloqueiam D010, 0 `UNKNOWN`.

---

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

Atualizado em: 2026-07-21 (dashboard + D010-G0). O painel acima é a fonte de estado; as seções abaixo detalham camadas.

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
| provider detection | `hive_mind.agents.detect` | **pacote** | — | **NATIVE** (D009) |
| MCP registration | `hive_mind.agents.{register,mcp_config,toml_config}` | **pacote** | — | **NATIVE** (D009, D009-R4); scripts ainda LEGACY_OWNER até D009-R6 |
| capture install | `scripts/setup/install-capture-hooks.py` | script | `hive_mind.agents` | **TO_REMOVE** — desligado de ambos os instaladores (D009-R3); porte nativo em D009-R5 |
| supervisor | `npm/lib/supervisor.js` + Task Scheduler | Node/OS | `hive-mindd` (F4–F5) | NOT_STARTED |
| scheduler | `register-windows-jobs.ps1` + systemd timers | scripts/OS | `hive-mindd` + APScheduler (F6–F7) | NOT_STARTED |
| services status | `scripts/setup/install_services.py::unit_definitions` | script | `hive_mind.daemon.manifest` (F2/F11) | NOT_STARTED |
| Dream Cycle | `scripts/dream/dream_cycle.py` | script | job nativo (F7) | NOT_STARTED (porte); defeito de agrupamento **corrigido** em D002 |
| project identity | `hive_mind.projects.identity` | **pacote** | — | **NATIVE** (D003-R1); legado é SHIM |

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
