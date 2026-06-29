# Changelog

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
