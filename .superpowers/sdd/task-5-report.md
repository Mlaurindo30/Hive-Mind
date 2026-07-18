# Task 5 Report — Hermes Desktop Capture Recovery

## Outcome

Hermes CLI and Desktop top-level sessions now normalize through the canonical parser boundary. The parser no longer assigns project identity, excludes subordinate/internal sources, preserves all active non-empty conversation evidence in chronological order, and reads the installed WAL-backed database without mutation.

## Recovery from prohibited helper use

The previous implementer invoked `apply_patch` despite the explicit prohibition and was interrupted. At recovery start, production `scripts/capture/parsers/hermes.py` was still the old implementation; only the two new test files were untracked. Before any production change, both tests were read completely and then rewritten in full via PowerShell/.NET using UTF-8 without BOM and LF line endings. No `apply_patch` call was made during this recovery.

## TDD evidence

### RED

Command:

```powershell
.venv\Scripts\python.exe -m pytest -q `
  tests\unit\test_hermes_parser.py `
  tests\integration\test_hermes_parser_sqlite.py
```

Observed before production changes:

```text
3 failed, 1 passed
```

Failures were the expected contract gaps:

1. Desktop session returned zero rows.
2. CLI output lacked authoritative `surface`.
3. A committed Desktop conversation still present in the WAL returned zero rows.

### GREEN

Focused parser and WAL integration tests:

```text
4 passed in 0.20s
```

Final focused regression matrix covering Hermes, Windows adapters, realtime WAL routing, project identity, Git identity integration, capture core, source detection, and event normalization:

```text
125 passed in 20.92s
```

## Implementation

- Queries only top-level Hermes `source IN ('cli', 'desktop')` sessions.
- Excludes `subagent`, `cron`, `internal`, and any other non-top-level source by allowlist.
- Preserves native `sid`, `source`, authoritative `surface`, `model`, `started_at`, `cwd`, `git_branch`, and `git_repo_root`.
- Preserves every active, non-empty user prompt and assistant response, plus tool-message interleaving, in chronological `timestamp, id` order.
- Emits full `prompts`, timestamped `prompt_events`, timestamped assistant `turns`, full ordered `messages`, and `last` assistant response.
- Keeps full response evidence without the prior 4,000-character truncation.
- Keeps note stripping limited to a complete leading `[Note: ...]` prefix.
- Opens SQLite with a URI `mode=ro` connection and `PRAGMA query_only = ON`; it does not copy, checkpoint, or mutate the database.
- Removed `HERMES_PROJECT` and emits no parser-owned `project`; canonical identity remains delegated to `ProjectIdentityResolver` through `attach_project_identity`.
- No adapter change was necessary: the existing Hermes Windows source is `%LOCALAPPDATA%\hermes\state.db`.

## Live installed database proof — read-only

Database opened only with SQLite `mode=ro`:

```text
C:\Users\miche\AppData\Local\hermes\state.db
```

Latest Desktop evidence, with no private message content printed:

```text
sid: 20260717_224707_5d0606
source/surface: desktop/desktop
active non-empty DB rows: user=12, assistant=11, tool=123
parsed session: prompts=12, turns=11, messages=146
```

The `state.db` and `state.db-wal` sizes and nanosecond mtimes were identical before and after both direct read-only SQL inspection and parser execution:

```text
read_only_files_unchanged=true
```

## WAL trigger audit

No new delivery route or second source was introduced. Existing realtime behavior already maps a `state.db-wal` filesystem event back to the canonical `state.db`: `RealtimeCapture` falls back to registered sources and `capture_core._src_mtime()` includes `-wal` and `-shm`. The explicit regression `test_sqlite_wal_change_reparses_canonical_database` passed in the 125-test matrix. Startup catch-up uses the same WAL-aware mtime function.

## Safety and validation

- `python -m compileall -q scripts\capture`: PASS
- `git diff --check`: PASS
- identity delegation guard (`HERMES_PROJECT` and parser-owned `project` absent): PASS
- self-review: no unrelated source changes; adapter/realtime remained unchanged
- no daemon/process/service/task/reboot action
- no write to the installed Hermes database
- no write, drain, merge, delete, or reprocess of either protected outbox/database
- no real canary and no Task 6 work performed

## Files changed

- `scripts/capture/parsers/hermes.py`
- `tests/unit/test_hermes_parser.py`
- `tests/integration/test_hermes_parser_sqlite.py`
- `.superpowers/sdd/task-5-report.md`
