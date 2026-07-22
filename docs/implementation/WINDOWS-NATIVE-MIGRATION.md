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
| `install.ps1` | 568 | instalação completa, Docker, MCP, perfis | script | `hive-mind install` | **LEGACY_OWNER** | D011 | D014 |
| `scripts/setup/register-mcp.ps1` | 456 | detecção, paths, merge JSON/TOML, prompts | script | `hive_mind.agents` | **LEGACY_OWNER** | D009-R6 | D014 |
| `scripts/setup/register-mcp.sh` | 439 | idem (POSIX) | script | `hive_mind.agents` | **LEGACY_OWNER** | D009-R6 | D014 |
| `scripts/lib/HiveMind.Windows.psm1` | 388 | utilidades Windows compartilhadas | script | `hive_mind.platform` | **LEGACY_OWNER** | D011 | D014 |
| `scripts/setup/bootstrap-prerequisites.ps1` | 178 | pré-requisitos, Docker, downloads | script | `hive-mind install` | **LEGACY_OWNER** | D011 | D014 |
| `scripts/setup/install_services.py` | 1232 | **catálogo de serviços** (`unit_definitions`) | script | `config/runtime.yaml` | **LEGACY_OWNER** | D006-R1 | D014 |
| `npm/lib/services.js` | 74 | **catálogo de serviços** (Node) | Node | `config/runtime.yaml` | **LEGACY_OWNER** | D006-R1 | D014 |
| `npm/lib/supervisor.js` | 438 | **supervisor concorrente** | Node | `hive-mindd` | **LEGACY_OWNER** | D010 | D014 |
| `scripts/setup/register-windows-jobs.ps1` | 17 | **catálogo de jobs** + Task Scheduler | script | `hive-mindd` | **LEGACY_OWNER** | D010 | D014 |
| `scripts/setup/register-windows-runtime.ps1` | 14 | **catálogo de tarefas** de runtime | script | `hive-mindd` | **LEGACY_OWNER** | D010 | D014 |
| `scripts/setup/install-capture-hooks.py` | — | instalação de captura (outbox deprecada) | script | `hive_mind.agents` | **TO_REMOVE** | D009-R5 | D014 |
| `scripts/setup/backup-install-state.ps1` | 77 | snapshot de estado de instalação | script | `hive-mind install` | LEGACY_OWNER | D011 | D014 |
| `scripts/setup/fullstack-readiness.ps1` | 77 | readiness da stack | script | `hive-mindd` readiness | LEGACY_OWNER | D010 | D014 |
| `scripts/setup/setup-vault-enforcement.ps1` | 101 | ACL do vault | script | `hive_mind.install.vault` | LEGACY_OWNER | D011 | D014 |
| `scripts/maintenance/install-backup-cron.ps1` | 26 | agendamento de backup | script | `hive-mindd` scheduler | LEGACY_OWNER | D010 | D014 |
| `scripts/maintenance/backup-audit-daily.ps1` | 15 | auditoria de backup (dormente) | script | `hive-mind backup audit` | TO_REMOVE | D009-R6 | D014 |
| `scripts/maintenance/backup-prune-weekly.ps1` | 19 | poda de backup (dormente) | script | `hive-mind backup prune` | TO_REMOVE | D009-R6 | D014 |

## Já portados para o pacote nativo

| Componente | Destino nativo | Estado | Delivery |
|---|---|---|---|
| `ProjectIdentityResolver` | `hive_mind.projects.identity` | **NATIVE** (legado é SHIM) | D003-R1 ✅ |
| canary multiagente | `hive_mind.validation` | **NATIVE** (legado é SHIM, 225→28 L) | D004-R1 ✅ |
| motor de backup | `hive_mind.maintenance.backup` | **NATIVE** (legado é SHIM, 175→45 L) | D008-R1B ✅ |
| detecção de providers | `hive_mind.agents.detect` | **NATIVE** | D009 ✅ |
| merge MCP JSON | `hive_mind.agents.mcp_config` | **NATIVE** | D009 ✅ |
| writer TOML (Codex) | `hive_mind.agents.toml_config` | **NATIVE** | D009-R4 ✅ |
| manifesto declarativo | `hive_mind.daemon.manifest` | **NATIVE** | D006 ✅ |
| lock, shadow supervisor, HTTP, control socket, managed supervisor, scheduler | `hive_mind.daemon.*` | **NATIVE** (sem cutover) | D007, D008 ✅ |

## Scripts sem lógica de produto (lançadores)

Já são efetivamente thin — invocam um processo e repassam. Viram wrappers
formais ou são removidos junto do respectivo componente.

`scripts/services/{claude-mem-local,mcp-server,neural-memory-local,start-claude-mem,start-claude-mem-mcp,start-rtk,start-watcher,claude-mem-watchdog}.ps1`,
`scripts/capture/{claude-mem-hook,copilot-wrapper}.ps1`,
`scripts/graph/{build-graph,serve-graph}.ps1`,
`scripts/maintenance/{integrations-update,sync-diario}.ps1`,
`scripts/utils/recover.ps1`, `scripts/claude-mem-local.ps1`,
`scripts/setup/{setup-brain.ps1,start-windows-supervisor.ps1,apply-hidden-supervisor-task.ps1}`,
`scripts/setup/start-windows-supervisor-hidden.vbs`,
`install.bat`, `setup-brain.bat`, `scripts/setup/setup-brain.bat`,
`integrations/claude-mem-plugins/install.ps1`
→ **THIN_WRAPPER** · remoção D014.

## Node

| Arquivo | Função | Estado | Delivery |
|---|---|---|---|
| `npm/lib/supervisor.js` (438 L) | supervisor concorrente | **LEGACY_OWNER** | D010 |
| `npm/lib/services.js` (74 L) | catálogo de serviços | **LEGACY_OWNER** | D006-R1 |
| `npm/lib/{init,platform,wizard}.js` | bootstrap npm | THIN_WRAPPER | D014 |
| `npm/bin/hive-mind.js` | entry npm | THIN_WRAPPER | D014 |

## Task Scheduler (owners legados ativos)

| Tarefa | Trigger | Owner futuro | Estado |
|---|---|---|---|
| `HiveMind-Supervisor` | AtLogon | `hive-mindd` | **LEGACY_OWNER** |
| `HiveMind-PostRebootValidation` | AtLogon | `hive-mindd` post-reboot | **LEGACY_OWNER** |
| `HiveMind-DreamCycle` | Daily | `hive-mindd` scheduler | **LEGACY_OWNER** |
| `HiveMind-ClaudeMemBridge` | Daily | `hive-mindd` scheduler | **LEGACY_OWNER** |
| `HiveMind-KnowledgeHealth` | Daily | `hive-mindd` scheduler | **LEGACY_OWNER** |
| `HiveMind-Backup` | Daily | `hive-mindd` scheduler | **LEGACY_OWNER** (roda auditoria, não backup — ver [backup.md](../backup.md)) |

**WinSW**: não encontrado no repositório nem em uso — `EXTERNAL_COMPONENT`,
não aplicável nesta instalação.

## Docker

`falkordb`, `milvus`, `ragflow` (+ mysql/es01/redis/minio) →
`EXTERNAL_COMPONENT`. Orquestrados por compose, com
`restart: unless-stopped` (DR-001). O daemon apenas declara e observa.

## Resumo do gate D010-G0

| Categoria | Contagem |
|---|---:|
| NATIVE (portado) | 8 componentes |
| LEGACY_OWNER (bloqueiam D010) | **18** |
| TO_REMOVE | 3 |
| THIN_WRAPPER | ~22 |
| EXTERNAL_COMPONENT | Docker, WinSW |
| **UNKNOWN** | **0** |

D010 permanece **BLOCKED** enquanto houver `LEGACY_OWNER` com catálogo,
supervisor ou scheduler próprios.
