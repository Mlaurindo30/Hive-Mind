# Hive-Mind Canonical Runtime Consolidation Plan

> **Execution discipline:** execute with Superpowers subagent-driven development.
> Every behavior change starts with a focused failing test, receives an independent
> specification/quality review, and is reverified by the coordinator before cutover.

**Goal:** Consolidate all accepted Hive-Mind development into one canonical history,
promote it safely to the real runtime at `D:\Hive-Mind`, restore every installed
provider capture path, and remove backup/worktree locations from the operational
control plane without deleting historical data or publishing remote changes.

**Architecture:** The clean branch `codex/runtime-consolidation` is based on the
complete descendant of the currently active runtime. Staging validation occurs in
an external integration worktree. The real root remains untouched until all static,
unit, packaging and runtime-path gates are green. Cutover updates the canonical root,
then restarts only Hive-Mind-owned components and proves ownership plus capture with
new markers.

**Primary technologies:** Git, Python 3.12, pytest, Node.js test runner, PowerShell,
Windows Scheduled Tasks, SQLite/WAL, native provider parsers, Sinapse MCP, uv/hatch.

---

## Global constraints

- Do not delete or migrate historical databases, drain outboxes, change credentials,
  models, logins, or external providers.
- Do not push, publish a release, or mutate remote repositories.
- Do not modify `D:\Hive-Mind` before the staging gate is fully green.
- Preserve all prior states outside the canonical root with verified Git bundles,
  diffs, manifests and content archives.
- Fail validation if any live process, scheduled task, service, launcher, manifest,
  or operational config resolves to a backup/worktree path after cutover.
- Classify unavailable providers honestly as `NOT_INSTALLED`, `NOT_CONFIGURED`, or
  `NOT_A_CAPTURE_SOURCE`; do not turn absence into a passing capture result.

## Task 1: Resolve Windows installer from the executing checkout

**Files:**

- Modify: `npm/lib/init.js`
- Test: `tests/unit/test_windows_install_contract.py`
- Test: `npm/test/doctor.test.js`
- Test: `npm/test/supervisor.test.js`

**Steps:**

1. Run the Windows contract test and preserve the failure showing the hard-coded
   `C:\Users\miche\Hive-Mind\install.ps1` path.
2. Default `windowsInstallerArgs` to the repository containing `npm/lib/init.js`.
3. Preserve explicit `root` arguments used by `nativeWindowsInit` and tests.
4. Run the focused Python and Node suites and obtain independent review.
5. Commit as `fix(runtime): resolve Windows installer from current checkout`.

## Task 2: Select the newest contentful provider source

**Files:**

- Modify: `src/hive_mind/validation/canary.py`
- Optionally modify: `src/hive_mind/validation/sources.py`
- Modify: `tests/unit/test_validation_canary.py`

**Steps:**

1. Add a failing test with a newest initialized/empty source and an older source
   containing a real parseable session.
2. Make the canary try inventory files newest-first until one yields sessions.
3. Preserve parser exceptions as real errors and include attempted source evidence
   when all files are empty.
4. Run validation/capture parser suites and obtain independent review.
5. Commit as `fix(capture): skip empty newest provider sources`.

## Task 3: Enforce canonical operational paths

**Files:**

- Create: `src/hive_mind/validation/runtime_paths.py`
- Create: `tests/unit/test_runtime_path_policy.py`
- Modify the narrowest existing staging/health entrypoint that can invoke the gate.

**Steps:**

1. Add failing tests for `.worktrees`, `.codex/worktrees`, backup, archive, and
   temporary snapshot paths across manifests, operational configs and launchers.
2. Accept documentation, test fixtures and archive reports that merely describe
   historical paths; the policy targets executable runtime surfaces only.
3. Add live inspection inputs for processes, tasks and services so post-cutover
   ownership can be checked with the same normalized policy.
4. Run the focused suite, path scan and independent review.
5. Commit as `feat(runtime): enforce canonical operational paths`.

## Task 4: Complete the clean consolidated history

**Files:**

- Add this plan and final scoped reports only.
- Do not import archived root artifacts that are obsolete or superseded.

**Steps:**

1. Verify the development base contains every commit from the active runtime using
   `git log --left-right --cherry-pick`.
2. Compare the seven dirty tracked runtime files against the consolidation branch;
   carry forward only behavior not already present and covered by tests.
3. Classify all untracked root files from the external preservation manifest.
4. Run `git diff --check`, compile checks and focused suites.
5. Commit documentation/report changes separately from behavior changes.

## Task 5: Pass the staging gate

**Steps:**

1. Run all unit tests, then smoke/integration/E2E gates that do not require changing
   provider credentials or historical data.
2. Run the exact Windows PowerShell contracts and npm tests.
3. Build sdist and wheel with `uv build`; inspect both archives for secrets,
   databases, environment files and backup/worktree path leakage.
4. Exercise the disposable runtime/bootstrap flow from the clean checkout.
5. Produce a staging report with command, exit code, counts and artifact hashes.

## Task 6: Cut over the canonical runtime

**Steps:**

1. Recheck `D:\Hive-Mind` status and compare it to the preserved inventory. Abort on
   unexpected drift.
2. Stop only Hive-Mind-owned scheduled tasks and processes; do not stop unrelated
   provider applications.
3. Move the canonical Git root to the consolidated commit while retaining the
   external archive and recoverable refs.
4. Reinstall/update the local package and task definitions from `D:\Hive-Mind`.
5. Start supervisor, API, MCP, capture, indexes and required bridges from the
   canonical root only.

## Task 7: Prove runtime ownership and provider capture

**Steps:**

1. Verify process command lines, scheduled-task actions, services, launchers,
   manifests and configs contain no backup/worktree operational paths.
2. Re-run `sinapse_health` and required service readiness probes.
3. For every configured provider, write a new unique marker through the real source,
   wait for capture, and verify canonical project identity plus destination evidence.
4. Record `OK`, `BROKEN`, `NOT_INSTALLED`, `NOT_CONFIGURED`, or
   `NOT_A_CAPTURE_SOURCE` per provider with exact evidence.
5. Do not drain or rewrite historical provider/outbox data to manufacture success.

## Task 8: Retire obsolete operational copies and report

**Steps:**

1. Remove stale worktree registrations and operational references only after the
   canonical runtime is healthy and the external preservation is reverified.
2. Keep recoverable historical content in `D:\Hive-Mind-Archive\<timestamp>`; never
   delete historical databases or unverified unique work.
3. Produce final repository inventory, provider status, runtime ownership, test,
   package and rollback reports.
4. Save verified decisions/learnings to Sinapse and call `sinapse_session_end`.

