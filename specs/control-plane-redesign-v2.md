# Hive-Mind — Redesenhó do Control Plane (revisão)

> **Status: DRAFT — aguardando nova aprovação antes de qualquer implementação**
> Branch correto: codex/windows-zero-install-impl @ d246f0c6e6661e7c9a052108387bd52819483b8d
> Worktree: D:\\Hive-Mind\\backups\\worktrees\\hive-mind-windows-zero-install
> Substitui: specs/control-plane-redesign.md (versão 1, baseada em HEAD errado 3d362c6).
> Gates de instalação limpa / reboot: **PAUSADOS** até aprovação final.
> Versão da implementação: **a decidir após os gates** (atual no repo: 3.10.1).

---



## 1. Confirmacao de branch e HEAD

Executado a partir de `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install`:

```text
branch: codex/windows-zero-install-impl
HEAD:   d246f0c6e6661e7c9a052108387bd52819483b8d
log -15: d246f0c fix(windows): close runtime isolation and citation cleanup gaps
         20c95c5 fix(windows): complete zero-install full profile
         9b49fba fix(release): enforce post-v3.10 version floor
         fcbdf0e feat(windows): make doctor enforce required service health
         f73b479 build(windows): validate release contract in CI
         18279ca fix(windows): require healthy services before install completes
         9b3ce1f fix(windows): gate full install on required service readiness
         aa9435e docs: plan clean Windows operational recovery
         3d362c6 M4: supervisor boot must not abort on one service's readiness timeout
         945c6a0 M3: add scheduled knowledge jobs to install.ps1
         ff12102 M1: establish canonical Windows installer and contracts of profile
         6c53c9a M0: preserve canonical Windows native base
         206b020 feat(windows): add autostart and scheduled knowledge jobs
         5a20f62 feat(runtime): add declarative services and readiness supervisor
         38770f4 feat(windows): unify installer and installation profiles
```

`git status --short` (no worktree correto): working tree limpo. Nenhum arquivo modificado pelo desenho.

## 2. Diferencas arquiteturais entre 3d362c6 e d246f0c6

`git diff --stat 3d362c6..d246f0c6` retorna **73 arquivos modificados, 2.352 insercoes, 181 delecoes**. As areas afetadas sao:

| Area | Arquivos | LOC adicionados | O que mudou |
|---|---|--:|---|
| **Installer Windows (canonico)** | `install.ps1` (+56) | 56 | Parametros `-SystemService`, `-Repair`, `-Update`, `-Uninstall`, `-InstallPrerequisites`, `-DryRun`; snapshot pre-install; invocacao de `fullstack-readiness.ps1`; novo passo `Invoke-LocalFullCompose` para FalkorDB/Milvus/RAGFlow reutilizando containers existentes; novo passo `services wait` no Node supervisor; `Sync-HiveMindVaultTemplates` substitui copia bruta de templates. |
| **Readiness do full stack** | `scripts/setup/fullstack-readiness.ps1` (novo) | 77 | `Test-HiveMindTcpReadiness`, `Test-HiveMindHttpReadiness`, `Test-HiveMindFullStackReadiness` com politica `Ready` para `local-full` (docker-desktop, milvus, ragflow, falkordb, syncthing-watcher). |
| **Bootstrap protegido** | `scripts/setup/backup-install-state.ps1` (novo) | 72 | `New-HiveMindInstallSnapshot` salva copia do vault + .env + manifests antes da instalacao. |
| **Pos-reboot Windows** | `scripts/health/validate_after_reboot_windows.py` (novo) | 105 | Le `logs/supervisor/state.json` + `manifest.json`; valida `HiveMind-Supervisor` Task Scheduler e servicos required; escreve `logs/post-reboot-validation.json`. Nao usa systemd/procfs. |
| **Modulo PowerShell** | `scripts/lib/HiveMind.Windows.psm1` (+31) | 31 | `Sync-HiveMindVaultTemplates`: materializa templates sem sobrescrever arquivos do usuario. |
| **Supervisor Node** | `npm/lib/supervisor.js` (+67), `npm/lib/services.js` (+5) | 72 | `healthStateTransition`, `requiredServiceHealth`, `waitForRequiredHealthy`; novo subcomando `services wait` no CLI. |
| **Testes do supervisor** | `npm/test/supervisor.test.js` (+80), `npm/test/doctor.test.js` (novo +34) | 114 | Cobrem `waitForRequiredHealthy`, ordem de inicializacao, rollback, `healthStateTransition`. |
| **Release contract** | `scripts/release/validate_package.py` (novo +108) | 108 | Valida que `pyproject.toml`, `npm/package.json`, `core/version.py`, `scripts/services/sinapse-api.py` e `scripts/services/sinapse_mcp.py` concordam na versao e respeitam o piso SemVer `>=3.10`. |
| **Contratos Windows (pytest)** | `tests/unit/test_windows_install_contract.py` (novo +40), `test_windows_runtime_contract.py` (+25) | 65 | Cobre dry-run, Repair+Uninstall mutually exclusive, contrato de profile, sync nao-destrutivo de vault, version_only_3.12, repair only-when-invalid, invocacao de uv provision. |
| **Auditoria** | `tests/helpers/audit_cleanup.py` (novo +145), `tests/unit/test_audit_cleanup.py` (novo +118) | 263 | Detecta e remove skip-flakes no log de audit; relatorio `logs/audit/final-skips-inventory.json`. |
| **Citacoes normalizadas** | `core/retrieval/router.py` (+45), `tests/unit/test_citation_path_normalization.py` (novo +125) | 170 | K5 summary vectors mesclados apos Context Fusion; URI portavel (sem prefixo absoluto do host); `_is_synthesis_query` separa consultas explicitas de sintese. |
| **Recuperação operacional** | `docs/15-windows-clean-install.md` (novo +51), `docs/superpowers/plans/2026-07-13-clean-windows-operational-recovery.md` (novo +271), `docs/superpowers/plans/2026-07-13-clean-windows-operational-recovery-design.md` (novo +25) | 347 | Procedimento de aceitacao, plano de implementacao TDD, design. |
| **Patch de integracao** | `integrations/patches/rtk-umc-logging.patch` (+280) | 280 | Logging do RTK no UMC. |
| **Build / tests** | `pyproject.toml` (+2/-1), `uv.lock` (+2/-1), `tests/conftest.py` (+10) | 14 | Bump para 3.10.1; fixture de profile. |
| **Outros** | `scripts/dream/{daily,monthly,session,yearly}_*.py`, `scripts/knowledge/{drift,generate_mocs,pattern_distiller}.py`, `scripts/health/alert_dispatcher.py`, `scripts/services/sinapse_mcp.py` (+55), `core/memory/writers.py` (+8/-1), `core/telemetry.py` (+2/-1), `core/indexing/vector_jobs_worker.py` (+7), `CHANGELOG.md` (+4), `config/profiles/local-full.env.example` (+3), `tests/...` (~30 ajustes) | ~250 | Ajustes de cadencia, formatacao de timestamps, novos campos em observacoes, atualizacao de snapshots. |

A migracao do control plane **ja foi parcialmente feita** no branch: `install.ps1` ja consome `fullstack-readiness.ps1`, ja valida servicos required antes de concluir, ja bloqueia em `services wait`, ja registra `HiveMind-Supervisor` no Task Scheduler. O que ainda falta e **consolidar o supervisor em Python** (substituir o Node) e **unificar o manifesto declarativo**. O desenho revisado trata disso.


## 3. Mapa real dos scripts no branch correto (d246f0c6)

Apenas arquivos do control plane (nao sao listados `scripts/capture/*`, `scripts/dream/*`, `scripts/knowledge/*`, `scripts/health/*`, `scripts/maintenance/*` cujo conteudo nao sera tocado, nem `integrations/*`):

| Arquivo | LOC | Funcao no control plane | Destino |
|---|--:|---|---|
| `install.sh` | 1319 | 12 passos: deps, uv sync, Graphify source, vault materialization, component bootstrap, MCP register, claude-mem native, RTK build, services install, cron, sinapse-memory plugin, Dreamer LLM, agents, test suites, vault enforcement. | **Mover para `hive_mind.install.linux`**. Encolher para <100 LOC. |
| `install.ps1` | 568 | Idem para Windows; parametros extras: `-SystemService`, `-Repair`, `-Update`, `-Uninstall`, `-InstallPrerequisites`, `-DryRun`, `-PreserveVault`, `-PreserveDatabase`. Chama `fullstack-readiness.ps1` e `services wait`. | **Mover para `hive_mind.install.windows`**. Encolher para <100 LOC. |
| `install.bat` | 5 | Shallow wrapper para chamar `install.ps1`. | Substituido por `hive-mind install`. |
| `setup-brain.bat`, `scripts/setup/setup-brain.bat` | 5 cada | Shallow wrappers para `setup-brain.py`. | `hive-mind brain setup`. |
| `scripts/lib/HiveMind.Windows.psm1` | 388 | Modulo PowerShell com `Get-HiveMindRoot`, `Get-HiveMindPython`, `Test-HiveMindPythonVersion`, `Test-HiveMindPythonRuntime`, `Repair-HiveMindPythonRuntime`, `Ensure-HiveMindPythonRuntime`, `Invoke-HiveMindPython`, `Invoke-HiveMindCommand`, `Read-HiveMindDotEnv`, `Apply-HiveMindProfileContract`, `Set-HiveMindDotEnvValue`, `Import-HiveMindDotEnv`, `New-HiveMindApiKey`, `Ensure-HiveMindDirectory`, `Test-HiveMindCommand`, `Remove-HiveMindOldFiles`, `Sync-HiveMindVaultTemplates`. | **Portar para `hive_mind.platform.windows`** (mesma funcao, snake_case). |
| `scripts/setup/bootstrap-prerequisites.ps1` | 178 | Lista de prereqs (winget id), restart-handling. | `hive_mind.install.prereqs`. |
| `scripts/setup/backup-install-state.ps1` | 72 | `New-HiveMindInstallSnapshot` antes da instalacao. | `hive_mind.install.state.snapshot()`. |
| `scripts/setup/fullstack-readiness.ps1` | 77 | `Test-HiveMindTcpReadiness`, `Test-HiveMindHttpReadiness`, `Test-HiveMindFullStackReadiness`. | `hive_mind.install.readiness.fullstack()`. |
| `scripts/setup/install_services.py` | 1230 | `unit_definitions` (12 services + 15 timers), `service_specs` (7 daemon + 6 external), `launchd_definitions`, `manifest`, `install`, `check`, `arm_post_reboot`, `_install_screenpipe`, `_start_falkordb`, `_configure_claude_mem_settings`, `claude_mem_plugin_path`, `api_enabled`, `validate_runtime`, `_enrich_service_specs`. | **Mover para `hive_mind.daemon.manifest`** e **`hive_mind.platform.{linux,darwin,windows}.systemd_unit/plist/xml`**. |
| `scripts/setup/register-mcp.sh` | 439 | Detecta 12 agents, injeta MCP em 5 formatos JSON + 1 TOML. | `hive_mind.agents.register`. |
| `scripts/setup/register-mcp.ps1` | 454 | Idem para Windows. | Idem. |
| `scripts/setup/setup-brain.sh` / `.ps1` | 5+14 | Shallow wrappers para `setup-brain.py`. | `hive-mind brain setup`. |
| `scripts/setup/setup-brain.py` | 939 | Aplica `HIVE_DREAMER_*` em `.env`. | `hive_mind.install.brain`. |
| `scripts/setup/setup-vault-enforcement.sh` / `.ps1` | 190+101 | chown + systemd drop-in / NTFS ACL. | `hive_mind.install.vault_enforcement`. |
| `scripts/setup/register-windows-jobs.ps1` | 18 | 4 tasks diarias no Task Scheduler. | Substituido por jobs do manifesto. |
| `scripts/setup/register-windows-runtime.ps1` | 15 | 2 tasks AtLogOn. | Substituido por 1 unico WinSW service. |
| `scripts/setup/start-windows-supervisor.ps1` | 7 | `node npm/lib/supervisor.js __daemon`. | Eliminado; daemon e o supervisor. |
| `scripts/setup/apply-hidden-supervisor-task.ps1` | 5 | Reaplica task hidden (VBS). | Eliminado; WinSW ja roda hidden. |
| `scripts/maintenance/install-backup-cron.sh` | 39 | Adiciona 2 entradas no crontab. | Substituido por jobs do manifesto. |
| `scripts/maintenance/install-backup-cron.ps1` | 26 | Idem Task Scheduler. | Idem. |
| `scripts/utils/recover.sh` / `.ps1` | 37+18 | Wrappers para `recovery.py`. | `hive-mind doctor --repair`. |
| `scripts/graph/{build,serve}-graph.{ps1,sh}` | 13+12 | Wrappers para `graphify build/serve`. | `hive-mind graph {build,serve}`. |
| `scripts/services/start-watcher.{ps1,sh}` | 20+24 | Wrappers para `python -m graphify watch`. | **Eliminar**; daemon sobe direto. |
| `scripts/services/start-claude-mem-mcp.{ps1,sh}` | 16+21 | Wrappers para `sinapse-mcp.py`. | **Eliminar**. |
| `scripts/services/start-claude-mem.{ps1,sh}` | 15+6 | Shims -> mcp-server.{ps1,sh}. | **Eliminar**. |
| `scripts/services/mcp-server.{ps1,sh}` | 16+40 | Wrappers para `sinapse-mcp.py`. | **Eliminar**. |
| `scripts/services/claude-mem-watchdog.{ps1,sh}` | 18+25 | Tail + restart. | Substituido por healthcheck + circuit-breaker. |
| `scripts/services/claude-mem-local.{ps1,sh}` | 15+3 | Apenas no PS1: `exec worker-service.cjs`. | Manter **so** como entry-point externo (Node). |
| `scripts/services/neural-memory-local.{ps1,sh}` | 17+12 | `exec .venv/bin/nmem start`. | **Eliminar**. |
| `scripts/services/start-rtk.ps1` | 31 | Compila rtk Rust, configura por agent. | `hive-mind rtk configure`. |
| `scripts/services/start-rtk.sh` | 149 | Idem. | Idem. |
| `scripts/services/claude-mem-local.sh` | 3 | Apenas `exec mcp-server.sh`. | **Eliminar**. |
| `scripts/services/sinapse-api.py` | 819 | API REST. | `hive_mind.services.api`. |
| `scripts/services/sinapse_mcp.py` | 890 | Servidor MCP stdio. | `hive_mind.services.mcp`. |
| `scripts/services/sinapse-mcp-http.py` | n/a | MCP Streamable HTTP. | `hive_mind.services.mcp_http`. |
| `scripts/services/otel_collector.py` | 275 | OTLP local. | `hive_mind.services.otel`. |
| `scripts/services/claude_mem_bridge.py` | n/a | Ponte claude-mem -> UMC. | `hive_mind.services.bridge` (job, nao servico). |
| `npm/bin/hive-mind.js` | 134 | CLI Node: `init`, `init wizard`, `doctor`, `services start/stop/status/restart/wait`, `mcp register`, `update`, `version`, `help`. | Substituido por `hive_mind.cli.main`. |
| `npm/lib/services.js` | 74 | `SYSTEMD_UNITS` hardcoded, `backend()`, `dispatch()`. | Substituido por `hive_mind.daemon.control`. |
| `npm/lib/supervisor.js` | 423 | `loadManifest`, `selectServices`, `topologicalServices`, `probeReadiness`, `waitForReadiness`, `restartDelayMs`, `canRestart`, `healthStateTransition`, `requiredServiceHealth`, `waitForRequiredHealthy`, `daemon()`, `start/stop/status`, state.json, pidFiles. | **Portar para `hive_mind.daemon.supervisor`** (preservar todas as invariantes). |
| `npm/lib/init.js` | 113 | `init()` -> uv sync + supervisor start. | `hive_mind.install.install`. |
| `npm/lib/wizard.js` | 38 | Wizard interativo. | `hive-mind init --wizard`. |
| `npm/lib/platform.js` | 52 | `isWSL`, `homeDir`, `which`. | `hive_mind.platform.detect`. |
| `npm/test/supervisor.test.js` | 157 | Testa `topologicalServices`, `restartDelayMs`, `probeReadiness`, `waitForRequiredHealthy`, `healthStateTransition`, `reconcileServiceState`. | `tests/unit/test_daemon_supervisor.py` (pytest). |
| `npm/test/doctor.test.js` | 34 | Testa `npm/bin/hive-mind.js doctor`. | `tests/unit/test_hive_mind_doctor.py`. |
| `npm/package.json` | n/a | `bin: hive-mind`. | Removido; entry points no `pyproject.toml`. |
| `tests/run_all.{ps1,sh}` | 22+41 | Driver pytest + smoke. | Mantem shell como thin driver. |
| `tests/run_real_knowledge.{ps1,sh}` | 10+81 | Real knowledge suite. | Idem. |
| `tests/smoke/test_smoke.{ps1,sh}` | 34+81 | Smoke binarios no PATH. | Idem. |
| `tests/install/test_windows_bootstrap.ps1` | 65 | Bootstrap Windows contract. | Substituido por `tests/install/test_bootstrap.py` (pytest). |
| `tests/unit/test_windows_install_contract.py` | 294 | Contrato do installer (pytest). | Mantem. |
| `tests/unit/test_windows_runtime_contract.py` | (parcial) | Contrato do runtime Windows. | Mantem. |
| `tests/helpers/audit_cleanup.py` | 145 | Limpa audit log. | Mantem (audit). |
| `tests/release_version_floor.py` / `test_release_validate_package.py` | 31+21 | Gate de release. | Mantem. |

## 4. Responsabilidades atuais

A inspecao confirma 4 control planes paralelos hoje, no worktree d246f0c6:

1. **systemd user units** gerados por `install_services.py::install()` no Linux. 7 services + 15 timers. Habilitados em `default.target`.
2. **Task Scheduler** gerado por `register-windows-jobs.ps1` (4 jobs diarios) + `register-windows-runtime.ps1` (2 tasks AtLogOn).
3. **Node supervisor** em `npm/lib/supervisor.js` (423 LOC). Usado em Windows nativo e quando `HIVE_MIND_SUPERVISOR=1`. Ja tem `waitForRequiredHealthy` no d246f0c6, e o `install.ps1` ja chama `services wait`.
4. **crontab** gerado por `install-backup-cron.sh` para backup-audit e backup-prune.

Os 4 NAO sao exclusivos: no Windows, Task Scheduler (4 jobs) e Node supervisor (servicos) coexistem; no Linux, systemd (servicos+timers) e crontab (backup) coexistem. O `install.ps1` ja exige readiness de servicos required antes de concluir (Gate 4 do plano), mas o scheduler ainda tem **duas origens** no mesmo host.

Adicionalmente, no `local-full`:
- `install.ps1` invoca `Invoke-LocalFullCompose` para 7 containers canonicos (FalkorDB + Milvus + RAGFlow stack) e inicia `syncthing serve` se nao estiver rodando. Tudo via PowerShell.
- `Test-HiveMindFullStackReadiness` probe ate 180s para que 5 servicos external se tornem saudaveis.

Captura de Claude Mem (hooks, adapters, `scripts/capture/*`) NAO sera alterada.

## 5. Empacotamento real e build-system (correcao da secao 10 do desenho v1)

### 5.1. Decisao

**Nao usar `uv tool install .`**. A aplicacao permanece instalada no **ambiente do projeto** (venv local) e o servico de SO aponta para o executavel absoluto dela. Isso preserva o modelo de instalacao atual (que ja funciona com `uv sync` produzindo `.venv`) e isola o daemon de outros pacotes Python do usuario.

### 5.2. Build-system escolhido

**`uv` continua sendo o build-system** (ja em uso, com `uv.lock` pinned). Mudanca minima no `pyproject.toml`:

```toml
[project]
name = "hive-mind"
version = "3.10.1"          # valor atual; NAO mexer nesta revisao
requires-python = ">=3.12,<3.13"

[build-system]
requires = ["hatchling>=1.18"]   # novo: explicito (uv usa hatchling se package=true)
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/hive_mind"]
include = [
    "src/hive_mind/resources/*.md",
    "src/hive_mind/resources/config/*.yaml",
    "src/hive_mind/resources/profiles/*.env.example",
    "src/hive_mind/resources/components.lock.json",
    "src/hive_mind/resources/winsw/*",
    "src/hive_mind/resources/systemd/*",
    "src/hive_mind/resources/launchd/*",
]

[tool.uv]
package = true                 # muda de false para true (com src layout)
# editable = true               # NAO usar editable em service
# mantem sources de integrations/

[project.scripts]
hive-mind = "hive_mind.cli:main"
hive-mindd = "hive_mind.daemon.main:main"
```

Por que hatchling e nao setuptools: ja e o default do `uv build` quando `package=true`; nenhum setup.py adicional; `include` explicito cobre `resources/`.

### 5.3. Configuracao de package discovery

`src/hive_mind/` layout (nao flat-layout). `core/` permanece no **project root** (nao sob `src/`) e e consumido por `hive_mind` via `hatch` config ou `tool.hatch.build.targets.wheel` com `force-include`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"core" = "hive_mind/_core"
```

OU (preferido, menos invasivo) o codigo sob `core/` ganha shims minimos em `hive_mind.core.*` que importam de `core.*`:

```python
# src/hive_mind/core/paths.py
from core.paths import *  # noqa
# (uma unica linha por modulo)
```

Decisao final: **shim minimo**, sem mover `core/` para `src/`. Mantem historico, blame, e PRs de integracoes inalterados.

### 5.4. Como `core/` sera incluido

- `core/` permanece no project root, fora de `src/`.
- Cada modulo `hive_mind.core.X` em `src/hive_mind/core/X.py` faz `from core.X import *`.
- Testes que importam `from core.X` continuam funcionando; testes que passam a usar `from hive_mind.core.X` tambem.
- Periodo de transicao (Fase 1-2): ambos os imports convivem.

### 5.5. Como recursos de config serao incluidos

`src/hive_mind/resources/`:

```
resources/
  sinapse-agent-prompt.md
  sinapse.yaml
  profiles/
    local-min.env.example
    local-full.env.example
  config/
    env.roles.example
    model-gateway.env.example
    model-gateway.yaml
  components.lock.json
  systemd/hive-mindd.service
  launchd/com.hivemind.daemon.plist
  winsw/hive-mindd.exe            # binario, NAO commitado; baixado em install
  winsw/hive-mindd.xml
  shell/completions.bash
  shell/completions.zsh
  shell/completions.fish
```

Acesso em runtime via `importlib.resources.files("hive_mind")`. Em M1 esses arquivos sao **copiados** do local atual (`config/`) e `git mv` nao e necessario ate M8.

### 5.6. Como scripts Python legados serao acessados

`scripts/dream/dream_cycle.py`, `scripts/health/*.py`, `scripts/knowledge/*.py`, `scripts/capture/*.py`, `plugins/sqlite-vec-worker/worker.py` continuam em seus paths atuais. O daemon os invoca como `subprocess` com `sys.executable` apontando para `<root>/.venv/Scripts/python.exe` (Windows) ou `<root>/.venv/bin/python` (Linux/macOS). Sao **consumidores** do scheduler, nao parte do pacote.

`scripts/services/sinapse-api.py`, `sinapse_mcp.py`, `sinapse-mcp-http.py`, `otel_collector.py`, `claude_mem_bridge.py`: na F1 (migracao) o daemon os invoca do path atual. Sao candidatos a `hive_mind.services.*` em F5 (opcional).

### 5.7. Como o project root sera resolvido

```python
# src/hive_mind/platform/paths.py
import os
import sys
from pathlib import Path

def project_root() -> Path:
    'Resolve o root do projeto a partir do caminho do executavel.'
    # Quando executado como `hive-mindd.exe` (Windows) ou `hive-mindd` (Linux),
    # o binario vive em <root>/.venv/Scripts/ ou <root>/.venv/bin/.
    exe = Path(sys.executable).resolve()
    candidates = [exe.parent.parent, exe.parent.parent.parent]
    for c in candidates:
        if (c / "pyproject.toml").is_file() and (c / ".venv").is_dir():
            return c
    # Fallback: env var (definida pelo WinSW / systemd / launchd).
    env = os.environ.get("HIVE_MIND_HOME")
    if env:
        return Path(env).resolve()
    raise RuntimeError("hive-mindd: cannot resolve project root")
```

O servico de SO define `HIVE_MIND_HOME` no EnvironmentFile/EnvironmentVariables, mas o fallback por `sys.executable` funciona mesmo se a env var sumir.

### 5.8. Como uma wheel sera construida e validada posteriormente

`uv build` produz `dist/hive_mind-3.10.1-py3-none-any.whl`. Validacao:

1. `uv build` (gera wheel + sdist).
2. `pip install dist/hive_mind-*.whl --target /tmp/hive-isolated --no-deps` (smoke).
3. `PYTHONPATH=/tmp/hive-isolated python -c "import hive_mind; from hive_mind.cli import main; print(main(['--version']))"`.
4. Verificar entry points: `/tmp/hive-isolated/bin/hive-mind --version`, `/tmp/hive-isolated/bin/hive-mindd --version`.
5. `scripts/release/validate_package.py --source-root .` ja em uso: garante concordancia entre `pyproject.toml`, `npm/package.json` (ate ser removido), `core/version.py`, `scripts/services/sinapse-api.py`, `scripts/services/sinapse_mcp.py`. Estender para ler `hive_mind.__version__` em F1.

A wheel **nao** e distribuida via `uv tool install`; ela e construida para auditoria e empacotamento offline. O fluxo real de instalacao continua sendo `uv sync` no projeto.


## 6. Resolucao do project root

Ver `hive_mind.platform.paths::project_root()` no item 5.7. Resumo:

- **Primario**: `Path(sys.executable).resolve().parent.parent` (sobe de `.venv/Scripts/hive-mindd.exe` para o root).
- **Validacao**: o candidato deve conter `pyproject.toml` e `.venv/`.
- **Fallback**: `HIVE_MIND_HOME` definida pelo servico de SO.
- **Erro fatal**: se nenhum bate, log estruturado e exit 2 antes de fork de qualquer filho.

Tambem sao resolvidos no mesmo modulo:

- `vault_root() -> project_root() / "cerebro"`
- `venv_python() -> project_root() / ".venv" / ("Scripts" if is_windows else "bin") / ("python.exe" if is_windows else "python")`
- `data_dir()`:
  - Windows: `%LOCALAPPDATA%\Hive-Mind` (resolve via `os.environ['LOCALAPPDATA']`; nunca `%APPDATA%`).
  - Linux: `$XDG_STATE_HOME/hive-mind` ou `~/.local/state/hive-mind`.
  - macOS: `~/Library/Application Support/Hive-Mind`.
- `logs_dir() -> data_dir() / "logs"`
- `state_dir() -> data_dir() / "state"`
- `config_user_dir()`: `%APPDATA%/Hive-Mind` no Windows, `~/.config/hive-mind` no Linux, `~/Library/Application Support/Hive-Mind/config` no macOS. Onde o usuario pode opcionalmente editar um `runtime.yaml` de override.

O `cerebro/`, `hive_mind.db` e `~/.claude-mem` continuam no project root (sua localizacao atual). Sao **dados**, nao **estado**. Migrar para `%LOCALAPPDATA%` quebraria a expectativa do usuario; o desenho NAO altera.

## 7. Paths canonicos: config, state, log, data

| Categoria | Windows | Linux | macOS | Conteudo |
|---|---|---|---|---|
| **Codigo** | `<root>` (install path) | `<root>` | `<root>` | repo, `.venv/`, executaveis do venv |
| **Config (template)** | `<root>\config\` | `<root>/config/` | `<root>/config/` | `runtime.yaml` (canonico), `profiles/`, `sinapse.yaml`, `components.lock.json`, `sinapse-agent-prompt.md` |
| **Config (override usuario)** | `%APPDATA%\Hive-Mind\runtime.yaml` (opcional) | `~/.config/hive-mind/runtime.yaml` (opcional) | `~/Library/Application Support/Hive-Mind/config/runtime.yaml` (opcional) | Override nao-destrutivo: campos do usuario prevalecem sobre o template |
| **State** | `%LOCALAPPDATA%\Hive-Mind\state\` | `~/.local/state/hive-mind/` | `~/Library/Application Support/Hive-Mind/state/` | `daemon.pid`, `daemon.sock` (ou `\\.\pipe\hive-mindd`), `services.json`, `jobs.json`, `health.json`, `<service>.pid`, `<service>.log` |
| **Logs** | `%LOCALAPPDATA%\Hive-Mind\logs\` | `~/.local/state/hive-mind/logs/` | `~/Library/Application Support/Hive-Mind/logs/` | `daemon.log`, `daemon.err.log`, `<service>.log`, `jobs/<job>.log` (rotacionados, manter ultimas N=10) |
| **Data (vault)** | `<root>\cerebro\` | `<root>/cerebro/` | `<root>/cerebro/` | vault Obsidian. **NAO mover**. |
| **Data (UMC)** | `<root>\hive_mind.db` | `<root>/hive_mind.db` | `<root>/hive_mind.db` | **NAO mover**. Backup continua hot-copy diario. |
| **Data (claude-mem)** | `%USERPROFILE%\.claude-mem\` | `~/.claude-mem/` | `~/.claude-mem/` | Worker claude-mem e dados por projeto. Multi-host. **NAO mover**. |
| **Data (Syncthing, opcional)** | `%USERPROFILE%\Sync\` (padrao Syncthing) | `~/Sync/` | `~/Sync/` | **NAO mover**. |
| **Config instalacao** | `<root>\.env` | `<root>/.env` | `<root>/.env` | Segredos (HIVE_MIND_API_KEY, GOOGLE_API_KEY, etc.). NAO em state/. |

**Regras**:

1. **State NAO em `logs/`**. Logs podem ser rotacionados/deletados; state tem que sobreviver. Separacao fisica.
2. **Logs em `%LOCALAPPDATA%`, nao em `<root>/logs/`**. O `<root>/logs/install-report.md` continua (artefato de install), mas o daemon NAO escreve mais em `<root>/logs/supervisor/`. Backward-compat: le arquivos antigos por 1 release.
3. **Config (template) versionado no git; config (override) NAO versionado, reside em `%APPDATA%`/`~/.config`**.
4. **Dados (vault, UMC, claude-mem) NAO migram**. Continuam onde estao. Backup continua como antes.
5. **`.env` no root do projeto**, nao em `%APPDATA%`. Operadores editam `.env` no root, e o daemon le de la. Segredos nunca em state/.
6. **Paths podem ser overridados por env**: `HIVE_MIND_STATE_DIR`, `HIVE_MIND_LOG_DIR`, `HIVE_MIND_CONFIG_DIR`. `HIVE_MIND_HOME` ja existe.

## 8. Schema final do manifesto `config/runtime.yaml`

```yaml
# runtime.yaml — Hive-Mind declarative control plane
schema_version: 3
profile: local-min               # local-min | local-full
vault: cerebro
pyproject_root: .                # resolvido em relacao a este arquivo

# ─── Paths (override dos defaults de Secao 7) ───────────────────
paths:
  data_dir: null                 # null = XDG/LOCALAPPDATA default
  state_dir: null
  log_dir: null
  user_config_dir: null
  config_file: null              # null = nao ha override do usuario

# ─── Servicos locais ───────────────────────────────────────────
services:
  - name: sinapse-claude-mem
    description: claude-mem Worker (multi-project data)
    enabled: true
    required: true                 # gate de doctor
    profiles: [local-min, local-full]
    ownership: legacy              # legacy | shadow | managed (definidos em Secao 9.1; use "ownership: shadow" e "ownership: managed" na mesma posicao)
    command: ["python", "-m", "claude_mem.worker"]
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
    healthcheck: null              # null = herda de readiness
    requires_claude_mem_plugin: true
    category: background-service    # ver Secao 14

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
    command: ["python", "-m", "hive_mind.services.api"]
    env_file: .env
    dependencies: [sinapse-sqlite-vec]
    startup_order: 40
    readiness:
      type: http
      url: http://127.0.0.1:37702/api/v1/health
      expected_status: [200, 401]
      timeout_seconds: 60

  - name: sinapse-mcp-http
    command: ["python", "-m", "hive_mind.services.mcp_http"]
    dependencies: [sinapse-api]
    startup_order: 50
    readiness: { type: http, url: http://127.0.0.1:37703/health, expected_status: [200] }

  - name: hive-otel-collector
    command: ["python", "-m", "hive_mind.services.otel", "--host", "127.0.0.1"]
    startup_order: 15
    restart_policy: on-failure

  - name: sinapse-capture-realtime
    command: ["python", "-m", "hive_mind.services.capture_realtime"]
    env_file: .env
    dependencies: [sinapse-claude-mem, sinapse-sqlite-vec]
    startup_order: 60
    restart_policy: always
    category: user-session          # captura, NAO roda em Session 0 (ver Secao 14)

# ─── Servicos externos (apenas health-check) ───────────────────
external_services:
  - name: ollama
    required: true
    profiles: [local-min, local-full]
    readiness: { type: http, url: http://127.0.0.1:11434/api/tags, expected_status: [200] }
  - name: docker-desktop
    required: true
    profiles: [local-full]
    readiness: { type: command, command: ["docker", "info", "--format", "{{.ServerVersion}}"] }
  - name: falkordb
    required: true
    profiles: [local-full]
    dependencies: [docker-desktop]
    readiness: { type: tcp, host: 127.0.0.1, port: 6379, timeout_seconds: 120 }
  - name: milvus
    required: true
    profiles: [local-full]
    dependencies: [docker-desktop]
    readiness: { type: tcp, host: 127.0.0.1, port: 19530, timeout_seconds: 120 }
  - name: ragflow
    required: true
    profiles: [local-full]
    dependencies: [docker-desktop]
    readiness: { type: http, url: http://127.0.0.1:9380/api/v1/system/healthz, expected_status: [200], timeout_seconds: 180 }
  - name: syncthing-watcher
    required: true
    profiles: [local-full]
    readiness: { type: http, url: http://127.0.0.1:8384/rest/noauth/health, expected_status: [200, 401, 403] }
  - name: lightrag
    required: false
    profiles: [local-full]
    readiness: { type: http, url: http://127.0.0.1:9621/health, expected_status: [200] }

# ─── Jobs periodicos (substitui systemd timers + Task Scheduler + crontab) ──
jobs:
  - name: dream-cycle
    command: ["python", "scripts/dream/dream_cycle.py"]
    schedule:
      type: cron
      expression: "0 3 * * *"
      timezone: "America/Sao_Paulo"
      misfire_policy: run_once
      max_instances: 1
    enabled: true
    timeout_seconds: 1800
    retry:
      max_attempts: 0               # 0 = sem retry
    on_failure: log
    category: scheduled-job
    blocking_service: null          # null = roda sem checar readiness

  - name: capture-tailer
    command: ["python", "scripts/capture/capture-tailer.py", "--all", "--scan", "--since-hours", "1"]
    schedule:
      type: interval
      seconds: 30
      run_on_startup: false
      max_instances: 1
    enabled: true
    category: scheduled-job

  # ... 20 outros jobs (vide secao 5 do desenho v1; transicao dos timers atuais)

# ─── Docker compose projects (apenas o que o daemon sobe) ───────
compose_projects:
  - name: falkordb
    file: docker-compose.falkordb.yml
    profiles: [local-full]
    health_check: { type: tcp, host: 127.0.0.1, port: 6379, timeout_seconds: 60 }
  - name: milvus
    file: integrations/milvus/docker-compose.yml
    profiles: [local-full]
    health_check: { type: tcp, host: 127.0.0.1, port: 19530, timeout_seconds: 120 }
  - name: ragflow
    file: integrations/ragflow/docker-compose.yml
    profiles: [local-full]
    health_check: { type: http, url: http://127.0.0.1:9380/api/v1/system/healthz, expected_status: [200], timeout_seconds: 180 }
  - name: langfuse
    file: integrations/langfuse/docker-compose.yml
    profiles: [local-full]
    required: false
    health_check: { type: http, url: http://127.0.0.1:3000/api/public/health, expected_status: [200] }

# ─── Restart policy global ─────────────────────────────────────
restart:
  default_policy: on-failure
  default_delay_seconds: 15
  default_max_delay_seconds: 120
  default_limit: 10
  on_circuit_open: log_and_mark_degraded
```

Validacao: `tests/unit/test_runtime_yaml_schema.py` usa Pydantic v2 para garantir invariantes (deps declaradas, startup_order unico por servico, profiles consistentes, `category` valido). O schema sera **v3** (v1 e v2 estao em uso no supervisor Node). Migracao de v2->v3 adiciona `category` e `ownership`; v1->v3 exige gerador automatico a partir de `unit_definitions`.


## 9. Modelo de ownership: legacy / shadow / managed

A secao 4 do pedido (revisor) e a secao 16 do desenho v1 ja apontavam direcao. Esta secao **define formalmente** os tres estados e o fluxo de transicao.

### 9.1. Os tres estados

| Estado | Significado | Comportamento |
|---|---|---|
| `legacy` | O sistema antigo continua executando. **O daemon NAO toca.** | Daemon apenas observa (le `state.json` do supervisor Node se existir, le saida de `systemctl list-units --user sinapse*` se existir, le `schtasks /Query` se existir). Nao inicia, nao para, nao sobe job, nao escreve no manifesto. |
| `shadow` | Daemon **le** o manifesto, calcula dependencias, executa readiness, calcula schedules, compara estado. **NAO** inicia servico, **NAO** executa job. | A cada tick, log `shadow: <service> expected=healthy actual=degraded reason=...`. Util para validar que o daemon teria agido corretamente. |
| `managed` | Servico ou job legado foi desabilitado. Daemon assume 100%. | Aciona restart, agenda, health check, circuit-breaker. |

### 9.2. Fluxo de cutover (obrigatorio)

```
shadow (validado >= 24h sem falsos positivos)
  --> comando explicito: hive-mind service adopt <name> --from legacy --to managed
  --> daemon:
       1. Verifica que <name> esta em shadow e validado.
       2. Le pid atual do legado (systemctl/schtasks/launchctl/Node supervisor).
       3. stop --now (systemctl) / Stop-ScheduledTask (Task Scheduler) / unload (launchd) / supervisor.stopOne(name) (Node).
       4. wait ateh pid morto (max 30s, depois SIGKILL / taskkill /F / kill -9).
       5. Marca ownership: managed. Persiste em runtime.yaml.
       6. Inicia via managed.
       7. waitForReadiness(timeout).
       8. Se OK: ok. Se NAO: rollback automatico.
```

### 9.3. Rollback automatico de cutover

```
managed startup falhou (readiness timeout / crash loop / circuit-open)
  --> daemon:
       1. Para managed (kill tree).
       2. Re-habilita legacy: systemctl start (Linux) / schtasks /Run (Windows) / launchctl load (macOS) / supervisor.startOne(name) (Node).
       3. waitForReadiness legacy.
       4. Marca ownership: legacy.
       5. Log rollback: <name> cutover reverted after Ns.
       6. Notifica via health_dashboard (M10).
```

### 9.4. Garantia: zero dupla-execucao

A frase canonica do item 4 do pedido de revisao e a regra de proibicao absoluta:

> Nunca manter dois watchers, dois schedulers ou dois Dream Cycles ativos simultaneamente.

Isso e verificado em teste de smoke `tests/integration/test_exclusive_ownership.py` antes de qualquer cutover para managed.

- Antes de iniciar managed, daemon **garante** que o legado morreu: `pid dead AND port free AND (servico especifico) state==stopped`.
- No caso de Task Scheduler, alem do `Stop-ScheduledTask`, daemon verifica que nao ha Trigger registrado: `schtasks /Query /TN <name> /XML | grep <trigger>` deve ser vazio.
- No caso de crontab, daemon comita `# hive-mind-disabled` na linha e roda `crontab -` para recarregar.
- No caso de Node supervisor, daemon le `state.json` e `checa pid`; se pid esta vivo e nao e filho do daemon, `supervisor.stopOne(name)`.

### 9.5. Estado inicial por servico

| Servico | d246f0c6 | F1 (M1-M2) | F4 (cutover) |
|---|---|---|---|
| sinapse-claude-mem | legacy (systemd/sheduled/Node) | legacy | managed (apos M5) |
| sinapse-sqlite-vec | legacy | legacy | managed |
| sinapse-graphify-watch | legacy | legacy | managed |
| sinapse-api | legacy | legacy | managed |
| sinapse-mcp-http | legacy | legacy | managed |
| hive-otel-collector | legacy | legacy | managed |
| sinapse-capture-realtime | legacy | shadow (validar 24h) | managed |
| sinapse-capture-tailer (job) | legacy (Task Scheduler) | shadow (validar 24h) | managed |
| Todos os outros 18 jobs | legacy (systemd timer/Task Scheduler/crontab) | shadow (validar 24h) | managed (um por vez) |

`sinapse-capture-realtime` comeca em **shadow** ja em M3, porque e stateless restartavel. Os outros 6 services vao em **managed** direto na F4 (cutover nao-critico).

## 10. Modelo de processos e contencao

### 10.1. Arvore de processos

```
hive-mindd (PID 1 do servico, user session)
  +-- sinapse-claude-mem
  +-- sinapse-sqlite-vec
  +-- sinapse-graphify-watch
  +-- sinapse-api
  +-- sinapse-mcp-http
  +-- hive-otel-collector
  +-- sinapse-capture-realtime
  +-- [ad-hoc subprocess para jobs]
```

Todos filhos sao processos diretos de `hive-mindd` (herdam `os.setpgrp` no Unix, Job Object no Windows). O daemon NAO usa `subprocess.Popen` sem `start_new_session=True` (Unix) ou `creationflags=CREATE_NEW_PROCESS_GROUP` (Windows).

### 10.2. Conetencao: Windows (Job Objects)

```python
import ctypes
from ctypes import wintypes

def create_job_object():
    job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
    info = ctypes.create_string_buffer(1024)
    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("LimitFlags", wintypes.DWORD), ("...", ctypes.c_ulong * 8)]
    info = JOBOBJECT_BASIC_LIMIT_INFORMATION()
    info.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ctypes.windll.kernel32.SetInformationJobObject(job, 2, ctypes.byref(info), ctypes.sizeof(info))
    return job

def assign_to_job(pid, job):
    hprocess = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, pid)
    ctypes.windll.kernel32.AssignProcessToJobObject(job, hprocess)
    ctypes.windll.kernel32.CloseHandle(hprocess)
```

Quando `hive-mindd` termina, o Job Object fecha, e **todos** os filhos sao terminados em cascata. Resolve o problema classico do Windows Service de deixar filhos orfaos na Session 0.

### 10.3. Conetencao: Linux / macOS (process group)

```python
import os, subprocess
proc = subprocess.Popen(
    cmd,
    start_new_session=True,   # novo process group + session
    preexec_fn=os.setsid,     # redundante, mas explicito
)
```

`os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` mata o grupo inteiro no shutdown. Timeout de 30s, depois SIGKILL no grupo.

### 10.4. Shutdown

1. `SIGTERM` (Linux/macOS) / `Stop-Service` (Windows) recebido pelo daemon.
2. Persistir state.json final.
3. Marcar todos servicos como `stopping`.
4. Iterar em **ordem inversa de startup_order**: SIGTERM ao grupo (Linux/macOS) / TerminateProcess (Windows).
5. Esperar ate 30s por pid morto.
6. SIGKILL/TerminateProcess forcado.
7. Fechar Job Object (Windows) / matar process group residual (Linux/macOS).
8. Exit 0.

### 10.5. Falha de filho

- Se filho morre antes de `waitForReadiness`, marcar como `failed` e (se `restart_policy=on-failure`) tentar de novo com backoff.
- Apos `restart_limit` falhas em 1h, abrir circuit-breaker, marcar como `degraded`. **Nao** levantar mais ate `hive-mind service reset <name>` ou ate `restart_max_delay_seconds` passar.

### 10.6. Orfaos

- Linux/macOS: `start_new_session=True` garante novo pgid. Daemon eh o unico no pgid pai. `killpg` no shutdown cobre todos.
- Windows: Job Object cobre. `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` garante cascata.
- Verificacao em teste: `tests/unit/test_containment.py` faz fork de 1 daemon com 3 filhos, mata o daemon, valida que todos os 3 morreram em <= 5s.

## 11. Modelo de scheduler (correcao da secao 13 do desenho v1)

### 11.1. Decisao

**Usar APScheduler** (ja consolidado, em `pyproject.toml` nao esta: sera adicionado como `apscheduler>=3.10,<4.0` em F1). **Nao** implementar parser proprio de `OnCalendar=`.

APScheduler expoe:
- `CronTrigger` com `timezone`, `misfire_grace_time`, `coalesce`, `max_instances`.
- `IntervalTrigger` com `seconds`, `start_date`, `end_date`.
- `BaseScheduler` com `add_job`, `remove_job`, `pause`, `resume`, `get_jobs`.

### 11.2. Schema no manifesto (ja em Secao 8)

```yaml
schedule:
  type: cron                       # cron | interval | date
  expression: "0 3 * * *"          # para cron
  timezone: "America/Sao_Paulo"    # IANA; default = local
  misfire_policy: run_once         # run_once | run_many | skip
  max_instances: 1                 # coalescing explicito
```

Para intervalos:

```yaml
schedule:
  type: interval
  seconds: 30
  run_on_startup: false            # se true, dispara ao subir o daemon
  max_instances: 1
```

### 11.3. Parametros explicitos definidos (todos no schema)

| Parametro | Onde | Valores | Default |
|---|---|---|---|
| `timezone` | `schedule` | IANA tz | sistema |
| DST | via `apscheduler.triggers.cron.CronTrigger` que respeita DST automaticamente | - | - |
| `misfire_policy` | `schedule` | `run_once` (default), `run_many`, `skip` | `run_once` |
| `coalescing` | implicito em `max_instances=1` | - | `1` |
| `max_instances` | `schedule` | int | `1` |
| `timeout_seconds` | `jobs[]` | int | `3600` |
| `retry.max_attempts` | `jobs[]` | int | `0` (sem retry) |
| `retry.backoff_seconds` | `jobs[]` | int | `30` |
| `locking` | interno (JobStore `MemoryJobStore` por padrao; opcional `SQLAlchemyJobStore` se `state_dir/jobs.db` existir) | - | `memory` |
| `on_failure` | `jobs[]` | `log` (default), `mark_degraded`, `escalate` | `log` |

### 11.4. Persistencia

- Por padrao, `MemoryJobStore` (in-process). Perde schedule apos restart, mas daemon no boot le `state_dir/jobs.json` e re-agenda.
- Opcionalmente, `SQLAlchemyJobStore` apontando para `state_dir/jobs.db` (SQLite). Mantem schedules e run history entre reboots. Configuravel por `paths.state_dir/jobs_db: true`.
- `state_dir/jobs.json` (escrito a cada conclusao de job) contem: `last_run`, `next_run`, `last_status`, `last_exit_code`, `last_duration_seconds`, `last_error`, `consecutive_failures`. Atomic write.

### 11.5. Migracao dos timers atuais

Cada `*.timer` em `install_services.py::unit_definitions()` vira 1 entrada `jobs:` com:
- `OnCalendar=*-*-* 03:00:00` -> `cron: "0 3 * * *"`.
- `OnCalendar=Sun 04:00` -> `cron: "0 4 * * 0"`.
- `OnCalendar=*-*-01 02:00:00` -> `cron: "0 2 1 * *"`.
- `OnBootSec=30s;OnUnitActiveSec=30s` -> `interval: seconds=30, run_on_startup=false`.
- `OnCalendar=*-01-01 01:00` -> `cron: "0 1 1 1 *"`.

Tabela de equivalencia em `tests/unit/test_scheduler_translation.py` (1:1 com os 15 timers atuais + 4 jobs do `register-windows-jobs.ps1` + 2 do `install-backup-cron.sh`).

### 11.6. Interacao com readiness

```python
def job_decorator(svc, job, fn):
    @functools.wraps(fn)
    def wrapper():
        for dep in (job.blocking_service or []):
            if svc.services[dep].state != "healthy":
                raise ServiceNotReady(dep)
        return fn()
    return wrapper
```

Apos conclusao (sucesso ou falha), `state_dir/jobs.json` e atualizado. Fim.


## 12. Modelo Docker

### 12.1. Decisao

`install.ps1` ja implementa o conjunto canonico para `local-full` no branch d246f0c6. **Manter e estender**:

- `invoke-LocalFullCompose -Name "FalkorDB" -ComposeFile docker-compose.falkordb.yml -ContainerNames @("sinapse-falkordb")`
- `invoke-LocalFullCompose -Name "Milvus" -ComposeFile integrations/milvus/docker-compose.yml -ContainerNames @("hive-mind-milvus")`
- `invoke-LocalFullCompose -Name "RAGFlow" -ComposeFile integrations/ragflow/docker-compose.yml -ContainerNames @("hive-mind-ragflow-mysql", "es01", "redis", "minio", "hive-mind-ragflow")`

Reuso: se **todos** os containers existem, `docker start` em cada um. Se **alguns** existem, **falha explicita** (instrui o usuario a resolver). Se **nenhum** existe, `docker compose up -d`.

O daemon (F8) **nao** chama `docker compose` diretamente; em vez disso, importa a mesma logica em Python (`hive_mind.docker.orchestrator.reuse_or_up`) e adiciona `wait_healthy` ate a politica estar satisfeita.

### 12.2. Comportamento "container running" NAO conta como healthy

Ja garantido: `Test-HiveMindTcpReadiness` (porta TCP) e `Test-HiveMindHttpReadiness` (endpoint com status code esperado) sao obrigatorios. O `install.ps1` ja chama `Test-HiveMindFullStackReadiness` com timeout de 180s e aborta o install se qualquer servico required nao responder.

### 12.3. Repair

- A cada tick de 5min, daemon verifica `compose_projects`. Se um container esta `unhealthy` (Docker healthcheck reported unhealthy), chama `docker compose restart <service>`.
- Apos 2 restarts, `docker compose pull <service>` + `docker compose up -d <service>`.
- Apos 3 tentativas falhadas em 30min, marca compose project como `failed` e notifica via `health_dashboard.py`.

### 12.4. Portabilidade

Identica a do desenho v1: Docker Engine (Linux), Docker Desktop (macOS, Windows via WSL2). `docker compose` (Compose V2) no PATH. Nenhum codigo novo precisa diferenciar.

## 13. Estrategia Windows Service (correcao da secao 6 do desenho v1)

### 13.1. Comando de entrada do daemon

```text
hive-mindd run
```

O daemon **permanece em foreground**. Nao faz `daemon()` (no-fork). O sistema operacional e responsavel por iniciar, parar e reiniciar.

`hive-mindd` aceita tambem (sub-comandos):

```text
hive-mindd start    # alias para "run"; mantem compat com npm supervisor
hive-mindd stop     # envia SIGTERM (ou PostMessage no Windows) ao PID do daemon
hive-mindd status   # consulta via control socket; imprime resumo
hive-mindd reload   # re-le runtime.yaml
hive-mindd validate # roda doctor e sai
hive-mindd run-job <name>  # executa 1 job (testes)
hive-mindd post-reboot    # executa validate_after_reboot_windows.py (Windows)
hive-mindd register       # cria o servico nativo (WinSW / systemd / launchd)
hive-mindd unregister
```

### 13.2. Sub-comandos de gestao de servico (separados do daemon)

```text
hive-mind service install    # chama hive-mindd register
hive-mind service uninstall  # chama hive-mindd unregister
hive-mind service start      # controle via socket: startAll
hive-mind service stop       # controle via socket: stopAll
hive-mind service status     # controle via socket: listAll
```

### 13.3. Identidade do Windows Service (correcao do ponto 7 do pedido)

**Checklist canonico de acesso** (a verificar antes de habilitar managed no Windows):

| Recurso | Default (current user) | Producao (dedicated) | Notas |
|---|---|---|---|
| `%USERPROFILE%` (home) | sim | sim | `hive-mind-svc$` precisa ACL `Modify` |
| `%USERPROFILE%\.claude-mem\` | sim | sim | Worker claude-mem grava aqui |
| Vault `<root>\cerebro\` | sim | sim | ACL `Modify` para `hive-mind-svc$`, `Read` para usuario humano (VSCode/Obsidian) |
| Workspace | sim | sim | Dono do diretorio do projeto |
| Configuracoes dos agentes | sim | sim | `~/.claude/`, `~/.codex/`, etc. |
| Docker Desktop | usuario em `docker-users` | adicionar `hive-mind-svc$` em `docker-users` via `Add-LocalGroupMember` | named pipe `\\.\pipe\docker_engine` |
| Ollama | usuario roda `ollama serve` | `hive-mind-svc$` em `Ollama` ACL; `ollama serve` em Task Scheduler AtLogOn do usuario | HTTP `127.0.0.1:11434` |


#### 13.3.1. Por que NAO `LocalSystem`

`LocalSystem` nao tem acesso a:
- `%USERPROFILE%\.claude-mem\` (precisa de per-fil).
- `%USERPROFILE%\.ollama\` (modelos baixados pelo usuario).
- `C:\\Users\\<user>\\AppData\\Local\\Docker\` (Docker Desktop persiste credenciais aqui).
- `C:\\Users\\<user>\\AppData\\Local\\Programs\\Ollama\` (binario).
- `C:\\Users\\<user>\\AppData\\Local\\Microsoft\\WindowsApps\\` (winget CLI).
- Variaveis de ambiente do usuario: PATH do usuario, GOPATH, NVM_DIR, CARGO_HOME.
- **Nao pode** acessar Syncthing, vault, workspace, sem ACLs explicitas em cada path.

#### 13.3.2. Solucao: servico por usuario (gMSA nao atende consumer)

1. **Modo "current user"** (default, dev / single-user):
   - WinSW XML: `<serviceaccount><domain>\<user></domain></serviceaccount>` com `<password>` (NUNCA plain text; usar `<passwordpromptmode>credential</passwordpromptmode>` + `hive-mindd.exe password` ou vault).
   - Alternativa mais simples: registrar via `sc.exe create <name> binPath= ... obj= "<domain>\<user>" password= <prompt>`.
   - **Para o branch: nao registrar automaticamente com senha.** `install.ps1 -SystemService` chama `Register-HiveMindUserService` que:
     1. Detecta `$env:USERNAME` e `$env:USERDOMAIN`.
     2. Pergunta interativamente: "Hive-Mindd will run as you ($env:USERNAME). Confirm?"
     3. Usa `cmdkey` para armazenar credencial, e WinSW `<passwordpromptmode>store</passwordpromptmode>` (WinSW >= 2.12).
     4. `sc.exe create hive-mindd binPath= "<root>\.venv\Scripts\hive-mindd.exe run" obj= "$env:USERDOMAIN\$env:USERNAME" password= <cmdkey>`.

2. **Modo "dedicated service user"** (producao / multi-user):
   - Provisiona conta local `hive-mind-svc$` (ou AD) sem privilegio de login interativo, com `SeServiceLogonRight`.
   - Owner de `%LOCALAPPDATA%\Hive-Mind\` e `%USERPROFILE%\.claude-mem\` (em `setup`).
   - Secrets (GOOGLE_API_KEY, HIVE_MIND_API_KEY) em Windows Credential Manager, acessiveis por `hive-mind-svc$`.
   - Vault (`cerebro/`) com ACL `hive-mind-svc$ : Modify` + `Users : Read` + `SYSTEM : Full`.

3. **Permissoes necessarias** (ACLs):
   - `%USERPROFILE%\.claude-mem\`: `Modify` para o usuario do servico.
   - `<root>\cerebro\`: `Modify` para o usuario do servico + `Read` para o usuario humano que usa VSCode/Obsidian.
   - `%LOCALAPPDATA%\Hive-Mind\state\`: `Modify` para o usuario do servico.
   - `%LOCALAPPDATA%\Hive-Mind\logs\`: `Modify` para o usuario do servico.
   - `C:\Users\<user>\.ollama\`: `Modify` (para pre-warm dos modelos).
   - `C:\Program Files\Docker\Docker\`: ja tem ACL padrao para usuario do servico (Docker Desktop gerencia).

4. **Credenciais**:
   - NUNCA plain text em WinSW XML.
   - WinSW `<passwordpromptmode>credential</passwordpromptmode>` referencia Windows Credential Manager. A credencial e gravada em `%LOCALAPPDATA%\Hive-Mind\state\.wincred` (apenas se o usuario confirmar; recomendado: usar `cmdkey /generic:hive-mindd-svc /user:<user> /pass:<pass>`).
   - API keys (`HIVE_MIND_API_KEY`, `GOOGLE_API_KEY`) no `.env` em `<root>\.env`, NAO no WinSW XML. `.env` ja tem ACL `Modify` para o usuario do servico.

5. **Diretorios**:
   - `state` em `%LOCALAPPDATA%\Hive-Mind\state\` (default; override via `HIVE_MIND_STATE_DIR`).
   - `logs` em `%LOCALAPPDATA%\Hive-Mind\logs\`.
   - `data` (vault + UMC) em `<root>\` (sem mudar).
   - Lock em `state\daemon.pid`.

6. **Docker Desktop**:
   - Docker Desktop escuta em `\\.\pipe\docker_engine`. O named pipe tem ACL padrao que permite usuarios do mesmo grupo `docker-users`. Adicionar `hive-mind-svc$` a `docker-users` automaticamente em `install.ps1 -SystemService`:
     ```powershell
     Add-LocalGroupMember -Group "docker-users" -Member "hive-mind-svc$" -ErrorAction SilentlyContinue
     ```
   - Em modo "current user", o usuario ja esta em `docker-users` (senao Docker Desktop nao funcionaria).
   - O daemon sobe o Docker Compose com `docker compose ...`; o named pipe ja lida com auth.

7. **Ollama**:
   - Ollama escuta em `http://127.0.0.1:11434` (default). Nao usa named pipe; ACL de processo cuida.
   - O usuario do servico precisa poder **iniciar** ollama. Em Windows, Ollama nao e Windows Service ainda. Alternativas:
     - Usuario inicia Ollama manualmente; daemon so checa readiness.
     - `hive-mindd --register` adiciona `ollama serve` ao Task Scheduler do usuario (AtLogOn), NAO ao servico.

8. **Shutdown**:
   - WinSW recebe `Stop-Service` do SCM, envia CTRL_BREAK_EVENT ao processo `hive-mindd`.
   - `hive-mindd` intercepta, executa Secao 10.4 (kill de filhos com timeout 30s), persiste state, exit 0.
   - Apos 60s sem exit, WinSW faz TerminateProcess (forcado).

9. **Atualizacao**:
   - `hive-mind update` faz `git pull && uv sync` e reinicia o servico.
   - SCM `sc.exe stop hive-mindd` -> WinSW -> CTRL_BREAK_EVENT -> daemon faz shutdown limpo.
   - Apos 60s sem exit, sc.exe force-kill.
   - `hive-mindd` reinicia automaticamente via SCM (Restart=on-failure com 15s).

10. **Secrets no XML**:
    - NAO colocar `Environment=GOOGLE_API_KEY=...` em WinSW XML.
    - Ler de `<root>\.env` em runtime (`os.environ` carregado no boot).
    - WinSW `<env>` so para **paths** e **flags** (HIVE_MIND_HOME, PYTHONPATH, PYTHONUTF8).

## 14. Componentes interativos: classificacao

### 14.1. As 5 categorias

| Categoria | Descricao | Quem sobe | Onde roda |
|---|---|---|---|
| `background-service` | Stateless, sem GUI, restartavel. | `hive-mindd` (managed) | Windows Service / systemd / launchd |
| `user-session` | Acessa display, hooks de IDE, clipboard, OAuth flow. | **NAO** pelo daemon. Registrado separadamente no user session (Task Scheduler AtLogOn, launchd user agent). | User session (NAO Session 0) |
| `hook` | Scripts chamados por IDE em pre/post tool. | Pelo proprio IDE (NÃO pelo daemon). | Subprocess do IDE |
| `external-container` | Docker. | `hive-mindd` (compose_orchestrator) | Docker engine |
| `scheduled-job` | Job periodico. | `hive-mindd` (scheduler APScheduler) | Herda categoria do servico (background-service ou user-session) |

### 14.2. Classificacao por componente

| Componente | Categoria | Roda em Session 0? | Notas |
|---|---|---|---|
| `sinapse-claude-mem` | background-service | sim | Worker Node, sem GUI. |
| `sinapse-sqlite-vec` | background-service | sim | Python, FastAPI. |
| `sinapse-graphify-watch` | background-service | sim | Watcher, sem GUI. |
| `sinapse-api` | background-service | sim | FastAPI, sem GUI. |
| `sinapse-mcp-http` | background-service | sim | MCP HTTP, sem GUI. |
| `hive-otel-collector` | background-service | sim | OTLP, sem GUI. |
| `sinapse-capture-realtime` | user-session | **NAO** | Watch de filesystem com `watchdog`. **NAO** roda em Session 0 (perde eventos em alguns paths de rede). Roda como **user session** (Task Scheduler AtLogOn). |
| `scripts/capture/claude-mem-hook.{ps1,sh}` | hook | n/a | Chamado por Claude Code. NAO mexer. |
| `scripts/capture/copilot-wrapper.{ps1,sh}` | hook | n/a | Chamado por Copilot. NAO mexer. |
| `ollama` (binario) | external | n/a | Manual / startup logon do usuario. |
| `docker-compose.*.yml` | external-container | n/a | Docker Desktop. |
| `syncthing` (binario) | user-session | **NAO** | Sync de vault; precisa de credenciais do usuario. |
| 18 jobs (dream, daily, weekly, ...) | scheduled-job | herda | dream roda em Session 0; capture-tailer roda em user session; health/audit/backup rodam em Session 0. |

### 14.3. Como o daemon distingue

O daemon **nao** inicia componentes `user-session`. Eles sao registrados **separadamente** (em F9, pelo adapter do SO) como:
- Windows: Task Scheduler AtLogOn com `<UserContext>Interactive</UserContext>`.
- macOS: LaunchAgent `RunAtLoad=True` (ja roda no user session).
- Linux: systemd **user** unit `WantedBy=default.target` (ja roda no user session).

Componentes `user-session` que rodem em background **nao compartilham o socket de controle** do daemon managed. Eles tem seu proprio contrato (HTTP/127.0.0.1, socket de user). Se o daemon managed falhar, user-session continua (e vice-versa). Captura de Claude Mem **nao** e alterada.

### 14.4. Captura de Claude Mem: NAO MEXER

- `scripts/capture/claude-mem-hook.{ps1,sh}` sao hooks chamados pelo Claude Code. NAO devem ser movidos, renomeados, ou reescritos.
- `scripts/capture/copilot-wrapper.{ps1,sh}` sao hooks para Copilot. Idem.
- `scripts/capture/{capture-realtime,capture_core,capture_sources,capture_queue}.py` continuam em `scripts/capture/`. O daemon os invoca como subprocess se/quando em `managed`.
- `capture-realtime.py` e classificado como `user-session` (Secao 14.2). NAO roda em Session 0.


## 15. Controle seguro (correcao do ponto 9 do pedido)

### 15.1. HTTP loopback exposto pelo daemon

As 3 rotas explicitas e a unica coisa que o HTTP exposto faz:

- `GET /health` -> `{"state": "healthy", "services": {...}, "jobs": {...}}`
- `GET /ready` -> 200 se todos servicos `required: true` estao `healthy`; 503 caso contrario.
- `GET /metrics` -> Prometheus-style (`hive_service_starts_total{name=...}`).

Bind em `127.0.0.1:37780`. Sem TLS, sem autenticacao, sem body de write. Loopback e considerado confiavel; mutacoes passam pelo control socket ACL (Secao 15.2).

```text
GET  /health   -> {"state": "healthy", "services": {...}, "jobs": {...}}
GET  /ready    -> 200 se todos required estao healthy; 503 caso contrario
GET  /metrics  -> Prometheus-style (counters: hive_service_starts_total{name=...})
```

Bind em `127.0.0.1:<port>` (default `127.0.0.1:37780`). **Sem TLS, sem auth, sem qualquer body**, porque loopback e considerado confiavel.

### 15.2. Controle: named pipe / Unix socket, NAO HTTP

| Operacao | Canal |
|---|---|
| `hive-mind service start\|stop\|restart` | Named pipe `\\.\pipe\hive-mindd` (Windows) ou Unix socket `state_dir/daemon.sock` (Linux/macOS) |
| `hive-mind service status` | Mesmo |
| `hive-mind service install\|uninstall` | Mesmo (mas pode pedir confirmacao; so aceita de usuario local) |
| `hive-mindd reload` | Mesmo |
| `hive-mindd run-job <name>` | Mesmo |
| `GET /health\|/ready\|/metrics` | HTTP loopback (so leitura) |

### 15.3. ACL dos canais de controle

- **Windows named pipe**:
  ```python
  import win32security, win32api
  sd = win32security.SECURITY_DESCRIPTOR()
  sd.Initialize()
  user, domain, _ = win32security.LookupAccountName("", win32api.GetUserName())
  sid = win32security.GetSecurityInfo(user, ...).GetSecurityDescriptor()
  sd.SetSecurityDescriptorOwner(user, False)
  ace = win32security.ACCESS_ALLOWED_ACE()
  ace.AccessMask = 0x001F0003  # GENERIC_READ | GENERIC_WRITE | GENERIC_EXECUTE
  ace.Sid = sid
  dacl = win32security.ACL()
  dacl.AddAccessAllowedAce(win32security.ACL_REVISION, ace.AccessMask, ace.Sid)
  sd.SetDacl(True, dacl, False)
  ```
  Resultado: apenas o usuario que instalou o servico pode abrir o pipe. Outros usuarios recebem `ACCESS_DENIED` (0xC0000022).

- **Unix domain socket**:
  - Permissoes do arquivo: `0o660` com grupo `<user>`.
  - Diretorio: `state_dir/` com `0o700`.
  - Se o usuario for root e o servico roda como root, restringir a `wheel` group.
  - Validar `SO_PEERCRED` no server: o cliente precisa ter o mesmo uid.

### 15.4. NAO expor start/stop/restart/reload por HTTP

`http://127.0.0.1:37780/` NAO tem `POST /start`, `POST /stop`, `POST /reload`, `POST /run-job`. Qualquer tentativa retorna 404. Toda mutacao passa pelo canal de controle autenticado (named pipe / Unix socket).

A constante:
```python
READ_ONLY_HTTP_ROUTES = {"/health", "/ready", "/metrics"}
```

Em F4, teste `tests/unit/test_daemon_http_routes.py` enumera todas as rotas e falha se houver alguma que NAO esteja em `READ_ONLY_HTTP_ROUTES` e que NAO comece com `/docs` ou `/openapi.json` (para o FastAPI). Mutacoes = 0 rotas no FastAPI. Mutacoes = so no control socket.

## 16. Plano de migracao corrigido (12 fases, cutover exclusivo, rollback automatico)

### 16.1. Visao geral

| Fase | Escopo | Ownership final | Reversivel? | Gate |
|---:|---|---|---|---|
| 1 | Pacote e entry points, sem mudar runtime | legacy em 100% | sim (sem deploy) | `hive-mind --version`; `hive-mindd --version`; `pyproject.toml` com `package=true`; `uv build`; wheel funcional. |
| 2 | Manifesto extraido do codigo atual (`hive-mind config validate`) | legacy | sim | `hive-mind config show` reproduz o que `unit_definitions()` produz hoje. |
| 3 | Daemon em **shadow** (le manifesto, calcula deps, readiness, schedules, **NAO** inicia servico, **NAO** roda job) | shadow | sim (kill -9 o daemon) | 24h sem alertas spurios. `hive-mind doctor` verde. |
| 4 | Cutover **exclusivo** de 1 servico nao-critico: `sinapse-capture-realtime` (ja classificado como `user-session` no manifesto, mas pode rodar em managed) | managed para capture-realtime; resto legacy | sim (rollback automatico) | 7 dias `healthy`. Readiness verde. |
| 5 | Cutover dos demais 6 servicos daemon, **um por vez**, com 48h de soak entre eles | managed para todos os 7; legacy ainda configurado mas parado | sim | 7 dias `healthy` em todos. |
| 6 | Scheduler em **shadow** (calcula schedules, **NAO** dispara job) | legacy ainda ativo | sim | 24h comparando schedules calculados vs. systemd/timer. |
| 7 | Cutover de jobs **um por vez** (dream-cycle primeiro, depois daily, weekly, ...) com 7 dias de soak | managed para o job; legacy parado | sim | 14 dias `healthy` no dream-cycle (que e o mais sensivel). |
| 8 | Docker orchestration em **shadow** (calcula `docker compose up`, **NAO** executa) | legacy ainda | sim | 24h. |
| 9 | Adapters de SO (WinSW / systemd / launchd) registram `hive-mindd` no SO | managed (daemon e o servico nativo) | sim | 1 reboot com `hive-mindd` iniciando. |
| 10 | Instaladores finos (`install.sh` / `install.ps1` / `install.bat` < 100 LOC) | managed | sim | install fresco em Linux, Windows, macOS. |
| 11 | Remocao dos scripts legados (`install_services.py::unit_definitions`, `register-windows-jobs.ps1`, `register-windows-runtime.ps1`, `register-mcp.{ps1,sh}` -> Python, `install-backup-cron.{ps1,sh}`, wrappers de `scripts/services/*`, `npm/`, ...) | managed | **NAO** (git revert se necessario) | grep nao acha referencias. `tests/unit/test_legacy_removal.py` verde. |
| 12 | Clean install em maquina virgem + reboot + post-reboot + rollback test | managed | sim | `hive-mind install --profile=local-min` (e `--profile=local-full`) em CI Linux/Windows/macOS. `hive-mindd post-reboot` verde. `tests/install/test_clean_install.py` verde. |

### 16.2. Fluxo de cutover (Fase 4 a 7 e 9)

```
fase de preparacao (>= 7 dias)
  - daemon em shadow
  - servico legado continua rodando
  - daemon le o state atual, loga "would-start <name> if managed"
  - alarme: 0 discrepancias entre shadow e real
  - decisao humana: "go"

comando explicito (humano):
  hive-mind service adopt <name> --from legacy --to managed
    [--wait-healthy-seconds=120]
    [--rollback-on-failure=true]

daemon:
  1. Verifica que <name> esta em shadow e validado.
  2. Captura PID do legado (systemctl --user show <name> / schtasks /Query / supervisor state.json).
  3. stop --now (systemctl) / Stop-ScheduledTask (Task Scheduler) / unload (launchd) / supervisor.stopOne(name) (Node).
  4. wait ate PID morto (max 30s, depois SIGKILL / taskkill /F / kill -9).
  5. wait ate port free (max 5s).
  6. Marca ownership: managed. Persiste em runtime.yaml (atomic write).
  7. Inicia via managed.
  8. waitForReadiness(timeout=120s).
  9. Se OK: ok. Se NAO: rollback automatico.

rollback automatico:
  1. Para managed (kill tree com timeout 30s).
  2. Re-habilita legacy: systemctl start (Linux) / schtasks /Run (Windows) / launchctl load (macOS) / supervisor.startOne(name) (Node).
  3. waitForReadiness legacy.
  4. Marca ownership: legacy.
  5. Log rollback em health_dashboard.
  6. Exit 1 do comando `adopt` (codigo de erro na shell).
```

### 16.3. Rollback por fase (cada fase tem seu proprio)

| Fase | Como reverter |
|---|---|
| 1 | `git revert` ou `git checkout pyproject.toml`. |
| 2 | Apagar `config/runtime.yaml`; `unit_definitions()` ja e o source-of-truth. |
| 3 | `kill -9 <daemon.pid>`. Voltar tudo a legacy. |
| 4 | `hive-mind service release <name> --to legacy`. Servico para managed, volta a legacy. |
| 5 | Idem, por servico. |
| 6 | `kill -9 <daemon.pid>`. Schedulers legados (systemd timer / Task Scheduler / crontab) seguem ativos. |
| 7 | `hive-mind service release <job-name> --to legacy`. Job volta para o scheduler legado. |
| 8 | `kill -9 <daemon.pid>`. Compose up segue manual (install.ps1 ja o faz). |
| 9 | `sc.exe delete hive-mindd` (Windows) / `systemctl --user disable hive-mindd` (Linux) / `launchctl unload com.hivemind.daemon` (macOS). |
| 10 | `git revert`. |
| 11 | `git revert`. CUIDADO: revisar se o `runtime.yaml` salvo tem todas as configs. |
| 12 | `git revert` + reinstall do install.sh/install.ps1. |

### 16.4. Comandos `adopt` e `release` (Fase 4+)

```text
hive-mind service adopt <name>
    [--from {legacy|shadow}]
    [--to {managed}]
    [--wait-healthy-seconds=120]
    [--rollback-on-failure=true]
    [--yes]

hive-mind service release <name>
    [--to {legacy|shadow}]
    [--wait-healthy-seconds=60]
    [--yes]

hive-mind service status
hive-mind service plan
    # mostra o que adopt faria sem executar
```

`adopt` falha (exit 1) se:
- Shadow ainda nao validado (24h sem discrepancias).
- Servico legado nao esta rodando (significa que ja esta managed, ou nunca foi instalado).
- Readiness de managed nao atinge em 120s (rollback automatico).

`release` falha se:
- Managed nao esta healthy (ja esta degradado; rollback manual via `hive-mind service reset`).
- Legacy nao inicia em 60s (significa: ambiente quebrado, nao foi problema do cutover).

## 17. Testes (correcao do ponto 15 do pedido)

### 17.1. Criterio de aceitacao da suite (nao "zero skips" indiscriminado)

O teste **passa** quando:
- `failures == 0`
- `errors == 0`
- `timeouts == 0`
- `skips == 0` para componentes obrigatorios do perfil testado
- `skips` para componentes opcionais: OK, mas classificados em 3 buckets:
  - `BLOCKED: <reason>`: precisa de plataforma que o runner nao tem (ex.: Docker no Windows runner).
  - `ACCEPTED: <reason>`: skip intencional com `pytest.mark.skip(reason=...)` que foi revisado.
  - `FLAKY: <reason>`: conhecido flake; tem issue aberta; CI nao bloqueia.

Nenhum skip sem `reason` explicita. CI falha se encontrar `pytest.mark.skip` sem `reason=`.

### 17.2. Testes ja existentes (preservar)

- `tests/unit/test_service_backends.py` (5 testes).
- `tests/unit/test_install_services.py` (adaptar imports).
- `tests/unit/test_windows_install_contract.py` (294 LOC, 8 testes).
- `tests/unit/test_windows_runtime_contract.py` (varios testes).
- `tests/unit/test_release_validate_package.py`, `test_release_version_floor.py` (gate de release).
- `tests/helpers/audit_cleanup.py` + `tests/unit/test_audit_cleanup.py` (limpa audit).
- `tests/unit/test_citation_path_normalization.py` (125 LOC).
- `tests/integration/test_api_query_hybrid.py`, `test_graphiti.py`, `test_crdt.py`.
- `tests/real/test_cadence_real.py`, `test_disaster_recovery.py`, `test_k5_*`, `test_k8_gate.py`.
- `npm/test/supervisor.test.js` (157 LOC) -> port para `tests/unit/test_daemon_supervisor.py` (pytest).
- `npm/test/doctor.test.js` (34 LOC) -> port para `tests/unit/test_hive_mind_doctor.py`.

### 17.3. Testes novos por fase

| Fase | Teste | O que cobre |
|---|---|---|
| 1 | `tests/unit/test_package_layout.py` | entry points existem, `hive-mind --version`, `hive-mindd --version`. |
| 1 | `tests/unit/test_wheel_build.py` | `uv build` produz wheel valido; imports funcionais. |
| 1 | `tests/unit/test_project_root.py` | `project_root()` resolve em 3 cenarios (venv, env var, fallback). |
| 2 | `tests/unit/test_runtime_yaml_schema.py` | Pydantic schema; YAML invalido. |
| 2 | `tests/unit/test_runtime_yaml_invariants.py` | deps declaradas, profiles consistentes, `category` valido. |
| 2 | `tests/unit/test_runtime_yaml_translation.py` | gerador de runtime.yaml a partir de `unit_definitions()` atual (roundtrip). |
| 3 | `tests/unit/test_daemon_manifest.py` | port do test_service_backends. |
| 3 | `tests/unit/test_daemon_supervisor.py` | port do npm/test/supervisor.test.js. |
| 3 | `tests/integration/test_daemon_shadow.py` | daemon em shadow, nao inicia servico, nao roda job, mas calcula tudo. |
| 4 | `tests/integration/test_cutover_capture_realtime.py` | cutover real em maquina de teste, com readiness probe. |
| 4 | `tests/integration/test_cutover_rollback.py` | forca falha de readiness, valida que legacy volta. |
| 5 | `tests/integration/test_cutover_each_service.py` | parametrizado sobre os 7 servicos. |
| 6 | `tests/integration/test_scheduler_shadow.py` | scheduler calcula 22 jobs, nao dispara nenhum. |
| 7 | `tests/integration/test_cutover_jobs.py` | parametrizado sobre os 22 jobs. |
| 7 | `tests/unit/test_scheduler_translation.py` | tabela de equivalencia 1:1 systemd/Task Scheduler/crontab -> APScheduler. |
| 8 | `tests/integration/test_docker_shadow.py` | orquestrador em shadow. |
| 9 | `tests/integration/test_winsw_register.py` (Windows) | `hive-mindd --register` cria servico. |
| 9 | `tests/integration/test_systemd_register.py` (Linux) | `hive-mindd --register` cria unit. |
| 9 | `tests/integration/test_launchd_register.py` (macOS) | `hive-mindd --register` cria plist. |
| 9 | `tests/integration/test_user_session_acl.py` (Windows) | named pipe tem ACL correto. |
| 9 | `tests/integration/test_unix_socket_acl.py` (Linux/macOS) | socket tem 0o660 + grupo. |
| 10 | `tests/install/test_thin_installers.py` | `install.sh` < 100 LOC, `install.ps1` < 100 LOC, install.bat < 20 LOC. |
| 10 | `tests/install/test_bootstrap.py` (substitui test_windows_bootstrap.ps1) | bootstrap Windows pytest. |
| 11 | `tests/unit/test_legacy_removal.py` | `git ls-files` nao contem scripts removidos. |
| 12 | `tests/install/test_clean_install.py` | install fresco em CI Linux/Windows/macOS. |
| 12 | `tests/integration/test_post_reboot.py` | `hive-mindd post-reboot` verde. |

### 17.4. Testes de stress especificados no pedido

| Cenario | Teste | O que valida |
|---|---|---|
| daemon crash | `tests/integration/test_daemon_crash_recovery.py` | `kill -9` no daemon; SO reinicia (WinSW/systemd); filhos mortos em cascata (Job Object/pgid). |
| filho orfao | `tests/integration/test_orphan_prevention.py` | daemon termina abruptamente; verifica que nenhum filho PID conhecido fica vivo. |
| schedule duplicada | `tests/unit/test_scheduler_no_overlap.py` | 2 daemon na mesma maquina com mesmo runtime.yaml; segundo daemon detecta socket ocupado e recusa subir. |
| DST | `tests/unit/test_scheduler_dst.py` | America/Sao_Paulo 2026-11-01 (spring forward em BR e diferente de US); job agendado `0 3 * * *` continua disparando em 03:00 BRT/BRST. |
| missed run | `tests/integration/test_scheduler_missed_run.py` | daemon inicia 1h apos o ultimo run; dispara imediatamente. |
| job overlap | `tests/integration/test_scheduler_overlap.py` | job demorado (sleep 60); daemon nao dispara de novo em 30s. |
| manifest invalido | `tests/integration/test_manifest_invalid.py` | YAML com `dependencies` apontando para servico inexistente; daemon recusa iniciar. |
| rollback de cutover | `tests/integration/test_cutover_rollback.py` | readiness probe falha; legacy volta. |
| servico requerido indisponivel | `tests/integration/test_required_unavailable.py` | `sinapse-api` nao sobe; daemon marca degraded; `/ready` retorna 503. |
| Docker demorado apos reboot | `tests/integration/test_docker_slow_after_reboot.py` | milvus demora 90s apos reboot; daemon espera ate 120s, marca healthy. |
| Windows Service executando sob usuario correto | `tests/integration/test_windows_user_context.py` | `whoami` no servico retorna o usuario esperado; tem acesso a `%USERPROFILE%\.claude-mem\`. |



## 18. Riscos

| # | Risco | Prob | Impacto | Mitigacao |
|---:|---|---|---|---|
| 1 | Cutover falha em producao: managed nao atinge readiness em 120s | Baixa | Alto | Rollback automatico (Secao 16.2). Soak >= 7 dias em shadow antes de tentar. |
| 2 | WinSW nao inicia apos login (Session 0, sem perfil) | Media | Alto | Modo "current user" (Secao 13.3.1) com `cmdkey`; teste `test_windows_user_context.py`. Fallback: registrar manualmente via `sc.exe create`. |
| 3 | launchd no macOS perde env vars | Media | Medio | Carregar `.env` no plist via `set -a; . ./.env; set +a; exec ...`. |
| 4 | APScheduler nao cobrir uma schedule exotica | Baixa | Medio | Tabela de equivalencia testada (Secao 17.3). |
| 5 | Docker Desktop offline apos reboot | Media | Baixo | Daemon marca `degraded`; servicos que dependem ficam `degraded`; doctor reporta. |
| 6 | claude-mem worker-service.cjs nao responde a SIGTERM | Baixa | Baixo | Timeout 30s + SIGKILL/TerminateProcess forcado. |
| 7 | Race entre `hive-mind install` reescrevendo runtime.yaml e daemon lendo | Baixa | Medio | install faz `hive-mindd reload` (SIGHUP/PostMessage) apos escrever. |
| 8 | Race entre `hive-mind service adopt` e restart do servico legado | Baixa | Alto | Stop --now + wait ate PID morto (max 30s) + port free. |
| 9 | Vault write enforcement quebrar com `hive-mindd` rodando como usuario de servico | Media | Alto | Em modo "current user", o usuario ja e owner do vault. Em modo "dedicated service user", ACL e provisionado por `install.ps1 -SystemService`. |
| 10 | `~/.claude-mem/` nao acessivel pelo usuario de servico | Media | Alto | ACL: `Modify` para o usuario de servico, `Read` para o usuario humano. Documentado em `install.ps1 -SystemService`. |
| 11 | Regressao no `sinapse_query` (federacao) | Baixa | Alto | **NAO mexer** em `core/federation.py` e `core/retrieval/router.py` (ja ajustado no d246f0c6). |
| 12 | Testes E2E reais quebrarem por mudanca de imports | Media | Medio | Shims de compat em F1-F11. `tests/unit/test_compat_shims.py` trava cada shim. |
| 13 | Performance do scheduler (22 jobs) | Baixa | Baixo | APScheduler e single-thread + non-blocking. 22 jobs = 22 cron jobs in-process. |
| 14 | Crash do daemon derruba todos os servicos managed | Media | Alto | SO reinicia o daemon (WinSW/systemd Restart=on-failure 15s). Filhos protegidos por Job Object / pgid. |
| 15 | `runtime.yaml` editado a mao com YAML invalido | Media | Medio | Pydantic schema estrito; `hive-mind config validate` antes de `hive-mindd start`. |
| 16 | Falta de testes E2E reais (CI nao roda install fresca + reboot) | Media | Alto | Runners com reboot (Azure DevOps, GitHub Actions com `reboot` action) em F12. |
| 17 | Drift entre daemon Python e supervisor Node durante transicao | Media | Alto | Shadow mode na F3 e F6; cutover 1-servico e 1-job por vez. |
| 18 | `sinapse-mcp-http` opcional fica enabled em runtime que nao tem API key | Baixa | Baixo | HIVE_MIND_API_KEY detection em `api_enabled()`. `sinapse-mcp-http` NAO esta em `required`. |
| 19 | Usar `uv tool install .` em algum tutorial terceiro | Baixa | Alto | `pyproject.toml` documenta que `package=true` se aplica **somente** a wheel. `uv sync` no projeto continua sendo o fluxo oficial. README reforca. |
| 20 | Versao SemVer mudar inadvertidamente | Baixa | Alto | `scripts/release/validate_package.py` (ja no d246f0c6) trava 5 fontes. Estender para ler `hive_mind.__version__` em F1. |
| 21 | `daemon.sock` (Unix) com permissao errada vira escalation de privilegio | Baixa | Alto | ACL: 0o660 + grupo `<user>`. SO_PEERCRED validado. Teste `test_unix_socket_acl.py`. |
| 22 | `\\.\pipe\hive-mindd` (Windows) aberto para outros usuarios | Baixa | Alto | ACL: ACE `GENERIC_READ|WRITE|EXECUTE` apenas para o usuario que instalou. Teste `test_user_session_acl.py`. |
| 23 | APScheduler in-process morre com daemon | Baixa | Baixo | `state_dir/jobs.json` persiste ultimo run. Boot le manifest e re-agenda. Nao usa persistent job store por padrao. |

## 19. Arquivos que serao alterados (durante a migracao)

| Arquivo | Quando | Mudanca |
|---|---|---|
| `pyproject.toml` | F1 | `package=true`, `[project.scripts]`, `[build-system]` (hatchling), `[tool.hatch.build.targets.wheel]`. **Nao** muda `version`. |
| `install.sh` | F10 | Encolhe de 1319 LOC para < 100 LOC; delega para `hive-mind install`. |
| `install.ps1` | F10 | Encolhe de 568 LOC para < 100 LOC; delega para `hive-mind install`. |
| `install.bat` | F10 | Substituido por shim. |
| `setup-brain.bat` | F10 | Substituido por shim. |
| `scripts/setup/setup-brain.bat` | F10 | Substituido por shim. |
| `scripts/setup/setup-brain.sh` | F10 | Substituido por shim. |
| `scripts/setup/setup-brain.ps1` | F10 | Substituido por shim. |
| `scripts/setup/install_services.py` | F11 | Removido (substituido por `hive_mind.daemon.manifest`). |
| `scripts/setup/register-mcp.sh` | F11 | Removido (substituido por `hive_mind.agents.register`). |
| `scripts/setup/register-mcp.ps1` | F11 | Removido. |
| `scripts/setup/setup-vault-enforcement.sh` | F11 | Removido (substituido por `hive_mind.install.vault_enforcement`). |
| `scripts/setup/setup-vault-enforcement.ps1` | F11 | Removido. |
| `scripts/setup/bootstrap-prerequisites.ps1` | F11 | Removido (substituido por `hive_mind.install.prereqs`). |
| `scripts/setup/backup-install-state.ps1` | F11 | Removido (substituido por `hive_mind.install.state.snapshot`). |
| `scripts/setup/fullstack-readiness.ps1` | F11 | Removido (substituido por `hive_mind.install.readiness.fullstack`). |
| `scripts/setup/register-windows-jobs.ps1` | F11 | Removido. |
| `scripts/setup/register-windows-runtime.ps1` | F11 | Removido. |
| `scripts/setup/start-windows-supervisor.ps1` | F11 | Removido. |
| `scripts/setup/apply-hidden-supervisor-task.ps1` | F11 | Removido. |
| `scripts/maintenance/install-backup-cron.sh` | F11 | Removido. |
| `scripts/maintenance/install-backup-cron.ps1` | F11 | Removido. |
| `scripts/services/{start-watcher,start-claude-mem,start-claude-mem-mcp,start-rtk,mcp-server,claude-mem-watchdog,neural-memory-local}.{ps1,sh}` | F11 | Removidos. |
| `scripts/services/claude-mem-local.{ps1,sh}` | F11 | Mantido **so** o `.ps1` como entry-point externo (Node); removido `.sh`. |
| `scripts/utils/recover.{ps1,sh}` | F11 | Removidos (substituidos por `hive-mind doctor --repair`). |
| `scripts/graph/{build-graph,serve-graph}.{ps1,sh}` | F11 | Removidos. |
| `scripts/lib/HiveMind.Windows.psm1` | F11 | Removido (funcionalidade portada para `hive_mind.platform.windows`). |
| `npm/` (inteiro) | F11 | Removido. |
| `config/components.lock.json` | F8 | Copiado para `src/hive_mind/resources/components.lock.json`. |
| `config/sinapse.yaml` | F8 | Copiado para `src/hive_mind/resources/sinapse.yaml`. |
| `config/profiles/*.env.example` | F8 | Copiados para `src/hive_mind/resources/profiles/`. |
| `config/sinapse-agent-prompt.md` | F8 | Atualizado (Anexo B do desenho v1) e copiado. |
| `tests/run_all.{ps1,sh}` | F11 | Mantidos; reduzidos a driver thin. |
| `tests/run_real_knowledge.{ps1,sh}` | F11 | Mantidos. |
| `tests/smoke/test_smoke.{ps1,sh}` | F11 | Mantidos. |
| `tests/install/test_windows_bootstrap.ps1` | F11 | Substituido por `tests/install/test_bootstrap.py` (pytest). |
| `tests/install/run-clean-install-test{,-local}.{ps1,sh}` | F11 | Substituidos por `tests/install/test_clean_install.py`. |
| `tests/conftest.py` | F1 | Adicionar `hive_mind` ao `sys.path` e fixture de project root. |
| `tests/unit/test_service_backends.py` | F2 | Adaptar imports para `hive_mind.daemon.manifest`. |
| `tests/unit/test_install_services.py` | F2 | Idem. |
| `tests/unit/test_windows_install_contract.py` | F11 | Adaptar (nao quebrar) quando install.ps1 for reduzido. |
| `tests/unit/test_release_validate_package.py` | F1 | Adicionar leitura de `hive_mind.__version__`. |
| `npm/test/supervisor.test.js` | F3 | Removido; substituido por `tests/unit/test_daemon_supervisor.py`. |
| `npm/test/doctor.test.js` | F11 | Removido; substituido por `tests/unit/test_hive_mind_doctor.py`. |

## 20. Arquivos que serao removidos (na F11, com pre-aviso de 30 dias)

| Arquivo | Categoria | Justificativa |
|---|---|---|
| `npm/` (inteiro) | Control plane | Substituido por `hive-mind` CLI Python. |
| `scripts/setup/install_services.py` | Control plane | Substituido por `hive_mind.daemon.manifest`. |
| `scripts/setup/{register-mcp,setup-brain,setup-vault-enforcement,bootstrap-prerequisites,backup-install-state,fullstack-readiness}.{ps1,sh}` | Control plane | Substituidos por modulos Python. |
| `scripts/setup/{register-windows-jobs,register-windows-runtime,start-windows-supervisor,apply-hidden-supervisor-task}.ps1` | Control plane | Substituidos pelo SO adapter (WinSW). |
| `scripts/services/{start-watcher,start-claude-mem,start-claude-mem-mcp,start-rtk,mcp-server,claude-mem-watchdog,neural-memory-local}.{ps1,sh}` | Control plane | Wrappers sem logica. Daemon sobe direto. |
| `scripts/services/claude-mem-local.sh` | Control plane | Wrapper obsoleto. |
| `scripts/utils/recover.{ps1,sh}` | Control plane | `hive-mind doctor --repair`. |
| `scripts/graph/{build-graph,serve-graph}.{ps1,sh}` | Control plane | `hive-mind graph {build,serve}`. |
| `scripts/maintenance/install-backup-cron.{ps1,sh}` | Control plane | Substituido por jobs do manifesto. |
| `scripts/lib/HiveMind.Windows.psm1` | Control plane | Funcionalidade portada para `hive_mind.platform.windows`. |
| `install.bat`, `setup-brain.bat`, `scripts/setup/setup-brain.bat` | Control plane | Substituidos por `hive-mind install` / `hive-mind brain setup`. |
| `tests/install/test_windows_bootstrap.ps1` | Test | Substituido por pytest. |
| `tests/install/run-clean-install-test{,-local}.{ps1,sh}` | Test | Substituido por pytest. |
| `npm/test/*.js` | Test | Substituido por pytest. |

**Nao serao removidos** (escopo do desenho):
- `scripts/capture/*` (capture, NAO mexer)
- `scripts/dream/*` (consumidores do scheduler, NAO mexer)
- `scripts/knowledge/*` (consumidores do scheduler, NAO mexer)
- `scripts/health/*` (consumidores do scheduler, doctor)
- `scripts/maintenance/backup*` (logica de backup, NAO mexer)
- `scripts/maintenance/integrations-update.{ps1,sh}` (uso manual)
- `claude-mem/`, `integrations/`, `core/`, `cerebro/`, `plugins/` (sem mudanca de localizacao)
- `templates/vault/` (materializado por `Sync-HiveMindVaultTemplates` em install)


---

# Anexo A. Aprovacao necessaria antes de F1

Para avancar, o operador deve confirmar:

1. **Branch e HEAD**: trabalho sera em `codex/control-plane-redesign` a partir de `codex/windows-zero-install-impl @ d246f0c6e6661e7c9a052108387bd52819483b8d`. Sem merge, sem push, sem tag, sem release.

1b. **Decisoes corretas preservadas** (item 2 do pedido): runtime nativo no host; Docker somente para infraestrutura externa; `hive-mind` como CLI Python; hive-mindd como control plane unico (hive-mindd = unico control plane do host); manifesto declarativo unico; scheduler interno; PowerShell e Bash apenas como bootstrap/registro; Windows Service / systemd / launchd apenas iniciando `hive-mindd`; Sinapse como interface de memoria, NAO substituto da leitura do codigo; Claude Mem e sua captura atual sem alteracao.

2. **Empacotamento**: build-system `hatchling` via `uv build`; **nao** `uv tool install`; executaveis vivem em `<root>\.venv\Scripts\` (Windows) e `<root>/.venv/bin/` (Linux/macOS); `core/` permanece no project root com shim minimo.

3. **Ownership**: tres estados `legacy | shadow | managed`; cutover **um servico por vez** com rollback automatico; jobs cortados um por um com 7 dias de soak.

4. **Containment**: Windows Job Object + Linux/macOS process group; shutdown 30s timeout, depois forcado.

5. **Scheduler**: APScheduler (nao parser proprio); schedules em `cron` ou `interval` com `timezone`, `misfire_policy`, `max_instances`, `timeout`, `retry`, `locking`.

6. **Identidade do Windows Service**: **nao** `LocalSystem`; rodar como `current user` (dev) ou `dedicated service user` (producao); secrets em `.env`, **nao** no WinSW XML.

7. **Categorias**: `background-service`, `user-session`, `hook`, `external-container`, `scheduled-job`; captura de Claude Mem NAO e alterada.

8. **Controle seguro**: HTTP loopback so com `/health`, `/ready`, `/metrics`; mutacoes via named pipe (Windows) ou Unix socket (Linux/macOS) com ACL de usuario.

9. **Paths**: codigo em `<root>`; state em `%LOCALAPPDATA%\Hive-Mind\state` (Windows) / `~/.local/state/hive-mind` (Linux) / `~/Library/Application Support/Hive-Mind/state` (macOS); logs separados de state; vault, UMC, claude-mem NAO migram.

10. **Testes**: zero failures, zero timeouts, zero skips sem `reason=`. Cobertura de: crash, orfao, schedule duplicada, DST, missed run, overlap, manifest invalido, rollback, servico requerido indisponivel, Docker lento, Windows Service user context.

11. **Versao da implementacao**: a decidir apos os gates. Atual `3.10.1`; gate de release em `scripts/release/validate_package.py` ja em uso; estender para `hive_mind.__version__` em F1.

12. **Migracao em 12 fases** (F1-F12), cada uma com `gate` obrigatorio. Rollback de cada fase descrito na Secao 16.3.

Ate a confirmacao, **nenhuma mudanca** e feita em `pyproject.toml`, `install.sh`, `install.ps1`, `install_services.py`, `npm/`, `scripts/setup/`, `scripts/services/*.{ps1,sh}`, `scripts/utils/recover.{ps1,sh}`, `scripts/maintenance/install-backup-cron.{ps1,sh}`, `scripts/lib/HiveMind.Windows.psm1`, ou `tests/install/test_windows_bootstrap.ps1`. Captura de Claude Mem continua intocada.

Gates de instalacao limpa e reboot continuam **pausados** ate a aprovacao final.

---

# Anexo B. Anexo sinapse-agent-prompt.md (copiado do desenho v1, revalidado)

O Anexo A do desenho v1 continua valido. Resumo do que muda no `config/sinapse-agent-prompt.md`:

- A restricao "Use ONLY sinapse_* tools" passa a ser **explicitamente limitada aos backends de memoria**.
- Adicionada secao "Codigo atual e runtime" que obriga o agente a:
  - Ler o codigo pelo **filesystem** (Read, rg, git, ls).
  - Usar `shell` para inspecionar o repo.
  - **Ler arquivos completos** quando a pergunta for sobre o codigo.
  - **Executar testes** para validar.
  - Tratar o codigo atual como **prevalece** sobre a memoria historica.
- **Sinapse nao substitui inspecao do repositorio.** Sinonimo: "use a memoria para contexto/decisoes/observacoes previas; use o filesystem para o estado atual."
- A captura do claude-mem NAO e alterada.

O Anexo A do desenho v1 ja cobre esses pontos; nao precisa de revisao adicional.

---

# Anexo C. O que o desenho v1 errou e o que mudou

| Erro do v1 | Correcao do v2 | Secao |
|---|---|---|
| HEAD errado (3d362c6 em vez de d246f0c6) | Inspecao refeita em `backups/worktrees/hive-mind-windows-zero-install` | 1, 2 |
| Empacotamento generico (`[project.scripts]` e `uv tool install`) | `hatchling` + wheel no projeto, sem tool install; executaveis na `.venv` | 5 |
| Paths genericos (`logs/daemon/`) | `%LOCALAPPDATA%\Hive-Mind\state` (Windows) / XDG (Linux/macOS); logs separados | 7 |
| Scheduler com parser proprio de `OnCalendar=` | APScheduler; `cron` ou `interval` | 11 |
| `hive-mindd` era generico (start/stop via control socket) | `hive-mindd run` em foreground; `hive-mind service {install,...}` separado | 13.1, 13.2 |
| Identidade do Windows Service nao decidida | `current user` (dev) ou `dedicated service user` (producao); `.env` para secrets, nao XML | 13.3 |
| HTTP com start/stop/reload | Apenas `/health`, `/ready`, `/metrics`; mutacoes via named pipe / Unix socket com ACL | 15 |
| Componentes interativos nao classificados | 5 categorias: `background-service`, `user-session`, `hook`, `external-container`, `scheduled-job` | 14 |
| Cutover de todos os servicos de uma vez (M4) | Cutover **um servico por vez** com rollback automatico (F4) | 16 |
| 10 fases (M1-M10) | 12 fases (F1-F12) com gates explicitos | 16 |
| Testes exigiam "zero skips" | "zero failures, zero timeouts, skips classificados em BLOCKED/ACCEPTED/FLAKY" | 17.1 |
| Versao 3.11.0 definida | "versao a decidir apos os gates"; `3.10.1` atual | Anexo A item 11 |
| Captura Claude Mem mencionada, mas implicita em "scripts/capture/*" | Categoria `user-session` explicita; NAO roda em Session 0 | 14.2, 14.4 |
| Containers do `local-full` nao enumerados | 7 containers canonicos: sinapse-falkordb, hive-mind-milvus, hive-mind-ragflow-mysql, es01, redis, minio, hive-mind-ragflow | 12.1 |
| Perfis com contradicao sobre RAGFlow opt-in vs obrigatorio | RAGFlow **obrigatorio** em `local-full`; `lightrag` e `langfuse` sao `required: false` | 8 (external_services) |
