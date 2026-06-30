# Changelog

## v3.7.1 — Role Config Hotfix

Release date: 2026-06-30

### Fixed

- Keeps `graphiti` and `lightrag` roles on local Ollama instead of
  inheriting the Dreamer provider. Without this shortcut, when the
  Dreamer is configured as `antigravity` or any Gemini-tier provider,
  `get_role_config("graphiti")` returned the Dreamer config and the
  Graphiti / LightRAG workers would either burn Antigravity quota or
  fail with the wrong model.
- Honors `HIVE_GRAPHITI_MODEL` / `HIVE_LIGHTRAG_MODEL` env vars; falls
  back to `qwen2.5:3b` when unset. Provider is forced to `ollama` and
  fallback chain is `None` for both roles — they are local-only by
  design.

### Validation

- `.venv/bin/python -m pytest tests/unit/test_role_config.py -v`:
  9 passed (incl. the new
  `test_local_extraction_roles_should_not_inherit_dreamer`).
- `.venv/bin/python -m pytest tests/unit -q`: 497 passed, 3 skipped
  (no regressions vs v3.7.0).
- Runtime probe with `HIVE_DREAMER_PROVIDER=antigravity` and
  `HIVE_GRAPHITI_MODEL=qwen2.5:7b`:
  - `get_role_config("graphiti")` -> `provider=ollama, model=qwen2.5:7b`
  - `get_role_config("lightrag")` -> `provider=ollama, model=qwen2.5:3b`
  - `get_role_config("dreamer")`  -> `provider=antigravity, model=gemini-3.5-flash`
  (and other roles still inherit Dreamer as expected).

## v3.7.0 — K9 Test Harness Real Sem Mocks + K10 Installer E Maquina Zerada

Release date: 2026-06-30

### Added

K9 — Test Harness Real Sem Mocks (docs/12 §K9):

- Adds `milvus_or_skip`, `milvus_backend` (com teardown de colecoes) and
  `claude_mem_or_skip` (SQLite temporario com schema real) fixtures in
  `tests/real/conftest.py` so the real suite no longer relies on a
  pre-running Milvus or claude-mem worker.
- Adds `scripts/setup/audit_test_layering.py` to enforce the real × unit
  × integration layering (no MagicMock in `tests/real/`, no `real` marker
  in `tests/unit/`/`tests/integration/`). Writes
  `docs/reports/k9/test-layering-audit.md` with the offender
  list and counts.
- Adds `tests/real/test_acceptance_split.py` to defend the boundary at
  pytest-collection time — any regression that lets a real test mock
  something, or a unit test mark itself `real`, fails the run.
- Adds `tests/real/test_golden_retrieval.py` with the precision/recall@k
  gate from `docs/11` §17.3: intent classification >= 75% and
  precision@k/recall@k >= 0.5 over `tests/real/golden_retrieval.jsonl`
  (skips cleanly when the seed corpus does not match — does not silently
  pass).
- Marks `tests/real/test_knowledge_health.py` with `@pytest.mark.real`
  (was missing) so it counts toward the knowledge-architecture
  acceptance.
- Expands `tests/run_real_knowledge.sh` with `--report=<path>`: runs
  pytest with junit-xml and writes a Markdown summary next to the run
  log. Used by the new installer flow.

K10 — Installer E Maquina Zerada (docs/12 §K10):

- Adds `--profile=local-min|local-full` and `--with-real-tests` to
  `install.sh`. `local-min` keeps claude-mem + graphify-watch only;
  `local-full` brings up Milvus + RAGFlow via `docker compose up` and
  warns if FalkorDB is offline. Default profile is `local-min` to
  preserve the original behavior on small machines.
- Adds a K10 block to `install.sh` that re-applies
  `core.database.ensure_migrations` (idempotent), runs
  `scripts/setup/register-mcp.sh` after the profile, and (with
  `--with-real-tests`) chains `./tests/run_real_knowledge.sh --report=...`
  into the install flow.
- Adds a final install report at `logs/install-report.md` with vault
  path, ports (claude-mem 37700, sqlite-vec 37701, api 37702, mcp-http
  37703), installed Ollama models, and the full
  `sinapse-write.py health` output. Mirrors the same summary on stdout
  so the operator sees it without opening the file.
- Hardens `install.sh` argument parsing: rejects unknown flags and
  invalid `--profile` values, keeps the old flags backward compatible
  (`--force`, `--with-tests`, `--skip-agent=`, `--provider=`,
  `--model=`, `--non-interactive`).

### Validation

- `.venv/bin/python -m pytest tests/real -m real -q`: 37 passed, 8 skipped
  in 38.88s. Skips are all `requires_service:milvus` (Milvus not started
  in this profile) and are intentional.
- `./tests/run_real_knowledge.sh --report=cerebro/cortex/insula/saude/k9-real-suite.md`:
  45 collected, 37 passed, 8 skipped, 0 failed, 0 errors. Report written.
- `.venv/bin/python scripts/setup/audit_test_layering.py`: 17/17 tests
  in `tests/real/` carry the `real` marker; 0 use mocks; 0 unit /
  integration tests claim `real`. Audit log written to
  `cerebro/cortex/insula/saude/test-layering-audit.md`.
- `.venv/bin/python -m pytest tests/real/test_acceptance_split.py -q`:
  4 passed (boundary guard).
- `.venv/bin/python -m pytest tests/real/test_golden_retrieval.py -q`:
  2 passed (intent gate + precision/recall@k gate).
- `.venv/bin/python scripts/services/sinapse-write.py health`:
  `healthy=true`, 7/7 backends up (umc, neural_memory, sqlite_vec,
  claude_mem, graphify, graphiti, filesystem), 1020 graph nodes,
  5706 neurons, 97.76% vectorized.
- `bash -n install.sh` and `bash -n tests/run_real_knowledge.sh`: no
  syntax errors after the K10 block insertion.

## v3.6.0 — K8 Knowledge Health

Release date: 2026-06-30

### Added

- Adds `scripts/health/knowledge_health.py` to measure knowledge coverage
  without replacing the existing insula health dashboard.
- Measures `neurons_vectorized_pct`, `observations_linked_pct`,
  `discoveries_pending`, `summary_vectors_total`, `orphan_vectors`,
  `milvus_sync_lag`, `query_route_distribution` and per-collection
  `*_vectorized_pct`.
- Adds `knowledge_tombstones` and `query_route_log` to the UMC schema and
  CRR-safe schema.
- Adds best-effort route telemetry in `RetrievalRouter` so
  `query_route_distribution` is based on stored route paths, not guesses.
- Keeps route telemetry fail-open/fail-fast under SQLite lock, preventing
  `sinapse-write.py query` from timing out while preserving K8 route logs.
- Adds intentional forgetting for orphan vectors: prune local sqlite-vec rows,
  clean metadata and write auditable tombstones with reason `orphan_vector`.
- Exposes K8 coverage in `sinapse_health` under `knowledge_health` using a
  quick/read-only path; the CLI and REST endpoint keep the complete gate.
- Adds authenticated REST endpoint `GET /api/v1/knowledge/health` with
  read-only default and `prune=true` maintenance mode.
- Writes Markdown reports to
  `cerebro/cortex/insula/saude/knowledge-health-YYYY-MM-DD.md`.
- Adds real K8 coverage in `tests/real/test_knowledge_health.py`.

### Validation

- `.venv/bin/python scripts/health/knowledge_health.py --fail-closed --json`:
  exit 0, `failures=[]`, `orphan_vectors=0`.
- `.venv/bin/python -m pytest tests/real/test_knowledge_health.py -q`:
  2 passed.
- `.venv/bin/python -m pytest tests/unit/test_sinapse_write_cli.py::TestSinapseWriteCLI::test_query_command tests/unit/test_sinapse_mcp.py tests/integration/test_sinapse_api.py tests/real/test_knowledge_health.py -q`:
  21 passed, 1 skipped.
- `./tests/run_all.sh`: Smoke 19 passed; Unit 497 passed / 3 skipped;
  Integration 111 passed / 2 skipped; E2E 22 passed.

## v3.5.0 — K7 RetrievalRouter

Release date: 2026-06-30

### Added

- Adds `core/retrieval/router.py` with explicit query intents:
  `recent_activity`, `decision`, `learning`, `document`, `code`, `causal`,
  `multi_hop`, `visual`, `self_state`, `operational`, `sector` and `hybrid`.
- Returns an auditable retrieval envelope with `answer_context`, `citations`,
  `retrieval_path`, `confidence` and `missing_context`.
- Routes recent activity through claude-mem temporal search/hydration, documents
  through `document_vectors`, memory questions through `memory_vectors`, code
  through `code_vectors` + Graphify, causal questions through Graphiti +
  `graph_vectors`, and multi-hop questions through LightRAG.
- Integrates the router into MCP `sinapse_query`, REST `/api/v1/query` and
  `scripts/services/sinapse-write.py query` while preserving legacy
  Context-Fusion fields for existing clients.
- Adds `core.search.route_retrieval()` as the internal search-layer adapter for
  callers that need the K7 envelope without going through MCP/REST.
- Adds optional `integrations/llama_index/` reranker adapter, disabled by
  default and fail-open.
- Adds `tests/real/golden_retrieval.jsonl` for intent accuracy regression.

### Validation

- `.venv/bin/python -m pytest tests/real/test_retrieval_router_real.py -q`:
  3 passed.
- `.venv/bin/python -m pytest tests/unit/test_sinapse_mcp.py tests/unit/test_sinapse_write_cli.py tests/integration/test_sinapse_api.py tests/real/test_retrieval_router_real.py -q`:
  29 passed, 1 skipped.
- `python3 scripts/services/sinapse-write.py query "o que foi decidido sobre embeddings?"`:
  exit 0 and returned K7 fields (`intent`, `retrieval_path`, `citations`,
  `confidence`, `missing_context`).
- `./tests/run_all.sh`:
  Smoke 19 passed; Unit 497 passed / 3 skipped; Integration 109 passed /
  2 skipped; E2E 22 passed.

## v3.4.0 — K6 DocumentPipeline With Parent Context

Release date: 2026-06-30

### Added

- Adds `core/document_pipeline.py` as the canonical K6 document ingestion
  pipeline with parent records, structural chunks, offsets, hashes and
  citation return.
- Adds Markdown section chunking, plain text ingestion, real PDF parsing via
  `pypdf`/`PyMuPDF`, and DOCX parsing via `python-docx`.
- Adds `document_chunks` to the UMC schema and CRR-safe schema.
- Indexes document chunks into `document_vectors` through `SQLiteVecBackend`
  with canonical vector metadata.
- Adds optional RAGFlow adapter health integration while keeping UMC as the
  source of truth.
- Connects `scripts/knowledge/document_ingest.py` to the K6 pipeline for real
  PDF/DOCX ingestion while preserving legacy observation records.
- Adds real K6 coverage for Markdown, PDF and the legacy ingest bridge.

### Validation

- `.venv/bin/python -m pytest tests/real/test_document_pipeline_markdown.py tests/real/test_document_pipeline_pdf.py tests/real/test_document_ingest_pipeline.py -q`:
  3 passed.
- `.venv/bin/python -m pytest tests/unit/test_document_ingest.py -q`:
  8 passed.
- `./tests/run_all.sh`: Smoke 19 passed; Unit 497 passed / 3 skipped;
  Integration 109 passed / 2 skipped; E2E 22 passed.

## v3.3.0 — K5 Hierarchical Cadence

Release date: 2026-06-29

### Added

- Adds K5 monthly and yearly cadence writers:
  `scripts/dream/monthly_synthesizer.py` and
  `scripts/dream/yearly_synthesizer.py`.
- Adds structured Pydantic contracts for higher cadence synthesis:
  `MonthlySummaryModel` and `YearlySummaryModel`.
- Writes monthly summaries to `MONTHLY_ROOT` and yearly summaries to
  `YEARLY_ROOT` using the canonical paths in `core/paths.py`.
- Indexes session, daily, weekly, monthly and yearly cadence outputs into
  `summary_vectors` through a new `index_summary_file_to_sqlite()` helper.
- Extends `summary_vectors` backfill to include `cerebro/cerebelo/anual`.
- Adds real K5 cadence coverage in `tests/real/test_cadence_real.py`.

### Validation

- `HIVE_SESSION_SUMMARIZER_PROVIDER=ollama HIVE_SESSION_SUMMARIZER_MODEL=qwen2.5:3b .venv/bin/python scripts/dream/session_consolidator.py --real`:
  exit 0, session summary indexed in `summary_vectors`.
- `.venv/bin/python scripts/dream/monthly_synthesizer.py --month "$(date +%Y-%m)" --real`:
  exit 0, wrote `cerebro/cerebelo/mensal/2026-06.md` and indexed it.
- `.venv/bin/python scripts/dream/yearly_synthesizer.py --year "$(date +%Y)" --real`:
  exit 0, wrote `cerebro/cerebelo/anual/2026.md` and indexed it.
- `.venv/bin/python -m pytest tests/real/test_cadence_real.py -q`:
  1 passed.
- Focused cadence/vector regression:
  `tests/unit/test_session_cadence.py tests/real/test_vector_auxiliary_collections.py`:
  15 passed, 1 skipped.
- `./tests/run_all.sh`: Smoke 19 passed; Unit 496 passed / 3 skipped;
  Integration 109 passed / 2 skipped; E2E 22 passed.

## v3.2.1 — Vision Setup-Brain Validation Fix

Release date: 2026-06-29

### Fixed

- Fixes the real vision integration test to respect the active `setup-brain`
  configuration (`HIVE_VISION_*`) instead of forcing `ollama-cloud/gemma3:4b`.
  On this runtime the active path is local Ollama `llava:7b` with local fallback
  `qwen3.5:9b`.
- Removes the false external-billing assumption from the K4 validation notes:
  the vision path is local and must pass locally when the configured Ollama
  model is installed.

### Validation

- `HIVE_RUN_INTEGRATION=1 .venv/bin/python -m pytest tests/integration/vision/test_vision_real.py -q -rs`:
  3 passed.

## v3.2.0 — Claude-Mem Promotion Bridge

Release date: 2026-06-29

### Added

- Adds the K4 Claude-Mem Promotion Bridge in `core/knowledge/claude_mem_bridge.py`,
  importing Claude-Mem observations, discoveries and session summaries into UMC
  observations with stable `source_id` metadata.
- Exposes Claude-Mem import filters through CLI/MCP promotion:
  `sinapse-write.py promotion --import-claude-mem --source-id ...` and
  `sinapse_promote_knowledge(import_claude_mem=true, ...)`.
- Adds `operational_fact` as a canonical promotion type for completed session
  work from Claude-Mem summaries.

### Fixed

- Makes the Antigravity provider use the native `agy` auth token
  (`~/.gemini/antigravity-cli/antigravity-oauth-token`) as the primary
  configured-state check, instead of requiring Gemini CLI OAuth.
- Carries the native `agy` token into `AGY_USE_ISOLATED_HOME=1` diagnostic
  runs so isolated mode no longer drops Antigravity authentication.
- Updates `setup-brain.py` labels and model-source messages to distinguish
  `agy` auth from Gemini CLI OAuth.

### Validation

- `tests/real/test_claude_mem_bridge.py`: 2 passed.
- Focused K4/CLI/MCP/Antigravity regression: 83 passed.
- `./tests/run_real_knowledge.sh`: 21 passed, 8 skipped.
- Real Claude-Mem import/promotion:
  `sinapse-write.py promotion --import-claude-mem --source-id ...`: inserted 2,
  promoted 6, preserving `source_id` metadata.
- Acceptance CLI with system Python:
  `python3 scripts/services/sinapse-write.py query "ultimos discoveries promovidos"`:
  exit 0, no `sqlite-vec` import failure because the CLI re-executes through
  the project `.venv`.
- `./tests/run_all.sh`: Smoke 19 passed; Unit 496 passed / 3 skipped;
  Integration 107 passed / 4 skipped; E2E 22 passed.

## v3.1.0 — Knowledge Intake & Promotion Pipeline

Release date: 2026-06-29

### Highlights

- Introduces the K3 Knowledge Intake and Promotion pipeline for typed,
  evidence-preserving promotion of observations, discoveries, summaries,
  documents and code into durable knowledge candidates.
- Adds the K2 VectorBackend contract and canonical vector collections so
  SQLite/sqlite-vec and Milvus share one operational surface.
- Hardens the Antigravity (`agy`) provider path so it uses the real CLI
  authentication by default while keeping isolated HOME as an explicit
  diagnostic mode.
- Revalidates the real Dream Cycle path end to end with Antigravity,
  Graphiti, LightRAG, Ollama embeddings and the UMC schema.

### Changes

- Added `core/knowledge/intake.py` and `core/knowledge/promotion.py`.
- Added `knowledge_candidates` to the UMC schema, CRR schema and CRDT setup.
- Added CLI and MCP surfaces for K3 promotion:
  `sinapse-write.py promotion` and `sinapse_promote_knowledge`.
- Refactored specialized promoters to expose candidate-only outputs with
  `workspace_id`: `decision_promoter`, `pattern_distiller`,
  `conflict_detector`, `sector_classifier`, `drift_detector`,
  `topic_consolidator` and `work_tracker`.
- Added vector sync CLI and auxiliary vector collection tests.
- Added bounded Graphiti/LightRAG push behavior in Dream Cycle to prevent
  unbounded graph indexing from blocking promotion.

### Validation

- `tests/real/test_promotion_pipeline_sqlite.py`: 3 passed.
- `scripts/dream/dream_cycle.py --once --real`: ok, 30 observations,
  29 K3 candidate-only records, 19 neurons persisted across 3 projects.
- `scripts/services/sinapse-write.py query "decisoes promovidas hoje"`:
  exit 0, JSON on stdout.
- Focused K3/CLI/MCP/Graphiti regression: 89 passed.
- `./tests/run_real_knowledge.sh`: 19 passed, 8 skipped.
- `./tests/run_all.sh`: Smoke 19 passed; Unit 494 passed / 3 skipped;
  Integration 109 passed / 2 skipped; E2E 22 passed.

### Publication Notes

- This release intentionally replaces the previously pushed online K3/K5
  attempt on `origin/main`; the implementation commit is `a15c492`.
- GitHub Release should use the contents of this section as the release body.
