# Task 4 Report — Propagate Canonical Project Identity

## Outcome

Implemented the canonical identity attachment boundary for realtime sessions and supported hooks while preserving the single direct realtime delivery path (`parser -> capture_core.ingest -> Claude Mem`). No parser/provider behavior, Hermes code, service, database, backlog, historical record, outbox ownership, or active root was changed.

## TDD Evidence

### RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_capture_project_identity.py
```

Result: collection failed with one expected error because `attach_project_identity` did not exist:

```text
ImportError: cannot import name 'attach_project_identity'
1 error in 0.57s
```

The new tests specified these categories before production changes:

1. exactly one resolver call per realtime session immediately before ingest;
2. complete versioned identity envelope and legacy `project`/`cwd` compatibility;
3. provider/application/profile labels cannot become `project_id` without authoritative evidence;
4. `referenced_projects` remains secondary metadata;
5. init/observations/summarize metadata plus unchanged event/content hashes and replay idempotency;
6. equivalent hook boundary with canonical metadata.

### Intermediate GREEN feedback

The first implementation pass produced 3 passed / 2 failed because two insertions had not applied across mixed Windows line endings. After the minimal correction, the new suite passed 5/5. The first full focused regression produced 65 passed / 1 failed: an old hook assertion still expected the free-form label `project` to remain active. The assertion was updated to require `Unclassified (codex)` and `project_id=unclassified/codex`, while preserving native event ID, CWD, and replay idempotency.

### Final GREEN

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests\unit\test_capture_project_identity.py `
  tests\unit\test_capture_realtime.py `
  tests\unit\test_capture_core.py `
  tests\unit\test_capture_events.py `
  tests\unit\test_capture_hook.py `
  tests\unit\test_capture_adapters_windows.py `
  tests\unit\test_capture_context.py `
  tests\unit\test_capture_hook_idempotency.py `
  tests\unit\test_capture_queue.py `
  tests\unit\test_project_identity.py
```

Result:

```text
114 passed in 20.46s
```

Additional gates:

```text
compileall touched capture modules: PASS
git diff --check: PASS
```

## Implementation

- `session_events.attach_project_identity` creates a copied normalized session, consults the shared resolver exactly once, writes all canonical fields at top level, nests the complete `project_identity` envelope, and updates legacy `project` to canonical `project_name`.
- Free-form legacy `project` is offered as explicit evidence only when the declarative registry recognizes it; provider/application/profile labels are never used as project IDs.
- Realtime capture enriches each parsed session immediately before `capture_core.ingest`; delivery ownership remains unchanged.
- Hook callbacks resolve one canonical identity before creating `ProviderEvent`, merging the envelope into existing event metadata without changing the stable event ID inputs.
- Session-to-event normalization carries the envelope on prompts, tool calls/results, and final assistant events; canonical identity metadata wins over event-local metadata.
- Claude Mem init, observations, and summarize payloads receive the same compatible `metadata.project_identity` envelope. Existing sessions without an envelope keep their old payload behavior.
- `content_hash`, observation tool IDs, event IDs, SeenStore keys, and idempotency logic were not changed.

## Files

Modified:

- `scripts/capture/capture-realtime.py`
- `scripts/capture/capture_core.py`
- `scripts/capture/session_events.py`
- `scripts/capture/capture-hook.py`
- `tests/unit/test_capture_hook.py`

Created:

- `tests/unit/test_capture_project_identity.py`
- `.superpowers/sdd/task-4-report.md`

## Self-review

- No outbox/drainer/main-queue delivery changes.
- No provider parser or Hermes behavior changes.
- No capture adapter registry behavior changes.
- No service/process/database/backlog interaction.
- No identity field participates in content/event hashes.
- The realtime resolver is long-lived per daemon and called once per parsed session.
- The hook resolver is long-lived per hook process and called once per callback/session event.

## Remaining concerns outside Task 4

- Providers that do not yet emit an authoritative `surface` continue as `unknown` at realtime; provider-specific surface normalization belongs to Task 6.
- Hermes Desktop source parsing remains intentionally untouched and belongs to Task 5.
- Downstream Claude Mem bridge/UMC workspace mapping belongs to Task 7.