# Runtime & Daemon — `hive-mindd`

> **Hive-Mind v3.10.1** — the native Hive-Mind control plane: the `hive-mindd`
> daemon, the declarative manifest `config/runtime.yaml`, the service catalog,
> the scheduler, and the per-platform scheduling mechanisms.
>
> Normative references: [spec §15](../specs/control-plane-redesign-v2.md),
> Annexes D.2 (lock), D.4 (shadow purity), D.5 (project root), D.6 (scheduler),
> , and the operational
> documents in this set: [installation.md](installation.md),
> [operations.md](operations.md), [cli.md](cli.md),
> [observability.md](observability.md).

---

## 1. Mental model: who owns it today

Hive-Mind explicitly separates **three layers of truth** about the runtime.
Never confuse "what is declared" with "what is actually running":

| Layer | State | Real owner today |
|---|---|---|
| **CURRENT** | The legacy launcher (Task Scheduler on Windows, systemd timers on Linux, Node supervisor) **starts and monitors** the services and jobs. | Task Scheduler / systemd / Node supervisor |
| **TRANSITION** | `config/runtime.yaml` is the **candidate manifest**. `hive-mindd` in shadow mode only **observes** and **computes** next-run; it **does not trigger anything**. | `hive-mindd` (read-only) |
| **TARGET** | `hive-mindd` as the single owner of services and jobs, after cutover (D010). | `hive-mindd` (managed) |

**No automatic cutover occurs.** The ownership transition is always explicit,
one service at a time, with automatic rollback. Nothing is silently adopted.

---

## 2. Declarative manifest (`config/runtime.yaml`)

`config/runtime.yaml` (schema v3) is the single source of **declarative** truth
about:

- local services (`services`),
- external services (`external_services`),
- periodic jobs (`jobs`),
- compose projects (`compose_projects`),
- global restart policy (`restart`).

It is validated by Pydantic v2 in
[manifest.py](../src/hive_mind/daemon/manifest.py). The schema rejects, at load
time: nonexistent dependencies, self-references, and cycles in the topological
order.

```powershell
hive-mind config validate     # schema / invariant errors
hive-mind config show         # normalized manifest (YAML)
hive-mind config show --json  # normalized manifest (JSON)
```

### 2.1 Top-level fields

| Field | Type | Description |
|---|---|---|
| `schema_version` | int | Schema version (current: `3`) |
| `profile` | string | Active profile: `local-min` or `local-full` |
| `vault` | path | Vault directory (`cerebro`) |
| `pyproject_root` | path | Root resolved relative to the file (`.` = repo root) |
| `paths.*` | path/null | Overrides: `data_dir`, `state_dir`, `log_dir`, `user_config_dir`, `config_file` |
| `services` | list | Local manageable services |
| `external_services` | list | Services outside the daemon's control (ollama, docker, milvus…) |
| `jobs` | list | Periodic jobs with cron/interval |
| `compose_projects` | list | Required/optional `docker compose` projects |
| `restart` | map | Global restart policy |

---

## 3. Ownership model

Each service has an ownership state (spec §9):

| State | Meaning |
|---|---|
| `legacy` | The old launcher (Task Scheduler, Node, systemd) is still the owner |
| `shadow` | The daemon **observes** the service without acting |
| `managed` | The daemon is the owner (starts, monitors, restarts) |

The `legacy → shadow → managed` transition is always via explicit cutover, one
service at a time, with automatic rollback.

---

## 4. The `hive-mindd` daemon

The daemon is the control-plane binary (`hive-mindd`, entry point
[main.py](../src/hive_mind/daemon/main.py)). It operates in three modes:

```powershell
hive-mindd run --shadow                              # shadow pass (passive)
hive-mindd run --shadow --serve                      # shadow + HTTP + control socket
hive-mindd run --serve                               # managed (F4) + HTTP + control socket
hive-mindd run                                       # not implemented yet -> 69
```

| Invocation | Behavior | Exits |
|---|---|---|
| `run --shadow` | Single passive pass: observes, writes `services.shadow.json`, releases the lock. **Does not start any process.** | `0` |
| `run --shadow --serve` | Shadow + serves loopback HTTP and the control socket (mutations **refused**). | `0` (until interrupted) |
| `run --serve` | Managed: `ManagedSupervisor.start_all()`, monitors, serves HTTP and socket (mutations **allowed**). | `0` (until interrupted) |
| `run` (no flags) | Managed without HTTP not yet implemented in this slice. | `69` (`EX_UNAVAILABLE`) |

> **Note on `run --serve`:** managed mode is reached via `--serve` (the daemon
> supervises the services and exposes the read surface and the control socket).
> Bare `run` (without `--shadow` or `--serve`) returns `EX_UNAVAILABLE` (69) —
> the managed supervisor without the HTTP surface is not yet the canonical path.
> Shadow never becomes managed on its own.

Common `hive-mindd run` flags:

| Flag | Default | Description |
|---|---|---|
| `--manifest <file>` | `config/runtime.yaml` | Manifest path |
| `--state-dir <dir>` | `<root>/.hive-mind/state` | State directory |
| `--project-root <dir>` | auto-detected | Project root override |
| `--host <host>` | `127.0.0.1` | Loopback HTTP host |
| `--port <port>` | `37780` | Loopback HTTP port |

---

## 5. Single instance (Annex D.2)

Exactly **one** `hive-mindd` per host, guaranteed by
[lock.py](../src/hive_mind/daemon/lock.py):

| Platform | Mechanism | Name/File |
|---|---|---|
| Windows | named mutex (`CreateMutexW`) | `Local\Hive-Mind-hive-mindd` |
| Linux/macOS | `flock(LOCK_EX | LOCK_NB)` | `state_dir/daemon.lock` |

A second instance fails immediately with `SingleInstanceLockError` (exit
`EX_UNAVAILABLE`). The lock is held for the **entire** execution — not only
during the brief observation — so a second instance fails while the first is
alive, including during the serving loop.

> **Win32 note:** the literal spec name (`Local\Hive-Mind\hive-mindd`) has two
> backslashes; Win32 kernel objects accept only one after the `Local\` prefix.
> The segments are joined with a hyphen: `Local\Hive-Mind-hive-mindd`.

---

## 6. Shadow mode (F3 / D007)

```powershell
hive-mindd run --shadow [--project-root <dir>] [--manifest <file>] [--state-dir <dir>]
```

A **passive** pass: acquires the lock, reads the manifest, computes readiness
and the topological order of the active profile's services, writes the result,
and releases the lock. Exits `0`.

**Absolute purity** ([supervisor.py](../src/hive_mind/daemon/supervisor.py),
guaranteed by `test_shadow_purity.py`): in shadow mode the daemon does **not**

- start any process (`subprocess.Popen`/`run`/`call`);
- write to `runtime.yaml`;
- create any state file other than `services.shadow.json`
  (and `schedule.shadow.json` when the scheduler runs);
- fire jobs or execute cutover.

The observed state lives in `state_dir/services.shadow.json`:

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

`readiness` is `ready` / `not_ready` (with an injected prober) or `unknown`
(without a prober). Top-level `ready` is `true` **only** when every
`required: true` service is `ready`.

---

## 7. Managed mode (F4 / D008)

```powershell
hive-mindd run --serve [--host 127.0.0.1] [--port 37780]
```

The managed daemon actually **starts and supervises** the declared services via
`ManagedSupervisor` ([managed.py](../src/hive_mind/daemon/managed.py)):
`start_all()` → `start_monitor()` → state persisted to `services.managed.json`.
Under the single-instance lock, the daemon:

1. starts the services in topological order (`startup_order`);
2. applies `restart_policy` / `restart_delay_seconds` / `restart_limit`;
3. opens the control socket in **managed** mode (mutations allowed);
4. serves the loopback HTTP (`/health`, `/ready`, `/metrics`);
5. monitors until interruption, then `stop_monitor()` → `stop_all()`.

The transition of a service from `legacy` to `managed` is always via explicit
cutover — the transactional cutover journal (`cutover.journal`) is part of F4.

---

## 8. State directory

`state_dir` (default `<project-root>/.hive-mind/state/`, ignored by git) holds:

| File | Phase | Content |
|---|---|---|
| `daemon.lock` | D007 | Single-instance lock (POSIX) |
| `services.shadow.json` | D007 | Shadow observation, read-only over the legacy |
| `services.managed.json` | D008 | State of managed processes (PIDs, restarts) |
| `schedule.shadow.json` | D008 | Computed next-run of jobs (shadow, does not fire) |
| `cutover.journal` | F4 | Transactional cutover journal |
| `jobs.db` | F7 | SQLite persistence of the scheduler (`job_schedule`) |
| `windows-jobs.lock` | P1 | `MaintenanceLock` lock for task registration |
| `windows-runtime.lock` | P1 | `MaintenanceLock` lock for runtime tasks |

---

## 9. Read-only loopback HTTP (spec §15.1 / §15.4)

```powershell
hive-mindd run --shadow --serve [--host 127.0.0.1] [--port 37780]
```

After the pass, the daemon serves **exactly three read routes** in
[http_api.py](../src/hive_mind/daemon/http_api.py), loopback-bound, no TLS, no
auth, no write body:

| Route | Response |
|---|---|
| `GET /health` | `{"state": "healthy"\|"degraded"\|"unknown", "services": {...}, "jobs": {}}` |
| `GET /ready` | `200` if all `required` are ready; `503` otherwise (**fail-closed**) |
| `GET /metrics` | Prometheus: `hive_service_count`, `hive_service_ready`, `hive_daemon_ready` |

Without shadow observation yet, `/ready` is **503** (fail-closed, never
fail-open). No mutation route exists: `POST /start`, `/stop`, `/reload`,
`/run-job` return 404. The invariant is tested (`READ_ONLY_HTTP_ROUTES` in
`test_daemon_http_routes.py`).

**Default:** host `127.0.0.1`, port `37780`.

---

## 10. Control socket (spec §15.2/§15.3)

All mutation goes through an authenticated local control channel, **never** via
HTTP ([control.py](../src/hive_mind/daemon/control.py)):

| Platform | Transport | Protection |
|---|---|---|
| Windows | named pipe `\\.\pipe\hive-mindd` | DACL granting access only to the creating user (owner + `GENERIC_ALL` via pywin32); everyone else receives `ACCESS_DENIED` |
| POSIX | Unix socket `state_dir/daemon.sock` | `0o600` inside `state_dir` `0o700` |

Protocol: one JSON object per message — `{"command", "args"}` →
`{"ok", "data", "error"}`.

The shadow dispatcher
([control_dispatch.py](../src/hive_mind/daemon/control_dispatch.py)) honors
`ping`/`status` and **refuses** all mutation (`start`/`stop`/`restart`/
`reload`/`run-job`) — shadow never acts (Annex D.4). The managed dispatcher
(`ManagedControlDispatcher`) accepts supervised mutations.

```powershell
hive-mind service ping   # pong if the socket is alive
```

Dependency: `pywin32` (Windows), decided in ledger DH-002.

---

## 11. Scheduler (F6 shadow / D.6)

The scheduler ([scheduler.py](../src/hive_mind/daemon/scheduler.py)) in shadow
mode only **computes** when each job would run (`next_fire_time`) and persists
the plan to `schedule.shadow.json`. **It does not fire anything** (Annex D.4).
Firing jobs is a managed operation (F7).

- `next_fire_time` uses **APScheduler** triggers (spec D.6 sanction; no
  hand-rolled cron parser): `CronTrigger.from_crontab` for cron and direct
  computation for `interval`.
- `SchedulerStore` is the persistence interface (next_run/last_run/lease):
  - `MemorySchedulerStore` — default in-process, does **not** survive a restart;
  - `SqliteSchedulerStore` — SQLite persistence at `state_dir/jobs.db`
    (`job_schedule` table with `active_leases`), survives a restart (F7).
- `ShadowScheduler.compute(now)` writes, per job: `name`, `type`, `next_run`
  (ISO-8601 with offset), `last_run`, `max_instances`, `would_fire`.

---

## 12. Local service catalog

Source: `services` in `config/runtime.yaml`. `required: true` is the **doctor
gate** — an installation is healthy only when every `required` is `ready`.

| Service | Order | Required | Port | Dependencies | Readiness | Command |
|---|---|---|---|---|---|---|
| `sinapse-claude-mem` | 10 | **yes** | 37700 | — | tcp 127.0.0.1:37700 | `python -m hive_mind.services.claude_mem_launcher` |
| `hive-otel-collector` | 15 | no | 3100 | — | — | `python scripts/services/otel_collector.py --host 127.0.0.1` |
| `sinapse-sqlite-vec` | 20 | **yes** | 37701 | `sinapse-claude-mem` | tcp 127.0.0.1:37701 | `python plugins/sqlite-vec-worker/worker.py` |
| `sinapse-graphify-watch` | 30 | no | — | — | — | `python -m graphify watch cerebro --debounce 10.0` |
| `sinapse-api` | 40 | no | 37702 | `sinapse-sqlite-vec` | http `/api/v1/health` (200/401) | `python scripts/services/sinapse-api.py` |
| `sinapse-mcp-http` | 50 | no | 37703 | `sinapse-api` | http `/health` (200) | `python scripts/services/sinapse-mcp-http.py` |
| `sinapse-capture-realtime` | 60 | **yes** | — | `sinapse-claude-mem`, `sinapse-sqlite-vec` | — | `python scripts/capture/capture-realtime.py` |
| `sinapse-consolidate` | 65 | no | — | `sinapse-claude-mem`, `sinapse-sqlite-vec` | — | `python scripts/knowledge/consolidate_loop.py` |

> **`sinapse-claude-mem` and `sinapse-sqlite-vec`** require the claude-mem
> plugin installed (`requires_claude_mem_plugin: true`). On a machine without an
> agent/IDE, they are disabled at install to avoid a boot crash-loop — temporal
> memory comes up together with the first registered agent.

### 12.1 Per-service environment variables (summary)

| Service | Env |
|---|---|
| `sinapse-claude-mem` | `CLAUDE_MEM_WORKER_HOST=127.0.0.1`, `CLAUDE_MEM_WORKER_PORT=37700`, `CLAUDE_MEM_CHROMA_ENABLED=false`, `CLAUDE_MEM_MANAGED=true` |
| `sinapse-sqlite-vec` | `VEC_WORKER_PORT=37701`, `CLAUDE_MEM_DB`, `FASTEMBED_CACHE_PATH` |
| `sinapse-api` | `HIVE_MIND_API_HOST=127.0.0.1`, `HIVE_MIND_API_PORT=37702` (+ `env_file: .env`) |
| `sinapse-mcp-http` | `SINAPSE_MCP_HTTP_HOST=127.0.0.1`, `SINAPSE_MCP_HTTP_PORT=37703` (+ `env_file: .env`) |
| `sinapse-consolidate` | `HIVE_CONSOLIDATE_INTERVAL_SECONDS=60`, `HIVE_CONSOLIDATE_MEDIUM_SECONDS=300`, `HIVE_CONSOLIDATE_SLOW_SECONDS=3600` |

See the complete canonical variable table in
[04-infrastructure.md](04-infrastructure.md) and [architecture.md](architecture.md).

---

## 13. External services

Services outside the daemon's control (the daemon only **checks readiness**):

| Service | Required | Profiles | Readiness |
|---|---|---|---|
| `ollama` | yes | local-min, local-full | http `127.0.0.1:11434/api/tags` (200) |
| `docker-desktop` | yes | local-full | command `docker info --format {{.ServerVersion}}` |
| `falkordb` | yes | local-full | tcp `127.0.0.1:6379` |
| `milvus` | yes | local-full | tcp `127.0.0.1:19530` |
| `ragflow` | yes | local-full | http `127.0.0.1:9380/api/v1/system/healthz` (200) |
| `syncthing-watcher` | yes | local-full | http `127.0.0.1:8384/rest/noauth/health` (200/401/403) |
| `lightrag` | no | local-full | http `127.0.0.1:9621/health` (200) |

---

## 14. Periodic jobs (canonical inventory)

Source: `jobs` in `config/runtime.yaml` (18 jobs; all with a `__main__` entry
point, executable code, and an identifiable write target). Timezone of all
crons: `America/Sao_Paulo`.

| Job | Cron | Script | Writes to | Classification |
|---|---|---|---|---|
| `dream-cycle` | `0 */4 * * *` | `scripts/dream/dream_cycle.py` | `cortex/temporal/` | REQUIRED |
| `capture-tailer` | interval 30s | `scripts/capture/capture-tailer.py` | Claude Mem via `capture_core.ingest` | REQUIRED |
| `claude-mem-bridge` | `45 2 * * *` | `scripts/services/claude_mem_bridge.py` | UMC (observations) | REQUIRED |
| `daily-writer` | `55 23 * * *` | `scripts/dream/daily_writer.py` | `cerebelo/diario/` | REQUIRED |
| `weekly-synthesizer` | `0 4 * * 0` | `scripts/dream/weekly_synthesizer.py` | vault (weekly synthesis) | OPTIONAL_BY_PROFILE |
| `capture-maintenance` | `0 4 * * 0` | `scripts/capture/capture_maintenance.py` | capture database | REQUIRED |
| `health-dashboard` | `50 23 * * *` | `scripts/health/health_dashboard.py` | `cortex/insula/saude/` | REQUIRED |
| `alert-dispatcher` | `52 23 * * *` | `scripts/health/alert_dispatcher.py` | alerts (inbox) | OPTIONAL_BY_PROFILE |
| `backup-databases` | `0 2 * * *` | `hive-mind backup run --apply` | SQLite backups | REQUIRED |
| `knowledge-health` | `0 2 * * *` | `scripts/health/audit_memory.py` | `cortex/temporal/` + metrics | REQUIRED |
| `decision-promoter` | `40 23 * * *` | `scripts/knowledge/decision_promoter.py` | `cortex/frontal/decisoes/` | REQUIRED |
| `project-synthesizer` | `42 23 * * *` | `scripts/knowledge/project_synthesizer.py` | `cortex/frontal/projetos/` | OPTIONAL_BY_PROFILE |
| `work-tracker` | `44 23 * * *` | `scripts/knowledge/work_tracker.py` | `cortex/frontal/trabalho/` | OPTIONAL_BY_PROFILE |
| `pattern-distiller` | `0 5 * * 0` | `scripts/knowledge/pattern_distiller.py` | vault (patterns) | OPTIONAL_BY_PROFILE |
| `conflict-detector` | `30 5 * * 0` | `scripts/knowledge/conflict_detector.py` | `cortex/insula/conflitos/` | OPTIONAL_BY_PROFILE |
| `topic-consolidator` | `0 6 * * 0` | `scripts/knowledge/topic_consolidator.py` | `cortex/temporal/` | OPTIONAL_BY_PROFILE |
| `review-writer` | `7 8 * * *` | `scripts/knowledge/review_writer.py` | `cortex/insula/saude/revisao` | OPTIONAL_BY_PROFILE |
| `drift-detector` | `0 2 1 * *` | `scripts/knowledge/drift_detector.py` | `cortex/temporal/arquivo/` | OPTIONAL_BY_PROFILE |

> The `backup` job (the old `scripts/maintenance/backup.py`) was **removed** from
> the manifest: the script did not exist in the repository (untracked) and was,
> in fact, an artifact-audit wrapper — not a backup. The backup capability is
> covered by `backup-databases` (the native `hive-mind backup` engine). See
> [operations.md](operations.md).

### 14.1 Ordering as a dependency, not as a clock

Linux historically encoded "the bridge feeds the dream" as 02:45 vs 03:00. This
is **not a contract** — a slow bridge, a reboot in the interval, or a misfire
silently breaks the order. The manifest declares the dependency explicitly:

```yaml
  - name: dream-cycle
    depends_on:
      - claude-mem-bridge
    dependency_policy:
      require_success_since_last_run: true
```

The schema validates: nonexistent dependencies, self-references, and cycles are
rejected at manifest load.

---

## 15. Per-platform scheduling

The **real owner** of jobs today is the platform scheduler; the manifest is the
candidate catalog that the daemon only computes in shadow mode.

### 15.1 Windows — Task Scheduler

Registered via `hive-mind service windows-jobs --apply` and
`hive-mind service windows-runtime --apply` (see [cli.md](cli.md) and
[installation.md](installation.md)).

**Knowledge jobs** (`windows_jobs.py`):

| Task | Script / Command | Repetition |
|---|---|---|
| `HiveMind-DreamCycle` | `scripts/dream/dream_cycle.py` | **PT4H** (equivalent to cron `0 */4 * * *`) |
| `HiveMind-ClaudeMemBridge` | `scripts/services/claude_mem_bridge.py` | daily 02:00 |
| `HiveMind-KnowledgeHealth` | `scripts/health/audit_memory.py` | daily 02:00 |
| `HiveMind-Backup` | `hive-mind backup run --apply` | daily 02:00 |
| `HiveMind-DailyWriter` | `scripts/dream/daily_writer.py` | daily |
| `HiveMind-WeeklySynthesizer` | `scripts/dream/weekly_synthesizer.py` | daily |
| `HiveMind-HealthDashboard` | `scripts/health/health_dashboard.py` | daily |
| `HiveMind-AlertDispatcher` | `scripts/health/alert_dispatcher.py` | daily |
| `HiveMind-DecisionPromoter` | `scripts/knowledge/decision_promoter.py` | daily |
| `HiveMind-ProjectSynthesizer` | `scripts/knowledge/project_synthesizer.py` | daily |
| `HiveMind-WorkTracker` | `scripts/knowledge/work_tracker.py` | daily |
| `HiveMind-PatternDistiller` | `scripts/knowledge/pattern_distiller.py` | daily |
| `HiveMind-ConflictDetector` | `scripts/knowledge/conflict_detector.py` | daily |
| `HiveMind-TopicConsolidator` | `scripts/knowledge/topic_consolidator.py` | daily |
| `HiveMind-ReviewWriter` | `scripts/knowledge/review_writer.py` | daily |
| `HiveMind-DriftDetector` | `scripts/knowledge/drift_detector.py` | daily |
| `HiveMind-CaptureMaintenance` | `scripts/capture/capture_maintenance.py` | daily |

Each task's XML uses `LogonType=InteractiveToken`, `RunLevel=LeastPrivilege`,
`MultipleInstancesPolicy=IgnoreNew`, `StartWhenAvailable=true`. Registration
exports the previous XML to `logs/scheduled-tasks/` before overwriting
(rollback). `DreamCycle` is the only one with `Repetition Interval=PT4H
Duration=P1D`.

**Runtime tasks** (`windows_runtime.py`):

| Task | Trigger | Description |
|---|---|---|
| `HiveMind-Supervisor` | logon | Starts the supervisor (`hive-mind-supervisorw` launcher), `RestartOnFailure` 10× |
| `HiveMind-PostRebootValidation` | logon | Validates the stack post-reboot (`hive-mind-post-rebootw`), `ExecutionTimeLimit=PT1H` |

### 15.2 POSIX — systemd timers

Installed via `python -m hive_mind.maintenance.runtime_services install`
([runtime_services.py](../src/hive_mind/maintenance/runtime_services.py)).
User-level units in `~/.config/systemd/user/`. Canonical timers:

| Unit | `OnCalendar` | Service |
|---|---|---|
| `sinapse-capture-tailer.timer` | `OnUnitActiveSec=30s` | capture tailer (near-realtime) |
| `sinapse-maintenance.timer` | `Sun 04:00` | claude-mem compaction |
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

> **Documented discrepancy:** the canonical `dream-cycle` cron in the manifest
> is `0 */4 * * *` (every 4 hours), reproduced on Windows as `PT4H`. The systemd
> timer `sinapse-dream.timer` still uses the daily `03:00` cadence (pre-manifest
> legacy). The definitive alignment happens at cutover (D010).

---

## 16. Compose projects

Required/optional `docker compose` projects (see [installation.md](installation.md)):

| Project | Compose | Containers | Required |
|---|---|---|---|
| falkordb | `docker-compose.falkordb.yml` | `sinapse-falkordb` | local-full |
| milvus | `integrations/milvus/docker-compose.yml` | `hive-mind-milvus` | local-full |
| ragflow | `integrations/ragflow/docker-compose.yml` | `hive-mind-ragflow`, `-mysql`, `es01`, `redis`, `minio` | local-full |
| langfuse | `integrations/langfuse/docker-compose.yml` | langfuse | optional (`required: false`) |

### 16.1 The restart policy is what brings the stack back

Starting Docker is **not** enough: a container only returns if the service
declares `restart`. A real incident showed the difference — `falkordb` had
`unless-stopped` and came back, while milvus and the five ragflow containers had
`restart: no` and stayed down.

Every required compose service declares `restart: unless-stopped`.
`tests/unit/test_compose_restart_policy.py` reads the required projects from the
manifest and fails if any service does not return after a Docker restart —
including in a new project. The restart policy is present in the compose files
consumed by the clean install (`install.bat`/`install.sh` run `docker compose up
-d` over the repository's own files, without generating compose).

---

## 17. Implementation state and gates

| Gate | State |
|---|---|
| Shadow observation (readiness/topological order) | implemented (D007) |
| Read-only loopback HTTP | implemented (D007 slice 2) |
| Control socket (ping/status; mutations refused in shadow) | implemented (D008 slice 1) |
| Managed supervisor (`run --serve`) | implemented (F4/D008) |
| Shadow scheduler (`schedule.shadow.json`) | implemented (F6) |
| Real execution of the 18 jobs by the daemon | NOT_STARTED (F7) |
| Runtime enforcement of the bridge→dream dependency | NOT_STARTED |
| Single-execution lock/lease | PARTIAL — `SqliteSchedulerStore` exists, without real execution |
| Ownership cutover (`cutover.journal`) | NOT_STARTED (D010) |
| Post-reboot recovery proven in clean-install | NOT PROVEN (gate W2/W3) |

See  and
 (Runtime group),
as well as [incidents.md](incidents.md) and [observability.md](observability.md).

---

## 18. Cross-references

- **Installation** (profiles, Windows/Linux/Docker, rollback): [installation.md](installation.md)
- **Operations** (health, backup, recover, maintenance, P2P): [operations.md](operations.md)
- **CLI** (`config`, `service`, `backup`, `agents`, `validate`, `vault` subcommands): [cli.md](cli.md)
- **Architecture** (brain anatomy, knowledge flow): [architecture.md](architecture.md)
- **Data pipeline** (observations → neurons): [data-pipeline.md](data-pipeline.md)
- **Observability** (metrics, /health, /metrics): [observability.md](observability.md)
- **Incidents** (recovery, restart policy): [incidents.md](incidents.md)
- **Security** (control socket, DACL, loopback): [security.md](security.md)
- Canonical infrastructure reference: [04-infrastructure.md](04-infrastructure.md)
