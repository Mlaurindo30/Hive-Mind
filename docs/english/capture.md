# Capture

How Hive-Mind captures agent sessions, normalizes events, delivers with
durability guarantees, and decides which project each event belongs to.

Target audience: those who write or maintain a provider parser/hook, and those
who diagnose why an event reached (or did not reach) the brain.

References: [capture/providers.md](capture/providers.md),
[capture.md](capture.md),
[`scripts/capture/capture_events.py`](../scripts/capture/capture_events.py),
[`scripts/capture/capture_queue.py`](../scripts/capture/capture_queue.py).

---

## Canonical path

```
provider source → parser → hive_mind.capture.ingest → Claude Mem
```

`ingest` is the **only** place that decides the project identity. The
entrypoints provide **evidence** — a working directory, a workspace root, a
provider name, a surface. They do not decide what the project is, and cannot
override that decision.

This is deliberate. Until delivery D004-R2 the resolver was called by the
entrypoint, which meant each entrypoint had to remember to call it. One called it
(`capture-realtime.py`), one did not (`capture-tailer.py`), and the one that did
not wrote free-form labels directly into the field by which Claude Mem groups.
The measured result: prompt text became a project name, and this repository's
worktree became a project separate from its own root.

---

## Universal providers

The capture layer is **provider-agnostic**: any source that emits a normalized
`ProviderEvent` is accepted. The providers planned on the capture surface are:

```
codex, copilot, hermes, antigravity, kimi, qwen, kilo, roo, vscode/cursor,
opencode, openclaw, swarmclaw
```

The verification matrix **per provider has not been run yet** (D004): a green
event proves the path, not the 13 providers. Verification and acceptance are
independent columns — see [capture/providers.md](capture/providers.md),
section "Verification is not acceptance" (D004-P). The full matrix lives in
[`reports/provider-capture-matrix.md`](../reports/provider-capture-matrix.md).

> Relation to MCP registration: the set of registrable **agent keys**
> (`claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode openclaw
> swarmclaw`) is distinct from the set of **capture providers**. Registering an
> agent in the MCP (see [agents.md](agents.md)) does not install capture, and
> capturing a provider does not require MCP registration — they are independent
> layers.

---

## Normalized event contract

Every capture event becomes an immutable `ProviderEvent`, provider-neutral,
ready for durable delivery
([`capture_events.py`](../scripts/capture/capture_events.py)).

### Fields

| Field | Type | Required | Note |
|---|---|---|---|
| `provider` | `str` | yes | name of the provider that emitted the event |
| `session_id` | `str` | yes | identifies the session |
| `event_type` | `EventType` | yes | one of the six categories below |
| `content` | `str` | yes | the body of the event |
| `event_id` | `str` | yes (generated if omitted) | stable identity via fallback (hash) |
| `occurred_at` | `str` ISO-8601 UTC | normalized | always converted to UTC |
| `source_position` | `str` \| `None` | no | position in the source file |
| `project` | `str` \| `None` | no | filled by identity resolution |
| `cwd` | `str` \| `None` | no | working directory |
| `metadata` | `object` \| `None` | no | normalized (JSON serializable, sorted keys) |

### `EventType`

| Value | Meaning |
|---|---|
| `session_start` | session start |
| `prompt` | user prompt |
| `tool_use` | tool call |
| `tool_result` | tool result |
| `assistant` | assistant response |
| `session_end` | session end |

### Validation and normalization

- Required fields (`provider`, `session_id`, `content`, `event_id`) must be
  non-empty strings — otherwise `ValueError`.
- `occurred_at` accepts `datetime`, an ISO-8601 string, or `None`; converts to
  UTC; strings without a timezone are treated as UTC; non-UTC offsets are
  converted.
- `event_id`, if omitted, is derived by canonical SHA-256 of
  `{provider, session_id, event_type, content, source_position}` — stable.
- `metadata` is serialized/re-serialized with sorted keys (`sort_keys=True`) to
  guarantee canonical form.

### Deduplication key

`dedupe_key()` is a **provider-scoped** SHA-256 hash of
`{provider, session_id, event_type, event_id}`. It is the outbox's unique key —
a re-delivered event does not duplicate.

---

## Durable outbox with leases

The `CaptureQueue` ([`capture_queue.py`](../scripts/capture/capture_queue.py))
persists events until they are delivered or moved to dead-letter.

### Guarantees

- **Durability**: SQLite with `journal_mode=WAL`, `synchronous=NORMAL`,
  `busy_timeout=10000`, `BEGIN IMMEDIATE` transactions.
- **Deduplication**: `UNIQUE` index on `dedupe_key`; re-insertion is ignored
  (`INSERT OR IGNORE`).
- **Leases**: each event is claimed by a queue instance with `claim_owner`
  (instance UUID) and `claim_until` (lease deadline, `lease_seconds=30.0` by
  default). Only the claim owner, with a non-expired lease, can mark
  delivery/retry/dead-letter.
- **Session ordering**: an event is only eligible when no predecessor (same
  `provider` + `session_id`, earlier `occurred_at`/`id`) is pending — the
  session's "head" is delivered before the rest.

### Schema (`capture_outbox`)

| Column | Note |
|---|---|
| `dedupe_key` | unique deduplication key |
| `provider`, `session_id`, `occurred_at` | indexed (`capture_outbox_pending`) |
| `payload` | JSON of `ProviderEvent.as_payload()` |
| `attempts` | attempt counter (default 0) |
| `next_retry_at` | timestamp of the next retry (default 0) |
| `last_error` | last error message |
| `created_at`, `delivered_at`, `dead_letter_at` | lifecycle milestones |
| `claim_owner`, `claim_until` | lease (added by schema migration if absent) |

### Operations

| Method | Effect |
|---|---|
| `enqueue(event)` | inserts once; returns `False` if the key already exists |
| `pending(limit)` | atomically claims the eligible session heads |
| `mark_delivered(item_id)` | marks delivery if this instance's lease is valid |
| `mark_retry(item_id, error, retry_at)` | increments `attempts`, releases the lease |
| `move_dead_letter(item_id, error)` | stops retrying after permanent failure |
| `health()` | count of mutually exclusive states |

### States (`health()`)

| State | Meaning |
|---|---|
| `pending` | deliverable now, no pending predecessor |
| `claimed` | claimed (lease not expired) |
| `retrying` | waiting for `next_retry_at` |
| `blocked` | predecessor of the same session not yet delivered |
| `delivered` | delivered |
| `dead_letter` | permanent failure, no further retry |

---

## Deprecated path

The old path **must not be re-linked** (ADR-004):

```
provider hook → ProviderEvent → CaptureQueue → capture_outbox  (no drainer)
```

Two outbox databases survived from it, and neither ever attempted a delivery —
`attempts=0`, `last_error=0`, `dead_letter_at=0` on every row. They are an
**ownerless queue**, which is different from a delivery that failed.

| Outbox | Rows | Providers | Writer | State |
|---|---:|---|---|---|
| `<SINAPSE_HOME>/logs/capture-outbox.db` | 2.070 | claude | `capture-hook.py`, wired into `~/.claude/settings.json` | `LEGACY_ACTIVE_WRITER` — still growing |
| `~/.claude-mem/capture.db` | 18.579 | codex, antigravity, mimo | `capture-hook.py`, wired into `~/.codex/hooks.json` | `LEGACY_INACTIVE_WRITER` — nothing since 2026-07-20 |

`~/.claude-mem/capture.db` is **not** the Claude Mem store, despite living in
that directory. The store is `~/.claude-mem/claude-mem.db`, next to it.

No writer was disabled here. Removing them is a cutover, and a cutover is a
delivery of its own. Maintenance of these databases: `hive-mind backup
archive-historical-outbox` and `hive-mind backup scrub-capture-outbox`
(both dry-run by default — see [cli.md](cli.md)).

---

## Canonical project identity

Claude Mem indexes and groups by `observations.project`. The contract:

| Field | Value |
|---|---|
| `observation.project` | `identity.project_name` — always canonical |
| `metadata.project_identity` | the complete canonical envelope |
| `metadata.project_identity.project_id` | `identity.project_id` |
| `metadata.capture.raw_project_label` | what the parser said — **audit only** |

The parser label is **never** authoritative. It is never used as `project`,
`project_id`, `project_name`, `workspace_id`, a Markdown path, a vector filter,
or a graph namespace. That is what prevents values like
`preciso-que-verifique-o-por-que`, `shadow-run-clean`, `miche`, or
`Microsoft VS Code` from becoming projects again.

### The two fields

| Field | Meaning | Where it lives |
|---|---|---|
| `project_id` | stable identifier for database, filters, Dream Cycle, and vectors | `observations.workspace_id`; frontmatter `project_id` |
| `project_name` | human name shown in the interface | `observations.project`; frontmatter `project_name` |

Worktree, branch, provider, and surface are **metadata**, never identity.

### Resolution order

`ProjectIdentityResolver` ([`scripts/capture/project_identity.py`](../scripts/capture/project_identity.py))
applies, in order:

| # | Evidence | Method | Confidence |
|---|---|---|---|
| 1 | explicit project provided and validated | `explicit` | — |
| 2 | `HIVE_PROJECT_ID` / `HIVE_PROJECT_ROOT` | `environment_id` | — |
| 3 | official workspace provided by the application | — | — |
| 4 | `git rev-parse --show-toplevel` | `git_root` | 0.96 |
| 5 | `git rev-parse --git-common-dir` | `git_common_dir` | 0.96 |
| 6 | normalized Git remote | `git_remote` | 0.95 |
| 7 | explicit alias map | `alias_root` | 0.90 |
| 8 | known project markers | `marker` | 0.80 |
| 9 | `unclassified/<provider>` | `unclassified_provider` | 0.0 |

`Path(cwd).name` is **never** canonical identity.

**Git common dir rule:** root and worktrees that share the same `git-common-dir`
receive the **same** `project_id`:

```
D:\Hive-Mind                                        → hive-mind
D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install → hive-mind
```

The branch (`codex/control-plane-redesign`) and the worktree name
(`hive-mind-windows-zero-install`) live only in metadata. The `project_name`
also derives from the git common dir — fixing only the `id` fixed nothing
visible, because the `name` is the field that Claude Mem indexes (D004-R2).

### Identity policy

A session without a Git repository is **not an error**. Much legitimate capture
happens outside one, and refusing it would lose real data to protect a dropdown.

| Status | Meaning | Delivery |
|---|---|---|
| `CLASSIFIED` | identity resolved from evidence | allowed |
| `UNCLASSIFIED` | insufficient evidence; resolves to `unclassified/<provider>` | allowed, flagged, degraded health |
| `INVALID` | malformed, inconsistent, or irresolvable envelope | **refused before writing** |

`UNCLASSIFIED` is deterministic: the same provider with the same absent evidence
always produces the same id. It is auditable, and never borrows a name from
prompt text or a directory basename.

### Envelope validation

A session may arrive with `metadata.project_identity` already attached — the
hook computes one. The `ingest` does **not trust it blindly**:

- the schema is validated;
- `project_id` and `resolution_method` are checked;
- the envelope is compared against the same session's evidence;
- the fields are normalized.

An envelope that disagrees with its own evidence is `INVALID`. A session without
an envelope is resolved. Either way, the two entrypoints arrive at the same
answer, because the answer is computed in a single place.

### Entrypoints

| Entrypoint | Declared as | Role |
|---|---|---|
| `scripts/capture/capture-realtime.py` | `sinapse-capture-realtime` service | observes provider sources continuously |
| `scripts/capture/capture-tailer.py` | `capture-tailer` job | periodic scan of the provider files |

Both import `hive_mind.capture.ingest`. Neither resolves identity on its own —
guaranteed by `tests/unit/test_capture_canonical_identity.py`, which fails if
either one calls `attach_project_identity` again.

### Active project vs. mentioned project

Mentioning a project in the conversation does **not** make it the active
project:

```
Qwen opened at C:\Users\miche\Documents\Qwen, conversation mentions Hive-Mind
→ active_project:      unclassified/qwen
→ referenced_projects: [hive-mind]
```

Semantic resolution only occurs with the policy enabled, above the configured
threshold, recorded as `semantic_reference`, and auditable. There is never
silent classification. (Fix recorded in CHANGELOG v3.10.1: "referenced projects
no longer activate the primary id".)

### Propagation

```
parser → normalized session → ProjectIdentityResolver
       → capture_core.ingest() → Claude Mem
       → bridge (workspace_id = project_id) → UMC
       → Dream Cycle → Markdown → indices → query
```

The bridge ([`core/knowledge/claude_mem_bridge.py`](../core/knowledge/claude_mem_bridge.py))
writes `workspace_id = project_id` and preserves the `project_identity` envelope
in `observations.metadata`.

### Legacy data

Earlier records carry `workspace_id='default'`. They are **neither rewritten nor
deleted** (ADR-012). They remain readable and are classified as `legacy_label`.
To inventory them without changing anything:

```powershell
hive-mind projects audit
hive-mind projects audit --json
```

---

## Boundaries

What this layer **does** and what it **does not do**:

| Does | Does not |
|---|---|
| normalizes and validates events from any provider | does not decide the project outside `ingest` |
| delivers with durability, lease, and dead-letter | is not a memory database (the store is Claude Mem) |
| resolves identity in a single place, from evidence | does not use prompt text or basename as identity |
| refuses an inconsistent envelope before writing | does not re-link the deprecated path (ADR-004) |
| preserves the parser label for audit only | does not rewrite or delete legacy data |

Related:

- [agents.md](agents.md) — MCP registration (layer independent of capture)
- [capture.md](capture.md) — the resolver and its precedence chain
- [data-pipeline.md](data-pipeline.md) — what happens after the ingest
-  — D004-R2 and errata
