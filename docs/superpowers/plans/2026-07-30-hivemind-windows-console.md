# Hive-Mind Windows Console-Free Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Hive-Mind Windows runtime start, supervise, validate, and capture without opening visible console windows.

**Architecture:** Scheduled Tasks execute validated PEP 621 GUI entry points. Managed children use project `python.exe` with Windows no-console creation flags. Post-reboot validation trusts fresh managed state, and legacy Codex hooks are removed only after canonical capture is proven.

**Tech Stack:** Python 3.12, Hatchling, uv, PEP 621, Windows PE, Task Scheduler, pytest, pywin32.

## Global Constraints

- Operate only on Hive-Mind; do not change Hermes or Open Design.
- Do not change providers, models, `setup-brain.bat`, Claude Mem databases, or historical capture data.
- Keep Watchdog disabled throughout implementation and rollback.
- Do not use `.ps1`, `.cmd`, or `.vbs` as runtime fallbacks.
- Do not reset, stash, checkout, or discard the existing dirty worktree.
- Do not register a task before its installed launcher proves PE Subsystem 2, project `sys.prefix`, and project package origin.
- Do not claim completion before a ten-minute live monitor and a real reboot validation.

---

### Task 1: GUI launcher contract and installation gate

**Files:**
- Create: `src/hive_mind/windows/__init__.py`
- Create: `src/hive_mind/windows/entrypoints.py`
- Create: `src/hive_mind/install/windows_launchers.py`
- Modify: `pyproject.toml`
- Modify: `src/hive_mind/install/windows.py`
- Test: `tests/unit/test_windows_gui_launchers.py`
- Test: `tests/install/test_windows_gui_entrypoints.py`

**Interfaces:**
- Produces: `read_pe_subsystem(path: Path) -> int`
- Produces: `expected_gui_launchers(root: Path) -> dict[str, Path]`
- Produces: `validate_gui_launchers(root: Path) -> tuple[LauncherEvidence, ...]`
- Produces: `supervisor_main() -> int`, `post_reboot_main() -> int`

- [ ] Write failing unit tests for PE values 2/3, malformed files, missing launchers, wrong prefix, and package origin outside the root.
- [ ] Run `D:\Hive-Mind\.venv\Scripts\python.exe -m pytest tests\unit\test_windows_gui_launchers.py -q` and confirm failures are caused by missing production interfaces.
- [ ] Add `[project.gui-scripts]` entries for `hive-mind-supervisorw` and `hive-mind-post-rebootw`.
- [ ] Implement launcher probe output through an explicit JSON file argument; never depend on GUI stdout.
- [ ] Implement fail-closed launcher validation and call it immediately after package synchronization but before hooks/tasks.
- [ ] Run unit tests and `uv sync --frozen --all-groups`, then prove both installed executables have PE Subsystem 2 and project prefix/origin.

### Task 2: Transactional Windows tasks and managed child lifecycle

**Files:**
- Modify: `src/hive_mind/maintenance/windows_runtime.py`
- Modify: `src/hive_mind/daemon/managed.py`
- Modify: `src/hive_mind/maintenance/runtime_services.py`
- Modify: `src/hive_mind/daemon/manifest.py`
- Test: `tests/unit/test_windows_install_contract.py`
- Test: `tests/unit/test_windows_runtime_contract.py`
- Test: `tests/unit/test_managed_supervisor.py`
- Test: `tests/unit/test_managed_restart.py`

**Interfaces:**
- Consumes: validated GUI launcher paths from Task 1
- Produces: transactional export/register/restore result for Supervisor and PostRebootValidation
- Produces: deterministic restart scheduling with delay, capped backoff, and exact limit

- [ ] Write failing tests requiring GUI task executables and rejecting Console launchers.
- [ ] Write failing tests proving Watchdog is not enabled or recreated.
- [ ] Write failing tests proving generic Python resolves to `.venv\Scripts\python.exe` with both no-console flags.
- [ ] Write failing tests for `on-failure`, initial delay, capped exponential backoff, and restart limit.
- [ ] Implement transactional XML backup/restore and the two GUI task specs.
- [ ] Implement child command resolution and restart scheduling without `pythonw.exe`.
- [ ] Run all four task test files and inspect the generated XML.

### Task 3: Fresh managed state and post-reboot validation

**Files:**
- Modify: `src/hive_mind/daemon/state.py`
- Modify: `src/hive_mind/daemon/managed.py`
- Create: `src/hive_mind/validation/post_reboot_windows.py`
- Modify: `scripts/health/validate_after_reboot_windows.py`
- Modify: `scripts/health/audit_runtime_paths_windows.py`
- Test: `tests/unit/test_daemon_state.py`
- Test: `tests/unit/test_validate_after_reboot_windows.py`

**Interfaces:**
- Produces managed state fields: `supervisor_pid`, `started_at`, `updated_at`
- Produces `validate_live_runtime(root: Path) -> PostRebootReport`

- [ ] Write failing tests for stale state, dead Supervisor, dead child, orphan child, PID mismatch, and unhealthy required service.
- [ ] Write failing subprocess tests requiring `CREATE_NO_WINDOW` for `schtasks` and PowerShell fallback.
- [ ] Persist Supervisor identity and timestamps in the managed state.
- [ ] Implement live PID/ancestry/readiness validation from `.hive-mind/state/services.managed.json`.
- [ ] Convert the script to a thin compatibility wrapper over the packaged validator.
- [ ] Run the state and post-reboot test files.

### Task 4: Codex capture cutover without legacy shell hooks

**Files:**
- Modify: `scripts/setup/install-capture-hooks.py`
- Modify: `tests/unit/test_install_capture_hooks.py`
- Runtime config: `C:\Users\miche\.codex\hooks.json`

**Interfaces:**
- Produces: idempotent cleanup that removes only Hive-Mind-owned Codex `capture-hook.py` records
- Preserves: every foreign hook and unrelated setting

- [ ] Write failing tests proving clean install does not create legacy Codex hooks, cleanup is idempotent, and foreign hooks survive.
- [ ] Implement cleanup mode while leaving non-Codex behavior unchanged.
- [ ] Snapshot the live hooks file and record the legacy outbox count.
- [ ] Prove canonical capture of one fresh prompt, tool result, and assistant response.
- [ ] Remove only the five owned records and restart Codex.
- [ ] Repeat capture proof and confirm the legacy outbox count does not increase.
- [ ] If canonical capture fails, stop cutover and implement the GUI capture entry point before retrying.

### Task 5: Controlled runtime cutover and local acceptance

**Files:**
- Create runtime evidence under:
  `D:\Hive-Mind-Archive\2026-07-30\windows-console-cutover\`
- Update Scheduled Tasks only after Tasks 1-4 pass

- [ ] Export task XML, process trees, command lines, executable hashes, and state hashes.
- [ ] Disable Supervisor/PostReboot temporarily; keep Watchdog disabled.
- [ ] Archive stale managed, shadow, legacy, and post-reboot state files.
- [ ] Terminate only verified orphan PIDs from the cutover ledger.
- [ ] Install the package/entrypoints without changing providers, models, containers, or databases.
- [ ] Register both GUI tasks transactionally and validate their PE subsystem.
- [ ] Start exactly one Supervisor and prove all children descend from it.
- [ ] Restore sqlite-vec health and deliberately restart it while monitoring consoles.
- [ ] Exercise Codex capture and monitor Hive-Mind-attributable consoles for ten minutes.

### Task 6: Clean-install and reboot acceptance

**Files:**
- Modify: `tests/install/test_windows_bootstrap.py`
- Create: `tests/install/test_windows_gui_entrypoints.py`
- Create: `reports/windows-console-runtime-acceptance.md`

- [ ] Run a disposable clean installation rooted outside the active runtime.
- [ ] Prove installed GUI launchers, prefix, package origin, and no runtime wrapper scripts.
- [ ] Run the complete targeted and Windows integration suites.
- [ ] Reboot Windows with the acceptance monitor armed.
- [ ] Prove no logon console, one live Supervisor, passing fresh PostRebootValidation, healthy sqlite-vec, and no later recurrence.
- [ ] Audit every objective requirement and record evidence or an explicit remaining failure.
