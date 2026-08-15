# Windows Native Migration — inventário obrigatório

Inventário de **todo** componente Windows, descoberto via `git ls-files` e
filesystem — não por lista fornecida. Gate: **D010-G0**.

Descoberta: **36** arquivos `.ps1/.psm1/.bat/.vbs` rastreados (fora de
`tests/`) + **6** arquivos Node + 2 entry points Python.

## Arquitetura final obrigatória

| Camada | Responsabilidades |
|---|---|
| `hive-mind` | instalação, configuração, agents, MCP, captura, backup, doctor, repair, update, rollback, uninstall, validação |
| `hive-mindd` | supervisor, scheduler, jobs, process lifecycle, health, readiness, restart, post-reboot |
| PowerShell/Bash | localizar executável, repassar argumentos, preservar stdout/stderr, devolver exit code — **nada mais** |

Scripts **não podem** manter: catálogo de serviços ou jobs, lista de
providers, paths de agentes, edição JSON/TOML/YAML, scheduler, supervisor,
retry, rollback, backup, captura, project identity, Dream Cycle,
instalação de instruções, registro MCP, manipulação de banco.

Estados: `NATIVE` · `PORT_IN_PROGRESS` · `LEGACY_OWNER` · `THIN_WRAPPER` ·
`SHIM` · `TO_REMOVE` · `EXTERNAL_COMPONENT`. **`UNKNOWN` não é aceito no
D010-G0.**

## Bloqueadores de D010 (lógica de produto em script)

| Arquivo | L | Função atual | Owner | Destino | Estado | Delivery | Remoção |
|---|--:|---|---|---|---|---|---|
| `install.bat` | 12 | bootstrap que resolve Python e delega para o owner nativo | `src/hive_mind/install/windows.py` | `hive-mind install` | **THIN_WRAPPER** | D011 | D014 |
| `scripts/lib/HiveMind.Windows.psm1` | 388 | camada PowerShell de compatibilidade; owners reais portados para `hive_mind.install.windows_support` | `src/hive_mind/install/windows_support.py` | `hive_mind.platform` | **THIN_WRAPPER** | D011 | D014 |
| `scripts/setup/bootstrap-prerequisites.ps1` | 178 | shim PowerShell que delega pré-requisitos ao owner Python nativo | `src/hive_mind/install/windows_prereqs.py` | `hive-mind install` | **THIN_WRAPPER** | D011 | D014 |
| `scripts/setup/install_services.py` | 12 | shim Python que reexporta o owner nativo de serviços | `src/hive_mind/maintenance/runtime_services.py` | `config/runtime.yaml` | **THIN_WRAPPER** | D006-R1 | D014 |
| `npm/lib/services.js` | 72 | wrapper Node que deriva units/labels do manifest via supervisor | `npm/lib/supervisor.js` + `config/runtime.yaml` | `config/runtime.yaml` | **THIN_WRAPPER** | D006-R1 | D014 |
| `npm/lib/supervisor.js` | 279 | wrapper Node do `hive-mindd` gerenciado; ainda mantém start/stop/wait do daemon | `hive_mind.daemon.*` | `hive-mindd` | **PORT_IN_PROGRESS** | D010 | D014 |
| `scripts/setup/register-windows-jobs.ps1` | 18 | wrapper fino que delega para `hive_mind.cli service windows-jobs` | `src/hive_mind/maintenance/windows_jobs.py` | `hive-mindd` | **THIN_WRAPPER** | D010 | D014 |
| `scripts/setup/register-windows-runtime.ps1` | 13 | wrapper fino que delega para `hive_mind.cli service windows-runtime` | `src/hive_mind/maintenance/windows_runtime.py` | `hive-mindd` | **THIN_WRAPPER** | D010 | D014 |
| `scripts/setup/install-capture-hooks.py` | — | instalação de captura (outbox deprecada) | script | `hive_mind.agents` | **TO_REMOVE** | D009-R5 | D014 |
| `scripts/setup/backup-install-state.ps1` | 77 | snapshot de estado de instalação | script | `hive-mind install` | LEGACY_OWNER | D011 | D014 |
| `scripts/setup/fullstack-readiness.ps1` | 77 | shim PowerShell de compatibilidade que delega o readiness para o owner Python nativo | `src/hive_mind/install/fullstack_readiness.py` | `hive-mindd` readiness | THIN_WRAPPER | D010 | D014 |
| `scripts/setup/vault_enforcement.py` | Python | ACL do vault | script | `hive_mind.install.vault` | NATIVE | D011 | D014 |
| `scripts/maintenance/install_backup_tasks.py` | Python | agendamento de backup | script | Task Scheduler | NATIVE | D010 | D014 |
| `scripts/maintenance/backup-audit-daily.ps1` | 15 | auditoria de backup (dormente) | script | `hive-mind backup audit` | TO_REMOVE | D009-R6 | D014 |
| `scripts/maintenance/backup-prune-weekly.ps1` | 19 | poda de backup (dormente) | script | `hive-mind backup prune` | TO_REMOVE | D009-R6 | D014 |

## Já portados para o pacote nativo

| Componente | Destino nativo | Estado | Delivery |
|---|---|---|---|
| registro MCP (`register-mcp.ps1` 456→55 L, `.sh` 444→50 L) | `hive_mind.agents` + `hive_mind.agents.compat` | **NATIVE** (ambos os scripts são THIN_WRAPPER) | D009-R6 ✅ |
| `ProjectIdentityResolver` | `hive_mind.projects.identity` | **NATIVE** (legado é SHIM) | D003-R1 ✅ |
| canary multiagente | `hive_mind.validation` | **NATIVE** (legado é SHIM, 225→28 L) | D004-R1 ✅ |
| motor de backup | `hive_mind.maintenance.backup` | **NATIVE** (legado é SHIM, 175→45 L) | D008-R1B ✅ |
| detecção de providers | `hive_mind.agents.detect` | **NATIVE** | D009 ✅ |
| merge MCP JSON | `hive_mind.agents.mcp_config` | **NATIVE** | D009 ✅ |
| writer TOML (Codex) | `hive_mind.agents.toml_config` | **NATIVE** | D009-R4 ✅ |
| manifesto declarativo | `hive_mind.daemon.manifest` | **NATIVE** | D006 ✅ |
| catálogo/manifesto operacional de serviços | `hive_mind.maintenance.runtime_services` | **NATIVE** (shim legado em `scripts/setup/install_services.py`) | D006-R1 ✅ |
| lock, shadow supervisor, HTTP, control socket, managed supervisor, scheduler | `hive_mind.daemon.*` | **NATIVE** (sem cutover) | D007, D008 ✅ |

## Scripts sem lógica de produto (lançadores)

Já são efetivamente thin — invocam um processo e repassam. Viram wrappers
formais ou são removidos junto do respectivo componente.

`scripts/services/{claude-mem-local,mcp-server,neural-memory-local,start-claude-mem,start-claude-mem-mcp,start-rtk,start-watcher,claude-mem-watchdog}.ps1`,
`scripts/capture/{claude-mem-hook,copilot-wrapper}.ps1`,
`scripts/graph/{build-graph,serve-graph}.ps1`,
`scripts/maintenance/{integrations-update,sync-diario}.ps1`,
`scripts/setup/{register-mcp.ps1,register-mcp.sh}` (D009-R6),
`scripts/utils/recover.ps1`, `scripts/claude-mem-local.ps1`,
`scripts/setup/{setup-brain.ps1,start-windows-supervisor.ps1,apply-hidden-supervisor-task.ps1}`,
`scripts/setup/start-windows-supervisor-hidden.vbs`,
`install.bat`, `setup-brain.bat`, `scripts/setup/setup-brain.bat`,
`integrations/claude-mem-plugins/install.ps1`
→ **THIN_WRAPPER** · remoção D014.

## Node

| Arquivo | Função | Estado | Delivery |
|---|---|---|---|
| `npm/lib/supervisor.js` (279 L) | wrapper Node do daemon gerenciado | **PORT_IN_PROGRESS** | D010 |
| `npm/lib/services.js` (72 L) | wrapper de dispatch derivado do manifest | **THIN_WRAPPER** | D006-R1 |
| `npm/lib/{init,platform,wizard}.js` | bootstrap npm | THIN_WRAPPER | D014 |
| `npm/bin/hive-mind.js` | entry npm | THIN_WRAPPER | D014 |

## Task Scheduler (owners nativos declarativos)

| Tarefa | Trigger | Owner atual | Estado |
|---|---|---|---|
| `HiveMind-Supervisor` | AtLogon | `src/hive_mind/maintenance/windows_runtime.py` | **PORT_IN_PROGRESS** |
| `HiveMind-PostRebootValidation` | AtLogon | `src/hive_mind/maintenance/windows_runtime.py` | **NATIVE** |
| `HiveMind-DreamCycle` | Daily | `src/hive_mind/maintenance/windows_jobs.py` | **NATIVE** |
| `HiveMind-ClaudeMemBridge` | Daily | `src/hive_mind/maintenance/windows_jobs.py` | **NATIVE** |
| `HiveMind-KnowledgeHealth` | Daily | `src/hive_mind/maintenance/windows_jobs.py` | **NATIVE** |
| `HiveMind-Backup` | Daily | `src/hive_mind/maintenance/windows_jobs.py` | **NATIVE** (`hive-mind.exe backup run --apply`; ver [backup.md](../backup.md)) |

**WinSW**: não encontrado no repositório nem em uso — `EXTERNAL_COMPONENT`,
não aplicável nesta instalação.

## Docker

`falkordb`, `milvus`, `ragflow` (+ mysql/es01/redis/minio) →
`EXTERNAL_COMPONENT`. Orquestrados por compose, com
`restart: unless-stopped` (DR-001). O daemon apenas declara e observa.

## Resumo do gate D010-G0

| Categoria | Contagem |
|---|---:|
| NATIVE (portado) | 9 componentes |
| LEGACY_OWNER (bloqueiam D010) | **0** |
| TO_REMOVE | 3 |
| THIN_WRAPPER | ~26 (inclui `install.ps1`, `scripts/setup/install_services.py`, `npm/lib/services.js`, os 3 registradores e D009-R6) |
| EXTERNAL_COMPONENT | Docker, WinSW |
| **UNKNOWN** | **0** |

D010 permanece **BLOCKED** enquanto houver `LEGACY_OWNER` com catálogo,
supervisor ou scheduler próprios.
