# HANDOVER — Handover to Sustainment

> **Hive-Mind v3.10.1** (release 2026-08-15) — Project handover document for the sustainment team.
> Objective: whoever takes over maintenance must be able to (1) understand what it is, (2) locate each area, (3) know the known pending items and (4) validate that they are fit to operate, **without** depending on whoever built it.

---

## 1. What Hive-Mind is

Hive-Mind is a **collective and multimodal intelligence** infrastructure: it unifies what the agent does, sees and reads into a single persistent and distributed memory, organized as a **born-large knowledge architecture** (born ready to scale, local-first by operation, pluggable by contract). The source of truth is the anatomical vault (`cerebro/`, Obsidian/Markdown); SQLite (`hive_mind.db` with `sqlite-vec` + FTS5) is the index.

Summary rule: **local-first by operation · born-large by architecture · pluggable by contract · anatomical by source of truth · auditable by evidence**.

Canonical flow (9 steps): `Capture → Temporal Hippocampus (claude-mem) → Knowledge Intake (K3) → Promotion Layer (K4) → Anatomical Memory → Indexing → RetrievalRouter (K7) → Answer with citation → Feedback`.

### 1.1 Stack in one line

| Layer | Technology |
|---|---|
| Brain (UMC) | `hive_mind.db` — SQLite + `sqlite-vec` (1024d `snowflake-arctic-embed2`) + FTS5 + graph + multimodal + `workspace_id` |
| Structural | Graphify (clone `integrations/`, pin commit) |
| Temporal | claude-mem (TypeScript/Bun, wrapper, `~/.claude-mem`) |
| Vectors | `VectorBackend` — `sqlite_vec` (local) / Milvus (production) |
| Documents | `DocumentPipeline` (K6) + RAGFlow headless (optional) |
| Retrieval | `RetrievalRouter` (K7) + LlamaIndex (rerank, optional) |
| LLM execution | `core/model_gateway.py` (only path, ADR-019) |
| Access | MCP (16 tools) · Hermes plugin · CLI · REST `:37702` |
| Distribution | Syncthing (P2P) + UUID v4 + SHA-256 + Dialectic Synthesis + Ed25519 |

---

## 2. Current state

- **Version:** `3.10.1` (agreement across 5 sources: `pyproject.toml`, `npm/package.json`, `core/version.py`, `scripts/services/sinapse-api.py`, `scripts/services/sinapse_mcp.py`; the `scripts/release/validate_package.py` validator locks the SemVer floor `>=3.10`).
- **Phases:** HM-01 to HM-12 ✅; **K0–K10** implemented (K7 `v3.5.0`, K8 `v3.6.0`; K9/K10 as contract). See [`architecture.md`](architecture.md) §21.
- **Model Gateway** is the canonical LLM execution path (`MODEL_GATEWAY_MODE=auto` default; `HIVE_FORCE_LEGACY_LLM=true` as emergency bypass).
- **Windows-native runtime** mature in v3.10.1 (Dockerfile + docker-compose, native scheduler, supervisor).
- **Tests:** dynamic suite (measure with `rg -n "^\s*(async\s+def|def)\s+test_" tests | wc -l`; do not trust a fixed number). Separate real K9 gate (`tests/run_real_knowledge.sh`).

---

## 3. Owners and boundaries — where each area is

Table **area → where it is (code) → documentary reference**. No area is orphaned; each has a write owner and a contract.

| Area | Where it is | Reference |
|---|---|---|
| Canonical architecture (principles, UMC, flows, ADRs 001–019, Born-Large §22–§31) | — (normative) | [`architecture.md`](architecture.md) (canonical, prevails over any other in case of divergence) |
| Brain/UMC (schema, connections, WAL, migrations) | `core/umc_schema.sql`, `core/database.py` | [`architecture.md`](architecture.md) §4; [`04-infrastructure.md`](04-infrastructure.md) §6.1 |
| Anatomical vault (path constants) | `core/paths.py` | [`architecture.md`](architecture.md) §2.7, §12 |
| Model Gateway (LLM execution) | `core/model_gateway.py`, `core/model_registry.py`, `integrations/model_gateway/` | [`ai-models.md`](ai-models.md); ADR-019 |
| Multi-provider auth (roles) | `core/auth.py` (`PROVIDERS_CONFIG`, `get_role_config`) | [`architecture.md`](architecture.md) §11; [`02-ai-models.md`](02-ai-models.md) |
| Knowledge Intake (K3) | `core/knowledge/intake.py` | [`architecture.md`](architecture.md) §27.1 |
| Promotion Layer (K4) | `core/knowledge/promotion.py`, `claude_mem_bridge.py` | [`architecture.md`](architecture.md) §27.3–27.5 |
| DocumentPipeline (K6) | `core/knowledge/document_pipeline.py` | [`architecture.md`](architecture.md) §25 |
| VectorBackend (K1) | `core/vector_backend.py`, `core/vector_collections.py` | [`architecture.md`](architecture.md) §24 |
| RetrievalRouter (K7) | `core/retrieval/router.py`, `core/search.py` | [`architecture.md`](architecture.md) §26 |
| Knowledge health (K8) | `scripts/health/knowledge_health.py` | [`architecture.md`](architecture.md) §28; [`observability.md`](observability.md) §3 |
| Insula health (M1–M13) | `scripts/health/health_dashboard.py`, `alert_dispatcher.py` | [`observability.md`](observability.md) §6 |
| Dream Cycle / Cadence (K5) | `scripts/dream/dream_cycle.py`, `{session_consolidator,daily,weekly,monthly,yearly}_*.py`, `pattern_distiller.py` | [`architecture.md`](architecture.md) §7, §29 |
| Capture | `scripts/capture/visual_capture.py`, `scripts/capture/capture_adapters.py` | [`docs/capture/providers.md`](capture/providers.md) |
| MCP / CLI / REST | `scripts/services/sinapse_mcp.py`, `sinapse-write.py`, `sinapse-api.py` | [`architecture.md`](architecture.md) §10 |
| Agent registration | `src/hive_mind/agents/` (wrappers in `scripts/setup/`) | [`docs/agents.md`](agents.md), [`AGENTS.md`](../AGENTS.md) |
| P2P / conflict | `scripts/health/audit_memory.py`, `core/database.register_ambiguity`, `scripts/dream/semantic_diff.py` | [`architecture.md`](architecture.md) §8; [`07-p2p-sync-setup.md`](07-p2p-sync-setup.md) |
| Federation (HM-12) | `core/signing.py` (Ed25519), `core/redactor.py` (PII), export endpoint | [`architecture.md`](architecture.md) §19; [`security.md`](security.md) |
| Telemetry / OTEL | `core/model_telemetry.py`, `core/telemetry.py` | [`observability.md`](observability.md) §4–§5 |
| Circuit breaker / Context Fusion | `core/memory/circuit_breaker.py`, `core/memory/context_fusion.py`, `core/memory/health.py` | [`architecture.md`](architecture.md) §5; [`observability.md`](observability.md) §2 |
| Installation | `install.sh`, `install.ps1`, `src/hive_mind/install/`, `Dockerfile` + `docker-compose.yml` | [`installation.md`](installation.md), [`15-windows-clean-install.md`](15-windows-clean-install.md) |
| Runtime / scheduler / supervisor | `config/runtime.yaml`, `src/hive_mind/maintenance/` | [`docs/runtime.md`](runtime.md), [`docs/runtime.md`](runtime.md) |
| Backup / recovery | `scripts/health/backup_databases.py`, `scripts/utils/recover.sh` | [`04-infrastructure.md`](04-infrastructure.md) §5; [`architecture.md`](architecture.md) §16 |
| Vendoring (negative contract) | `components.lock.json` | [`architecture.md`](architecture.md) §2.6, §22.3; ADR-018 |
| Tests | `tests/{smoke,unit,integration,e2e,real}` | [`architecture.md`](architecture.md) §15; [`tests/README.md`](../tests/README.md) |
| Canonical identity | `docs/capture.md` | [`docs/capture.md`](capture.md) |

### 3.1 Boundaries the sustainment team must defend

1. **The vault is the truth.** In a divergence, the auditor reconciles **in favor of `cerebro/`**.
2. **External organs are not the source of truth.** Milvus, RAGFlow, and LlamaIndex accelerate/scale/specialize indexes; they never replace the vault + UMC. RAGFlow: never a source; its store is an ingestion cache.
3. **`components.lock.json` is a negative contract.** Clones (`graphify`, `neural-memory`, `rtk`) pinned by commit. If Milvus, RAGFlow, or LlamaIndex appear there, the implementation is **wrong**.
4. **Never call a raw backend.** Use only `sinapse_*`/`search_memories`; never `nmem`, `claude-mem`, `graphify`, or `falkordb` directly.
5. **Never hardcode a model.** Strictly obey `HIVE_*_PROVIDER/MODEL`.
6. **No version suffix in file/class/table.** Use a semantic suffix (`setup_crdt.py`, not `migrate_to_v2.py`).
7. **Quarantine never discarded; a refuted hypothesis corrected in place.** See [`incidents.md`](incidents.md) §4.
8. **Never modify `cerebro/` without the Watcher active** (or run `./scripts/graph/build-graph.sh` afterwards).

---

## 4. Known pending items (take on with full knowledge)

| # | Pending item | Where it is documented | Impact |
|---|---|---|---|
| 1 | **3 vector collections with no producer** — `code_vectors`, `graph_vectors`, `summary_vectors` have a table + `vector_jobs` enqueue, but no producer populates real embeddings yet | [`architecture.md`](architecture.md) §24.2 (status note) | `*_vectorized_pct` of these 3 collections is a target contract, not a real metric |
| 2 | **Reranker** — `HIVE_RETRIEVAL_RERANKER=1` delivers deterministic fail-open lexical rerank; a local cross-encoder is opt-in (`HIVE_RERANKER_PROVIDER/MODEL` + extra `reranker`) | [`architecture.md`](architecture.md) §31.1 | Relevance reordering only partial |
| 3 | **Intentional forgetting** — `forget()` covers `orphan_vector`; `secret_leak`, `expired`, `superseded`, `user_request` are still contract (same `knowledge_tombstones` table) | [`architecture.md`](architecture.md) §31.2 | Auditable delete of non-orphan data pending |
| 4 | **Retrieval evaluation** — golden set `tests/real/golden_retrieval.jsonl` with `precision@k`/`recall@k`/`intent_accuracy` is contract | [`architecture.md`](architecture.md) §31.3 | Answer quality not measured by the K8 gate (K8 measures coverage) |
| 5 | **Missing doc numbering** — `06-gap-analysis.md`, `10-…`, `11-knowledge-promotion-architecture.md`, `12-…`, `13-*.md` are cited but **do not exist in this checkout**; they point to `architecture.md §22–§31` | [`docs/README.md`](README.md) §maintenance note | Broken links until intentional recreation/removal |
| 6 | **Presumed STALE/CONTRADICTORY documentation** — `README.md`, `AGENTS.md`, `docs/README.md`, `architecture.md` (pre-redesign), `installation.md`; line-by-line audit pending |  | doc×code divergences documented there ("Divergences" table) |
| 7 | **Optional Milvus/RAGFlow** — without `VECTOR_BACKEND=milvus`, K8 reports `milvus_sync_lag.available=false` (expected). Both are wrappers/containers, never cloned | [`04-infrastructure.md`](04-infrastructure.md) §2.3 | Without them, uses local `sqlite_vec` |
| 8 | **Model Gateway — limitations** — LiteLLM only HTTP proxy; streaming not implemented; vision delegated to the legacy path; tool-calling declared but not exercised; basic SSRF (no anti-DNS-rebinding) | [`ai-models.md`](ai-models.md) § "Known limitations" | Known operational constraints |
| 9 | **Old-convention files** in the vault (`cerebro/cortex/frontal/trabalho/ativo/`) — 4 files with numbering lacking a project prefix; rename on the next manual edit (via Syncthing, not git) | [`architecture.md`](architecture.md) §21 | Cosmetic/consistency |
| 10 | **`MODEL_GATEWAY_ENABLED` deprecated** — shim for `MODEL_GATEWAY_MODE`; will be removed | [`ai-models.md`](ai-models.md) § "Operating modes" | Operator migration |

---

## 5. Handover checklist (fitness validation)

Execute, in order, and **record the result with evidence**. Only consider the handover complete when all of them pass.

1. **Environment:** `python --version` (3.10+), `sqlite3 --version` (3.44+), `uv --version`, `syncthing --version`.
2. **Backend health:** `sinapse_health()` (or `python scripts/services/sinapse-write.py health`) → the 7 `read_backends` and the `knowledge_health` block present.
3. **Knowledge health:** `python scripts/health/knowledge_health.py --json` → `status=ok` and empty `failures` list (or understand each failure).
4. **Model Gateway:** `python scripts/analytics/model_benchmark.py --health` → enabled profiles resolve.
5. **REST API:** start it with `HIVE_MIND_API_KEY` and call `GET /api/v1/health`.
6. **Minimum tests:** `bash tests/smoke/test_smoke.sh` (minimum acceptable); ideally `./tests/run_all.sh`.
7. **Backup:** confirm that `backup_databases.py` runs and the latest backup is < 36 h old.
8. **Dream Cycle:** confirm `logs/dream-cycle.log` with the last run < 36 h ago and `status=ok`.
9. **Watcher:** `pgrep -f start-watcher` (POSIX) or the equivalent Windows task/service active.
10. **Recovery:** know `./scripts/utils/recover.sh` (and not have run it without need).
11. **Memory access:** `sinapse_query("<topic>")` returns context; `sinapse_temporal_search` locates recent sessions.
12. **Secrets:** confirm `.env` is out of version control (`git status` does not list `.env`/`*.db`/`config/keys/`).

---

## 6. Recommended reading sequence

1. [`../README.md`](../README.md) → public overview.
2. [`architecture.md`](architecture.md) → canonical reference (read §1–§13 and then §22–§32).
3. [`04-infrastructure.md`](04-infrastructure.md) → services, ports, env, cron.
4. [`observability.md`](observability.md) → backend health, K8, telemetry, OTEL.
5. [`incidents.md`](incidents.md) → severity and runbooks.
6. [`security.md`](security.md) → secrets, PII, signing, validation.
7. [`ai-models.md`](ai-models.md) → LLM execution and limitations.
8.  → documentation state and known divergences.
9.  and  → history of deliveries and debts.

> New squad documents (Portuguese names): [`architecture.md`](architecture.md), [`operations.md`](operations.md), [`data-pipeline.md`](data-pipeline.md), [`installation.md`](installation.md), [`development.md`](development.md), [`blueprint.md`](blueprint.md). When they exist, they are the entry doors per reader profile; until then, the canonical files listed above are the truth.

---

## Cross-references

- [`observability.md`](observability.md) — health and telemetry surfaces.
- [`incidents.md`](incidents.md) — severity, runbook, escalation, boundaries.
- [`security.md`](security.md) — secrets, PII, signing, data classification.
- [`architecture.md`](architecture.md) · [`operations.md`](operations.md) · [`data-pipeline.md`](data-pipeline.md) · [`installation.md`](installation.md) · [`development.md`](development.md) · [`blueprint.md`](blueprint.md) — squad documents (under construction).
