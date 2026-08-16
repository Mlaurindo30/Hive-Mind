# Hive-Mind Documentation

> Index of the **new documentation** (Portuguese set, organized by subject).
> Last reviewed: 2026-08-15.

The project documentation is being reorganized from numbered documents
(`architecture.md`, `02-ai-models.md`, …) into a set named by subject. This
`README.md` is the index of that new set. The numbered documents still exist and
remain the **canonical reference** until each area's migration is complete — see
[Sources of truth](#sources-of-truth-evidence-priority).

---

## New documentation index

| Document | Content | Status |
|---|---|---|
| [blueprint.md](blueprint.md) | Architecture diagrams and flowcharts, capture flow, Dream Cycle, cadence, and RetrievalRouter | to write (migrates `blueprint.md`) |
| [architecture.md](architecture.md) | Canonical architecture reference: brain anatomy, UMC, read/write flows, Born-Large Knowledge architecture (K0–K10), ADRs | to write (migrates `architecture.md`) |
| [data-pipeline.md](data-pipeline.md) | Data pipeline: Capture → Intake → Promotion → Persistence → Index; `DocumentPipeline` (K6) and `VectorBackend` (K1) | to write (migrates `03-data-pipeline.md`) |
| [ai-models.md](ai-models.md) | AI models and embeddings, canonical roles, fallback chain, Model Gateway | to write (migrates `02-ai-models.md` + `ai-models.md`) |
| [runtime.md](runtime.md) | `hive-mindd` daemon, declarative manifest `config/runtime.yaml`, ownership model, control socket | **already exists** |
| [cli.md](cli.md) | Native CLI `hive-mind` and subcommands | to write |
| [agents.md](agents.md) | MCP agent registration (`hive-mind agents`), transactional writes, instruction block, undo | **written** |
| [capture.md](capture.md) | Capture providers, normalized event contract, durable outbox with leases, canonical project identity | **written** |
| [development.md](development.md) | How to make changes, change→documentation matrix, tests, build, release, boundaries | **written** |
| [installation.md](installation.md) | Installation on a new machine (Linux/WSL2 and native Windows) | to write (migrates `installation.md`) |
| [operations.md](operations.md) | Operations: services, ports, cron jobs, backup and recovery | to write (migrates `04-infrastructure.md` §3–§5 + `operations.md`) |
| [observability.md](observability.md) | Observability: health check, metrics, integrity audit, Knowledge Health (K8) | to write |
| [incidents.md](incidents.md) | Incident response and disaster recovery (`recover.sh`) | to write |
| [security.md](security.md) | Security principles, attack surface, sensitive files, fail-closed | to write (migrates `04-infrastructure.md` §7) |
| [HANDOVER.md](HANDOVER.md) | Handover between sessions/agents: current state, pending items, how to resume | to write |

---

## Where to start

| If you need… | Read… |
|---|---|
| To understand the architecture and the "why" of the decisions | [architecture.md](architecture.md) → [architecture.md](architecture.md) |
| To see the diagrams and flows | [blueprint.md](blueprint.md) |
| To register Hive-Mind in an agent (MCP) | [agents.md](agents.md) |
| To understand how capture works and how the project is identified | [capture.md](capture.md) → [capture.md](capture.md) |
| To change code, run tests, make a release | [development.md](development.md) |
| To install from scratch | [installation.md](installation.md) → [installation.md](installation.md) |
| To operate services, cron and backups | [operations.md](operations.md) |
| To diagnose system health | [observability.md](observability.md) |
| To respond to a failure / recover | [incidents.md](incidents.md) |
| To review security before exposing something | [security.md](security.md) |
| To configure the daemon and the service manifest | [runtime.md](runtime.md) |
| To use the native CLI | [cli.md](cli.md) |

---

## Sources of truth (evidence priority)

When two documents diverge, the order below applies. Documents closer to the
code take priority over derived documents.

1. **Source code and build artifacts** — `src/`, `scripts/`, `core/`,
   `config/runtime.yaml`, `pyproject.toml`, `components.lock.json`.
2. **Tests** — `tests/` document the expected behavior and what is considered a
   regression.
3. **Specs and ADRs** — `specs/`, .
4. **New documentation (this set)** — the index and the named documents.
5. **Legacy numbered documentation** — `architecture.md` and the others, until
   each area's migration is complete.
6. **`AGENTS.md` (root)** — operational guide for agents; a summary, not a
   primary source.

When in conflict, fix the documentation **in the same delivery** that fixes the
code — never leave a document describing the old behavior.

---

## Maintenance rules

1. **Reflect the code.** The documentation describes what is delivered, not what
   was planned. Check the command, table, and path in the code before
   documenting.
2. **Do not compress specs or evidence.** Concise = organized, not emptied. Do
   not delete tables of commands, options, exit codes, or test matrices to
   shorten the text.
3. **Do not leave stale documentation.** Every behavior change is made together
   with the update of the corresponding document (matrix in
   [development.md](development.md)).
4. **Use the evidence order.** In a divergence, the code prevails; fix the
   document that is behind.
5. **Do not invent.** No commands, flags, or paths that do not exist in the
   code. When in doubt, run the command or read the file.
6. **Do not touch the source documents.** The legacy documents (`agents.md`,
   `capture/providers.md`, `capture.md`, `04-infrastructure.md`,
   `09-integration-study.md`) are only removed or rewritten when the migration of
   the corresponding area is complete and reviewed.
7. **Cross-reference.** Every new document points to the documents that detail
   the areas it only mentions. Link, do not duplicate.
8. **Clear target audience.** Each document states for whom it was written;
   command examples are copyable.
9. **Never document secrets.** `.env`, API keys, tokens, and paths that leak
   credentials do not appear in the documentation.
10. **Keep the index up to date.** When creating, renaming, or removing a
    document from this set, update the table above in the same delivery.

---

## Legacy documentation (canonical reference during the migration)

| Document | Content | Replaced by |
|---|---|---|
| [architecture.md](architecture.md) | Canonical architecture (Born-Large §22–§31) | architecture.md |
| [02-ai-models.md](02-ai-models.md) | AI models and roles | ai-models.md |
| [03-data-pipeline.md](03-data-pipeline.md) | Data pipeline | data-pipeline.md |
| [04-infrastructure.md](04-infrastructure.md) | Infrastructure, ports, security | operations.md + security.md |
| [blueprint.md](blueprint.md) | Diagrams | blueprint.md |
| [ai-models.md](ai-models.md) | Model Gateway (canonical LLM execution layer) | ai-models.md |
| [installation.md](installation.md) | Installation | installation.md |
| [runtime.md](runtime.md) | Daemon and manifest | runtime.md (already named) |
| [capture.md](capture.md) | Canonical project identity | capture.md |
| [capture/providers.md](capture/providers.md) | Capture providers | capture.md |
| [agents.md](agents.md) | MCP registration (English) | agents.md |
