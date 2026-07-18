# Canonical Project Identity and Windows Capture Design

**Date:** 2026-07-17

**Status:** approved

## Objective

Make the Windows path preserve the capture behavior that is already functional on
Linux while assigning one stable, auditable project identity to every new event.
The identity must survive the complete path from a provider source to Claude Mem,
UMC, retrieval indexes, graphs, the Dream Cycle, Markdown and all public access
surfaces.

The target operational flow is:

```text
provider source
  -> parser
  -> normalized session
  -> ProjectIdentityResolver
  -> capture_core.ingest
  -> Claude Mem
  -> Claude Mem bridge
  -> UMC
  -> FTS / sqlite-vec / Milvus
  -> Graphify / Graphiti / LightRAG
  -> Dream Cycle
  -> canonical Markdown
  -> REST / MCP / CLI
```

This design also makes Hermes App on Windows a required real-provider acceptance
case. A detected Hermes database or a running Hermes process is not proof of
capture; a fresh prompt must reach Claude Mem and every downstream gate.

## Superseded Capture Decision

The delivery architecture in
`docs/superpowers/specs/2026-07-09-universal-provider-capture-design.md` is
superseded where it makes `CaptureQueue -> OutboxDrainer -> ClaudeMemSink` the
owner of delivery.

For new events, there is one delivery owner:

```text
parser -> normalized session -> capture_core.ingest -> Claude Mem
```

The experimental delivery/outbox modules and their exclusive tests are removed
from this increment. Historical databases are not opened for delivery, migrated,
drained, merged, cleaned or deleted. In particular, these remain untouched:

```text
D:\Hive-Mind\logs\capture-outbox.db
C:\Users\miche\.claude-mem\capture.db
```

Claude Code native capture remains unchanged. The universal capture daemon handles
only providers that need the filesystem, SQLite/WAL or supported hook adapters.

## Project Identity Model

`ProjectIdentity` is an immutable, versioned value object with this contract:

```text
schema_version
project_id
project_name
workspace_root
repository_root
repository_remote
git_common_dir
worktree_name
branch
provider
surface
resolution_method
resolution_confidence
referenced_projects
```

The fields have distinct meanings:

- `project_id` is the stable storage, filtering and routing key.
- `project_name` is the human-facing label sent to the Claude Mem project field.
- `workspace_root` is the workspace in which the provider operated.
- `repository_root` is the current worktree's Git top level.
- `git_common_dir` is the shared repository identity evidence across worktrees.
- `worktree_name` and `branch` describe the current checkout and never become the
  project identity.
- `provider` identifies the tool family; `surface` identifies CLI, IDE, desktop,
  extension or hook.
- `resolution_method` and `resolution_confidence` make every decision auditable.
- `referenced_projects` records mentioned projects without changing the active
  project.

`workspace_id` remains the isolation boundary in existing UMC APIs and schemas.
For new captured knowledge, the bridge writes `workspace_id = project_id`. It is
not independently inferred from a provider name or a free-form label.

## ProjectIdentityResolver

All parsers provide evidence to one resolver. No parser implements its own project
classification. The resolver accepts explicit project hints, environment hints,
official application workspace data, CWD, provider, surface and optional audited
semantic references.

Resolution follows this order:

1. validated explicit project;
2. `HIVE_PROJECT_ID` and `HIVE_PROJECT_ROOT`;
3. official workspace supplied by the application;
4. `git rev-parse --show-toplevel` from the workspace/CWD;
5. `git rev-parse --git-common-dir`;
6. normalized Git remote;
7. declarative project aliases;
8. known project markers;
9. `unclassified/<provider>`.

The resolver gathers all safe Git evidence before selecting the final identity so
that an alias may map a common directory, root or normalized remote to a canonical
ID without changing the required precedence of evidence.

### Git and path rules

- Git commands are executed without a command shell, with bounded timeouts.
- Remote credentials, userinfo and transient URL syntax are removed before use.
- SCP-style SSH and HTTPS remotes normalize to the same repository identity.
- Windows paths are resolved through junctions and symlinks where possible and
  compared case-insensitively without lowercasing their display form.
- Unicode, spaces, UNC paths and both Windows separators are supported.
- A repository root and all worktrees sharing the same Git common directory map
  to one `project_id`.
- Detached HEAD produces an empty/null branch and does not change project ID.
- Repositories without a remote use a deterministic local repository identity.
- A non-Git directory is never promoted from `Path(cwd).name` alone.

### Canonical ID selection

An explicit validated ID or a registry mapping always wins. A known remote maps to
the registry's ID. An unknown remote produces a deterministic normalized Git ID.
A repository without a remote produces a deterministic local ID based on its
canonical common directory. A non-Git source falls back to
`unclassified/<provider>` unless another higher-priority source is valid.

## Declarative Alias Registry

The project owns a versioned declarative registry. Its schema supports canonical
ID, display name, normalized remotes, canonical roots, Git common directories,
legacy labels and marker files. The initial Hive-Mind entry maps at least:

```text
D:\Hive-Mind
D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install
https://github.com/Mlaurindo30/Hive-Mind.git
Hive-Mind
hive-mind-windows-zero-install
Hive-Mind/hive-mind-windows-zero-install
```

to:

```text
project_id: hive-mind
project_name: Hive-Mind
```

Registry validation rejects duplicate canonical evidence, unsafe IDs and aliases
that ambiguously map to multiple projects.

## Active and Referenced Projects

The resolver never turns every project mention into the active project.
`active_project` comes from explicit selection, environment, official workspace,
Git evidence, aliases or markers. Mentions are stored only in
`referenced_projects`.

Semantic activation is opt-in and disabled by default. When enabled, it requires
exactly one known reference, no contradictory workspace evidence and confidence
above a configured threshold. The resolver records `semantic_reference` and the
score. No semantic classification is silent.

## Capture Contract and Compatibility

Parsers continue returning normalized session dictionaries during migration. A
single normalization boundary attaches `ProjectIdentity` before ingest. Provider
and surface are never treated as project labels.

The session preserves:

```text
session_id, timestamps, cwd, prompts, turns, last,
project_id, project_name, workspace_root, repository_root,
repository_remote, git_common_dir, branch, worktree_name,
provider, surface, resolution_method, resolution_confidence,
referenced_projects
```

Legacy `project` remains populated with `project_name` for compatibility. Existing
content-hash deduplication remains the delivery idempotency mechanism. Identity is
metadata and does not introduce a second queue or delivery path.

## Claude Mem

The canonical `project_name` is sent in the existing `project` field used by the
Claude Mem dropdown. The versioned identity envelope is added as compatible
metadata to session init, observations and summaries. Existing endpoint shapes
remain valid:

```text
POST /api/sessions/init
POST /api/sessions/observations
POST /api/sessions/summarize
```

New sessions from the Hive-Mind root and its development worktree must appear as a
single `Hive-Mind` project. Historical labels remain unchanged until a separately
authorized migration.

## Claude Mem Bridge and UMC

The bridge reads the versioned identity envelope, validates it and writes:

```text
workspace_id = project_id
project = project_name
metadata.project_id
metadata.project_name
metadata.provider
metadata.surface
metadata.branch
metadata.worktree_name
metadata.source_session
```

Legacy records without an envelope remain readable and are reported as
`legacy/unclassified`; they are not deleted or rewritten. Relevant tables and
query APIs gain compatible project filters without removing existing workspace
filters.

## Retrieval, Graphs and Dream Cycle

Every new vector carries project ID/name, source ID/type, session ID and provider.
Both sqlite-vec and Milvus enforce project filters. Cross-project retrieval is an
explicit mode rather than a missing filter.

Graphify and Graphiti nodes/edges carry `project_id`. Cross-project relations use
an explicit relation such as `references`. LightRAG uses a project namespace or a
mandatory project filter and cannot return project-B-only content for a project-A
query.

The Dream Cycle groups new observations by `project_id`, not the free-form
`project` label. Legacy fallback is explicit and measurable. New Markdown routes
to:

```text
cerebro/cortex/temporal/<project_id>/<topic>/neuronio-*.md
```

and includes the complete canonical provenance required by the master acceptance
prompt. Root and worktree observations for Hive-Mind land in the same canonical
directory.

## Hermes App on Windows

The installed Hermes App source is expected at:

```text
C:\Users\miche\AppData\Local\hermes\state.db
```

The implementation must inspect the real installed schema in read-only mode,
including WAL-aware changes. The adapter must distinguish application/profile
names from project evidence, parse every new user prompt and relevant assistant
response, and use the shared resolver. A hardcoded `hermes` project label is not
allowed.

Hermes is accepted only when a unique real prompt proves:

1. the installed source changed;
2. the parser extracted the event;
3. a normalized session was created;
4. the resolver returned the expected project identity;
5. direct `capture_core.ingest` ran;
6. Claude Mem search found the marker;
7. timeline contains the session;
8. hydrated observations contain the prompt and response;
9. the bridge wrote the canonical workspace;
10. a repeat scan created no duplicate.

## Historical Project Audit

A read-only `hive-mind projects audit` command inventories legacy labels and
proposes mappings with counts for sessions, observations, vectors and Markdown.
It classifies at least the labels required by the master prompt as `CANONICAL`,
`ALIAS`, `SURFACE`, `PROFILE`, `UNCLASSIFIED` or `AMBIGUOUS`.

The command does not migrate data. A future transaction requires explicit
authorization and the sequence backup, dry-run, sessions, observations,
workspace, vectors, graphs, Markdown, reindex, validation and rollback.

## Error Handling and Observability

- Resolution failures produce a structured fallback and diagnostics; they do not
  stop other providers.
- Provider health distinguishes detected, parser-active and end-to-end healthy.
- Git and database reads have bounded timeouts and useful errors.
- No exception on the capture path is silently swallowed.
- Duplicate, unresolved and legacy counters are visible in readiness evidence.

## Testing Strategy

Unit tests cover resolver precedence, real path variants, remote normalization,
worktrees, aliases, semantic references, compatibility, bridge workspace mapping,
Dream grouping and retrieval filters.

Integration tests use real temporary Git repositories/worktrees, SQLite, HTTP and
filesystem sources. They prove that root/worktree identities match, unrelated
repositories differ, Claude Mem-compatible payloads retain identity, the bridge
writes the correct workspace and Dream selects only the requested project.

Operational gates use real installed providers and real services. Mocks and file
detection do not score. After identity changes, all installed providers are
revalidated one at a time, including Claude Code, Codex, Antigravity IDE/CLI,
Kimi, Qwen CLI/Desktop, Hermes, Mimo and Kilo.

Two synthetic real projects prove isolation through Dream, UMC, vectors, graphs
and retrieval. Cleanup targets only IDs created by that run.

## Windows Lifecycle and Packaging

Identity/capture/Dream gates precede lifecycle work. The installer must eventually
implement the currently declared repair, update and uninstall operations plus a
verified rollback path. The Python distribution must include the runtime modules
required for a clean installation rather than only `src/hive_mind`.

Clean installation, upgrade, reboot, repair, update, rollback, uninstall and
reinstall run first in a disposable Windows environment. The active root is not
updated by this increment and is never the first installation test.

## Implementation Order

1. Preserve and reconcile the mixed Git state; remove experimental delivery code
   from this increment without touching historical databases.
2. Add the resolver, model, registry and focused unit/integration tests.
3. Attach identity at the single session-normalization boundary.
4. Propagate the envelope through direct ingest and Claude Mem.
5. Update bridge, UMC and project audit surfaces.
6. Enforce identity in vectors, graphs, LightRAG, Dream and Markdown.
7. Diagnose and fix Hermes against its real Windows database, then revalidate all
   installed providers individually.
8. Run complete regression, integrity metrics and the two-project operational
   isolation gate.
9. Implement and test packaging and Windows lifecycle in a disposable machine.
10. Produce the 100-point readiness reports and the required 45-item final report.

## Acceptance Boundary

The project is not complete until every operational gate in the master prompt has
current evidence. Narrow tests, detected files, process health or historical
canaries cannot support a full-success claim. F2, root update, historical migration,
merge, push, PR, release and reboot remain prohibited until their explicit gates
and authorization are satisfied.
