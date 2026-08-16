# Operations and Maintenance — Hive-Mind

> **Hive-Mind v3.10.1** — day-to-day operations routines: health diagnostics,
> verified backup, disaster recovery, maintenance commands, and P2P sync.
>
> References: [runtime.md](runtime.md) (daemon/services/scheduler),
> [installation.md](installation.md), [cli.md](cli.md),
> [operations.md](operations.md) (backup engine audit),
> [07-p2p-sync-setup.md](07-p2p-sync-setup.md).

---

## 1. Health diagnostics

### 1.1 Backend pre-check (MCP)

Whenever there is doubt about the backends' state, use `sinapse_health()` — it
returns the status of the 7 backends federated by `sinapse_query` (UMC,
NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem) and the
`knowledge_health` metrics.

### 1.2 `hive-mind doctor`

**Read-only** diagnostics of agent integrations (writes nothing):

```powershell
hive-mind doctor                 # all detected providers
hive-mind doctor --only claude   # one provider
hive-mind doctor --json
```

Exit `0` only when **all detected providers** are fully configured. An
uninstalled agent is **not** a failure — there is nothing to configure for an
absent provider.

### 1.3 `hive-mind service status` / `service ping`

```powershell
hive-mind service status          # shadow/legacy/state observation
hive-mind service status --json
hive-mind service ping            # pong if the control socket is alive
```

`service status` reads `state_dir/services.shadow.json` (or the legacy Node
supervisor state in `logs/supervisor/state.json`) and prints `mode`, `profile`,
`required`, and, per service: `ownership`, `required`, `readiness`,
`startup_order`. Without observation, it exits `1` with a clear message — it
never invents "healthy".

### 1.4 Daemon loopback HTTP

With `hive-mindd run --shadow --serve` (or managed `--serve`):

```powershell
curl http://127.0.0.1:37780/health     # {"state": ..., "services": {...}}
curl http://127.0.0.1:37780/ready      # 200 (ready) or 503 (fail-closed)
curl http://127.0.0.1:37780/metrics    # Prometheus
```

### 1.5 Pipeline validators

```powershell
hive-mind validate vault      # Markdown/links/encoding audit (read-only)
hive-mind validate delivery   # capture backlog and legacy buckets (read-only)
hive-mind validate topology   # worktrees/copies + cleanup suggestion
hive-mind validate agents     # multi-agent capture canary
```

See [cli.md](cli.md) §validate for the full semantics of each one.

---

## 2. Verified backup

The real backup is the native `hive-mind backup` engine, ported from
`scripts/health/backup_databases.py` (delivery D008-R1B). It uses
`sqlite3.Connection.backup()` over a `mode=ro` source (a consistent copy with
the database in use) and adds the guarantees that were missing in the legacy:

| Guarantee | Detail |
|---|---|
| Single-execution lock | `MaintenanceLock` (exclusive-create) — no two simultaneous runs |
| Atomic finalization | `.partial` + `os.replace` |
| Verification | `integrity_check` + `foreign_key_check` + SHA-256 |
| Safe retention | prunes **only after** the new backup is verified (a new corrupt backup never evicts a good old one) |
| Content manifest | JSON with artifacts, hashes, sizes, coverage |
| Dry-run by default | `run` does not write without `--apply` |
| Protected restore | writes to an alternate directory by default |

### 2.1 Commands

```powershell
hive-mind backup run [--apply]                  # dry-run by default
hive-mind backup status
hive-mind backup verify [--manifest <path>]
hive-mind backup restore --manifest <path> --into <dir> [--overwrite-live]
```

`restore` writes to an **alternate directory** by default; overwriting requires
an explicit `--overwrite-live` (destructive).

### 2.2 Coverage by component

| Component | Coverage |
|---|---|
| claude-mem SQLite | BACKED_UP |
| UMC / `hive_mind.db` | BACKED_UP |
| swarmclaw / hermes SQLite | BACKED_UP |
| `cerebro/` Markdown | NOT_SUPPORTED (outside the SQLite backup; see P2P §6) |
| Milvus / FalkorDB / RAGFlow | REQUIRES_SERVICE_SNAPSHOT |
| LightRAG | EXTERNALLY_MANAGED (regenerable via Dream Cycle) |
| `.env` / secrets | NOT_SUPPORTED (deliberate) |

Copying an in-use Docker volume **is not** a consistent backup and is not done.

### 2.3 Sanitation subcommands (`backup scrub-*` / archiving)

The `backup` group also exposes legacy data sanitation — all dry-run by default:

| Command | What it does |
|---|---|
| `backup archive-historical-outbox` | Archives inert `capture_outbox` rows (`--cutoff-occurred-at`) |
| `backup scrub-capture-outbox` | Redacts secret-shaped material from the outbox |
| `backup scrub-runtime-artifacts` | Redacts secrets from log/audit artifacts |
| `backup scrub-env-backups` | Redacts legacy `.env` secret values in `backups/` |
| `backup archive-topology` | Archives topology paths classified as ARCHIVE |
| `backup cleanup-topology-stale` | Archives/removes stale residue marked `REMOVE_AFTER_APPROVAL` |

---

## 3. Disaster recovery (`recover.sh`)

If `hive_mind.db` is corrupted or lost, it is **fully rebuildable** from the
vault. The `scripts/utils/recover.sh` wrapper delegates to
`scripts/utils/recovery.py`:

```bash
./scripts/utils/recover.sh verify                    # checks integrity
./scripts/utils/recover.sh backup                    # consistent snapshot
./scripts/utils/recover.sh rebuild-indexes           # rebuilds indexes
./scripts/utils/recover.sh restore BACKUP_DB [--rebuild-indexes]
```

Classic flow of a complete index rebuild from the `.md` files:

1. Stop the Watcher (`sinapse-graphify-watch`).
2. Back up the corrupted DB (if it exists).
3. Create a new `hive_mind.db` from scratch (schema from zero).
4. Reindex all files of `cerebro/` via Graphify.
5. Restart the Watcher.

Estimated time: 2–10 minutes depending on the vault size.

> `restore` stops `sinapse-graphify-watch.service`/`sinapse-api.service` before
> restoring and restarts them afterwards (`EXIT` trap), avoiding concurrent
> writes during the restoration.

---

## 4. Maintenance commands

### 4.1 Watcher (real-time sync)

```bash
./scripts/services/start-watcher.sh          # starts the watcher in background
pgrep -f "start-watcher" && echo "OK"        # checks it is running
pkill -f "start-watcher"                     # stops it
```

The Watcher uses `watchdog` over `cerebro/`. On each `.md` change: queues the
event (500ms debounce), calls Graphify to reindex, and updates the structural
graph; the UMC/FTS/vector path belongs to `WriteIndexer`. It should **not** be
the only synchronous write path (see [runtime.md](runtime.md) and
[04-infrastructure.md](04-infrastructure.md) §3.1).

### 4.2 Dream Cycle (consolidation)

```bash
python scripts/dream/dream_cycle.py --once --real     # one real run
python scripts/dream/dream_cycle.py                   # dry-run
```

Consolidates observations → validated facts → Atlas (`cortex/temporal/`). The
automatic go-live is gated by M9 green ≥ 7 days (see [runtime.md](runtime.md)
§15.2).

### 4.3 Memory audit

```bash
python scripts/health/audit_memory.py            # read-only
python scripts/health/audit_memory.py --fix      # reindexes divergences
python scripts/health/audit_memory.py --fix --verbose
python scripts/health/audit_memory.py --trace "file-name.md"
```

Audits only real temporal-cortex neurons; `type: moc` files stay out of the
index (and are removed if an old version indexed them).

### 4.4 Visual portal

```bash
python scripts/knowledge/generate_portal.py      # generates portal.canvas (Obsidian Canvas)
```

### 4.5 Backfills and draining (PHASE 2)

| Command | Use | Effect |
|---|---|---|
| `python scripts/maintenance/vector-backfill.py [--limit N] [--batch B]` | fixes the gap of neurons outside `search_vec` | indexes via `core.indexing.index_neuron_ids` (embed + search_vec + HNSW) |
| `python scripts/maintenance/data-backfill.py [--dry-run]` | data integrity | `consumed_by='legacy'` (archived), `project='unclassified'`, `topic` derived from `source_file` |
| `python scripts/maintenance/drain-candidates.py [--dry-run] [--limit N]` | drains stuck `knowledge_candidates` | promotes `verified+low`, holds `hypothesis`/`risk=high` |
| `python scripts/knowledge/backfill_decisions.py` | decision backfill | consolidates legacy decisions |
| `python scripts/maintenance/backfill_document_parents_chunks.py` | document backfill | K6 parents/chunks |
| `python scripts/maintenance/backfill_review_dates.py` | review date backfill | `review_date`/`next_review` |

All are idempotent and non-destructive; those that mutate use `--dry-run` by
default when applicable.

### 4.6 Scheduled routines

See [runtime.md](runtime.md) §14–15 for the complete job inventory (cron in the
manifest, Task Scheduler on Windows, systemd timers on POSIX).

---

## 5. P2P sync (Syncthing)

### 5.1 Swarm architecture

```
  Machine A (PC)           Machine B (Laptop)         VPS
  cerebro/                 cerebro/                   cerebro/
     │                         │                         │
     └──────── Syncthing ───────┴──────── Syncthing ─────┘
                (TLS, P2P, without a central server)

  Each machine has its own hive_mind.db, a background Watcher, and
  audit_memory.py via cron (1x/hour).
```

Syncthing transports the `.md` files between machines. `hive_mind.db` is **not**
synchronized — each machine keeps its own local index, rebuilt from the received
Markdown files.

### 5.2 Configuration

1. Install Syncthing (`apt install syncthing` / `brew install syncthing` /
   download at syncthing.net).
2. UI at `http://localhost:8384` → **Add Folder**.
3. Folder Path = absolute path of `cerebro/`; Folder Type = "Send & Receive";
   File Versioning = "Simple File Versioning" (≥ 5 versions).
4. Share with the other machines via **Device ID**.

### 5.3 Collision prevention (UUID v4)

All UMC primary keys use a locally-generated UUID v4:

```python
import uuid
neuron_id = str(uuid.uuid4())   # "550e8400-e29b-41d4-a716-446655440000"
```

Sequential IDs would collide between machines (both would create `id=1`). UUID
v4 has a collision probability of 1 in 10^36 — irrelevant in practice.

### 5.4 Integrity by hash (SHA-256)

Each indexed file receives a hash at index time, stored in `neurons.hash` and in
the frontmatter (`integrity_hash`). `audit_memory.py` compares the physical
file's hash with `neurons.hash`; a divergence indicates a file modified on
another machine and a stale local index.

### 5.5 Dialectic Synthesis (conflict resolution)

When two texts of the same `source_file` have **irreconcilable** semantic
content (a factual conflict, not just a different hash), the system records an
**ambiguity** and schedules autonomous LLM resolution (`semantic_diff.py`):

```
  cosine(embed(A), embed(B))
  ├── > 0.92: almost identical → simple reindex
  ├── 0.70–0.92: complementary → candidate merge
  └── < 0.70: divergent → LLM for semantic analysis
```

Possible resolutions: `merge` (combined note), `choose_a`/`choose_b` (keeps one,
archives the other), `branch` (keeps both with suffix `-version-a`/
`-version-b`). Results written to the `ambiguities` table
(`pending | resolved | escalated`).

### 5.6 Provenance metadata

```yaml
---
title: Decision to migrate to Hetzner
agent: claude-fable-5
trust_level: 2           # 1=low, 2=medium, 3=high
machine_id: laptop-home
integrity_hash: a3b4c5d6e7f8...
created: 2026-06-10
source_observation_ids: ["550e8400-...", "6ba7b810-..."]
---
```

To trace a suspicious fact: `audit_memory.py --trace "file.md"`.

---

## 6. Cross-references

- **Runtime/daemon**: [runtime.md](runtime.md)
- **Installation**: [installation.md](installation.md)
- **Full CLI**: [cli.md](cli.md)
- **Backup (audit and real state)**: [operations.md](operations.md)
- **P2P (original reference)**: [07-p2p-sync-setup.md](07-p2p-sync-setup.md)
- **Observability (metrics/alerts)**: [observability.md](observability.md)
- **Incidents (recovery runbook)**: [incidents.md](incidents.md)
- **Data pipeline (Dream Cycle, promotion)**: [data-pipeline.md](data-pipeline.md)
