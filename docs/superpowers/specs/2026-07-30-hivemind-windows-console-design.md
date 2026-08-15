# Hive-Mind Windows Console-Free Runtime Design

## Objective

Eliminate every visible Windows console created by the Hive-Mind runtime while
preserving automatic startup, service supervision, post-reboot validation, and
canonical Codex capture. The implementation must also work from a clean
installation rooted at the selected Hive-Mind directory.

## Scope

Included:

- `HiveMind-Supervisor`
- `HiveMind-PostRebootValidation`
- processes owned by `ManagedSupervisor`
- Hive-Mind-owned Codex hook records
- the native Windows installer and project `.venv`
- managed state, orphan detection, rollback, and live acceptance

Excluded:

- Hermes and Open Design
- provider/model configuration and `setup-brain.bat`
- Claude Mem databases and historical capture migration
- reprocessing or draining legacy capture backlogs

## Architecture

Long-running Scheduled Tasks use PEP 621 GUI entry points generated from
`[project.gui-scripts]`. Task registration is fail-closed: the installer must
prove that each installed executable is PE Subsystem 2, runs with the project
virtual environment, and imports `hive_mind` from the selected project root
before it may update Task Scheduler.

Managed child services use the project `.venv\Scripts\python.exe` with
`CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`. They must never be rewritten to
`.venv\Scripts\pythonw.exe`, because the current `uv venv` launcher is PE
Subsystem 3 and delegates to the global `uv` Python.

Post-reboot validation reads `.hive-mind/state/services.managed.json` as the
runtime authority. It rejects stale state, missing Supervisor PID, dead service
PIDs, required services without readiness, and children outside the Supervisor
tree. Legacy `logs/supervisor/state.json` and `manifest.json` are not runtime
authorities.

The five Hive-Mind-owned Codex command hooks are legacy capture writers. Before
removing them, acceptance must prove that the canonical native capture path
records a fresh prompt, tool result, and assistant response exactly once. If
that proof fails, a GUI capture entry point is implemented as a fallback;
otherwise no replacement hook is installed.

## Safety and Rollback

Before runtime mutation, export the XML for Supervisor, PostRebootValidation,
and Watchdog; record task state, process trees, command lines, executable
hashes, and state-file hashes. Preserve in-scope dirty files without reset,
stash, checkout, or broad cleanup.

The Watchdog remains disabled. Task replacement is transactional: if either new
task cannot be registered and validated, restore both exported definitions.
Runtime rollback terminates only PIDs created by the cutover ledger and restores
the two previous task XML files. Historical databases and provider settings are
never touched.

## Acceptance

- one live Supervisor owns every managed child
- no orphaned Hive-Mind child process
- sqlite-vec is healthy
- the two logon tasks execute only PE Subsystem 2 launchers
- no Hive-Mind-attributable `cmd`, `conhost`, `pwsh`, or `powershell` window
  during a ten-minute Codex session
- a deliberate sqlite-vec restart creates no visible console
- prompt, tool-result, and assistant capture each arrive exactly once
- a disposable clean installation produces and validates the GUI launchers
- after a real reboot, no console appears, Supervisor is live, validation
  passes from fresh managed state, and no later recurrence is observed

