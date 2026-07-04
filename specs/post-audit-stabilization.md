# Post-Audit Stabilization — Hive-Mind

## Goal

Transform the Hive-Mind project from a post-audit `PARCIAL` state to a verifiable `OK` for production use, by closing the broken write/index path (`Markdown → UMC → FTS → vector → query with citation`), restoring the RTK hook compile sanity, repairing historical `document_vectors` orphans, and tightening workspace isolation, security, hooks, and documentation. Every fix MUST be validated by a real command against a real database, a real file, a real FTS, a real vector, a real query, and a real automated test, with documentation updated to match runtime.

## Source

This spec is the normalized form of the audit report delivered on 2026-07-03. The full audit reasoning lives in the report referenced from `docs/reports/POST_AUDIT_FIX_LOG.md` (created during execution); this document is the contract, the report is the evidence.

## Branch and governance

1. The work MUST be done on branch `fix/hive-mind-post-audit-stabilization`, branched from `main` at the audit baseline.
2. A git tag `audit-baseline-2026-07-03` MUST exist at the commit that represents the pre-fix state.
3. A pre-change snapshot directory `backups/audit-2026-07-03/` MUST contain copies of: `cerebro/`, `hive_mind.db`, `components.lock.json`, `.env.example`, `pyproject.toml`, `requirements.txt`, `scripts/`, `core/`, `plugins/`, `integrations/`, `tests/`.
4. Two tracking files MUST be created and kept current:
   - `docs/plans/POST_AUDIT_STABILIZATION_PLAN.md` — the plan reference
   - `docs/reports/POST_AUDIT_FIX_LOG.md` — per-delivery log with date, commit, problem, root cause, fix, tests run, evidence, status

## Requirements

Each item is a single observable behavior. MUST = blocking; SHOULD = blocking for `OK`; MAY = follow-up.

### R0 — Baseline (Phase 0)

- **R0.1** The system MUST run `bash tests/smoke/test_smoke.sh` and the command MUST exit 0.
- **R0.2** The system MUST run `bash tests/run_real_knowledge.sh` and the command MUST exit 0.
- **R0.3** The system MUST run `python -m compileall -q core scripts plugins integrations` and the command MUST exit non-zero with the error reproducible against `integrations/rtk/hooks/hermes/rtk-rewrite/__init__.py` until Phase 1 closes it.
- **R0.4** A report at `docs/reports/BASELINE_POST_AUDIT_2026-07-03.md` MUST exist and MUST contain: smoke exit code, real-knowledge exit code, compileall stderr excerpt, and the list of detected failures.

### R1 — RTK hook (Phase 1)

- **R1.1** `python -m compileall -q core scripts plugins integrations` MUST exit 0.
- **R1.2** A test file `tests/unit/test_rtk_hooks_compile.py` MUST exist and MUST fail before the fix and pass after the fix. Its body MUST use `py_compile.compile(..., doraise=True)` over every `*.py` under `integrations/rtk/hooks`.
- **R1.3** The string `rtk` MUST NOT appear in `core/sinapse_query*`, `core/context_fusion*`, `core/retrieval_router*`, or in any `read_backends` configuration list. RTK is shell optimization only.
- **R1.4** The runtime RTK version reported by `rtk --version` MUST equal the version pinned in `components.lock.json`. If the lock is the canonical source, runtime MUST be updated; if the runtime is the canonical source, the lock MUST be updated. The change MUST be reflected in the `FIX_LOG`.
- **R1.5** `./scripts/services/start-rtk.sh --only codex --dry-run` MUST exit 0 and its stdout MUST NOT report "No hook installed" once Phase 1 is complete.

### R2 — Write path Markdown → UMC → FTS → vector → query (Phase 2)

- **R2.1** A new module `core/indexing/write_indexer.py` MUST exist and expose a class `WriteIndexer` with method `index_markdown_file(path: str, workspace_id: str = "default", reason: str = "write_path") -> dict` returning a dict with the boolean keys `markdown_written`, `neuron_indexed`, `fts_indexed`, `vector_indexed`, `query_recoverable`, and the string keys `source_file`, `neuron_id`.
- **R2.2** `WriteIndexer.index_markdown_file` MUST, in order: (a) read the file; (b) parse YAML frontmatter and reject if missing or invalid; (c) compute content hash; (d) upsert a row in `neurons`; (e) update `search_fts`; (f) compute and write the vector in `search_vec`; (g) optionally update `synapses`; (h) return the structured dict.
- **R2.3** `scripts/services/sinapse-write.py` `decision` and `learning` subcommands MUST call `WriteIndexer.index_markdown_file` synchronously and MUST propagate the returned dict to stdout as JSON.
- **R2.4** A test file `tests/e2e/test_decision_write_index_query.py` MUST exist. It MUST run, in order: (1) call the decision subcommand; (2) assert the file exists and its frontmatter is valid; (3) assert a `neurons` row with the file's `source_file` exists; (4) assert `search_fts` has a row for the neuron; (5) assert `search_vec` has a row for the neuron with non-zero vector; (6) call `sinapse_query` for the decision title; (7) assert at least one citation points to the test's `source_file`. The test MUST clean up its artifacts on success or be marked as an audit fixture.
- **R2.5** The watcher process (`scripts/services/start-watcher.sh`) MUST continue to exist but MUST NOT be the only path that updates `neurons`/`search_fts`/`search_vec`. Synchronous indexing in R2.3 is the primary path; the watcher is fallback/reindex.

### R3 — Vectorization post-Dream Cycle (Phase 3)

- **R3.1** A table named `vector_jobs` MUST exist in `hive_mind.db` with columns `id`, `entity_type`, `entity_id`, `collection`, `workspace_id`, `status`, `attempts`, `error`, `created_at`, `updated_at`. The schema MAY reuse an existing equivalent table if its contract is identical and documented.
- **R3.2** The vectorization worker MUST cover all seven canonical collections: `memory_vectors`, `observation_vectors`, `document_vectors`, `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors`.
- **R3.3** Whenever the Promotion Layer (`core/knowledge/promotion.py`) creates or updates a `neurons` row, it MUST enqueue a `vector_jobs` row with `entity_type='neuron'`, `entity_id=<neuron_id>`, `collection='memory_vectors'`, `status='pending'`. The actual vector write MAY be async, but the enqueue MUST be synchronous and MUST be visible immediately after the write.
- **R3.4** A test file `tests/real/test_dream_cycle_vectorization.py` MUST exist. It MUST: (1) insert a controlled observation with `archived=0`; (2) run `scripts/dream/dream_cycle.py --once --real`; (3) assert a `neurons` row with `source_file` pointing to a created `neuronio-*.md` exists; (4) assert `search_fts` has a row for that neuron; (5) assert `search_vec` has a non-zero row for that neuron; (6) assert `sinapse_query` for the observation's terms returns a citation to the created Markdown.
- **R3.5** A K8 gate MUST exist. The production-readiness gate MUST fail if `neurons_vectorized_pct < 99` OR `orphan_vectors > 0` OR `vectors_model_mismatch > 0`.

### R4 — DocumentPipeline historical consistency (Phase 4)

- **R4.1** A script `scripts/health/audit_document_pipeline_consistency.py` MUST exist. It MUST print, for the live database: count of `document_vectors` without a parent, count without a chunk, count of chunks without a parent, count of parents without chunks, count of chunks without vectors, count of vectors missing required metadata, count of duplicate hashes, count of rows missing `source_uri`, count of rows missing `workspace_id`.
- **R4.2** A test file `tests/real/test_document_vector_parent_consistency.py` MUST exist. It MUST assert: every `document_vectors` row has a valid `document_chunks` reference; every `document_chunks` row has a valid `document_memories` reference; every document query response includes `source_uri`, `offset_start`, `offset_end`, and a `parent` reference.
- **R4.3** A script `scripts/maintenance/backfill_document_parents_chunks.py` MUST exist. It MUST support `--dry-run` and `--apply` modes. It MUST require a backup to exist before `--apply` is accepted. It MUST NOT overwrite an existing parent. It MUST require `workspace_id` on every produced row. It MUST print a before/after report.
- **R4.4** Strategy preference: backfill (using existing `source_uri` and hash) when both are present; rebuild (drop orphans, re-ingest from source) when metadata is incomplete. The chosen strategy MUST be recorded in the `FIX_LOG` per run.

### R5 — Hooks, agents, MCP contract (Phase 5)

- **R5.1** The MCP server MUST expose exactly the toolset documented in `docs/03-mcp-tools.md`. If the current runtime exposes 16 tools (including `sinapse_promote_knowledge`), the doc MUST be updated to 16 and the change recorded in the `FIX_LOG`. If the extra tool is removed, the runtime MUST match the 15 documented tools.
- **R5.2** Hooks for Claude, Codex, and Hermes MUST be materialized at their documented paths under `cerebro/tronco/infra/agentes/<agent>/`. If the canonical paths are different, the docs MUST be updated to match. Either the files or the docs MUST be corrected, never both left inconsistent.
- **R5.3** A test file `tests/integration/test_agent_hooks_materialized.py` MUST exist. It MUST assert: every documented hook file exists; every hook file's referenced script path exists; every referenced script is executable or importable; calling each script with a no-op input does not error.
- **R5.4** `./scripts/setup/register-mcp.sh --check` MUST exit 0 and report the same tool count that `docs/03-mcp-tools.md` documents.

### R6 — Claude Mem HTTP search (Phase 6)

- **R6.1** A test file `tests/real/test_claude_mem_search_endpoint.py` MUST exist. It MUST: (1) pick a term that the local SQLite FTS finds in `~/.claude-mem/claude-mem.db`; (2) call `http://127.0.0.1:37700/api/search?query=<term>`; (3) assert the response contains at least one ID that the FTS query also returned. If the endpoint cannot be made consistent, the test MUST fail.
- **R6.2** The Claude Mem worker MUST either (a) make `/api/search` return results consistent with the local FTS for the same terms, or (b) explicitly document the SQL bridge as the canonical read path and remove or relabel the HTTP endpoint so it does not appear functional. The choice MUST be recorded in the `FIX_LOG`.
- **R6.3** An HTTP failure on `/api/search` MUST NOT be masked as success. Tests that call it MUST assert on the response shape and fail if a fallback returns 200 with empty results without surfacing the failure.

### R7 — Security and redactor (Phase 7)

- **R7.1** A test file `tests/unit/test_redactor_aws_tokens.py` MUST exist. It MUST assert that `core.redactor.redact_for_export` returns a redacted value for each of: `AKIA1234567890ABCDEF`, `ASIA1234567890ABCDEF`, `aws_access_key_id=AKIA...`, `aws_secret_access_key=...`, `Bearer eyJ...`, `sk-proj-...`, `api_key=abcdef0123456789`.
- **R7.2** The order of redactor rules MUST place AWS-key matchers before generic phone or generic identifier matchers. The test in R7.1 MUST fail if the order causes partial masking.
- **R7.3** All existing tests in `tests/unit/test_redactor.py` MUST continue to pass after the order change.

### R8 — Workspace isolation global (Phase 8)

- **R8.1** A test file `tests/real/test_workspace_isolation_global.py` MUST exist. It MUST, for each of `neurons`, `observations`, `synapses`, `document_chunks`, `document_vectors`, `vector_metadata`, `query_route_log`: create data in workspace A, create data in workspace B, query as workspace A, assert B's data is absent, query as workspace B, assert A's data is absent.
- **R8.2** When `VECTOR_BACKEND=milvus`, the test MUST also assert that Milvus collections or partitions are filtered by `workspace_id`. If Milvus is not the active backend in the test environment, the test MUST skip that branch with a recorded reason.
- **R8.3** The `query_route_log` table MUST NOT contain raw query text that crosses workspaces. If raw text is stored, it MUST be scoped by `workspace_id` and the test MUST verify that.

### R9 — Graphify, watcher, version (Phase 9)

- **R9.1** The Graphify runtime version reported by `graphify --version` MUST equal the version pinned in `components.lock.json` and in any skill manifest. The chosen canonical version MUST be recorded in the `FIX_LOG`.
- **R9.2** Responsibility split MUST be documented in `docs/04-infrastructure.md` or equivalent: Graphify produces the structural graph; `WriteIndexer` (R2) is responsible for `UMC`/`FTS`/`vector`; the watcher triggers async reindex. The watcher MUST NOT be the only mechanism that updates `neurons`/`search_fts`/`search_vec` for the synchronous write path.
- **R9.3** A test file `tests/integration/test_watcher_graphify_indexing.py` MUST exist. It MUST assert: creating a Markdown file in the watched area triggers a `graph.json` update within the configured debounce; if the watcher also claims responsibility for `UMC`, the `neurons` row appears; otherwise the test MUST verify that `WriteIndexer` is the responsible path and the watcher only updates `graph.json`.

### R10 — K5 cadence (Phase 10)

- **R10.1** Running the following six commands in order, each with `--real --workspace audit-ws`, MUST exit 0:
  - `scripts/dream/session_consolidator.py`
  - `scripts/dream/daily_writer.py`
  - `scripts/dream/weekly_synthesizer.py`
  - `scripts/dream/monthly_synthesizer.py`
  - `scripts/dream/yearly_synthesizer.py`
  - `scripts/dream/pattern_distiller.py`
- **R10.2** After R10.1, the following MUST exist and be non-empty: `cerebelo/sessoes/`, `cerebelo/diario/`, `cerebelo/semanal/`, `cerebelo/mensal/`, `cerebelo/anual/`, `cerebelo/padroes/Patterns.md`. `summary_vectors` MUST have new rows.
- **R10.3** A query via `sinapse_query` for terms appearing in a generated synthesis MUST return a citation pointing to the corresponding synthesis file.

### R11 — Syncthing, P2P, disaster recovery (Phase 11)

- **R11.1** Either Syncthing is installed and `syncthing --version` exits 0, OR the project README MUST state that Syncthing is an optional, out-of-scope component for this build. The decision MUST be recorded in the `FIX_LOG`.
- **R11.2** `./scripts/utils/recover.sh --target /tmp/hive-mind-recovery-test` MUST be executed against a copy of `cerebro/` and `hive_mind.db`. After execution, a `sinapse_query` against the recovered copy MUST return results with citations, and `search_vec`, `search_fts`, and the graph MUST be populated. The test MUST NOT touch the live database.
- **R11.3** A P2P conflict test MAY be run if Syncthing is available: two nodes modify the same file, the system MUST detect the conflict and route it to an `ambiguities` folder or a documented synthesis flow. Silent overwrite MUST NOT occur.

### R12 — Documentation finalization (Phase 12)

- **R12.1** The following files MUST be updated to match runtime, with the change recorded in the `FIX_LOG`: `README.md`, `AGENTS.md`, `docs/01-architecture.md`, `docs/03-mcp-tools.md` (or its replacement), `docs/04-infrastructure.md`, `docs/05-blueprints.md`, `docs/11-knowledge-promotion-architecture.md`, `docs/12-knowledge-implementation-plan.md`.
- **R12.2** Every command documented in the above files MUST exist in the repository. Every path documented MUST exist on disk or be explicitly marked as future.
- **R12.3** The list of documented MCP tools MUST equal the runtime tool count (see R5.1). The RTK role (shell optimization, not a memory backend) MUST be stated explicitly in `docs/04-infrastructure.md`.
- **R12.4** `docs/reports/POST_AUDIT_FIX_LOG.md` MUST list, for every fix delivered, the date, commit SHA, problem ID, root cause, fix summary, tests run, evidence path, and final status.

## Sprints

The Requirements above are organized into four sprints, each with an exit gate that MUST pass before the next sprint begins.

### Sprint 1 — Critical stabilization (R0, R1, R2, R3)

Exit gate (all MUST pass):

```bash
.venv/bin/python -m compileall -q core scripts plugins integrations
.venv/bin/python -m pytest tests/unit/test_rtk_hooks_compile.py -q
.venv/bin/python -m pytest tests/e2e/test_decision_write_index_query.py -q
.venv/bin/python -m pytest tests/real/test_dream_cycle_vectorization.py -q
```

### Sprint 2 — Document and workspace consistency (R4, R7, R8, R6)

Exit gate:

```bash
.venv/bin/python scripts/health/audit_document_pipeline_consistency.py
.venv/bin/python -m pytest tests/real/test_document_vector_parent_consistency.py -q
.venv/bin/python -m pytest tests/real/test_workspace_isolation_global.py -q
.venv/bin/python -m pytest tests/unit/test_redactor_aws_tokens.py tests/unit/test_redactor.py -q
.venv/bin/python -m pytest tests/real/test_claude_mem_search_endpoint.py -q
```

### Sprint 3 — Agents, hooks, Graphify (R5, R9)

Exit gate:

```bash
./scripts/setup/register-mcp.sh --check
.venv/bin/python -m pytest tests/integration/test_agent_hooks_materialized.py -q
.venv/bin/python -m pytest tests/integration/test_watcher_graphify_indexing.py -q
```

### Sprint 4 — Cadence, P2P, recovery, production gate (R10, R11, R12)

Exit gate:

```bash
.venv/bin/python scripts/dream/session_consolidator.py --real --workspace audit-ws
.venv/bin/python scripts/dream/daily_writer.py --real --workspace audit-ws
.venv/bin/python scripts/dream/weekly_synthesizer.py --real --workspace audit-ws
.venv/bin/python scripts/dream/monthly_synthesizer.py --real --workspace audit-ws
.venv/bin/python scripts/dream/yearly_synthesizer.py --real --workspace audit-ws
.venv/bin/python scripts/dream/pattern_distiller.py --real --workspace audit-ws
./scripts/utils/recover.sh --target /tmp/hive-mind-recovery-test
./install.sh --with-tests
./tests/run_all.sh
bash tests/run_real_knowledge.sh
.venv/bin/python -m compileall -q core scripts plugins integrations
```

## Out of Scope

The following are explicitly NOT part of this build, even if they appear related:

- **New features or interfaces.** No new CLI commands, no new API routes, no new UI surfaces. This is a stabilization, not a feature release.
- **LLM model upgrades or migrations.** Snowflake Arctic embedding model, Ollama model versions, Milvus versions, RAGFlow versions are taken as-is.
- **Performance optimization beyond the K8 gate.** Sub-100ms retrieval, batched ingest, GPU acceleration are follow-ups.
- **Visual capture (`sinapse_capture_screen`)** in production. Multimodal visual real capture is a separate workstream.
- **Re-architecting the brain layout.** Anatomical cortex regions (`cerebro/cortex/...`) keep their current structure.
- **Multi-tenant billing, auth providers, SSO.** Bearer token only.
- **Replacing the VectorBackend.** The contract is fixed; only its implementation is repaired.
- **Rerank real execution** with LlamaIndex. Code references may stay; runtime exercise is a follow-up.

## Edge Cases & Error Handling

Each entry names the input/state, then the expected response.

- **Decision content is empty** (`sinapse_save_decision` with `content=""`) → MUST return error `{error: "content_empty"}` and MUST NOT create a Markdown file.
- **Decision frontmatter is invalid YAML** → MUST return error `{error: "frontmatter_invalid"}` and MUST NOT write to `neurons`.
- **Markdown file is deleted while in `neurons`** → the row stays, the FTS row is removed, the vector row is removed. `WriteIndexer` on a re-create with the same `source_file` MUST treat it as an update, not a duplicate.
- **Vector backend unreachable during `WriteIndexer`** → MUST return `vector_indexed=false` and `query_recoverable=false` in the dict, MUST still write `neurons` and `search_fts`, MUST log the error with `entity_id` and `collection`. The caller MUST see the partial-success state, not silent success.
- **Dream Cycle encounters an observation with no `content`** → MUST skip with a logged warning, MUST NOT enqueue a `vector_jobs` row for it.
- **DocumentPipeline backfill encounters a `document_vectors` row with a `source_uri` that no longer exists on disk** → MUST mark the row as `orphan` in metadata, MUST NOT delete it without explicit `--apply` and backup.
- **Two writers race on the same `source_file`** → second writer MUST see the first's hash in `neurons` and MUST NOT overwrite blindly; the dict MUST include a `conflict_detected=true` flag.
- **Workspace A queries while workspace B is mid-write** → workspace A MUST NOT see workspace B's partial writes; isolation is per-transaction.
- **Syncthing conflict** (only if Syncthing is in scope per R11.1) → file MUST be moved to `ambiguities/`, original MUST NOT be overwritten silently.
- **Claude Mem HTTP `/api/search` returns 5xx** → callers MUST surface the error; fallback to SQL bridge MUST be opt-in and explicit, never silent.
- **Compile fails for a non-RTK file** (e.g., a new syntax error introduced by a fix) → `compileall` MUST report it; the fix MUST land before its sprint gate runs.

## Production Readiness Gate (Definition of Done)

The project is `OK` (vs. `PARCIAL`) only when ALL of the following are true, each verifiable by a command in the same environment used for the audit:

| # | Check | Verifier |
|---|-------|----------|
| D1 | `python -m compileall -q core scripts plugins integrations` exits 0 | shell exit code |
| D2 | `bash tests/smoke/test_smoke.sh` exits 0 | shell exit code |
| D3 | `pytest tests/unit/ -q` exits 0 | shell exit code |
| D4 | `pytest tests/integration/ -q` exits 0 | shell exit code |
| D5 | `pytest tests/e2e/ -q` exits 0 | shell exit code |
| D6 | `bash tests/run_real_knowledge.sh` exits 0 | shell exit code |
| D7 | `./install.sh --with-tests` exits 0 | shell exit code |
| D8 | Decision write path closes (R2.4 test passes) | pytest |
| D9 | Dream Cycle vectorization closes (R3.4 test passes) | pytest |
| D10 | DocumentPipeline consistency (R4.1 + R4.2) | script + pytest |
| D11 | Workspace isolation global (R8.1) | pytest |
| D12 | RTK hooks compile (R1.2) | pytest |
| D13 | MCP tools count matches docs (R5.4) | shell + manual check |
| D14 | Claude/Codex/Hermes hooks materialized (R5.3) | pytest |
| D15 | Redactor covers AWS/OpenAI/Bearer/API key (R7.1) | pytest |
| D16 | Graphify version aligned (R9.1) | shell + manifest |
| D17 | Disaster recovery tested in `/tmp` (R11.2) | shell |
| D18 | Documentation matches runtime (R12.1, R12.3) | manual review against the `FIX_LOG` |

K8 health gate (must hold continuously after Sprint 1):

- `neurons_vectorized_pct >= 99`
- `orphan_vectors == 0`
- `vectors_model_mismatch == 0`
- `observations_linked_pct` is non-decreasing across consecutive Dream Cycle runs
- every `document_chunks` row has a non-null `parent_id`
- every document answer from `RetrievalRouter` includes a citation with `source_uri`

## Open Questions for Reviewer

These were not resolved in the source material; `/build` should pause and ask before assuming:

- **Q1.** ~~Syncthing is described in R11.1 as either installed OR explicitly optional.~~ **RESOLVED 2026-07-04: installed.** No interactive `sudo` was available in the stabilization environment, so Syncthing was installed user-space (the official static binary at `~/.local/bin/syncthing`, no root required) rather than via `apt`. `syncthing --version` → v2.1.1. `docs/README.md`'s Syncthing status note updated accordingly.
- **Q2.** R3.2 lists seven canonical collections. The audit evidence covers `memory_vectors`, `observation_vectors`, `document_vectors`, `visual_vectors`. The other three (`code_vectors`, `graph_vectors`, `summary_vectors`) were not directly tested. Should the worker cover all seven, or only the four the audit confirmed?
- **Q3.** R6 gives two options for Claude Mem: fix `/api/search` or remove it. The audit suggested fixing it. The user did not pick. Is fixing the HTTP endpoint in scope, or is the SQL bridge the canonical path?
- **Q4.** R12 says MCP tools count MUST match docs. The audit found 16 real vs 15 documented. The user did not pick between "officialize the 16th" and "remove the 16th." Which way?
- **Q5.** R10.2 expects `summary_vectors` to grow with each cadence run. The audit did not confirm that path. If it does not exist, is creating it in scope for Sprint 4, or should it be added as a follow-up?
- **Q6.** R3.5's K8 gate mentions `observations_linked_pct` increasing. The audit did not define a baseline. What is the starting value, and what counts as "increasing"?
- **Q7.** ~~R11.3 P2P conflict test is `MAY`.~~ **RESOLVED 2026-07-04: exercised.** `tests/real/test_p2p_conflict.py` drives the real conflict router (`scripts/health/audit_memory.py` + `core.database.register_ambiguity`, no mocks) against an isolated SQLite file, reproducing the exact `.sync-conflict-<date>-<time>-<device>.md` filename Syncthing generates on a real collision. 2/2 passing: conflict registered in `ambiguities`, file moved to `cortex/insula/conflitos/`, canonical neuron never silently overwritten. Running two live Syncthing daemons end-to-end remains a manual exercise (`docs/07-p2p-sync-setup.md`), not part of the automated suite.

These questions MUST be answered before the corresponding sprint begins. The `FIX_LOG` MUST record the answer and the decision rationale.
