# Capture: providers, paths and who owns delivery

## The canonical path

```
provider source → parser → hive_mind.capture.ingest → Claude Mem
```

`ingest` is the only place that decides project identity. Entrypoints supply
evidence — a working directory, a workspace root, a provider name, a surface.
They do not decide what the project is, and they cannot override it.

This is deliberate. Until D004-R2 the resolver was called by the entrypoint,
which meant every entrypoint had to remember to call it. One did
(`capture-realtime.py`), one did not (`capture-tailer.py`), and the one that
did not wrote free-text labels straight into the field Claude Mem groups by.
The measured result: prompt text became a project name, and this repository's
own worktree became a project separate from its root.

## The deprecated path

```
provider hook → ProviderEvent → CaptureQueue → capture_outbox  (no drainer)
```

ADR-004 deprecated this. It must not be re-wired. Two outbox databases exist
from it, and neither has ever attempted a delivery — `attempts=0`,
`last_error=0`, `dead_letter_at=0` across every row. They are a queue with no
owner, which is a different thing from delivery that failed.

| Outbox | Rows | Providers | Writer | State |
|---|---:|---|---|---|
| `<SINAPSE_HOME>/logs/capture-outbox.db` | 2.070 | claude | `capture-hook.py`, wired in `~/.claude/settings.json` | `LEGACY_ACTIVE_WRITER` — still growing |
| `~/.claude-mem/capture.db` | 18.579 | codex, antigravity, mimo | `capture-hook.py`, wired in `~/.codex/hooks.json` | `LEGACY_INACTIVE_WRITER` — nothing since 2026-07-20 |

`~/.claude-mem/capture.db` is **not** the Claude Mem store despite living in
that directory. The store is `~/.claude-mem/claude-mem.db` beside it.

Neither writer is disabled here. Removing them is a cutover, and a cutover is
its own delivery.

## The project field

Claude Mem indexes and groups by `observations.project`. The contract:

| Field | Value |
|---|---|
| `observation.project` | `identity.project_name` — always canonical |
| `metadata.project_identity` | the full canonical envelope |
| `metadata.project_identity.project_id` | `identity.project_id` |
| `metadata.capture.raw_project_label` | whatever the parser said — audit only |

The parser's label is never authority. It is never used as `project`,
`project_id`, `project_name`, `workspace_id`, a Markdown path, a vector
filter, or a graph namespace. That is what stops values like
`preciso-que-verifique-o-por-que`,
`referenced-chatgpt-conversation-this-is-untrusted`, `shadow-run-clean`,
`miche` or `Microsoft VS Code` from becoming projects again.

## Identity policy

A session without a Git repository is not an error. Plenty of legitimate
capture happens outside one, and refusing it would lose real data to protect a
dropdown.

| Status | Meaning | Delivery |
|---|---|---|
| `CLASSIFIED` | identity resolved from evidence | allowed |
| `UNCLASSIFIED` | not enough evidence; resolved to `unclassified/<provider>` | allowed, flagged, health degraded |
| `INVALID` | envelope malformed, inconsistent, or unresolvable | **refused before writing** |

`UNCLASSIFIED` is deterministic: the same provider with the same absent
evidence always yields the same id. It is auditable, and it never borrows a
name from prompt text or a directory basename.

## Envelope validation

A session may arrive with `metadata.project_identity` already attached — the
hook computes one. `ingest` does not trust it blindly:

- the schema is validated;
- `project_id` and `resolution_method` are checked;
- the envelope is compared against the evidence in the same session;
- fields are normalised.

An envelope that disagrees with its own evidence is `INVALID`. A session with
no envelope is resolved. Either way both entrypoints reach the same answer,
because the answer is computed in one place.

## Entrypoints

| Entrypoint | Declared as | Role |
|---|---|---|
| `scripts/capture/capture-realtime.py` | service `sinapse-capture-realtime` | watches provider sources continuously |
| `scripts/capture/capture-tailer.py` | job `capture-tailer` | periodic scan of provider files |

Both import `hive_mind.capture.ingest`. Neither resolves identity itself —
asserted in `tests/unit/test_capture_canonical_identity.py`, which fails if
either one starts calling `attach_project_identity` again.

## What is proven, and what is not

| Leg | Status |
|---|---|
| parser → ingest → identity enforced | proven, new event with a unique marker |
| both entrypoints agree | proven, same event through each |
| worktree and root are one project | proven, real `git worktree add` |
| project A isolated from project B | proven |
| replay does not duplicate | proven |
| payload the Claude Mem worker would receive | proven, byte for byte |
| **row existing in a Claude Mem store** | **not proven** — the POST is recorded, not executed |
| bridge → UMC `workspace_id` | proven, production bridge against temporary databases |
| per-provider matrix | **not started** — one green event proves the path, not 13 providers |

The worker leg is stubbed because the real worker listens on a fixed port and
writes to the live store, which this work is not permitted to touch. Closing
it needs a temporary worker process.

## Related

- [../project-identity.md](../project-identity.md) — the resolver and its precedence chain
- [../implementation/DELIVERY-LEDGER.md](../implementation/DELIVERY-LEDGER.md) — D004-R2 and its errata
