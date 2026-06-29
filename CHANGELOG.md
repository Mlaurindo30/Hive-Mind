# Changelog

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
