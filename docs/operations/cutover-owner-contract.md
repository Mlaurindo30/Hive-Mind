# Cutover owner contract (P2-R4)

Prepared, **not applied**. This is the contract the P4 cutover must satisfy; it
changes no live task, service or process. It exists so that the move of the
runtime into `D:\Hive-Mind` is a checklist with objective pass/fail gates, not a
judgement call.

## Canonical owners after cutover

| Surface | Owner target | Working dir | Today (pre-cutover) |
|---|---|---|---|
| `capture-realtime` | `<root>\.venv\Scripts\python.exe scripts\capture\capture-realtime.py` | `D:\Hive-Mind` | **runs from `D:\Hive-Mind-Consolidation\...\repo`** (the one live violation) |
| `hive-mind` / `hive-mindd` | `<root>\.venv\Scripts\hive-mind*.exe` (installed by `uv sync`, package built from `src/hive_mind`) | `D:\Hive-Mind` | not installed in the canonical venv |
| supervisor (resident) | `HiveMind-Supervisor` → `start-windows-supervisor.ps1 -Root D:\Hive-Mind` | `D:\Hive-Mind` | task registered; no resident process |
| REST (`sinapse-api`) | supervisor-managed service from `config/runtime.yaml` | `D:\Hive-Mind` | not running |
| sqlite-vec worker | supervisor-managed service | `D:\Hive-Mind` | **down** (`sinapse_health` reports it false) |
| `HiveMind-Backup` | `<root>\.venv\Scripts\hive-mind.exe backup run --apply` | `D:\Hive-Mind` | points at the untracked wrapper — **migrated in P2-R1** |
| `HiveMind-KnowledgeHealth` | `<root>\.venv\Scripts\python.exe scripts\health\audit_memory.py` | `D:\Hive-Mind` | correct target; exit 1 is data, see below |
| `HiveMind-PostRebootValidation` | `<root>\.venv\Scripts\python.exe scripts\health\validate_after_reboot_windows.py` | `D:\Hive-Mind` | correct target; exit 1 is runtime state, see below |

## Forbidden in every persisted runtime surface

No task action/arguments/working-directory, service `PathName`, launcher,
entrypoint, `config/runtime.yaml` or `logs/supervisor/manifest.json` may
reference:

- `Hive-Mind-Consolidation`
- `Hive-Mind-Archive`
- any `*/backups` or `*/backups/worktrees` **under the canonical root**
- any `*/.tmp` **under the canonical root**
- `.codex/worktrees`, `.gemini/.../worktrees`, `.worktrees`
- any second `Hive-Mind` repository root (e.g. `E:\deploy\Hive-Mind`)

Enforced by `hive_mind.validation.runtime_paths.find_runtime_path_violations`
(P2-R4 widened it to cover the canonical `.tmp` and `backups` subdirs) and
surfaced by `scripts/health/audit_runtime_paths_windows.py`. The runtime is
canonical only when that audit reports **zero** findings — which cannot happen
while `capture-realtime` runs from staging, so the audit reaching zero is itself
a cutover completion gate.

## The two "failing" scheduled tasks are not code defects

Both were re-examined; neither has a fix that belongs in staging code, and
inventing one would be dishonest.

- **`HiveMind-PostRebootValidation` (exit 1):** the real host report
  (`logs/post-reboot-validation.json`, 2026-07-22 12:01) shows `status: fail`
  driven by `services_healthy: False`, with `findings: 0`. A required service
  was not healthy at reboot (sqlite-vec worker down, REST not running). The
  validator reported a true condition. It turns green when the services are
  actually up — an operational step in **P4/P5**, not a code change.
- **`HiveMind-KnowledgeHealth` (exit 1):** `audit_memory.py` exits non-zero when
  knowledge health is degraded. `sinapse_health` shows the live cause —
  `orphan_vectors=7`, `observations_linked_pct≈11.9% (<80%)`,
  `discoveries_pending=1242 (>500)`, Milvus sync lag 1036. These are data-state
  thresholds over the live databases, which this audit must not touch. The
  script is correct; the backlog is cleared by the Dream Cycle / promotion in
  **P5**, not by editing the validator.

Recording them here keeps the gate honest: P2 does not mark these "fixed", it
documents that they carry no staging code cause and assigns the real remediation
to the phase that owns live state.

## Rollback

The backup-task migration (P2-R1) exports the previous task XML before
replacing it and can restore it via `Restore-HiveMindTaskDefinition`. The
component checkouts roll back via `components.py rollback <manifest>`. The
runtime itself rolls back to the pre-cutover bundle captured at the start of P4.
