# Runtime & Daemon — `hive-mindd`

> **Hive-Mind v3.10.1** — o control plane nativo do Hive-Mind: o daemon
> `hive-mindd`, o manifesto declarativo `config/runtime.yaml`, o catálogo de
> serviços, o scheduler e os mecanismos de agendamento por plataforma.
>
> Referências normativas: [spec §15](../specs/control-plane-redesign-v2.md),
> Anexos D.2 (lock), D.4 (pureza shadow), D.5 (project root), D.6 (scheduler),
> , e os documentos
> operacionais deste conjunto: [instalacao.md](instalacao.md),
> [operacao.md](operacao.md), [cli.md](cli.md),
> [observabilidade.md](observabilidade.md).

---

## 1. Modelo mental: quem é o dono hoje

O Hive-Mind separa, de forma explícita, **três camadas de verdade** sobre o
runtime. Nunca confunda "o que está declarado" com "o que está rodando":

| Camada | Estado | Dono real hoje |
|---|---|---|
| **CURRENT** | O launcher legado (Task Scheduler no Windows, systemd timers no Linux, supervisor Node) **inicia e monitora** os serviços e jobs. | Task Scheduler / systemd / supervisor Node |
| **TRANSITION** | `config/runtime.yaml` é o **manifesto candidato**. O `hive-mindd` em modo shadow apenas **observa** e **calcula** next-run; **não dispara nada**. | `hive-mindd` (somente leitura) |
| **TARGET** | `hive-mindd` como dono único de serviços e jobs, após cutover (D010). | `hive-mindd` (managed) |

**Nenhum cutover automático ocorre.** A transição de ownership é sempre
explícita, um serviço por vez, com rollback automático. Nada é adotado
silenciosamente.

---

## 2. Manifesto declarativo (`config/runtime.yaml`)

`config/runtime.yaml` (schema v3) é a fonte única de verdade **declarativa**
sobre:

- serviços locais (`services`),
- serviços externos (`external_services`),
- jobs periódicos (`jobs`),
- projetos compose (`compose_projects`),
- política de restart global (`restart`).

É validado por Pydantic v2 em
[manifest.py](../src/hive_mind/daemon/manifest.py). O schema rejeita, na carga:
dependência inexistente, auto-referência e ciclos na ordem topológica.

```powershell
hive-mind config validate     # erros de schema / invariantes
hive-mind config show         # manifesto normalizado (YAML)
hive-mind config show --json  # manifesto normalizado (JSON)
```

### 2.1 Campos de topo

| Campo | Tipo | Descrição |
|---|---|---|
| `schema_version` | int | Versão do schema (atual: `3`) |
| `profile` | string | Perfil ativo: `local-min` ou `local-full` |
| `vault` | path | Diretório do vault (`cerebro`) |
| `pyproject_root` | path | Raiz resolvida em relação ao arquivo (`.` = raiz do repo) |
| `paths.*` | path/null | Overrides: `data_dir`, `state_dir`, `log_dir`, `user_config_dir`, `config_file` |
| `services` | list | Serviços locais gerenciáveis |
| `external_services` | list | Serviços fora do controle do daemon (ollama, docker, milvus…) |
| `jobs` | list | Jobs periódicos com cron/intervalo |
| `compose_projects` | list | Projetos `docker compose` obrigatórios/opcionais |
| `restart` | map | Política de restart global |

---

## 3. Modelo de ownership

Cada serviço tem um estado de ownership (spec §9):

| Estado | Significado |
|---|---|
| `legacy` | O launcher antigo (Task Scheduler, Node, systemd) ainda é o dono |
| `shadow` | O daemon **observa** o serviço, sem agir |
| `managed` | O daemon é o dono (inicia, monitora, reinicia) |

A transição `legacy → shadow → managed` é sempre por cutover explícito, um
serviço por vez, com rollback automático.

---

## 4. Daemon `hive-mindd`

O daemon é o binário de control plane (`hive-mindd`, entry point
[main.py](../src/hive_mind/daemon/main.py)). Ele opera em três modos:

```powershell
hive-mindd run --shadow                              # passada shadow (passiva)
hive-mindd run --shadow --serve                      # shadow + HTTP + socket de controle
hive-mindd run --serve                               # managed (F4) + HTTP + socket de controle
hive-mindd run                                       # ainda não implementado -> 69
```

| Invocação | Comportamento | Sai |
|---|---|---|
| `run --shadow` | Passada passiva única: observa, grava `services.shadow.json`, libera o lock. **Não inicia processo.** | `0` |
| `run --shadow --serve` | Shadow + serve HTTP loopback e socket de controle (mutações **recusadas**). | `0` (até interromper) |
| `run --serve` | Managed: `ManagedSupervisor.start_all()`, monitora, serve HTTP e socket (mutações **permitidas**). | `0` (até interromper) |
| `run` (sem flags) | Managed sem HTTP ainda não implementado nesta fatia. | `69` (`EX_UNAVAILABLE`) |

> **Nota sobre `run --serve`:** o modo managed é alcançado via `--serve` (o
> daemon supervisiona os serviços e expõe a superfície de leitura e o socket
> de controle). `run` puro (sem `--shadow` nem `--serve`) retorna
> `EX_UNAVAILABLE` (69) — o supervisor gerenciado sem a superfície HTTP ainda
> não é o caminho canônico. Shadow nunca vira managed sozinho.

Flags comuns de `hive-mindd run`:

| Flag | Default | Descrição |
|---|---|---|
| `--manifest <file>` | `config/runtime.yaml` | Caminho do manifesto |
| `--state-dir <dir>` | `<root>/.hive-mind/state` | Diretório de estado |
| `--project-root <dir>` | auto-detectado | Override do project root |
| `--host <host>` | `127.0.0.1` | Host do HTTP loopback |
| `--port <port>` | `37780` | Porta do HTTP loopback |

---

## 5. Instância única (Anexo D.2)

Exatamente **um** `hive-mindd` por host, garantido por
[lock.py](../src/hive_mind/daemon/lock.py):

| Plataforma | Mecanismo | Nome/Arquivo |
|---|---|---|
| Windows | named mutex (`CreateMutexW`) | `Local\Hive-Mind-hive-mindd` |
| Linux/macOS | `flock(LOCK_EX | LOCK_NB)` | `state_dir/daemon.lock` |

Uma segunda instância falha imediatamente com `SingleInstanceLockError` (exit
`EX_UNAVAILABLE`). O lock é mantido durante **toda** a execução — não apenas
durante a observação breve —, de modo que uma segunda instância falha enquanto
a primeira estiver viva, inclusive durante o serving loop.

> **Nota Win32:** o nome literal da spec (`Local\Hive-Mind\hive-mindd`) tem
> dois backslashes; objetos de kernel Win32 aceitam apenas um após o prefixo
> `Local\`. Os segmentos são unidos com hífen:
> `Local\Hive-Mind-hive-mindd`.

---

## 6. Modo shadow (F3 / D007)

```powershell
hive-mindd run --shadow [--project-root <dir>] [--manifest <file>] [--state-dir <dir>]
```

Uma passada **passiva**: adquire o lock, lê o manifesto, calcula readiness e
ordem topológica dos serviços do perfil ativo, grava o resultado e libera o
lock. Sai `0`.

**Pureza absoluta** ([supervisor.py](../src/hive_mind/daemon/supervisor.py),
garantida por `test_shadow_purity.py`): em shadow o daemon **não**

- inicia nenhum processo (`subprocess.Popen`/`run`/`call`);
- escreve em `runtime.yaml`;
- cria qualquer arquivo de state além de `services.shadow.json`
  (e `schedule.shadow.json` quando o scheduler roda);
- dispara jobs ou executa cutover.

O estado observado fica em `state_dir/services.shadow.json`:

```json
{
  "mode": "shadow",
  "profile": "local-min",
  "service_count": 8,
  "ready": false,
  "services": [
    {
      "name": "sinapse-claude-mem",
      "ownership": "legacy",
      "required": true,
      "dependencies": [],
      "startup_order": 10,
      "readiness": "unknown",
      "readiness_probe": "tcp",
      "would_start": true
    }
  ]
}
```

`readiness` é `ready` / `not_ready` (com um prober injetado) ou `unknown`
(sem prober). `ready` no topo é `true` **somente** quando todos os serviços
`required: true` estão `ready`.

---

## 7. Modo managed (F4 / D008)

```powershell
hive-mindd run --serve [--host 127.0.0.1] [--port 37780]
```

O daemon gerenciado de fato **inicia e supervisiona** os serviços declarados
via `ManagedSupervisor` ([managed.py](../src/hive_mind/daemon/managed.py)):
`start_all()` → `start_monitor()` → estado persistido em
`services.managed.json`. Sob o lock de instância única, o daemon:

1. inicia os serviços na ordem topológica (`startup_order`);
2. aplica `restart_policy` / `restart_delay_seconds` / `restart_limit`;
3. abre o socket de controle em modo **managed** (mutações permitidas);
4. serve o HTTP loopback (`/health`, `/ready`, `/metrics`);
5. monitora até interrupção, então `stop_monitor()` → `stop_all()`.

A transição de um serviço de `legacy` para `managed` é sempre por cutover
explícito — o journal transacional de cutover (`cutover.journal`) é parte da
F4.

---

## 8. State directory

`state_dir` (default `<project-root>/.hive-mind/state/`, ignorado pelo git)
guarda:

| Arquivo | Fase | Conteúdo |
|---|---|---|
| `daemon.lock` | D007 | Lock de instância única (POSIX) |
| `services.shadow.json` | D007 | Observação shadow, read-only sobre o legado |
| `services.managed.json` | D008 | Estado dos processos managed (PIDs, restarts) |
| `schedule.shadow.json` | D008 | next-run calculado dos jobs (shadow, não dispara) |
| `cutover.journal` | F4 | Journal transacional de cutover |
| `jobs.db` | F7 | Persistência SQLite do scheduler (`job_schedule`) |
| `windows-jobs.lock` | P1 | Lock de `MaintenanceLock` para registro de tarefas |
| `windows-runtime.lock` | P1 | Lock de `MaintenanceLock` para runtime tasks |

---

## 9. HTTP loopback de leitura (spec §15.1 / §15.4)

```powershell
hive-mindd run --shadow --serve [--host 127.0.0.1] [--port 37780]
```

Após a passada, o daemon serve **exatamente três rotas de leitura** em
[http_api.py](../src/hive_mind/daemon/http_api.py), bind loopback, sem TLS,
sem auth, sem body de escrita:

| Rota | Resposta |
|---|---|
| `GET /health` | `{"state": "healthy"\|"degraded"\|"unknown", "services": {...}, "jobs": {}}` |
| `GET /ready` | `200` se todos os `required` estão ready; `503` caso contrário (**fail-closed**) |
| `GET /metrics` | Prometheus: `hive_service_count`, `hive_service_ready`, `hive_daemon_ready` |

Sem observação shadow ainda, `/ready` é **503** (fail-closed, nunca fail-open).
Nenhuma rota de mutação existe: `POST /start`, `/stop`, `/reload`, `/run-job`
retornam 404. O invariante é testado (`READ_ONLY_HTTP_ROUTES` em
`test_daemon_http_routes.py`).

**Default:** host `127.0.0.1`, porta `37780`.

---

## 10. Socket de controle (spec §15.2/§15.3)

Toda mutação passa por um canal de controle local autenticado, **nunca** por
HTTP ([control.py](../src/hive_mind/daemon/control.py)):

| Plataforma | Transporte | Proteção |
|---|---|---|
| Windows | named pipe `\\.\pipe\hive-mindd` | DACL que concede acesso só ao usuário criador (owner + `GENERIC_ALL` via pywin32); demais recebem `ACCESS_DENIED` |
| POSIX | Unix socket `state_dir/daemon.sock` | `0o600` dentro de `state_dir` `0o700` |

Protocolo: um objeto JSON por mensagem — `{"command", "args"}` →
`{"ok", "data", "error"}`.

O dispatcher em shadow
([control_dispatch.py](../src/hive_mind/daemon/control_dispatch.py)) honra
`ping`/`status` e **recusa** toda mutação (`start`/`stop`/`restart`/`reload`/
`run-job`) — shadow nunca age (Anexo D.4). O dispatcher managed
(`ManagedControlDispatcher`) aceita as mutações supervisionadas.

```powershell
hive-mind service ping   # pong se o socket está vivo
```

Dependência: `pywin32` (Windows), decidido no ledger DH-002.

---

## 11. Scheduler (F6 shadow / D.6)

O scheduler ([scheduler.py](../src/hive_mind/daemon/scheduler.py)) em shadow
apenas **calcula** quando cada job rodaria (`next_fire_time`) e persiste o
plano em `schedule.shadow.json`. **Não dispara nada** (Anexo D.4). Disparar
jobs é operação managed (F7).

- `next_fire_time` usa os triggers do **APScheduler** (sanção da spec D.6; sem
  parser de cron caseiro): `CronTrigger.from_crontab` para cron e cálculo
  direto para `interval`.
- `SchedulerStore` é a interface de persistência (next_run/last_run/lease):
  - `MemorySchedulerStore` — default in-process, **não** sobrevive a restart;
  - `SqliteSchedulerStore` — persistência SQLite em `state_dir/jobs.db`
    (tabela `job_schedule` com `active_leases`), sobrevive a restart (F7).
- `ShadowScheduler.compute(now)` grava, por job: `name`, `type`,
  `next_run` (ISO-8601 com offset), `last_run`, `max_instances`, `would_fire`.

---

## 12. Catálogo de serviços locais

Fonte: `services` em `config/runtime.yaml`. `required: true` é o **gate de
doctor** — uma instalação só é saudável quando todos os `required` estão
`ready`.

| Serviço | Order | Required | Porta | Dependências | Readiness | Command |
|---|---|---|---|---|---|---|
| `sinapse-claude-mem` | 10 | **sim** | 37700 | — | tcp 127.0.0.1:37700 | `python -m hive_mind.services.claude_mem_launcher` |
| `hive-otel-collector` | 15 | não | 3100 | — | — | `python scripts/services/otel_collector.py --host 127.0.0.1` |
| `sinapse-sqlite-vec` | 20 | **sim** | 37701 | `sinapse-claude-mem` | tcp 127.0.0.1:37701 | `python plugins/sqlite-vec-worker/worker.py` |
| `sinapse-graphify-watch` | 30 | não | — | — | — | `python -m graphify watch cerebro --debounce 10.0` |
| `sinapse-api` | 40 | não | 37702 | `sinapse-sqlite-vec` | http `/api/v1/health` (200/401) | `python scripts/services/sinapse-api.py` |
| `sinapse-mcp-http` | 50 | não | 37703 | `sinapse-api` | http `/health` (200) | `python scripts/services/sinapse-mcp-http.py` |
| `sinapse-capture-realtime` | 60 | **sim** | — | `sinapse-claude-mem`, `sinapse-sqlite-vec` | — | `python scripts/capture/capture-realtime.py` |
| `sinapse-consolidate` | 65 | não | — | `sinapse-claude-mem`, `sinapse-sqlite-vec` | — | `python scripts/knowledge/consolidate_loop.py` |

> **`sinapse-claude-mem` e `sinapse-sqlite-vec`** exigem o plugin claude-mem
> instalado (`requires_claude_mem_plugin: true`). Numa máquina sem agente/IDE,
> eles são desabilitados no install para evitar crash-loop no boot — a memória
> temporal liga junto com o primeiro agente registrado.

### 12.1 Variáveis de ambiente por serviço (resumo)

| Serviço | Env |
|---|---|
| `sinapse-claude-mem` | `CLAUDE_MEM_WORKER_HOST=127.0.0.1`, `CLAUDE_MEM_WORKER_PORT=37700`, `CLAUDE_MEM_CHROMA_ENABLED=false`, `CLAUDE_MEM_MANAGED=true` |
| `sinapse-sqlite-vec` | `VEC_WORKER_PORT=37701`, `CLAUDE_MEM_DB`, `FASTEMBED_CACHE_PATH` |
| `sinapse-api` | `HIVE_MIND_API_HOST=127.0.0.1`, `HIVE_MIND_API_PORT=37702` (+ `env_file: .env`) |
| `sinapse-mcp-http` | `SINAPSE_MCP_HTTP_HOST=127.0.0.1`, `SINAPSE_MCP_HTTP_PORT=37703` (+ `env_file: .env`) |
| `sinapse-consolidate` | `HIVE_CONSOLIDATE_INTERVAL_SECONDS=60`, `HIVE_CONSOLIDATE_MEDIUM_SECONDS=300`, `HIVE_CONSOLIDATE_SLOW_SECONDS=3600` |

Consulte a tabela canônica completa de variáveis em
[04-infrastructure.md](04-infrastructure.md) e [arquitetura.md](arquitetura.md).

---

## 13. Serviços externos

Serviços fora do controle do daemon (o daemon só **verifica readiness**):

| Serviço | Required | Perfis | Readiness |
|---|---|---|---|
| `ollama` | sim | local-min, local-full | http `127.0.0.1:11434/api/tags` (200) |
| `docker-desktop` | sim | local-full | command `docker info --format {{.ServerVersion}}` |
| `falkordb` | sim | local-full | tcp `127.0.0.1:6379` |
| `milvus` | sim | local-full | tcp `127.0.0.1:19530` |
| `ragflow` | sim | local-full | http `127.0.0.1:9380/api/v1/system/healthz` (200) |
| `syncthing-watcher` | sim | local-full | http `127.0.0.1:8384/rest/noauth/health` (200/401/403) |
| `lightrag` | não | local-full | http `127.0.0.1:9621/health` (200) |

---

## 14. Jobs periódicos (inventário canônico)

Fonte: `jobs` em `config/runtime.yaml` (18 jobs; todos com entry point
`__main__`, código executável e destino de escrita identificável). Fuso de
todos os cron: `America/Sao_Paulo`.

| Job | Cron | Script | Escreve em | Classificação |
|---|---|---|---|---|
| `dream-cycle` | `0 */4 * * *` | `scripts/dream/dream_cycle.py` | `cortex/temporal/` | REQUIRED |
| `capture-tailer` | interval 30s | `scripts/capture/capture-tailer.py` | Claude Mem via `capture_core.ingest` | REQUIRED |
| `claude-mem-bridge` | `45 2 * * *` | `scripts/services/claude_mem_bridge.py` | UMC (observations) | REQUIRED |
| `daily-writer` | `55 23 * * *` | `scripts/dream/daily_writer.py` | `cerebelo/diario/` | REQUIRED |
| `weekly-synthesizer` | `0 4 * * 0` | `scripts/dream/weekly_synthesizer.py` | vault (síntese semanal) | OPTIONAL_BY_PROFILE |
| `capture-maintenance` | `0 4 * * 0` | `scripts/capture/capture_maintenance.py` | banco de captura | REQUIRED |
| `health-dashboard` | `50 23 * * *` | `scripts/health/health_dashboard.py` | `cortex/insula/saude/` | REQUIRED |
| `alert-dispatcher` | `52 23 * * *` | `scripts/health/alert_dispatcher.py` | alertas (inbox) | OPTIONAL_BY_PROFILE |
| `backup-databases` | `0 2 * * *` | `hive-mind backup run --apply` | backups SQLite | REQUIRED |
| `knowledge-health` | `0 2 * * *` | `scripts/health/audit_memory.py` | `cortex/temporal/` + métricas | REQUIRED |
| `decision-promoter` | `40 23 * * *` | `scripts/knowledge/decision_promoter.py` | `cortex/frontal/decisoes/` | REQUIRED |
| `project-synthesizer` | `42 23 * * *` | `scripts/knowledge/project_synthesizer.py` | `cortex/frontal/projetos/` | OPTIONAL_BY_PROFILE |
| `work-tracker` | `44 23 * * *` | `scripts/knowledge/work_tracker.py` | `cortex/frontal/trabalho/` | OPTIONAL_BY_PROFILE |
| `pattern-distiller` | `0 5 * * 0` | `scripts/knowledge/pattern_distiller.py` | vault (padrões) | OPTIONAL_BY_PROFILE |
| `conflict-detector` | `30 5 * * 0` | `scripts/knowledge/conflict_detector.py` | `cortex/insula/conflitos/` | OPTIONAL_BY_PROFILE |
| `topic-consolidator` | `0 6 * * 0` | `scripts/knowledge/topic_consolidator.py` | `cortex/temporal/` | OPTIONAL_BY_PROFILE |
| `review-writer` | `7 8 * * *` | `scripts/knowledge/review_writer.py` | `cortex/insula/saude/revisao` | OPTIONAL_BY_PROFILE |
| `drift-detector` | `0 2 1 * *` | `scripts/knowledge/drift_detector.py` | `cortex/temporal/arquivo/` | OPTIONAL_BY_PROFILE |

> O job `backup` (antigo `scripts/maintenance/backup.py`) foi **removido** do
> manifesto: o script não existia no repositório (untracked) e era, na
> verdade, um wrapper de auditoria de artefatos — não um backup. A capacidade
> de backup é coberta por `backup-databases` (motor nativo `hive-mind backup`).
> Ver [operacao.md](operacao.md).

### 14.1 Ordenação como dependência, não como relógio

O Linux historicamente codificava "a bridge alimenta o dream" como 02:45 vs
03:00. Isso **não é contrato** — uma bridge lenta, um reboot no intervalo ou um
misfire quebram a ordem em silêncio. O manifesto declara a dependência
explicitamente:

```yaml
  - name: dream-cycle
    depends_on:
      - claude-mem-bridge
    dependency_policy:
      require_success_since_last_run: true
```

O schema valida: dependência inexistente, auto-referência e ciclo são
rejeitados na carga do manifesto.

---

## 15. Agendamento por plataforma

O **dono real** dos jobs hoje é o agendador da plataforma; o manifesto é o
catálogo candidato que o daemon só calcula em shadow.

### 15.1 Windows — Task Scheduler

Registrado via `hive-mind service windows-jobs --apply` e
`hive-mind service windows-runtime --apply` (ver [cli.md](cli.md) e
[instalacao.md](instalacao.md)).

**Jobs de conhecimento** (`windows_jobs.py`):

| Tarefa | Script / Comando | Repetição |
|---|---|---|
| `HiveMind-DreamCycle` | `scripts/dream/dream_cycle.py` | **PT4H** (equivale ao cron `0 */4 * * *`) |
| `HiveMind-ClaudeMemBridge` | `scripts/services/claude_mem_bridge.py` | diária 02:00 |
| `HiveMind-KnowledgeHealth` | `scripts/health/audit_memory.py` | diária 02:00 |
| `HiveMind-Backup` | `hive-mind backup run --apply` | diária 02:00 |
| `HiveMind-DailyWriter` | `scripts/dream/daily_writer.py` | diária |
| `HiveMind-WeeklySynthesizer` | `scripts/dream/weekly_synthesizer.py` | diária |
| `HiveMind-HealthDashboard` | `scripts/health/health_dashboard.py` | diária |
| `HiveMind-AlertDispatcher` | `scripts/health/alert_dispatcher.py` | diária |
| `HiveMind-DecisionPromoter` | `scripts/knowledge/decision_promoter.py` | diária |
| `HiveMind-ProjectSynthesizer` | `scripts/knowledge/project_synthesizer.py` | diária |
| `HiveMind-WorkTracker` | `scripts/knowledge/work_tracker.py` | diária |
| `HiveMind-PatternDistiller` | `scripts/knowledge/pattern_distiller.py` | diária |
| `HiveMind-ConflictDetector` | `scripts/knowledge/conflict_detector.py` | diária |
| `HiveMind-TopicConsolidator` | `scripts/knowledge/topic_consolidator.py` | diária |
| `HiveMind-ReviewWriter` | `scripts/knowledge/review_writer.py` | diária |
| `HiveMind-DriftDetector` | `scripts/knowledge/drift_detector.py` | diária |
| `HiveMind-CaptureMaintenance` | `scripts/capture/capture_maintenance.py` | diária |

O XML de cada tarefa usa `LogonType=InteractiveToken`,
`RunLevel=LeastPrivilege`, `MultipleInstancesPolicy=IgnoreNew`,
`StartWhenAvailable=true`. O registro exporta o XML anterior para
`logs/scheduled-tasks/` antes de sobrescrever (rollback). O `DreamCycle` é o
único com `Repetition Interval=PT4H Duration=P1D`.

**Runtime tasks** (`windows_runtime.py`):

| Tarefa | Trigger | Descrição |
|---|---|---|
| `HiveMind-Supervisor` | logon | Sobe o supervisor (launcher `hive-mind-supervisorw`), `RestartOnFailure` 10× |
| `HiveMind-PostRebootValidation` | logon | Valida a stack pós-reboot (`hive-mind-post-rebootw`), `ExecutionTimeLimit=PT1H` |

### 15.2 POSIX — systemd timers

Instalados via `python -m hive_mind.maintenance.runtime_services install`
([runtime_services.py](../src/hive_mind/maintenance/runtime_services.py)).
Units user-level em `~/.config/systemd/user/`. Timers canônicos:

| Unit | `OnCalendar` | Serviço |
|---|---|---|
| `sinapse-capture-tailer.timer` | `OnUnitActiveSec=30s` | capture tailer (near-realtime) |
| `sinapse-maintenance.timer` | `Sun 04:00` | compactação claude-mem |
| `sinapse-bridge.timer` | `*-*-* 02:45:00` | `claude_mem_bridge.py` |
| `sinapse-dream.timer` | `*-*-* 03:00:00` | `dream_cycle.py` |
| `sinapse-daily.timer` | `*-*-* 23:55:00` | `daily_writer.py` |
| `sinapse-weekly.timer` | `Sun 04:00` | `weekly_synthesizer.py` |
| `sinapse-topics.timer` | `Sun 06:00` | `topic_consolidator.py` (log-only) |
| `sinapse-health.timer` | `*-*-* 23:50:00` | `health_dashboard.py` |
| `sinapse-alert.timer` | `*-*-* 23:52:00` | `alert_dispatcher.py --apply` |
| `sinapse-decisions.timer` | `*-*-* 23:40:00` | `decision_promoter.py --apply` |
| `sinapse-projects.timer` | `*-*-* 23:42:00` | `project_synthesizer.py --apply` |
| `sinapse-patterns.timer` | `Sun 05:00` | `pattern_distiller.py --apply` |
| `sinapse-conflicts.timer` | `Sun 05:30` | `conflict_detector.py --apply` |
| `sinapse-review.timer` | `*-*-* 08:07:00` | `review_writer.py` |
| `sinapse-work.timer` | `*-*-* 23:44:00` | `work_tracker.py --apply` |
| `sinapse-backup.timer` | `*-*-* 02:00:00` | `backup_databases.py` |
| `sinapse-drift.timer` | `*-*-01 02:00:00` | `drift_detector.py` (log-only) |

> **Discrepância documentada:** o cron canônico do `dream-cycle` no manifesto
> é `0 */4 * * *` (a cada 4 horas), reproduzido no Windows como `PT4H`. O
> timer systemd `sinapse-dream.timer` ainda usa a cadência diária `03:00`
> (legado pré-manifesto). O alinhamento definitivo ocorre no cutover (D010).

---

## 16. Compose projects

Projetos `docker compose` obrigatórios/opcionais (ver [instalacao.md](instalacao.md)):

| Projeto | Compose | Containers | Required |
|---|---|---|---|
| falkordb | `docker-compose.falkordb.yml` | `sinapse-falkordb` | local-full |
| milvus | `integrations/milvus/docker-compose.yml` | `hive-mind-milvus` | local-full |
| ragflow | `integrations/ragflow/docker-compose.yml` | `hive-mind-ragflow`, `-mysql`, `es01`, `redis`, `minio` | local-full |
| langfuse | `integrations/langfuse/docker-compose.yml` | langfuse | opcional (`required: false`) |

### 16.1 Restart policy é o que faz a stack voltar

Docker iniciar **não** basta: um container só retorna se o serviço declarar
`restart`. Um incidente real mostrou a diferença — `falkordb` tinha
`unless-stopped` e voltava, enquanto milvus e os cinco containers do ragflow
tinham `restart: no` e ficavam fora.

Todo serviço de compose obrigatório declara `restart: unless-stopped`.
`tests/unit/test_compose_restart_policy.py` lê os projetos obrigatórios do
manifesto e falha se algum serviço não voltar após um restart do Docker —
inclusive em projeto novo. A restart policy está presente nos compose
consumidos pela instalação limpa (`install.bat`/`install.sh` executam
`docker compose up -d` sobre os arquivos do próprio repositório, sem gerar
compose).

---

## 17. Estado de implementação e gates

| Gate | Estado |
|---|---|
| Observação shadow (readiness/ordem topológica) | implementado (D007) |
| HTTP loopback read-only | implementado (D007 fatia 2) |
| Socket de controle (ping/status; mutações recusadas em shadow) | implementado (D008 fatia 1) |
| Managed supervisor (`run --serve`) | implementado (F4/D008) |
| Scheduler shadow (`schedule.shadow.json`) | implementado (F6) |
| Execução real dos 18 jobs pelo daemon | NOT_STARTED (F7) |
| Enforcement da dependência bridge→dream em runtime | NOT_STARTED |
| Lock/lease de execução única | PARTIAL — `SqliteSchedulerStore` existe, sem execução real |
| Cutover de ownership (`cutover.journal`) | NOT_STARTED (D010) |
| Recuperação após reboot comprovada em clean-install | NÃO COMPROVADA (gate W2/W3) |

Ver  e
 (grupo Runtime),
bem como [incidentes.md](incidentes.md) e [observabilidade.md](observabilidade.md).

---

## 18. Cross-references

- **Instalação** (perfis, Windows/Linux/Docker, rollback): [instalacao.md](instalacao.md)
- **Operação** (health, backup, recover, manutenção, P2P): [operacao.md](operacao.md)
- **CLI** (subcomandos `config`, `service`, `backup`, `agents`, `validate`, `vault`): [cli.md](cli.md)
- **Arquitetura** (anatomia do cérebro, fluxo de conhecimento): [arquitetura.md](arquitetura.md)
- **Pipeline de dados** (observações → neurônios): [pipeline-dados.md](pipeline-dados.md)
- **Observabilidade** (métricas, /health, /metrics): [observabilidade.md](observabilidade.md)
- **Incidentes** (recuperação, restart policy): [incidentes.md](incidentes.md)
- **Segurança** (control socket, DACL, loopback): [seguranca.md](seguranca.md)
- Referência canônica de infra: [04-infrastructure.md](04-infrastructure.md)
