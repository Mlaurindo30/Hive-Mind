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
- Hook identity is persisted atomically per `(provider, session_id)` and reused across callback processes.

## Remaining concerns outside Task 4

- Providers that do not yet emit an authoritative `surface` continue as `unknown` at realtime; provider-specific surface normalization belongs to Task 6.
- Hermes Desktop source parsing remains intentionally untouched and belongs to Task 5.
- Downstream Claude Mem bridge/UMC workspace mapping belongs to Task 7.
## P1 Review Correction — Cross-process Hook Identity

The review identified that a process-local resolver did not satisfy the once-per-session contract because real hook callbacks may start a fresh Python process for every event. The hook now uses a SQLite-backed `SessionContextStore` with a separate `capture_session_context` table keyed by `(provider, session_id)`. Its `BEGIN IMMEDIATE` get-or-create transaction serializes competing processes: the first callback resolves and persists the complete envelope; every later callback reuses it without consulting cwd, environment, or resolver again.

The test uses `HIVE_CAPTURE_DB` pointing at pytest `tmp_path`; no protected or runtime database was opened, drained, or modified.

### RED

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests\unit\test_capture_project_identity.py `
  -k "reuses_persisted_identity"
```

Result before production changes:

```text
1 failed, 5 deselected in 0.59s
AssertionError: assert (1 + 1) == 1
```

The first prompt callback resolved once; a second tool-result callback loaded through a distinct module instance after `cwd`, `HIVE_PROJECT_ID`, and `HIVE_PROJECT_ROOT` changed, and incorrectly resolved again.

### GREEN

Focused hook identity:

```text
2 passed, 4 deselected in 0.42s
```

Complete Task 4 suite:

```text
115 passed in 12.89s
```

Additional gates:

```text
compileall scripts/capture/capture-hook.py scripts/capture/session_events.py: PASS
git diff --check: PASS
```

The regression test also proves that both native event IDs, tool metadata, current callback cwd, replay behavior, and the original canonical envelope survive the process/store boundary unchanged. The resolver is called exactly once across the two callbacks.
## P1 Review Correction — Dedicated Context DB and Cache Repair

The second review found two P1 issues in the cross-process hook cache. Both were corrected without changing the legacy `CaptureQueue` outbox path, delivery ownership, providers, Hermes, services, backlog, or protected databases.

### P1 A — Context DB isolation

`SessionContextStore` now resolves `HIVE_CAPTURE_CONTEXT_DB`, defaulting to `logs/capture-context.db`. `CaptureQueue` continues to resolve `HIVE_CAPTURE_DB`, defaulting to `logs/capture-outbox.db`; its path and schema are unchanged.

A tmp-path regression test proves:

- the two defaults are distinct;
- explicit outbox and context paths remain distinct;
- `capture_session_context` is created only in the context DB;
- no context table is created in the queue DB.

All hook tests force `HIVE_CAPTURE_CONTEXT_DB` to pytest `tmp_path`. No real or protected runtime database was opened or modified.

### P1 B — Invalid persisted envelope repair

Every cache hit is parsed and validated through `ProjectIdentity.from_dict`. Invalid JSON, missing/invalid fields, unsupported schema versions, and other contract failures become a cache miss. Under the existing `BEGIN IMMEDIATE` transaction, the resolver runs once, the canonical envelope is validated again, and the existing row is atomically replaced before commit. The current callback then continues to `CaptureQueue.enqueue`.

Parameterized regression coverage proves both `{not-json` and an invalid schema payload are repaired, persisted as a valid `ProjectIdentity`, and the callback event is still enqueued with the repaired envelope. Existing once-per-session and serialized cross-process behavior remains unchanged for valid cache rows.

### TDD RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_capture_project_identity.py `
  -k "context_database_is_isolated or repairs_invalid_persisted"
```

Result before production changes:

```text
3 failed, 6 deselected in 1.11s
```

Expected failures:

- `default_context_db_path` did not exist;
- both corruption cases found no context table in the dedicated DB because production still wrote it into the outbox.

### GREEN

New regression cases:

```text
3 passed, 6 deselected in 0.34s
```

Focused hook/identity/idempotency set:

```text
17 passed in 3.06s
```

Complete Task 4 suite:

```text
118 passed in 15.92s
```

Additional gates:

```text
compileall scripts/capture/capture-hook.py scripts/capture/project_identity.py scripts/capture/session_events.py: PASS
git diff --check: PASS
```

## P1 Review Correction — Unavailable Identity Context DB

The final Task 4 review found that an unavailable auxiliary identity cache aborted the callback before the durable event outbox opened. The hook now treats only context-cache construction and SQLite transaction/close failures as a degraded auxiliary component. It resolves the current callback through `attach_project_identity`, preserves the canonical envelope, and continues into the unchanged `CaptureQueue.enqueue` path. The once-per-session guarantee may degrade while the cache is unavailable, but the current event is not lost.

The returned hook result exposes a stable non-sensitive diagnostic:

```json
{"component":"identity_context_cache","status":"degraded","reason":"unavailable"}
```

No exception message, database path, payload, or secret is exposed. The cache boundary does not catch failures from the actual outbox: an explicit regression proves `CaptureQueue.enqueue` errors still propagate instead of reporting capture success.

### TDD RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_capture_project_identity.py `
  -k "context_db_constructor_is_unavailable or context_db_transaction_fails"
```

Result before the production correction:

```text
2 failed, 9 deselected in 0.86s
```

Both expected failures were `sqlite3.OperationalError`: one from `HIVE_CAPTURE_CONTEXT_DB` pointing at a directory and one injected during `get_or_resolve`. In both cases production aborted before enqueue.

### GREEN

New unavailable-cache regressions:

```text
2 passed, 9 deselected in 0.60s
```

Complete project-identity regression including the outbox failure boundary:

```text
12 passed in 0.74s
```

Complete Task 4 suite:

```text
121 passed in 17.71s
```

Additional gates:

```text
python -m compileall scripts\capture: PASS
git diff --check: PASS
```

All database paths used by these tests were under pytest `tmp_path`. No real/protected database, provider, Hermes implementation, service, backlog, active root, or historical data was opened or modified.