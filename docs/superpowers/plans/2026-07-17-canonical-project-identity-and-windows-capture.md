# Canonical Project Identity and Windows Capture Implementation Plan

> **Execution discipline:** use test-driven development for every behavior change.
> Run the named failing test first, implement only enough for green, then refactor
> while the focused suite remains green. Operational gates are additional evidence;
> mocks never replace them.

**Goal:** Deliver one canonical project identity from every installed provider to
Claude Mem, UMC, indexes, graphs, Dream/Markdown and public APIs, restore real
Hermes Desktop capture, and finish the verified Windows lifecycle without touching
the active root until disposable-Windows acceptance passes.

**Architecture:** A single immutable `ProjectIdentity` and
`ProjectIdentityResolver` attach at the normalized-session boundary. New capture
continues through direct `capture_core.ingest`; experimental outbox delivery is
removed from this increment. The identity envelope remains compatible with current
Claude Mem endpoints and maps `project_id` to UMC `workspace_id`.

**Primary technologies:** Python 3.12, pytest, SQLite/WAL, Git CLI, watchdog,
Claude Mem HTTP API, UMC SQLite, sqlite-vec, Milvus, Graphify, Graphiti/FalkorDB,
LightRAG, PowerShell, uv/hatch, npm and Windows Scheduled Tasks/services.

---

## Task 1: Preserve and Reconcile the Existing Git State

**Files:**

- Preserve all current tracked/untracked capture work in a named Git stash object.
- Remove from this increment:
  - `scripts/capture/capture_delivery.py`
  - `scripts/capture/capture_paths.py`
  - `scripts/capture/capture_policy.py`
  - `tests/integration/test_capture_delivery_local.py`
  - `tests/unit/test_capture_delivery.py`
  - `tests/unit/test_capture_paths.py`
  - `tests/unit/test_capture_policy.py`
  - `tests/unit/test_claude_mem_sink.py`
- Reconcile mixed hunks in:
  - `scripts/capture/capture-realtime.py`
  - `scripts/capture/capture-hook.py`
  - `scripts/capture/capture_events.py`
  - `scripts/capture/capture_queue.py`
  - `scripts/capture/session_events.py`
  - related tests

**Steps:**

1. Record branch, HEAD, status and both diff checks.
2. Create a named `git stash push --include-untracked` safety snapshot, record its
   commit hash, then restore it with `git stash apply --index`; do not drop it.
3. Verify the restored status and diff hashes match the pre-snapshot inventory.
4. Unstage all inherited changes without modifying the worktree.
5. Delete only the experimental new files listed above; retain queue code needed by
   existing hooks only if no runtime owner or test imports it.
6. Reconcile the mixed files so realtime capture has exactly one owner:
   `parser -> capture_core.ingest`.
7. Run:

```powershell
git diff --check
python -m compileall scripts/capture
python -m pytest -q tests/unit/test_capture_realtime.py tests/unit/test_capture_hook.py
```

8. Commit only the reconciled capture baseline:

```text
fix(capture): restore direct canonical delivery path
```

## Task 2: Add the Project Identity Model and Registry (TDD)

**Create:**

- `scripts/capture/project_identity.py`
- `config/project-aliases.yaml`
- `tests/unit/test_project_identity.py`
- `tests/fixtures/project-aliases.yaml`

**Steps:**

1. Write failing unit tests for:
   explicit ID, environment hints, official workspace, root repository, worktree,
   shared Git common-dir, normalized HTTPS/SSH remote, no remote, no Git, Unicode,
   spaces, Windows case folding, UNC, symlink/junction, detached HEAD, explicit
   alias, marker fallback, generic conversation and referenced projects.
2. Run the new test and confirm failures are caused by the missing resolver.
3. Implement an immutable versioned `ProjectIdentity`, validation and serialization.
4. Implement path normalization and bounded shell-free Git inspection.
5. Implement credential-free remote normalization.
6. Implement declarative registry loading/validation and the Hive-Mind mapping.
7. Implement deterministic fallback IDs and audited resolution method/confidence.
8. Keep semantic reference activation disabled by default.
9. Run the focused test until green, then add malformed-registry tests.
10. Commit:

```text
feat(projects): add canonical project identity resolver
```

## Task 3: Prove Root/Worktree Identity with Real Git Integration

**Create:**

- `tests/integration/test_project_identity_git.py`

**Modify:**

- `scripts/capture/project_identity.py`

**Steps:**

1. Write failing tests that create real temporary Git repositories and worktrees.
2. Prove root and worktree share one project ID but preserve different branch and
   worktree metadata.
3. Prove unrelated repositories with the same directory basename do not collide.
4. Prove remote normalization and a repository without remote.
5. Run:

```powershell
python -m pytest -q tests/integration/test_project_identity_git.py
```

6. Commit with Task 2 if inseparable; otherwise:

```text
test(projects): validate repository and worktree identity
```

## Task 4: Attach Identity at the Normalized Session Boundary (TDD)

**Modify:**

- `scripts/capture/capture-realtime.py`
- `scripts/capture/capture_core.py`
- `scripts/capture/session_events.py`
- `scripts/capture/capture_events.py`
- `scripts/capture/capture-hook.py`
- `scripts/capture/capture_adapters.py`
- `tests/unit/test_capture_realtime.py`
- `tests/unit/test_capture_core.py`
- `tests/unit/test_capture_events.py`
- `tests/unit/test_capture_hook.py`

**Create:**

- `tests/unit/test_capture_project_identity.py`

**Steps:**

1. Write failing tests proving one resolver call per session and complete envelope
   preservation through session normalization.
2. Test backward-compatible sessions containing only `project` and `cwd`.
3. Test that provider/application/profile labels do not become project IDs.
4. Attach identity immediately before `capture_core.ingest` for realtime sources
   and at the equivalent boundary for supported hooks.
5. Populate legacy `project` with canonical `project_name`.
6. Send compatible metadata in init, observations and summarize payloads.
7. Preserve existing content-hash idempotency.
8. Run all focused capture tests and commit:

```text
fix(capture): propagate canonical project metadata
```

## Task 5: Restore Hermes Desktop Capture Against the Real Schema (TDD)

**Modify:**

- `scripts/capture/parsers/hermes.py`
- `scripts/capture/capture_adapters.py`

**Create:**

- `tests/unit/test_hermes_parser.py`
- `tests/integration/test_hermes_parser_sqlite.py`

**Observed failure evidence:**

```text
Database: C:\Users\miche\AppData\Local\hermes\state.db
journal_mode: wal
latest source: desktop
latest session: 46 messages, 2 user prompts
current parser predicate: source = 'cli'
current parser result: parsed_sessions=0
```

**Steps:**

1. Build a real SQLite fixture matching the installed schema, with `cli`, `desktop`
   and `subagent` sessions.
2. Write a failing test proving desktop user/assistant messages are ignored today.
3. Specify accepted top-level sources (`cli`, `desktop`) and explicitly exclude
   subordinate/internal sources unless linked as separate audited events.
4. Preserve every user prompt, assistant response, timestamps, source/surface, CWD,
   Git hints and session ID.
5. Remove the hardcoded `HERMES_PROJECT`; delegate identity to the resolver.
6. Test note stripping, tool-message interleaving, empty content, active rows,
   multiple prompts and WAL-aware reopening.
7. Run focused unit/integration tests.
8. Parse the live DB in read-only mode and confirm the latest desktop session is
   returned before changing any daemon.
9. Commit:

```text
fix(capture): capture Hermes desktop sessions on Windows
```

10. Only after the worktree daemon is explicitly started in isolation, request one
    unique real Hermes prompt and prove search/timeline/get-observations, canonical
    project mapping, bridge workspace and no duplicate.

## Task 6: Normalize All Provider Parsers

**Modify:**

- `scripts/capture/parsers/antigravity.py`
- `scripts/capture/parsers/codex.py`
- `scripts/capture/parsers/copilot.py`
- `scripts/capture/parsers/hermes.py`
- `scripts/capture/parsers/kilo.py`
- `scripts/capture/parsers/kimi.py`
- `scripts/capture/parsers/mimo.py`
- `scripts/capture/parsers/qwen.py`
- `scripts/capture/parsers/roo.py`
- `scripts/capture/parsers/screenpipe.py`
- `scripts/capture/parsers/swarmclaw.py`
- corresponding unit tests

**Steps:**

1. Add provider-by-provider failing tests for workspace/CWD/source hints and surface.
2. Remove parser-local project basenames and hardcoded application project labels.
3. Preserve official workspace and Git hints without classifying them in parsers.
4. Run the complete capture parser unit suite.
5. Commit:

```text
fix(capture): normalize provider project evidence
```

## Task 7: Map Claude Mem Identity into UMC Workspaces (TDD)

**Modify:**

- `core/knowledge/claude_mem_bridge.py`
- `scripts/services/claude_mem_bridge.py`
- `core/database.py`
- `core/umc_schema.sql`
- `core/umc_schema_crr.sql`
- `tests/unit/test_claude_mem_bridge.py`
- `tests/real/test_claude_mem_bridge.py`

**Steps:**

1. Write failing tests for a versioned identity envelope and legacy records.
2. Prove `workspace_id = project_id` for new records and no implicit `default`.
3. Preserve project name, provider, surface, branch, worktree and source session.
4. Add compatible project indexes/metadata migrations without rewriting history.
5. Run unit and real bridge tests against isolated databases.
6. Commit:

```text
fix(memory): map canonical projects into UMC workspaces
```

## Task 8: Add Read-Only Historical Project Audit

**Create:**

- `core/projects/audit.py`
- `core/projects/__init__.py`
- `tests/unit/test_project_audit.py`
- `tests/integration/test_project_audit_sqlite.py`

**Modify:**

- `src/hive_mind/cli.py`

**Steps:**

1. Write failing tests for the required legacy labels and classifications.
2. Implement `hive-mind projects audit` as read-only by default.
3. Report sessions, observations, vectors, Markdown, proposal and confidence.
4. Ensure the command never writes or migrates historical records.
5. Add JSON output for later readiness evidence.
6. Commit:

```text
feat(projects): audit legacy project labels safely
```

## Task 9: Enforce Project Filters in Vector Retrieval

**Modify:**

- `core/vector_backend.py`
- `core/vector_sync.py`
- `core/search.py`
- `core/retrieval/router.py`
- vector unit/real tests

**Steps:**

1. Add failing tests requiring project metadata on all new vectors.
2. Test sqlite-vec and Milvus queries for strict project isolation.
3. Make cross-project retrieval an explicit option.
4. Test backfill/audit reporting for vectors missing project ID without rewriting
   them automatically.
5. Run unit and real vector suites.
6. Commit:

```text
fix(retrieval): enforce canonical project filters
```

## Task 10: Enforce Project Identity in Graphify, Graphiti and LightRAG

**Modify:**

- `core/memory/backends/graphify.py`
- `integrations/graphiti/client.py`
- `core/lightrag_index.py`
- relevant graph unit/integration/real tests

**Steps:**

1. Write failing project-isolation tests for each graph system.
2. Add project ID to nodes, edges and source metadata.
3. Represent cross-project references explicitly.
4. Require a project namespace/filter in LightRAG normal queries.
5. Prove project A cannot retrieve project-B-only content.
6. Commit:

```text
fix(graph): isolate graph knowledge by canonical project
```

## Task 11: Group Dream Cycle by Project ID and Write Canonical Markdown

**Modify:**

- `scripts/dream/dream_cycle.py`
- `core/knowledge/intake.py`
- `core/knowledge/promotion.py`
- `core/paths.py`
- Dream/Markdown unit, integration and real tests

**Steps:**

1. Write failing tests showing two labels for one project must share one bucket.
2. Group new observations by project ID, with measured legacy fallback.
3. Route Markdown to the canonical project-ID directory.
4. Write all required provenance frontmatter and integrity hash.
5. Prove a failing project does not archive another project's observations.
6. Run a real model-backed Dream gate only after isolated unit/integration tests.
7. Commit:

```text
fix(dream): isolate knowledge processing by project id
```

## Task 12: Prove Real Project A/B Isolation

**Create/Modify:**

- `tests/real/test_project_identity_isolation.py`
- `tests/real/test_workspace_isolation_global.py`
- supporting isolated cleanup helpers

**Steps:**

1. Create two real temporary Git projects with unique canary IDs.
2. Capture distinct real events through local HTTP/Claude Mem-compatible runtime.
3. Bridge into isolated UMC workspaces.
4. Run Dream with a real configured model.
5. Prove separate Markdown, UMC rows, vectors and graphs.
6. Prove filtered and explicit cross-project query behavior.
7. Delete only rows/files carrying this run's unique IDs.
8. Commit:

```text
test(dream): validate cross-project knowledge isolation
```

## Task 13: Revalidate Every Installed Provider One at a Time

**Evidence output:**

- `reports/provider-canaries/<timestamp>-<provider>.json`

**Order:** Claude Code, Codex, Antigravity IDE, Antigravity CLI, Kimi, Qwen CLI,
Qwen Desktop, Hermes, Mimo, Kilo, then every other detected provider.

For each provider, record source change, parser output, normalized session, resolver
result, direct ingest evidence, Claude Mem search/timeline/observations, bridge
workspace and duplicate count. Do not modify native Claude capture. Keep the normal
runtime's experimental delivery flag disabled.

## Task 14: Complete Packaging and Windows Lifecycle

**Modify:**

- `pyproject.toml`
- `install.ps1`
- `npm/lib/init.js`
- `scripts/utils/recover.ps1`
- Windows install/lifecycle tests and documentation

**Steps:**

1. Add failing wheel-content tests for `core`, `scripts`, templates, integrations
   and runtime resources.
2. Make the package self-contained or explicitly implement a verified repository
   bootstrap artifact; do not leave a partial wheel presented as complete.
3. Write lifecycle contract tests before implementing repair, update, rollback,
   uninstall and preserve flags.
4. Make every operation idempotent and transactionally tied to a verified snapshot.
5. Expose equivalent npm CLI flags.
6. Test only in isolated paths first, then a disposable Windows machine.
7. Commit lifecycle changes in coherent package/installer/test commits.

## Task 15: Complete Regression, Integrity and Readiness Evidence

Run exactly the master commands, inventory every skip, then execute DB checks and
semantic metrics. Generate:

```text
reports/full-system-readiness.md
reports/full-system-readiness.json
```

Score only current real evidence. A mock or unexecuted gate receives zero. Run
`git diff --check`, verify the branch is clean, and include the required 45-item
final report.

## Task 16: Disposable Windows Installation and Root Gate

Only after clean branch, full suites, provider canaries, project identity and Dream
are green, execute the complete local-min -> local-full -> reboot -> lifecycle ->
reinstall sequence in disposable Windows. The active root remains unchanged until
that evidence is reviewed and separate authorization is given.

---

## Immediate Execution Slice

The first implementation slice is Tasks 1-5. It produces a coherent direct-ingest
baseline, canonical resolver, real Git proof and Hermes Desktop repair. Tasks 6-16
remain mandatory and are not redefined as optional follow-up work.
