# [OBSOLETO] Redesenho do Control Plane v1 (HEAD errado)

> **Este arquivo esta OBSOLETO.**
> Foi produzido a partir de D:\\Hive-Mind @ 3d362c6 (HEAD errado).
> Substituido por:
> ackups/worktrees/hive-mind-windows-zero-install/specs/control-plane-redesign-v2.md
> Produzido a partir de codex/windows-zero-install-impl @ d246f0c6 (worktree correto).
>
> Mantido apenas para rastreabilidade. NAO usar.

---

# Hive-Mind â€” Redesenho do Control Plane

> Status: **DRAFT â€” aguardando aprovacao antes de qualquer implementacao**
> Branch preservado: codex/windows-zero-install-impl @ d246f0c6
> Gates de instalacao limpa / reboot: **PAUSADOS** ate aprovacao.

---


## 1. Mapa de responsabilidades atual

| Camada | Onde vive hoje | O que faz | Quem consome |
|---|---|---|---|
| **Provisionamento Python** | install.sh, install.ps1, pyproject.toml (tool.uv.package=false) | uv sync, valida .venv, expoe hive-mind somente via npm (ver secao 4) | Toda a runtime |
| **Bootstrap de pre-requisitos** | scripts/setup/bootstrap-prerequisites.ps1, install.sh passos 0-1 | winget/apt/brew; valida Node, Bun, Ollama, Docker; setup-brain | Instaladores |
| **Materializacao do vault** | install.sh (passo 3), install.ps1 (Step Vault materialization), scripts/setup/setup_umc.py, 	emplates/vault/ | Copia templates para cerebro/, cria ~30 diretorios, inicializa hive_mind.db | Todos os jobs |
| **Configuracao de perfis/modelos** | scripts/setup/setup-brain.{ps1,sh}, config/profiles/*, core/model_registry.py, core/model_gateway.py | Aplica contrato de perfil em .env; resolve LLM por role | Dreamer, Graphify, Vision |
| **Componentes editaveis** | install.sh passo 1 (components.py bootstrap), config/components.lock.json | Pina commits de integrations/* antes do uv sync | uv sync |
| **Registro MCP** | scripts/setup/register-mcp.{ps1,sh} (~410 linhas cada), npm/bin/hive-mind.js (mcp register) | Detecta agente -> injeta sinapse-memory em .mcp.json/config.toml/VSCode/Cursor | Todos os agents |
| **Definicao de servicos** | scripts/setup/install_services.py (unit_definitions+service_specs+launchd_definitions+manifest) **+** systemd, **+** Task Scheduler, **+** Node supervisor | Gera 3 representacoes da mesma lista | systemd, launchd, supervisor |
| **Supervisor de processo** | 
pm/lib/supervisor.js (Node) - apenas Windows / HIVE_MIND_SUPERVISOR=1 | Reinicio, backoff, healthcheck, circuit-breaker, state.json | Windows |
| **Wrapper de entry-point** | scripts/services/{start-watcher,start-claude-mem,claude-mem-local,start-rtk,start-claude-mem-mcp,mcp-server,claude-mem-watchdog,neural-memory-local}.{ps1,sh} | Exporta env e exec python -m ... / bun <entrypoint> | Unit systemd + Task Scheduler + supervisor Node |
| **Scheduler periodico** | install_services.py (systemd timers), scripts/setup/register-windows-jobs.ps1, scripts/setup/register-windows-runtime.ps1, scripts/maintenance/install-backup-cron.{ps1,sh} (crontab) | Dream, daily, weekly, monthly, yearly, backup, audit, prune, review, conflicts, drift, health, alert, decisions, projects, work, patterns, topics, bridge, capture-tailer | Toda a cadencia do brain |
| **Auto-start de SO** | scripts/setup/start-windows-supervisor.ps1 (Task AtLogOn), scripts/setup/apply-hidden-supervisor-task.ps1 (VBS hidden), systemd WantedBy=default.target | Garante que o supervisor rode apos login/reboot | Runtime |
| **Orquestracao de Docker** | docker-compose.falkordb.yml (1 stack), install_services.py (_start_falkordb) | Sobe FalkorDB; manual para Milvus/RAGFlow/MySQL/Elasticsearch/Redis/MinIO/Langfuse | local-full |
| **Validacao pos-reboot** | scripts/health/validate_after_reboot.py, unit sinapse-post-reboot-validation.service | Le logs/pre-reboot.json; dispara depois de systemctl restart | Linux |
| **Pos-instalacao / repair** | scripts/utils/recover.{ps1,sh}, 	ests/install/run-clean-install-test{,-local}.{ps1,sh} | Limpa caches, reindexa, re-sync, refaz service units | Instaladores |
| **Vault write enforcement** | scripts/setup/setup-vault-enforcement.{ps1,sh} (chown + systemd drop-in) | Restringe escrita em cerebro/ a um usuario servico; 90-intake/ e a unica excecao | Hosts compartilhados |
| **CLI do usuario final** | 
pm/bin/hive-mind.js (Node) - comandos init, doctor, services, mcp, update | Unico ponto de entrada humano | Operador |

Pontos criticos do mapa:
1. Tres representacoes de servico (unit_definitions, service_specs, launchd_definitions + manifesto JSON) geradas a partir de um unico arquivo Python de 1.235 linhas, mas com drift ja enraizado (ex.: service_specs nao conhece os timers; unit_definitions e a unica fonte de cadencias).
2. Quatro pilhas de scheduler paralelas: systemd user timers, Task Scheduler, crontab de backup, supervisor Node (readiness loop) - sem unicidade de source-of-truth.
3. Wrapper sh/ps1 por servico: cada entry-point tem um par redundante cuja unica funcao real e setar env e exec python ....
4. CLI unico do usuario e Node, mas tudo o que ele faz (registrar MCP, validar runtime, levantar servicos) ja e Python - Node vira um bootstrap desnecessario.


## 2. Logica existente em Bash (escopo control plane)

Total: 1.201 linhas em `install.sh` mais 26 wrappers/service/utility scripts.

| Arquivo | LOC | Responsabilidade real | Destino no desenho novo |
|---|---:|---|---|
| `install.sh` (top-level) | 1201 | 12 passos: deps / uv sync / Graphify source / vault materialization / component bootstrap / MCP register / claude-mem native / RTK build / services install / cron / cron sinapse-memory / Dreamer LLM / agents | Thin: detectar uv, `uv pip install -e .`, `hive-mind install`, registrar `hive-mindd` no SO. |
| `scripts/services/start-watcher.sh` | 21 | `exec .venv/bin/python -m graphify watch` | Eliminar; daemon chama `python -m graphify watch` direto. |
| `scripts/services/start-claude-mem.sh` | 6 | Wrapper obsoleto -> redireciona para mcp-server.sh | Eliminar. |
| `scripts/services/start-claude-mem-mcp.sh` | 16 | `exec sinapse-mcp.py` | Eliminar. |
| `scripts/services/claude-mem-local.sh` | 55 | `exec worker-service.cjs` (Node) | Manter como entry-point externo (worker claude-mem e Node); daemon sobe via `command: [...]`. |
| `scripts/services/start-rtk.sh` | 149 | Compila rtk Rust, configura por agent | Reduzir: daemon nao compila rtk; isso e responsabilidade do `hive-mind install`. |
| `scripts/services/mcp-server.sh` | 33 | Wrapper stdio de `sinapse-mcp.py` | Eliminar. |
| `scripts/services/claude-mem-watchdog.sh` | 23 | Tail de log + restart | Substituir por healthcheck + circuit-breaker do daemon. |
| `scripts/services/neural-memory-local.sh` | 10 | `exec .venv/bin/nmem start` | Eliminar. |
| `scripts/capture/copilot-wrapper.sh` | 144 | Captura output do Copilot CLI | Fora do control plane. NAO mexer. |
| `scripts/capture/claude-mem-hook.sh` | 63 | Hook pre/post Claude Code -> claude-mem | Idem. |
| `scripts/graph/build-graph.sh` | 117 | `graphify build` + export Obsidian | `hive-mind graph build`. |
| `scripts/graph/serve-graph.sh` | 10 | Wrapper de `graphify serve` | `hive-mind graph serve`. |
| `scripts/maintenance/install-backup-cron.sh` | 29 | Adiciona 2 entradas no crontab | Substituir por 2 jobs declarados em `runtime.yaml`. |
| `scripts/maintenance/backup-audit-daily.sh` | 35 | `python backup_audit.py` | Job `backup-audit` no manifesto. |
| `scripts/maintenance/backup-prune-weekly.sh` | 43 | `python backup_prune.py` | Job `backup-prune`. |
| `scripts/maintenance/integrations-update.sh` | 144 | git pull + reinstall nas `integrations/*` | `hive-mind update` (CLI). |
| `scripts/maintenance/sync-diario.sh` | 23 | rsync -> `cerebelo/diario` | Capturado em `capture/syncthing_watcher.py` no Windows. Cross-plataforma via daemon. |
| `scripts/setup/register-mcp.sh` | 409 | Detecta agent + injeta MCP em 12 formatos | `hive-mind mcp register --agent <name>`. |
| `scripts/setup/setup-brain.sh` | 5 | Wrapper de `python setup_brain.py` | `hive-mind brain setup`. |
| `scripts/setup/setup-vault-enforcement.sh` | 172 | chown + systemd drop-in | `hive-mind install --vault-enforcement`. |
| `scripts/utils/recover.sh` | 35 | `python recover.py` | `hive-mind doctor --repair`. |
| `tests/install/run-clean-install-test.sh` | 72 | CI runner de install fresco | `hive-mind install --test` (Python). Shell thin. |
| `tests/install/run-clean-install-test-local.sh` | 106 | Idem (sem network) | Idem. |
| `tests/run_all.sh` | 36 | Driver pytest | Mantem shell como thin driver. |
| `tests/smoke/test_smoke.sh` | 81 | Smoke tests | Mantem. |
| `tests/run_real_knowledge.sh` | 81 | Real knowledge suite | Mantem. |

Carga cognitiva estimada: ~85% substituivel por `hive-mind` CLI, ~15% (capture/graph wrappers) que viram sub-comandos.

## 3. Logica existente em PowerShell (escopo control plane)

Total: 473 linhas em `install.ps1` mais 21 scripts. O modulo `scripts/lib/HiveMind.Windows.psm1` (290 LOC) e a base.

| Arquivo | LOC | Responsabilidade real | Destino no desenho novo |
|---|---:|---|---|
| `install.ps1` (top-level) | 473 | 18 Steps: venv check / venv repair / profiles / setup-brain / prereq bootstrap / uv sync / Components bootstrap / Graphify verify / Vault materialize / Build-graph / register-mcp / install_services manifest / Node supervisor restart/status / register-windows-jobs / register-windows-runtime / tests | Thin: detectar uv, `uv pip install -e .`, `hive-mind install`, registrar `hive-mindd` (WinSW), `hive-mind doctor`. |
| `scripts/lib/HiveMind.Windows.psm1` | 290 | `Get-HiveMindRoot`, `Get-HiveMindPython`, `Test-HiveMindPythonVersion`, `Repair-HiveMindPythonRuntime`, `Invoke-HiveMindPython`, `Invoke-HiveMindCommand`, `Read-HiveMindDotEnv`, `Apply-HiveMindProfileContract`, `New-HiveMindApiKey`, `Ensure-HiveMindDirectory`, `Remove-HiveMindOldFiles` | Portar 1:1 para `hive_mind.platform.windows` (mesma funcao, mesma semantica, com testes pytest). |
| `scripts/setup/bootstrap-prerequisites.ps1` | 161 | Lista de prereqs (winget id), invoke winget, restart-handling | `hive_mind.install.prereqs` (Python). |
| `scripts/setup/backup-install-state.ps1` | 72 | Salva `backups/install-state/*.json` em caso de restart-required | `hive_mind.install.state`. |
| `scripts/setup/setup-brain.ps1` | 14 | `Invoke-HiveMindPython scripts/setup/setup_brain.py` | `hive-mind brain setup`. |
| `scripts/setup/setup-vault-enforcement.ps1` | 90 | chown + ACL NTFS | `hive-mind install --vault-enforcement`. |
| `scripts/setup/register-mcp.ps1` | 410 | Duplica a logica do `register-mcp.sh` para Windows | Unificar em `hive_mind.agents.register` (Python). |
| `scripts/setup/register-windows-jobs.ps1` | 18 | Task Scheduler: 4 jobs diarios (dream, bridge, audit, backup) | Substituir por jobs declarados em `runtime.yaml`. |
| `scripts/setup/register-windows-runtime.ps1` | 15 | Task Scheduler: 2 tasks AtLogOn (supervisor + post-reboot) | Substituir por **um unico** WinSW service. |
| `scripts/setup/start-windows-supervisor.ps1` | 7 | `node npm/lib/supervisor.js __daemon` | Eliminar com o supervisor Node. |
| `scripts/setup/apply-hidden-supervisor-task.ps1` | 5 | Reaplica task hidden (VBS) | Eliminar. |
| `scripts/maintenance/install-backup-cron.ps1` | 23 | Task Scheduler: audit (03:10) + prune (Sun 03:30) | Jobs do manifesto. |
| `scripts/services/*.ps1` (14 arquivos) | ~20 cada | Wrappers de `python -m ...` / `worker-service.cjs` | **Eliminar todos**; daemon sobe direto. |
| `scripts/graph/build-graph.ps1` | 45 | `python -m graphify build` | `hive-mind graph build`. |
| `scripts/graph/serve-graph.ps1` | 12 | `python -m graphify serve` | `hive-mind graph serve`. |
| `scripts/capture/*.ps1` | 19+23 | Hook wrappers | Mantem (capture). |
| `scripts/utils/recover.ps1` | 16 | `python recover.py` | `hive-mind doctor --repair`. |
| `tests/install/test_windows_bootstrap.ps1` | 65 | Driver de bootstrap | Substituir por pytest. |
| `tests/run_all.ps1` / `tests/smoke/test_smoke.ps1` / `tests/run_real_knowledge.ps1` | 17+30+9 | Driver de testes | Mantem shell como thin driver. |

## 4. Logica existente em Node (escopo control plane)

Total: ~570 LOC em `npm/`. Apenas 1 arquivo de runtime, `supervisor.js` (349 LOC), tem logica de servico real.

| Arquivo | LOC | Responsabilidade real | Destino no desenho novo |
|---|---:|---|---|
| `npm/lib/supervisor.js` | 349 | `loadManifest()`, `selectServices()`, `topologicalServices()`, `probeReadiness()`, `waitForReadiness()`, `daemon()` loop, `start`/`stop`/`status` (state.json, pidFiles, circuit-breaker) | **Portar para `hive_mind.daemon.supervisor`** (Python). Algoritmo preservado com 1 teste. |
| `npm/lib/services.js` | 62 | `SYSTEMD_UNITS` (lista hardcoded de 6 servicos), `backend()`, `dispatch(start/stop/status/restart)`, `launchd()`, `systemd()` | **Eliminar**: lista hardcoded vira leitura do manifesto; backends viram implementacoes em `hive_mind.platform.{windows,linux,darwin}`. |
| `npm/lib/platform.js` | 47 | `isWSL`, `wslAvailableFromWindows`, `homeDir`, `which` | Portar para `hive_mind.platform.detect` (e `shutil.which`). |
| `npm/bin/hive-mind.js` | 121 | CLI: `init`, `init wizard`, `doctor`, `services start/stop/status/restart`, `mcp register`, `update`, `version`, `help` | Substituir pelo entry-point `hive_mind.cli:main`. |
| `npm/lib/init.js` | 98 | `init()` -> `uv sync` + `node npm/lib/supervisor.js start` | Substituir por `hive_mind.install.install`. |
| `npm/lib/wizard.js` | 35 | Wizard interativo | `hive-mind init --wizard` (Python). |
| `npm/test/supervisor.test.js` | 69 | Testa `topologicalServices`, `restartDelayMs`, `probeReadiness` | Portar para `tests/unit/test_daemon_supervisor.py`. |
| `npm/package.json` | n/a | `bin: hive-mind`, `engines: node>=18` | Remover; mover para `pyproject.toml [project.scripts]`. |

NPM deixa de ser dependencia obrigatoria. Pacote `@hive-mind/installer` pode sobreviver como opcional para bootstrap em ambientes sem Python, mas a politica e: `npm` so existe para instalar a CLI Python; depois disso, ele some.


## 5. Logica existente em `install_services.py`

Arquivo unico: 1.235 LOC, dita o que roda em qualquer S.O. Hoje gera **3 representacoes de servico** e um manifesto JSON, e ainda e o ponto de entrada para Docker, screenpipe, claude-mem plugin e shell de validacao.

| Funcao | LOC | O que faz | Destino |
|---|---:|---|---|
| `unit_definitions()` | 620 | Template de unit systemd por servico (env, ExecStart, Restart, Install) | `hive_mind.platform.linux.systemd_unit(spec)`. So gera a unit, nao instala. |
| `_enrich_service_specs()` | 60 | Adiciona `command_variants` (windows/linux), `contracts` (deps+order+readiness), specs de `ollama/docker-desktop/milvus/ragflow/falkordb/syncthing-watcher` | `hive_mind.daemon.manifest.enrich(specs)`. |
| `service_specs()` | 138 | Lista de specs daemon (claude-mem, sqlite-vec, graphify-watch, api, mcp-http, otel, capture-realtime) | `hive_mind.daemon.manifest.service_specs()`. |
| `_launchd_program()` | 11 | Embrulha spec com sh para carregar .env | `hive_mind.platform.darwin._shim_env_file()`. |
| `launchd_definitions()` | 27 | Gera plist de cada spec | `hive_mind.platform.darwin.plist_for(spec)`. |
| `launchd_install()` | 28 | launchctl load/unload | `hive_mind.platform.darwin.install()`. |
| `manifest()` | 11 | Manifesto JSON v2 (root, log_dir, claude_mem_plugin_available, services) | `hive_mind.daemon.manifest.emit()`. |
| `_install_screenpipe()` | 47 | `npm install -g @screenpipe/cli-linux-x64` (opcional) | `hive_mind.install.optional_components.screenpipe()`. |
| `_start_falkordb()` | 27 | `docker compose -f docker-compose.falkordb.yml up -d` | `hive_mind.docker.up("falkordb")`. |
| `_configure_claude_mem_settings()` | 30 | Patch em `~/.claude-mem/settings.json` (CLAUDE_MEM_EXCLUDED_PROJECTS) | `hive_mind.agents.claude_mem.settings()`. |
| `validate_runtime()` | 11 | Verifica .venv/bin/python, .tools/bin/bun, hive_mind.db | `hive_mind.install.validate_runtime()`. |
| `claude_mem_plugin_path()` | 19 | Resolve caminho do plugin thedotmack no ~/.claude ou ~/.codex | `hive_mind.agents.claude_mem.resolve()`. |
| `claude_mem_plugin_available()` | 3 | Bool wrapper | Idem. |
| `api_enabled()` | 10 | Le `HIVE_MIND_API_KEY=` do .env | `hive_mind.config.api_enabled()`. |
| `install()` | 95 | systemd enable/restart + idempotencia + screenpipe + falkordb | `hive_mind.platform.linux.install()`. |
| `check()` | 9 | Drift check de units | `hive_mind.platform.linux.check()`. |
| `arm_post_reboot()` | 24 | Habilita `sinapse-post-reboot-validation.service` | `hive_mind.platform.linux.arm_post_reboot()`. |
| `main()` | 16 | argparse (install/check/arm-post-reboot/manifest/launchd) | `hive_mind.cli.main()` (sub-comandos). |

Codigo de referencia: **algoritmo de `selectServices` / `topologicalServices` / `probeReadiness` / `waitForReadiness` / `restartDelayMs`** em `npm/lib/supervisor.js` linhas 60-200 deve virar `hive_mind.daemon.supervisor` em Python, com **as mesmas invariantes** (4.5 testes em `test/supervisor.test.js`).

## 6. Duplicacoes detectadas

| # | Onde | O que duplica | Impacto |
|---:|---|---|---|
| 1 | `unit_definitions()` (systemd) vs `service_specs()` (neutro) | A mesma lista de 7 servicos (claude-mem, sqlite-vec, graphify-watch, api, mcp-http, otel, capture-realtime) aparece 2x, com `command`/`env` ligeiramente diferentes. `test_service_backends.py::test_specs_consistent_with_systemd_units` ja trava a consistencia. | Drift latente: adicionar um servico exige mexer em 2 templates. |
| 2 | `scripts/services/{start-watcher,start-claude-mem,start-claude-mem-mcp,mcp-server,neural-memory-local,claude-mem-watchdog}.{sh,ps1}` | Cada par sh/ps1 faz: set PATH, set SINAPSE_HOME, `exec python -m ...` | ~200 LOC de wrappers sem logica. |
| 3 | `scripts/setup/register-mcp.{sh,ps1}` | 410 + 409 LOC com a **mesma logica** (parse args, detecta 12 agentes, injeta em 5 formatos JSON + 1 TOML) | Um bugfix em um lado nao chega no outro. Ja tem teste (`tests/unit/test_register_mcp.py`). |
| 4 | `scripts/setup/install-backup-cron.{sh,ps1}` | Cron vs Task Scheduler para os mesmos 2 jobs (audit diario 03:10, prune domingo 03:30) | Drift em schedule/horario. |
| 5 | `scripts/setup/register-windows-jobs.ps1` (Task Scheduler) vs `install_services.py` (systemd timers) | 4 jobs diarios no Windows, 12+ timers no Linux, **sem manifesto comum** | Job `dream_cycle` no Windows 02:00; no Linux 03:00. Nao e mesma cadencia nem mesmo conceito. |
| 6 | `scripts/setup/setup-brain.{sh,ps1}` | Wrapper de 5-14 linhas chamando `python setup_brain.py` | 0 logica; pura indirecao. |
| 7 | `install.sh` (passos 0-1) vs `install.ps1` (Steps venv check/repair) vs `bootstrap-prerequisites.ps1` | Validacao de uv, Python 3.12, .venv, winget id, Ollama version | Cada plataforma tem sua lista. Triplicada. |
| 8 | `npm/lib/services.js` (lista hardcoded de 6 servicos) vs `install_services.py::service_specs()` (lista completa) | Lista do Node supervisor so tem 6 itens; specs tem 7 daemon + 6 external. Node ja roda com subset errado. | **Bug latente** quando um servico novo e adicionado. |
| 9 | `install_services.py::launchd_definitions()` e o **unico** gerador de plist launchd (nao ha `launchd_install` automatico no install.sh — install.sh so chama `manifest` e nao faz launchctl). | macOS install e manual. | `hive-mind install` no macOS deve chamar launchctl load. |
| 10 | `scripts/utils/recover.{ps1,sh}` (16 + 35 LOC) | Wrapper do mesmo `recover.py` | 0 logica propria. |

Total estimado de LOC duplicado: **~1.700** (12-15% do `scripts/` e 100% do `npm/lib/services.js`).

## 7. Codigo que sera **reutilizado** (move-and-keep)

| Codigo | Onde | Reuso pretendido |
|---|---|---|
| `scripts/setup/install_services.py::unit_definitions()` | raiz | Gerar `~/.config/systemd/user/*.service` (somente Linux). |
| `scripts/setup/install_services.py::service_specs()` | raiz | Lista canonica de servicos daemon. |
| `scripts/setup/install_services.py::launchd_definitions()` | raiz | Plist generation. |
| `scripts/setup/install_services.py::manifest()` | raiz | Saida para qualquer supervisor. |
| `npm/lib/supervisor.js::{topologicalServices,probeReadiness,waitForReadiness,restartDelayMs,canRestart}` | `npm/` | Algoritmo de readiness + backoff (portar para Python com mesmas invariantes). |
| `scripts/lib/HiveMind.Windows.psm1` | `scripts/lib/` | Portar 1:1 para `hive_mind.platform.windows` (mesmo comportamento, mesmos nomes em minusculo). |
| `scripts/setup/register-mcp.{sh,ps1}` (parse, detect, write) | `scripts/setup/` | Reescrever como `hive_mind.agents.register` (Python, uma implementacao para 3 SOs). |
| `scripts/capture/copilot-wrapper.sh` + `copilot-wrapper.ps1` | `scripts/capture/` | **NAO mexer** (e feature de capture, nao control plane). |
| `scripts/capture/claude-mem-hook.{sh,ps1}` | `scripts/capture/` | **NAO mexer**. |
| `scripts/health/validate_after_reboot.py` | `scripts/health/` | Job `post-reboot-validation` no manifesto (chamado pelo daemon apos startup). |
| `scripts/dream/{dream_cycle,daily_writer,weekly_synthesizer,monthly_synthesizer,yearly_synthesizer,session_consolidator}.py` | `scripts/dream/` | Sao os **consumidores** do scheduler. **NAO mexer** no codigo, apenas apontar via manifesto. |
| `scripts/knowledge/{decision_promoter,project_synthesizer,pattern_distiller,conflict_detector,drift_detector,work_tracker,review_writer,topic_consolidator}.py` | `scripts/knowledge/` | Idem. |
| `scripts/maintenance/backup_audit.py`, `scripts/maintenance/backup_prune.py` | `scripts/maintenance/` | Idem. |
| `scripts/services/claude_mem_bridge.py` | `scripts/services/` | Job `bridge` no manifesto. |
| `core/llm_client.py`, `core/model_registry.py`, `core/model_gateway.py`, `core/paths.py`, `core/database.py` | `core/` | Continua sendo a base. O daemon importa daqui. |
| `config/sinapse.yaml` (model_gateway, hybrid_search) | `config/` | Continua valido; o daemon le `.env` e `sinapse.yaml` identicamente. |
| `tests/unit/test_service_backends.py` (5 testes) | `tests/unit/` | Continua valido: testa `service_specs`, `unit_definitions`, `launchd_definitions`, `manifest`. **Adaptar imports** quando mover para `src/hive_mind/daemon/manifest.py`. |
| `npm/test/supervisor.test.js` (4 testes) | `npm/test/` | Reescrever como `tests/unit/test_daemon_supervisor.py` com mesmas assercoes. |
| `tests/unit/test_install_services.py` | `tests/unit/` | Continua valido; ajustar imports. |


## 8. Codigo que sera **movido** (sem reescrita)

| De | Para | Razao |
|---|---|---|
| `scripts/setup/install_services.py` | `src/hive_mind/daemon/manifest.py` (specs, units, plists, manifest) | Torna-se parte do pacote instalavel. |
| `scripts/setup/install_services.py` | `src/hive_mind/daemon/cli.py` (sub-comandos install/check/arm-post-reboot/manifest/launchd) | Idem. |
| `scripts/setup/install_services.py` | `src/hive_mind/install/optional.py` (screenpipe, falkordb, claude-mem settings) | Idem. |
| `scripts/setup/install_services.py` | `src/hive_mind/agents/claude_mem.py` (resolve plugin, settings) | Idem. |
| `npm/lib/supervisor.js` | `src/hive_mind/daemon/supervisor.py` (selectServices, topological, probe, wait, restart, circuit-breaker, state.json) | Algoritmo de runtime do SO. |
| `npm/lib/services.js` | `src/hive_mind/platform/{windows,linux,darwin}/__init__.py` (backends) | Cada SO vira um adapter fino. |
| `npm/lib/platform.js` | `src/hive_mind/platform/detect.py` | Detectar S.O. (is_windows, is_macos, is_linux, home_dir, which). |
| `npm/lib/init.js` | `src/hive_mind/install/install.py` | `hive-mind install` chama o que `npm/lib/init.js` chama. |
| `npm/lib/wizard.js` | `src/hive_mind/install/wizard.py` | Wizard em Python (questionary ou inquirer). |
| `npm/bin/hive-mind.js` | `src/hive_mind/cli.py` | CLI canonica. |
| `scripts/lib/HiveMind.Windows.psm1` | `src/hive_mind/platform/windows.py` | Portar funcoes, manter comportamento. |
| `scripts/utils/recover.py` | `src/hive_mind/doctor/repair.py` | Mantem logica, importa do pacote. |
| `scripts/setup/setup-brain.py` | `src/hive_mind/install/brain.py` | `hive-mind brain setup`. |
| `scripts/setup/components.py` | `src/hive_mind/install/components.py` | Pin de commits em `integrations/*`. |
| `scripts/setup/setup_umc.py` | `src/hive_mind/install/umc.py` | Idem. |
| `scripts/setup/verify_wrappers.py` | `src/hive_mind/install/verify.py` | Idem. |
| `scripts/setup/bootstrap-prerequisites.ps1` | `src/hive_mind/install/prereqs.py` | Listar prereqs e instalar (winget/choco/brew). |
| `scripts/setup/setup-vault-enforcement.{ps1,sh}` | `src/hive_mind/install/vault_enforcement.py` | Unificar chown (POSIX) e ACL (NTFS). |
| `scripts/setup/register-mcp.{ps1,sh}` | `src/hive_mind/agents/register.py` | Reescrever em Python; cobre todos os agentes via deteccao. |
| `tests/unit/test_service_backends.py` | `tests/unit/test_daemon_manifest.py` | Ajustar imports. |
| `npm/test/supervisor.test.js` | `tests/unit/test_daemon_supervisor.py` | Reescrever. |
| `tests/install/test_windows_bootstrap.ps1` | `tests/install/test_bootstrap.py` | Substituir por pytest. |
| `tests/install/run-clean-install-test{,-local}.{ps1,sh}` | `tests/install/test_clean_install.py` | Idem. |
| `config/sinapse-agent-prompt.md` | `src/hive_mind/resources/sinapse-agent-prompt.md` (vira package data) | Editado em M1 (ver §11 deste desenho). |
| `config/profiles/*` | `src/hive_mind/resources/profiles/*` (vira package data) | Idem. |
| `config/components.lock.json` | `src/hive_mind/resources/components.lock.json` | Idem. |
| `config/env.roles.example`, `config/model-gateway.env.example`, `config/model-gateway.yaml` | `src/hive_mind/resources/config/*` | Idem. |

## 9. Codigo que sera **removido**

| Arquivo | Razao |
|---|---|
| `npm/bin/hive-mind.js` | Substituido por `hive_mind.cli:main` em `pyproject.toml [project.scripts]`. |
| `npm/lib/{services,init,wizard,platform}.js` | Toda a logica migrou para `src/hive_mind/`. |
| `npm/lib/supervisor.js` | Migrou; testes reescritos. |
| `npm/test/supervisor.test.js` | Migrou. |
| `npm/package.json` | Opcional. Mantem-se so se o usuario quiser bootstrap via npm (Node apenas para setup de Python). **Default: removido.** |
| `scripts/services/{start-watcher,start-claude-mem,start-claude-mem-mcp,start-rtk,claude-mem-local,mcp-server,claude-mem-watchdog,neural-memory-local}.{sh,ps1}` | Wrappers sem logica; daemon sobe direto. **Excecao**: `claude-mem-local.{sh,ps1}` mantem-se **so como ponto de entrada** se for estritamente Node (worker-service.cjs), mas o daemon passa a invoca-lo via `command:` direto. |
| `scripts/capture/claude-mem-hook.{sh,ps1}` | **NAO removido** — capture e fora do control plane. |
| `scripts/capture/copilot-wrapper.{sh,ps1}` | **NAO removido**. |
| `scripts/setup/register-windows-jobs.ps1` | Substituido por `runtime.yaml::jobs[]` -> daemon scheduler. |
| `scripts/setup/register-windows-runtime.ps1` | Substituido por 1 WinSW service (`hive-mindd`). |
| `scripts/setup/start-windows-supervisor.ps1` | O daemon e o supervisor. |
| `scripts/setup/apply-hidden-supervisor-task.ps1` | WinSW ja roda hidden. |
| `scripts/setup/setup-brain.{ps1,sh}` | 5-14 LOC de wrapper. |
| `scripts/setup/setup-vault-enforcement.{ps1,sh}` | Movido para `hive_mind.install.vault_enforcement`. |
| `scripts/setup/register-mcp.{ps1,sh}` | Reescrito em Python. |
| `scripts/maintenance/install-backup-cron.{ps1,sh}` | Substituido por 2 jobs no manifesto. |
| `scripts/graph/{build-graph,serve-graph}.{ps1,sh}` | Movido para `hive-mind graph {build,serve}`. |
| `scripts/utils/recover.{ps1,sh}` | `hive-mind doctor --repair`. |
| `install.sh` (passos 2-12) | Substituido por `hive-mind install`. Mantem-se apenas os primeiros 30 LOC: `set -e`, parse `--profile=`, `command -v uv`, `uv pip install -e .[all]`, `hive-mind install "$@"`, `hive-mindd --register`. |
| `install.ps1` (Steps 2-18) | Idem. Mantem-se apenas os primeiros 30 LOC. |
| `install.bat` | Idem. |
| `setup-brain.bat` | `hive-mind brain setup`. |
| `tests/install/test_windows_bootstrap.ps1` | Reescrito em pytest. |

## 10. Novo package layout

Migracao **incremental** com **namespace de compatibilidade** para nao quebrar imports existentes durante a transicao.

```
src/
  hive_mind/
    __init__.py                     # __version__ = 3.11.0
    cli.py                          # entry-point: hive-mind
    daemon/
      __init__.py                   # entry-point: hive-mindd (chama .main)
      main.py                       # CLI do daemon (start/stop/status/reload/validate)
      supervisor.py                 # port de npm/lib/supervisor.js (Python)
      scheduler.py                  # jobs periodicos declarativos
      manifest.py                   # service_specs + unit_definitions + launchd_definitions + manifest
      state.py                      # state.json (servicos), jobs.json (cadencias)
      docker.py                     # wrapper de docker compose (FalkorDB, etc.)
      readiness.py                  # probe + wait (TCP/HTTP/command)
    platform/
      __init__.py                   # deteccao de SO
      detect.py                     # is_windows/is_macos/is_linux/home_dir/which
      windows.py                    # port 1:1 de HiveMind.Windows.psm1
      linux.py                      # systemd unit + systemd-run timer (transitorio)
      darwin.py                     # launchd plist + launchctl
      winsw.py                      # XML WinSW para `hive-mindd`
    install/
      __init__.py
      install.py                    # `hive-mind install` (full)
      prereqs.py                    # winget/choco/brew (antes: bootstrap-prerequisites.ps1)
      components.py                 # pin de integracoes (de scripts/setup/components.py)
      umc.py                        # inicializar hive_mind.db
      verify.py                     # verify_wrappers
      vault_enforcement.py          # chown/ACL unificado
      brain.py                      # LLM por role (de setup-brain.py)
      optional.py                   # screenpipe, falkordb, claude-mem settings
      wizard.py                     # `hive-mind init --wizard`
    agents/
      __init__.py
      register.py                   # registro MCP unificado (12 agentes, 6 formatos)
      claude_mem.py                 # resolve plugin + settings (de install_services.py)
    doctor/
      __init__.py
      check.py                      # health (de doctor + health/audit_memory)
      repair.py                     # de recover.py
    graph/
      __init__.py
      build.py                      # `hive-mind graph build`
      serve.py                      # `hive-mind graph serve`
    knowledge/
      __init__.py
      promote.py                    # (futuro, ver §11) reescrita do promote.py
    cli/
      __init__.py
      init.py                       # `hive-mind init`
      services.py                   # `hive-mind services` (delega para `hive-mindd status`)
      mcp.py                        # `hive-mind mcp register`
      update.py                     # `hive-mind update`
      doctor.py                     # `hive-mind doctor`
    resources/
      sinapse-agent-prompt.md
      sinapse.yaml
      profiles/
        local-min.yaml
        local-full.yaml
      config/
        env.roles.example
        model-gateway.env.example
        model-gateway.yaml
      components.lock.json
      shell/
        completions.bash
        completions.zsh
        completions.fish
    compat/
      __init__.py
      shims.py                      # re-exporta scripts/setup/install_services.py para
                                     # scripts/services/sinapse-write.py e outros
                                     # imports antigos durante a transicao

# Shim de compatibilidade para o diretorio legado `scripts/` (continua existindo,
# mas comeca a delegar a `hive_mind`):
scripts/
  setup/
    install_services.py             # vira wrapper: re-exporta de hive_mind.daemon
    register-mcp.sh                 # vira: `hive-mind mcp register "$@"`
    register-mcp.ps1                # idem
    setup-brain.sh                  # vira: `hive-mind brain setup "$@"`
    setup-brain.ps1                 # idem
  services/
    start-watcher.sh                # removido
    start-watcher.ps1               # removido
    ... (idem)
  lib/
    HiveMind.Windows.psm1           # removido (funcionalidade em hive_mind.platform.windows)

# Diretorios preservados sem alteracao no design:
core/                              # continua sendo a base
config/                            # mantido em paralelo; resincronizado em M8
integrations/                      # nao mexer
claude-mem/                        # nao mexer
tests/                             # novos testes adicionados, antigos ajustados
cerebro/                           # vault (sem alteracao)
```

### Estrategia incremental de migracao de imports

1. **M1** cria `src/hive_mind/` com shims vazios. `pyproject.toml` ganha `package = true` e `[project.scripts] hive-mind = hive_mind.cli:main`, `hive-mindd = hive_mind.daemon.main:main`. **Nenhum** arquivo existente e movido. Comando `hive-mind --version` ja responde 3.11.0.
2. **M2** cria `config/runtime.yaml` (vazio com stub de exemplo). O daemon existe mas ainda nao le nada. `scripts/setup/install_services.py` continua sendo o source-of-truth.
3. **M3** move `service_specs` + `unit_definitions` + `launchd_definitions` + `manifest` para `hive_mind.daemon.manifest` (com testes `tests/unit/test_daemon_manifest.py` copiando `test_service_backends.py`). `scripts/setup/install_services.py` vira:
   ```python
   from hive_mind.daemon import manifest as _m
   unit_definitions = _m.unit_definitions
   service_specs = _m.service_specs
   launchd_definitions = _m.launchd_definitions
   manifest = _m.manifest
   ```
4. **M4-M8** movem cada classe (supervisor, scheduler, agents/register, install/*, platform/*) para `hive_mind.*`, mantendo o shim em `scripts/setup/install_services.py`. Cada shim e **apagado** so apos o teste `tests/unit/test_compat_shims.py` rodar verde.
5. **M9** apaga `scripts/setup/install_services.py`, `npm/`, e os 14 wrappers `scripts/services/*.{sh,ps1}`. `install.sh` e `install.ps1` encolhem para <100 linhas. `hive-mind install` e a unica fonte de verdade para `runtime.yaml`, prereqs, components, vault, mcp, services, jobs, e registro de SO.
6. **M10** instala em maquina limpa, executa `hive-mind doctor`, reboot, `hive-mind doctor --post-reboot` para fechar o ultimo gate.

A invariante em cada marco e: `hive-mind --version` roda, `uv sync` nao quebra, `tests/unit/test_compat_shims.py` passa, e a runtime legada (systemd timers / Task Scheduler / supervisor Node) continua funcional **ate o novo caminho ser provado**.


## 11. Esquema do `config/runtime.yaml`

Arquivo canonico, **unico**, substitui:
- A lista hardcoded de `npm/lib/services.js::SYSTEMD_UNITS`.
- A combinacao `unit_definitions()` + `service_specs()` + `launchd_definitions()` + `manifest()` em `install_services.py`.
- As listas de PowerShell em `register-windows-jobs.ps1` e `register-windows-runtime.ps1`.
- As entradas em `install-backup-cron.{ps1,sh}`.

Localizacao: `config/runtime.yaml`. Editado por `hive-mind install`, `hive-mind services add`, `hive-mind jobs add`. Lido por `hive-mindd` no boot.

```yaml
# runtime.yaml — Hive-Mind declarative control plane
schema_version: 2
profile: local-min                       # local-min | local-full
vault: cerebro
log_dir: logs
state_dir: logs/daemon                   # state.json, jobs.json, *.pid

# ────────────── Servicos locais (gerenciados pelo daemon) ──────────────
services:
  - name: sinapse-claude-mem
    description: claude-mem Worker (multi-project data em ~/.claude-mem)
    enabled: true
    required: true
    profiles: [local-min, local-full]
    command: ["python", "-m", "claude_mem.worker"]   # ou worker-service.cjs
    working_directory: .
    env_file: .env
    env:
      CLAUDE_MEM_WORKER_HOST: 127.0.0.1
      CLAUDE_MEM_WORKER_PORT: 37700
      CLAUDE_MEM_CHROMA_ENABLED: "false"
      CLAUDE_MEM_MANAGED: "true"
    dependencies: []
    startup_order: 10
    restart_policy: on-failure
    restart_delay_seconds: 15
    restart_max_delay_seconds: 120
    restart_limit: 10
    readiness:
      type: tcp
      host: 127.0.0.1
      port: 37700
      timeout_seconds: 60
    healthcheck:                       # herdado de readiness se omitido
      type: tcp
      host: 127.0.0.1
      port: 37700
      interval_seconds: 15
    requires_claude_mem_plugin: true   # senao, nao habilita

  - name: sinapse-sqlite-vec
    command: ["python", "plugins/sqlite-vec-worker/worker.py"]
    dependencies: [sinapse-claude-mem]
    startup_order: 20
    readiness: { type: tcp, host: 127.0.0.1, port: 37701, timeout_seconds: 60 }

  - name: sinapse-graphify-watch
    command: ["python", "-m", "graphify", "watch", "cerebro", "--debounce", "10.0"]
    env: { GRAPHIFY_WATCH_DEBOUNCE: "10.0", PYTHONUNBUFFERED: "1" }
    startup_order: 30
    restart_policy: always

  - name: sinapse-api
    command: ["python", "scripts/services/sinapse-api.py"]
    env_file: .env
    dependencies: [sinapse-sqlite-vec]
    startup_order: 40
    readiness:
      type: http
      url: http://127.0.0.1:37702/api/v1/health
      expected_status: [200, 401]
      timeout_seconds: 60

  - name: sinapse-mcp-http
    command: ["python", "scripts/services/sinapse-mcp-http.py"]
    dependencies: [sinapse-api]
    startup_order: 50
    readiness: { type: http, url: http://127.0.0.1:37703/health, expected_status: [200] }

  - name: hive-otel-collector
    command: ["python", "scripts/services/otel_collector.py", "--host", "127.0.0.1"]
    startup_order: 15
    restart_policy: on-failure

  - name: sinapse-capture-realtime
    command: ["python", "scripts/capture/capture-realtime.py"]
    env_file: .env
    dependencies: [sinapse-claude-mem, sinapse-sqlite-vec]
    startup_order: 60
    restart_policy: always

# ────────────── Servicos externos (somente health-check) ──────────────
external_services:
  - name: ollama
    required: true
    profiles: [local-min, local-full]
    dependencies: []
    startup_order: 1
    readiness: { type: http, url: http://127.0.0.1:11434/api/tags, expected_status: [200] }
  - name: docker-desktop
    profiles: [local-full]
    startup_order: 2
    readiness: { type: command, command: ["docker", "info", "--format", "{{.ServerVersion}}"] }
  - name: falkordb
    profiles: [local-full]
    dependencies: [docker-desktop]
    startup_order: 75
    readiness: { type: tcp, host: 127.0.0.1, port: 6379, timeout_seconds: 120 }
  - name: milvus
    profiles: [local-full]
    dependencies: [docker-desktop]
    startup_order: 70
    readiness: { type: tcp, host: 127.0.0.1, port: 19530, timeout_seconds: 120 }
  - name: ragflow
    profiles: [local-full]
    dependencies: [docker-desktop]
    startup_order: 80
    readiness: { type: http, url: http://127.0.0.1:9380/api/v1/system/healthz, timeout_seconds: 180 }
  - name: syncthing-watcher
    profiles: [local-full]
    readiness: { type: http, url: http://127.0.0.1:8384/rest/noauth/health, expected_status: [200, 401, 403] }

# ────────────── Jobs periodicos (substitui timers systemd + Task Scheduler) ──────────────
jobs:
  - name: dream-cycle
    command: ["python", "scripts/dream/dream_cycle.py"]
    schedule: "OnCalendar=*-*-* 03:00:00"        # notacao iCal-like
    enabled: true
    timeout_seconds: 1800
    on_failure: log
  - name: daily-writer
    command: ["python", "scripts/dream/daily_writer.py"]
    schedule: "OnCalendar=*-*-* 23:55:00"
    enabled: true
  - name: weekly-synthesizer
    command: ["python", "scripts/dream/weekly_synthesizer.py"]
    schedule: "OnCalendar=Sun 04:00"
    enabled: true
  - name: monthly-synthesizer
    command: ["python", "scripts/dream/monthly_synthesizer.py"]
    schedule: "OnCalendar=*-*-01 02:00"
    enabled: true
  - name: yearly-synthesizer
    command: ["python", "scripts/dream/yearly_synthesizer.py"]
    schedule: "OnCalendar=*-01-01 01:00"
    enabled: true
  - name: session-consolidator
    command: ["python", "scripts/dream/session_consolidator.py"]
    schedule: "OnCalendar=*-*-* */2:00:00"        # a cada 2h
    enabled: true
  - name: claude-mem-bridge
    command: ["python", "scripts/services/claude_mem_bridge.py"]
    schedule: "OnCalendar=*-*-* 02:45:00"
    enabled: true
  - name: backup
    command: ["python", "scripts/health/backup_databases.py"]
    schedule: "OnCalendar=*-*-* 02:00:00"
    enabled: true
  - name: backup-audit
    command: ["python", "scripts/maintenance/backup_audit.py"]
    schedule: "OnCalendar=*-*-* 03:10"
    enabled: true
  - name: backup-prune
    command: ["python", "scripts/maintenance/backup_prune.py"]
    schedule: "OnCalendar=Sun 03:30"
    enabled: true
  - name: health
    command: ["python", "scripts/health/health_dashboard.py"]
    schedule: "OnCalendar=*-*-* 23:50:00"
    enabled: true
  - name: alert
    command: ["python", "scripts/health/alert_dispatcher.py", "--apply"]
    schedule: "OnCalendar=*-*-* 23:52:00"
    enabled: true
  - name: decisions
    command: ["python", "scripts/knowledge/decision_promoter.py", "--apply"]
    schedule: "OnCalendar=*-*-* 23:40:00"
    enabled: true
  - name: projects
    command: ["python", "scripts/knowledge/project_synthesizer.py", "--apply"]
    schedule: "OnCalendar=*-*-* 23:42:00"
    enabled: true
  - name: patterns
    command: ["python", "scripts/knowledge/pattern_distiller.py", "--apply"]
    schedule: "OnCalendar=Sun 05:00"
    enabled: true
  - name: conflicts
    command: ["python", "scripts/knowledge/conflict_detector.py", "--apply"]
    schedule: "OnCalendar=Sun 05:30"
    enabled: true
  - name: drift
    command: ["python", "scripts/knowledge/drift_detector.py"]
    schedule: "OnCalendar=*-*-01 02:00"
    enabled: true
  - name: work
    command: ["python", "scripts/knowledge/work_tracker.py", "--apply"]
    schedule: "OnCalendar=*-*-* 23:44:00"
    enabled: true
  - name: review
    command: ["python", "scripts/knowledge/review_writer.py"]
    schedule: "OnCalendar=*-*-* 08:07:00"
    enabled: true
  - name: topics
    command: ["python", "scripts/knowledge/topic_consolidator.py"]
    schedule: "OnCalendar=Sun 06:00"
    enabled: true
  - name: capture-tailer
    command: ["python", "scripts/capture/capture-tailer.py", "--all", "--scan", "--since-hours", "1"]
    schedule: "OnBootSec=30s;OnUnitActiveSec=30s"  # cadencia curta
    enabled: true
  - name: maintenance
    command: ["python", "scripts/capture/capture_maintenance.py"]
    schedule: "OnCalendar=Sun 04:00"
    enabled: true

# ────────────── Docker Compose projects (apenas o que o daemon sobe) ──────────────
compose_projects:
  - name: falkordb
    file: docker-compose.falkordb.yml
    profiles: [local-full]
    health_check: { type: tcp, host: 127.0.0.1, port: 6379, timeout_seconds: 60 }
  # Milvus / RAGFlow / MySQL / Elasticsearch / Redis / MinIO / Langfuse: declarados
  # mas nao gerados automaticamente ate M6 (ver §15). Mantidos como "user-managed".

# ────────────── Restart policy global ──────────────
restart:
  default_policy: on-failure
  default_delay_seconds: 15
  default_max_delay_seconds: 120
  default_limit: 10
  on_circuit_open: log_and_mark_degraded
```

Validacao: `tests/unit/test_runtime_yaml_schema.py` usa Pydantic v2 para garantir que todo `runtime.yaml` editado por humanos parseia e satisfaz invariantes (deps sao servicos declarados; startup_order unico; profiles consistentes).

## 12. API interna do daemon

`hive-mindd` expoe **3 superficies**:
1. **CLI local** (sub-comandos, mesmo binario, ver `hive_mind.daemon.main:main`).
2. **Control socket** (Unix socket em `runtime_dir/daemon.sock` ou named pipe `\\.\pipe\hive-mindd` no Windows) para `hive-mind services start|stop|status|restart`.
3. **HTTP health/control** em `http://127.0.0.1:37780/` (loopback, sem auth — usado por `hive-mind doctor`).

### 12.1. Sub-comandos do daemon (mesmo binario)

```
hive-mindd start                    # daemoniza, escreve daemon.pid, abre control socket
hive-mindd stop                     # SIGTERM aos filhos, fecha socket, sai
hive-mindd status [--json]          # lista servicos + jobs + ultimo erro
hive-mindd reload                   # re-le runtime.yaml, restart suave
hive-mindd validate                 # roda `hive-mind doctor` e sai
hive-mindd run-job <name>           # executa 1 job (usado por M5 em testes)
hive-mindd post-reboot              # executa validate_after_reboot.py
hive-mindd register                 # registra o servico no SO (systemd/WinSW/launchd)
hive-mindd unregister
```

### 12.2. Control socket (JSON-RPC estilo)

Mensagens JSON de uma linha, newline-delimited.

Request: `{"id": 1, "method": "service.status", "params": {"name": "sinapse-api"}}`
Response: `{"id": 1, "result": {"state": "healthy", "pid": 12345, "uptime_seconds": 312, "last_error": null}}`

Metodos expostos:
- `service.start` / `service.stop` / `service.restart` / `service.status`
- `service.list` (todas com estado)
- `job.run` / `job.status` / `job.list` / `job.history` (ultimas 50 execucoes)
- `manifest.read` (runtime.yaml canonico)
- `manifest.diff` (dry-run de `hive-mind install` para mostrar diff)
- `health.summary` (M1-M13 do `health_dashboard.py`)

O socket e Unix-only no Linux/macOS; named pipe no Windows. A mesma mensagem JSON serve.

### 12.3. HTTP health endpoint

`GET http://127.0.0.1:37780/health` -> `{"state": "healthy", "services": {...}, "jobs": {...}}`
`GET http://127.0.0.1:37780/ready` -> 200 se todos `required: true` estao healthy; 503 caso contrario.
`GET http://127.0.0.1:37780/metrics` -> Prometheus-style (counters: `hive_service_starts_total{name=...}`).
**Sem auth** (loopback only). Nao confundir com a porta 37702 do `sinapse-api` (que tem Bearer key).

### 12.4. Comportamento do supervisor

Inspirado no algoritmo ja existente em `npm/lib/supervisor.js` (portar para Python com mesmas invariantes):

1. Carrega `runtime.yaml` no boot. Erro de schema -> exit 2 com mensagem clara.
2. Seleciona servicos do profile ativo. Exclui os que tem `requires_claude_mem_plugin: true` se o plugin nao esta instalado.
3. Resolve `dependencies` em ordem topologica. Falha ciclica -> exit 3.
4. Para cada servico, em `startup_order`:
   a. `probeReadiness` (TCP/HTTP/command/none) ate `timeout_seconds`.
   b. Se OK, marca `healthy`. Se nao, marca `degraded` e segue (a menos que `required: true`).
5. Health loop a cada 15s. Falaha -> restart com backoff exponencial ate `restart_limit`, depois `circuit-open`.
6. Sinais: `SIGTERM` -> para todos (ordem inversa), `SIGHUP` -> reload do manifesto, `SIGUSR1` -> dump de estado em `logs/daemon/dump.json`.
7. Filhos mortos -> restart conforme `restart_policy` (always / on-failure).
8. Persiste `state.json` a cada mudanca de estado (atomic write: `state.json.tmp` + `os.replace`).

### 12.5. Estendido: API para o Dream Cycle

O Dream Cycle (ja em `scripts/dream/dream_cycle.py`) nao precisa de API nova; ele continua sendo um job. Ja tem CLI (`python dream_cycle.py`).

## 13. Estrategia de scheduler

**Decisao central**: 1 scheduler no proprio daemon Python. Sem timers systemd, sem Task Scheduler, sem crontab. O daemon expoe:

```
state:
  jobs.json        # ultima execucao de cada job
  services.json    # estado dos servicos
```

### 13.1. Loop do scheduler

```python
async def scheduler_tick(daemon):
    now = datetime.now()
    for job in daemon.jobs.values():
        if not job.enabled:
            continue
        if not daemon.cron_match(job.schedule, now):
            continue
        # Coalesce: nao rodar se ja esta rodando (exceto allow_overlap).
        if job.name in daemon.running_jobs:
            daemon.log("skip overlap", job=job.name)
            continue
        daemon.running_jobs.add(job.name)
        try:
            proc = await asyncio.create_subprocess_exec(*job.command, ...)
            job.last_run = now
            try:
                await asyncio.wait_for(proc.wait(), timeout=job.timeout_seconds)
                job.last_status = "success" if proc.returncode == 0 else "failed"
            except asyncio.TimeoutError:
                proc.kill()
                job.last_status = "timeout"
            job.last_exit_code = proc.returncode
            job.last_duration = (datetime.now() - now).total_seconds()
        finally:
            daemon.running_jobs.discard(job.name)
        daemon.persist_jobs_state()
```

Tick a cada 10s (nao 1s, nao 60s — 10s e o meio termo).

### 13.2. Persistencia

`logs/daemon/jobs.json` contem:
```json
{
  "dream-cycle": {
    "last_run": "2026-07-12T03:00:01",
    "next_run": "2026-07-13T03:00:00",
    "last_status": "success",
    "last_exit_code": 0,
    "last_duration_seconds": 312,
    "last_error": null,
    "consecutive_failures": 0
  }
}
```

Atomic write em tmp + replace. Carregado no boot. `next_run` e calculado uma vez no boot e atualizado a cada tick (calculo barato, ~1ms por job).

### 13.3. Expressao de schedule

Estilo iCal RFC 5545 subset (suficiente para o que ja existe):
- `OnCalendar=*-*-* 03:00:00` (todo dia 03:00)
- `OnCalendar=Sun 04:00` (domingo 04:00)
- `OnCalendar=*-*-01 02:00` (dia 1 do mes 02:00)
- `OnBootSec=30s;OnUnitActiveSec=30s` (composicao)
- `OnCalendar=*-01-01 01:00` (1o de janeiro)

Implementado com `croniter` (ja transitivo via `pyproject.toml`) ou um parser proprio. Cobertura: **100%** das schedules ja em uso (testado contra `install_services.py` e `register-windows-jobs.ps1`).

### 13.4. Faltou-run (boot atrasado)

Se o daemon inicia as 03:30 e o job `dream-cycle` estava agendado para 03:00, o scheduler dispara imediatamente (e marca `last_run`). Comportamento identico ao `Persistent=true` em systemd/Task Scheduler.

### 13.5. Interacao com readiness

Job que depende de um servico (ex.: `dream-cycle` precisa de `sinapse-claude-mem`): o scheduler checa `daemon.services[dep].state in {"healthy", "degraded"}` antes de rodar. Caso contrario, **adiar** para o proximo tick (com contador de retries) ate `timeout_seconds`. Comportamento identico a systemd `After=`.

### 13.6. Migra玢o dos timers atuais

Cada `*.timer` em `install_services.py::unit_definitions()` vira 1 entrada `jobs:` em `runtime.yaml` com mesmo schedule. O gerador `hive_mind.install.migrate_from_install_services` (utilizado em M3) faz a traducao automatica. Cada `Register-ScheduledTask` em `register-windows-jobs.ps1` vira 1 entrada `jobs:`. Diff mostrado antes de aplicar.

### 13.7. Persistir estado para sobreviver reboot

Como o scheduler e in-process do daemon, e o daemon e gerenciado por WinSW / systemd / launchd, o estado persiste. `OnBootSec=30s;OnUnitActiveSec=30s` no capture-tailer e capturado pelo croniter com `boot_time=now`.


## 14. Estrategia Docker

Docker e **apenas** para infra externa compartilhada (Milvus, RAGFlow, MySQL, Elasticsearch, Redis, MinIO, FalkorDB, Langfuse). **Nunca** para o vault, `hive_mind.db`, claude-mem, ou qualquer coisa que o usuario escreva em cerebro/.

### 14.1. Compose canonico

Hoje: `docker-compose.falkordb.yml` (1 stack) + manual para o resto. Ha dependencias implicitas (Milvus precisa de MinIO + etcd; RAGFlow precisa de MySQL + Elasticsearch + Redis). Sem compose canonico, o usuario segue um tutorial e quebra.

**Decisao**: 1 compose de referencia por stack externa, em `compose/`:
```
compose/
  falkordb.yml
  milvus.yml          # com milvus, etcd, minio na mesma rede
  ragflow.yml         # com ragflow, mysql, elasticsearch, redis
  langfuse.yml        # com langfuse-server, clickhouse
  observability.yml   # com prometheus, grafana, otel-collector (substitui hive-otel local)
```

Cada compose e **idempotente** (named volumes, healthchecks), com labels consistentes (`org.opencontainers.image.source=Hive-Mind`).

### 14.2. Orquestrador

`hive-mindd` nao chama `docker compose` diretamente. Em vez disso, `hive_mind.docker.Orchestrator` expoe:

```python
class Orchestrator:
    async def up(self, project: str) -> None: ...   # docker compose -f compose/<project>.yml up -d
    async def down(self, project: str) -> None: ...
    async def status(self, project: str) -> dict: ...  # parsed health
    async def wait_healthy(self, project: str, timeout: int) -> None: ...
    async def repair(self, project: str) -> None: ...   # restart unhealthy, pull latest, etc.
```

O `runtime.yaml` declara `compose_projects:` com `health_check`. O daemon chama `orchestrator.wait_healthy(project)` antes de marcar como `healthy`. **"Container running" nao conta como healthy** — o health check em compose + readiness no manifesto sao ambos obrigatorios.

### 14.3. Quando chamar o orquestrador

- **Boot** (M6): `hive-mindd start` detecta `compose_projects` ativos, chama `up` em paralelo, espera `wait_healthy`.
- **Reconciliacao periodica** (a cada 5min): se um container esta `unhealthy`, o daemon chama `repair` (1 retry com `docker compose restart`, depois `docker compose pull && up -d`).
- **Manual**: `hive-mind docker up falkordb` ou `hive-mind docker status` (sub-comandos).

### 14.4. Portabilidade

- **Linux** com Docker Engine: padrao. `docker compose` no PATH.
- **macOS** com Docker Desktop: idem. Docker Desktop ja e gerenciado pelo usuario.
- **Windows** com Docker Desktop: idem, mas via WSL2 (Docker Desktop usa WSL2 por baixo).
- **WSL2 nativo**: idem ao Linux.

Nenhum codigo novo precisa diferenciar. O orquestrador usa `docker compose` (Compose V2, ja em Docker Desktop 4.x).

### 14.5. Full stack vs minimo

`profile: local-min` -> sem compose. FalkorDB opcional (e local) ou via `nmem`. **Zero Docker obrigatorio**.
`profile: local-full` -> FalkorDB + Milvus (se `MILVUS_URI` apontar para o container). RAGFlow opt-in. Langfuse opt-in.

## 15. Estrategia Windows Service / systemd / launchd

**Decisao**: 1 unico servico nativo `hive-mindd` por plataforma. PowerShell e Bash **somente** para bootstrap e registro do daemon.

### 15.1. Windows (WinSW)

- **WinSW** (.NET wrapper, 5MB) embutido em `src/hive_mind/resources/winsw/hive-mindd.exe` (baixado em `hive-mind install`, nao commitado).
- XML em `src/hive_mind/resources/winsw/hive-mindd.xml`:
  ```xml
  <service>
    <id>hive-mindd</id>
    <name>Hive-Mind Daemon</name>
    <description>Runtime daemon for Hive-Mind services and scheduler</description>
    <executable>python</executable>
    <arguments>-m hive_mind.daemon start</arguments>
    <workingdirectory>%BASE%</workingdirectory>
    <stoptimeout>30sec</stoptimeout>
    <onfailure action="restart" delay="15 sec"/>
    <resetfailure>1 hour</resetfailure>
  </service>
  ```
- `hive-mindd --register` em PowerShell:
  1. Cria `logs/daemon/`
  2. Copia `hive-mindd.exe` + `hive-mindd.xml` para o diretorio
  3. `hive-mindd.exe install` (WinSW install)
  4. `hive-mindd.exe start`
- **Idempotente**: detecta versao antiga, atualiza XML se mudou, restart se a config mudou.
- **Substitui** o `register-windows-runtime.ps1` (15 LOC) e o `start-windows-supervisor.ps1` (7 LOC) e o `apply-hidden-supervisor-task.ps1` (5 LOC) — 27 LOC no total.

### 15.2. Linux (systemd user unit)

`src/hive_mind/resources/systemd/hive-mindd.service`:
```ini
[Unit]
Description=Hive-Mind Daemon
After=network.target

[Service]
Type=simple
UMask=0077
WorkingDirectory=%h/Hive-Mind
EnvironmentFile=-%h/Hive-Mind/.env
ExecStart=%h/Hive-Mind/.venv/bin/python -m hive_mind.daemon start
Restart=on-failure
RestartSec=15
StandardOutput=append:%h/Hive-Mind/logs/daemon/daemon.log
StandardError=append:%h/Hive-Mind/logs/daemon/daemon.err.log

[Install]
WantedBy=default.target
```

`hive-mindd --register` em Bash:
1. `mkdir -p ~/.config/systemd/user`
2. Escreve a unit (templated com `$HOME`)
3. `systemctl --user daemon-reload`
4. `systemctl --user enable hive-mindd`
5. `systemctl --user start hive-mindd`

Systemd continua sendo o **unico** auto-start no Linux. O daemon (e nao o supervisor Node) e o unico processo de longa duracao.

### 15.3. macOS (LaunchAgent)

`src/hive_mind/resources/launchd/com.hivemind.daemon.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
  <key>Label</key><string>com.hivemind.daemon</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>-c</string>
    <string>cd $HOME/Hive-Mind && set -a && . ./.env && set +a && exec ./.venv/bin/python -m hive_mind.daemon start</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$HOME/Hive-Mind/logs/daemon/daemon.log</string>
  <key>StandardErrorPath</key><string>$HOME/Hive-Mind/logs/daemon/daemon.err.log</string>
  <key>Umask</key><integer>63</integer>
</dict>
</plist>
```

`hive-mindd --register` em Bash:
1. Escreve plist em `~/Library/LaunchAgents/com.hivemind.daemon.plist`
2. `launchctl unload` (idempotente)
3. `launchctl load`

### 15.4. Comparacao

| Plataforma | Auto-start | Wrapper de exec | Diretorio de runtime |
|---|---|---|---|
| Windows | WinSW service `hive-mindd` | `python -m hive_mind.daemon start` | `logs/daemon/` |
| Linux | systemd user unit `hive-mindd.service` | `.venv/bin/python -m hive_mind.daemon start` | `~/.local/share/hive-mind/` + `logs/daemon/` |
| macOS | LaunchAgent `com.hivemind.daemon` | sh -c ". ./.env && exec ..." | `~/Library/Application Support/Hive-Mind/` + `logs/daemon/` |

Em todos os 3 casos: **1 unico processo nativo de longa duracao** (`hive-mindd`). Ele e o pai de todos os servicos. Sem wrappers, sem scripts de start.

## 16. Plano de migracao por commits (M1-M10)

Cada marco termina com: (a) runtime legada ainda funciona, (b) novo caminho co-existe, (c) testes verdes. **Nada** e deletado ate M9.

### M1 — Pacote Python e entry points (1-2 commits)
- Cria `src/hive_mind/__init__.py`, `cli.py` (placeholder), `daemon/__init__.py`, `daemon/main.py` (placeholder).
- `pyproject.toml`: remove `tool.uv.package = false`. Adiciona `[project.scripts] hive-mind`, `hive-mindd`.
- `tests/unit/test_smoke.py` valida `hive-mind --version` e `hive-mindd --version` retornam 0.
- **Nenhum** arquivo existente e movido.
- Validacao: `uv sync --frozen` nao quebra. `hive-mind --version` retorna `3.11.0`.

### M2 — Manifesto canonico vazio (1 commit)
- Cria `config/runtime.yaml` com schema Pydantic em `src/hive_mind/daemon/schema.py`.
- Adiciona `tests/unit/test_runtime_yaml_schema.py` validando YAML minimo.
- `hive-mind config show` e `hive-mind config validate` funcionam.
- Validacao: `hive-mind config validate` retorna 0.

### M3 — Daemon minimo gerenciando 1 servico (2-3 commits)
- Move `service_specs`, `unit_definitions`, `launchd_definitions`, `manifest` de `scripts/setup/install_services.py` para `src/hive_mind/daemon/manifest.py`.
- Adiciona shim de compat em `scripts/setup/install_services.py` (re-exporta).
- `src/hive_mind/daemon/supervisor.py` porta algoritmo de `npm/lib/supervisor.js` (somente `topologicalServices` + `probeReadiness` + `waitForReadiness`).
- Cria `tests/unit/test_daemon_supervisor.py` (port dos 4 testes JS) e `tests/unit/test_daemon_manifest.py` (port de `test_service_backends.py`).
- `hive-mindd --register` funciona em Linux (systemd) e Windows (WinSW). macOS stub.
- `hive-mindd start` sobe 1 servico (`sinapse-graphify-watch`) e mantem.
- **Runtime legada continua**: `scripts/setup/install_services.py` ainda instala systemd units como antes. Novo daemon e opcional.
- Validacao: `hive-mindd start && sleep 5 && hive-mindd status` mostra `healthy`. `systemctl --user status sinapse-graphify-watch` ainda funciona (legado). **Ambos sao saudaveis**.

### M4 — Migracao dos demais servicos locais (3-4 commits)
- Porta os 7 servicos daemon para `runtime.yaml` (gerado a partir de `service_specs()` por `hive_mind.install.migrate_from_install_services`).
- Adiciona `hive_mind.platform.linux.systemd_unit(spec)`, `hive_mind.platform.darwin.plist_for(spec)`, `hive_mind.platform.winsw.xml_for(spec)`.
- `hive-mindd start` sobe todos os 7 servicos daemon. Runtime legada fica em `legacy` (nao habilitada no boot).
- Validacao: `hive-mindd status` mostra 7 servicos `healthy`. `hive-mind doctor` passa.

### M5 — Scheduler (3-4 commits)
- Adiciona `src/hive_mind/daemon/scheduler.py` com loop de 10s e `croniter` para schedules.
- Move os 18 jobs de `install_services.py` (systemd timers) + 4 de `register-windows-jobs.ps1` para `runtime.yaml::jobs[]`.
- `logs/daemon/jobs.json` persiste `last_run`/`next_run`/`status`/`exit_code`/`duration`/`last_error`.
- Migra o `crontab` (backup-audit, backup-prune) para `runtime.yaml`.
- **Runtime legada**: timers systemd e Task Scheduler ainda ativos. `hive-mindd` ainda nao e obrigatorio.
- Validacao: `hive-mindd run-job dream-cycle` completa com sucesso. `jobs.json` e atualizado. **Comparar com execucao manual** em janela de 24h.

### M6 — Docker orchestration (2 commits)
- Cria `compose/{falkordb,milvus,ragflow,langfuse}.yml`.
- Adiciona `src/hive_mind/docker/orchestrator.py`.
- `runtime.yaml::compose_projects` referencia os compose files.
- `hive-mindd start` chama `orchestrator.up()` antes de marcar servicos como `healthy`. Health check obrigatorio.
- Validacao: `hive-mind docker up falkordb` sobe e healthcheck em <30s. `hive-mindd status` mostra `falkordb: healthy`. **Comparar com execucao manual** de `docker compose`.

### M7 — Adapters de sistema operacional (3 commits)
- Adiciona `src/hive_mind/platform/windows.py` (port de `HiveMind.Windows.psm1`).
- WinSW XML final. `hive-mindd --register` em Windows = `hive-mindd.exe install && hive-mindd.exe start`.
- macOS: `hive-mindd --register` escreve plist e chama `launchctl load`.
- Validacao: reboot Windows -> `hive-mindd` reinicia via WinSW. `hive-mindd status` mostra todos servicos `healthy` em <60s.

### M8 — Instaladores finos (1 commit)
- `install.sh` -> ~80 LOC: detecta uv, `uv pip install -e .`, `hive-mind install`, `hive-mindd --register`, `hive-mind doctor`.
- `install.ps1` -> ~80 LOC: idem.
- `install.bat` -> 10 LOC.
- `hive-mind install` ganha `--wizard` (substitui `npm/lib/wizard.js`).
- Validacao: install fresco em maquina Windows e Linux em <10min, doctor verde.

### M9 — Remocao gradual dos scripts legados (3-4 commits)
- Apaga `npm/`, `scripts/setup/install_services.py`, `scripts/services/*.{sh,ps1}` (exceto `claude-mem-local.{sh,ps1}` se ainda usado), `scripts/utils/recover.{ps1,sh}`, `scripts/setup/{setup-brain,setup-vault-enforcement,register-mcp,register-windows-jobs,register-windows-runtime,start-windows-supervisor,apply-hidden-supervisor-task,bootstrap-prerequisites,backup-install-state}.{ps1,sh}`, `scripts/maintenance/install-backup-cron.{ps1,sh}`.
- Apaga `scripts/lib/HiveMind.Windows.psm1`.
- `install.sh` e `install.ps1` ja estao em <100 LOC; OK.
- Atualiza `install.sh`/`install.ps1` para falhar com mensagem clara se a maquina nao tiver uv/Python.
- Validacao: `git grep` nao acha mais referencias aos scripts removidos. `tests/unit/test_compat_shims.py` e deletado.

### M10 — Instalacao limpa e reboot (1-2 commits)
- `tests/install/test_clean_install.py` (pytest) substitui `tests/install/run-clean-install-test*.{ps1,sh}`.
- Em maquina limpa (CI: Ubuntu runner, Windows runner, macOS runner): `uv pip install -e .` -> `hive-mind install --test` -> reboot -> `hive-mindd post-reboot` -> `hive-mind doctor` verde.
- Tag `v3.11.0` e **nao** feito ate o usuario aprovar. Sem push, sem release, sem PR ate aprovacao final do desenho.

### Resumo dos marcos

| M | Escopo | LOC novo estimado | LOC removido estimado | Risco |
|---:|---|--:|--:|---|
| 1 | pacote + entry points | 80 | 0 | baixo |
| 2 | manifesto canonico | 250 | 0 | baixo |
| 3 | daemon + 1 servico | 700 | 0 | medio (algoritmo JS -> Python) |
| 4 | 7 servicos | 400 | 0 | medio (drift com legada) |
| 5 | scheduler | 500 | 0 | medio (cadencias tem que bater) |
| 6 | Docker orchestration | 350 | 0 | medio (compose health) |
| 7 | OS adapters | 600 | 0 | alto (WinSW hidden, launchd) |
| 8 | instaladores finos | 200 | 1000 | baixo |
| 9 | remocao gradual | 50 | 2500 | alto (temer regressao) |
| 10 | install limpa + reboot | 100 | 200 | medio (depende de runner) |
| **Total** | | **~3.230** | **~3.800** | |


## 17. Riscos

| # | Risco | Probabilidade | Impacto | Mitigacao |
|---:|---|---|---|---|
| 1 | Drift entre `service_specs` (runtime legada) e `runtime.yaml` (novo) durante M3-M8 | Alta | Medio | M3-M8 mantem `tests/unit/test_daemon_manifest.py` espelhado de `tests/unit/test_service_backends.py`. CI falha se houver drift. |
| 2 | Cadencias (systemd timers vs scheduler Python) divergirem em 1 minuto | Media | Alto | M5: rodar 24h em 2 maquinas e comparar `jobs.json` com execucao manual. |
| 3 | WinSW nao inicia apos login no Windows (problema conhecido com session 0) | Media | Alto | M7: testar com `services.msc` + `sc query hive-mindd`. Fallback: Task Scheduler com acao de recovery. |
| 4 | launchd no macOS perde env vars (problema com shell quoting) | Media | Medio | M7: carregar `.env` dentro do plist via `set -a; . ./.env; set +a; exec ...` (padrao ja usado). |
| 5 | `croniter` (ou parser proprio) nao cobrir uma schedule exotica que existe hoje | Baixa | Medio | M5: gerar tabela de equivalencia (systemd OnCalendar -> croniter) e validar 1-a-1 antes de M6. |
| 6 | Docker Desktop no Windows ficar offline apos reboot | Media | Baixo | M6: `hive-mind doctor` reporta; servicos que dependem ficam `degraded`, nao crash. |
| 7 | Usuario perde `claude-mem` (que ja e Node) durante transicao | Baixa | Alto | M3-M9 mantem `claude-mem-local.{sh,ps1}` como entry-point externo. Worker continua Node; so o wrapper de env some. |
| 8 | Vault write enforcement (chown/ACL) quebrar com `hive-mindd` rodando como SYSTEM (Windows) | Media | Alto | M7: `hive-mindd` roda como **user** via WinSW `<serviceaccount>`. Vault enforcement testado em 3 cenarios. |
| 9 | Race entre `hive-mind install` reescrevendo `runtime.yaml` e `hive-mindd start` lendo | Baixa | Medio | `hive-mind install` faz `hive-mindd reload` (SIGHUP) apos escrever. |
| 10 | `npm` users existentes quebrarem (sem Node) | Baixa | Alto | M9: publicar `@hive-mind/installer@1.0` que apenas baixa o wheel Python. `npm i -g @hive-mind/installer` continua funcionando como bootstrap opcional. |
| 11 | Captura de agentes (claude-mem-hook) parar de funcionar | Baixa | Alto | **NAO MEXER** em `scripts/capture/*` no M9. Hooks continuam sendo sh/ps1 finos. |
| 12 | Testes de regressao quebrarem por mudanca de imports | Media | Medio | Shims de compat em M3-M8 (`scripts/setup/install_services.py` re-exporta). `tests/unit/test_compat_shims.py` trava que cada shim ainda funciona. |
| 13 | Performance do scheduler (tick 10s + 22 jobs) | Baixa | Baixo | Cron match em ~1ms por job, mesmo com 100 jobs. Async subprocess_exec sem GIL. |
| 14 | Crash do daemon derruba todos os servicos | Media | Alto | M7: WinSW / systemd restart on-failure com backoff. State persistido em disco. |
| 15 | `runtime.yaml` editado a mao com YAML invalido | Media | Medio | M2: Pydantic schema estrito, `hive-mind config validate` antes de `hive-mindd start`. |
| 16 | Falta de testes E2E reais (CI nao roda install fresca + reboot) | Media | Alto | M10: configurar runners Windows + Linux + macOS em CI com reboot (Azure DevOps, GitHub Actions com `reboot` action). |
| 17 | claude-mem worker-service.cjs (Node) nao responde a SIGTERM limpo | Baixa | Baixo | Daemon faz SIGTERM com 30s timeout, depois SIGKILL. Ja documentado no supervisor. |
| 18 | `hive_mind.daemon` nao compativel com Python 3.11 (hoje requer 3.12) | Baixa | Baixo | `pyproject.toml` ja trava `requires-python = ">=3.12,<3.13"`. CI roda 3.12. |
| 19 | Lock do `hive_mind.db` (SQLite) durante backup | Media | Baixo | M5: `backup_databases.py` ja usa SQLite backup API; scheduler dispara job em horario de baixo uso. |
| 20 | Regressao no `sinapse_query` (federacao de 7 backends) | Baixa | Alto | **NAO MEXER** em `core/federation.py`, `core/retrieval/router.py`. So adicionar entrada em `config/sinapse.yaml` se necessario. |

### Riscos especificos da migracao Windows (M7)

- **WinSW na Microsoft Store**: ha alerta de "app nao assinado". Mitigacao: gerar certificado self-signed em `hive-mind install` (instrucional) ou documentar bypass via `Set-MpPreference`.
- **PowerShell ExecutionPolicy**: Bypass ja usado. `hive-mind install` nao precisa mexer.
- **Path com espaco**: ja tratado em `HiveMind.Windows.psm1::Get-HiveMindRoot`. `hive_mind.platform.windows` mantem.
- **Long path (>260 chars)**: WinSW + Python 3.12 long path support. Ja habilitado por default no Python 3.12.

## 18. Testes de regressao

### 18.1. Testes existentes que devem continuar passando

- `tests/unit/test_service_backends.py` (5 testes) -> vira `tests/unit/test_daemon_manifest.py`. Assercoes preservadas.
- `tests/unit/test_install_services.py` -> ajusta imports para `hive_mind.daemon.manifest`.
- `tests/unit/test_recovery.py` -> ajusta imports para `hive_mind.doctor.repair`.
- `tests/unit/test_register_mcp.py` (se existir) -> ajusta imports para `hive_mind.agents.register`.
- `tests/unit/test_backup_audit.py` -> mantem (logica em `scripts/maintenance/backup_audit.py` nao muda).
- `tests/unit/test_audit_memory.py` e `test_audit_memory_cli.py` -> mantem.
- `tests/integration/test_api_query_hybrid.py` -> mantem (API nao muda).
- `tests/real/test_*` (suite real knowledge) -> mantem (claude-mem, dream, etc. nao mudam).
- `tests/e2e/test_*` -> mantem; ganham 1 novo teste: `test_daemon_manages_all_services.py`.

### 18.2. Testes novos (M1-M10)

| Marco | Teste | O que valida |
|---|---|---|
| M1 | `tests/unit/test_package_layout.py` | `hive-mind --version`, `hive-mindd --version`, entry points existem. |
| M2 | `tests/unit/test_runtime_yaml_schema.py` | Pydantic schema; YAML minimo/incompleto/invalido. |
| M2 | `tests/unit/test_runtime_yaml_invariants.py` | Deps sao declarados; startup_order unico por servico; profiles consistentes. |
| M3 | `tests/unit/test_daemon_manifest.py` | Service_specs + unit_definitions + launchd_definitions + manifest batem (port do test_service_backends). |
| M3 | `tests/unit/test_daemon_supervisor.py` | topologicalServices, probeReadiness (TCP/HTTP/command/none), waitForReadiness, restartDelayMs, canRestart. |
| M3 | `tests/integration/test_daemon_manages_one_service.py` | Sobe `sinapse-graphify-watch`, espera `healthy`, para limpo. |
| M4 | `tests/integration/test_daemon_manages_all_services.py` | 7 servicos daemon sobem, restart policy funciona, circuit-breaker dispara apos 10 falhas. |
| M5 | `tests/unit/test_scheduler.py` | `cron_match` para OnCalendar (5 variacoes), OnBootSec+OnUnitActiveSec, missed-run-on-boot. |
| M5 | `tests/integration/test_scheduler_runs_all_jobs.py` | 18 jobs rodam em sequencia rapida (substituindo `time` por `now+0`), `jobs.json` persiste. |
| M5 | `tests/integration/test_scheduler_overlap.py` | Job demorado nao dispara 2x (coalesce). |
| M5 | `tests/integration/test_scheduler_missed_run.py` | Daemon inicia 30min atrasado, dispara imediatamente. |
| M6 | `tests/integration/test_docker_orchestrator.py` | Compose up, wait_healthy, repair on unhealthy. |
| M7 | `tests/integration/test_winsw_register.py` (Windows-only) | `hive-mindd --register` cria servico; `sc query hive-mindd` retorna `RUNNING`. |
| M7 | `tests/integration/test_launchd_register.py` (macOS-only) | plist escrito; `launchctl list | grep com.hivemind.daemon` retorna PID. |
| M7 | `tests/integration/test_linux_register.py` | `systemctl --user status hive-mindd` retorna `active`. |
| M8 | `tests/install/test_thin_installers.py` | `install.sh --profile=local-min --dry-run` e `install.ps1` <100 LOC, e rodam sem erro em maquinas limpas. |
| M9 | `tests/unit/test_legacy_removal.py` | `git ls-files` nao contem os scripts removidos. |
| M10 | `tests/install/test_clean_install.py` | install fresca em CI: Linux + Windows + macOS. `hive-mindd post-reboot` verde. |

### 18.3. Suite minima por marco

Cada marco termina com: `pytest tests/unit -q` e `pytest tests/integration -q --timeout=60` verdes. **Nenhum** marco termina com teste vermelho ou skipped.

### 18.4. Suite de fuma莽a (ja existente, preservar)

`bash tests/smoke/test_smoke.sh` (81 LOC) e `tests/smoke/test_smoke.ps1` (30 LOC) continuam sendo a porta de entrada. Nao mexer.

### 18.5. Testes E2E de conhecimento real (manter)

`bash tests/run_real_knowledge.sh` e `tests/run_real_knowledge.ps1` continuam sendo o criterio de verdade do brain. A transicao M3-M9 nao toca claude-mem, dream, knowledge scripts.

### 18.6. Criterio de "regressao zero"

1. `pytest tests/unit -q` continua passando em CI.
2. `pytest tests/integration -q --timeout=60` continua passando em CI.
3. `bash tests/smoke/test_smoke.sh` continua verde.
4. `bash tests/run_real_knowledge.sh` continua completando em <30min.
5. Em maquina real, `hive-mind doctor` retorna 0.
6. Em maquina real, reboot -> `hive-mindd` reinicia -> servicos sobem em <60s -> health verde.

Se qualquer um dos 6 falhar, a transicao **nao** avanca para o proximo marco.

---

# Anexo A. Correcao do `config/sinapse-agent-prompt.md` (§11 do pedido original)

A restricao "Use ONLY sinapse_* tools" deve ser aplicada **somente** aos backends de memoria. O texto abaixo SUBSTITUI a secao "Usage rules" do prompt atual. **Captura do claude-mem nao e alterada**.

```markdown
## Usage rules

### Backends de memoria
- **Use ONLY the `sinapse_*` tools and `search_memories`** to read or write Hive-Mind memory.
- Never call `nmem`, `claude-mem`, `graphify`, or `falkordb` directly — sinapse
  already federates and deduplicates them via Context Fusion.

### Codigo atual e runtime
- O **codigo atual** deve ser lido pelo **filesystem** (Read, rg, git, ls, etc.).
- Use `shell` para inspecionar o repo; `rg` (ripgrep) para busca em texto;
  `git` para historico. **Nao** use `sinapse_query` para procurar funcoes,
  classes, ou arquivos no codigo atual.
- **Read files completely** quando a pergunta for sobre o codigo. Nao confie em
  citacoes resumidas.
- **Execute tests** para validar comportamento. `pytest`, `bash tests/smoke/test_smoke.sh`,
  e os jobs do `runtime.yaml` sao fontes de verdade.
- **O codigo e o runtime atuais prevalecem sobre a memoria historica.** Se houver
  conflito entre o que o codigo faz e o que a memoria diz, o codigo vence.
- **Sinapse nao substitui inspecao do repositorio.** Use sinapse para
  contexto/decisoes/observacoes previas; use o filesystem para o estado atual.

### Sinapse
- `sinapse_query` is the canonical orchestrator (7 backends). Use it instead of
  backend-specific tools whenever possible.
- `sinapse_temporal_graph_search` is deprecated: kept so as not to break existing
  clients, but the canonical brain query is `sinapse_query`.
- `sinapse_health()` returns the status of all backends; use it for diagnosis
  when a query returns empty unexpectedly.
- `sinapse_capture_screen` only on explicit request - never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor
  setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- **Vault write enforcement:** on hosts where `setup-vault-enforcement` has
  been applied, `cerebro/` is owned by a dedicated service user and the agent
  only has direct write access to `cerebro/90-intake/`. If a direct vault write
  is denied, `sinapse_save_decision` / `sinapse_save_learning` fall back
  automatically to the intake area - this is expected behavior, not a failure.
- **RTK is shell optimization only.** RTK is not a memory tool or a
  `sinapse_query` backend; it is only the shell command optimization layer.
  When you need to configure RTK, use `./scripts/services/start-rtk.sh --only
  <agent>` for the correct agent/CLI. (No M3 do redesenho, este script e
  removido e substituido por `hive-mind rtk configure --only <agent>`.)

### Captura
- A captura do claude-mem NAO foi alterada. Hooks, adapters e
  `scripts/capture/*` continuam como estao.
```

---

# Anexo B. Aprovacao necessaria antes de M1

Para avancar, o operador deve confirmar:

1. **Arquitetura**: pacote `src/hive_mind/` + binarios `hive-mind` / `hive-mindd` + manifesto `config/runtime.yaml` + scheduler in-process.
2. **Migracao**: 10 marcos com shims de compat ate M9. Nenhum script removido antes de M8.
3. **Captura e knowledge**: nao mexer em `scripts/capture/*`, `scripts/dream/*`, `scripts/knowledge/*`, `core/*`, `claude-mem/*`, `integrations/*`, `cerebro/`.
4. **Testes**: 6 criterios de "regressao zero" (§18.6) bloqueiam cada marco.
5. **Branch**: tudo vai em branch dedicado `codex/control-plane-redesign` a partir de `codex/windows-zero-install-impl @ d246f0c6`. Sem merge, sem push, sem tag, sem release.
6. **Sinapse prompt**: o Anexo A e aplicado **no fim** (M8) junto com a substituicao do `config/sinapse-agent-prompt.md` por `src/hive_mind/resources/sinapse-agent-prompt.md`.

Ate a confirmacao, **nenhuma mudanca** e feita no codigo, no `install.sh` / `install.ps1`, no `install_services.py`, no `npm/`, no `register-windows-jobs.ps1`, no `register-windows-runtime.ps1`, no `register-mcp.{ps1,sh}`, e nos wrappers `scripts/services/*.{ps1,sh}`.

Gates de instalacao limpa e reboot continuam **pausados** ate a aprovacao final.
