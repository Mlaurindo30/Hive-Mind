# Observability

> **Hive-Mind v3.10.1** — Backend health, knowledge health (K8), Model Gateway telemetry, and OTEL tracing.
> Normative observability document. Canonical sources: [`architecture.md`](architecture.md) §5 (read flow, circuit breaker), §28 (K8), §31 (pending contracts), [`04-infrastructure.md`](04-infrastructure.md) §2/§3 (env, services and ports), [`ai-models.md`](ai-models.md) (gateway telemetry) and the code: `core/memory/health.py`, `core/memory/circuit_breaker.py`, `core/memory/context_fusion.py`, `core/model_telemetry.py`, `core/telemetry.py`, `scripts/health/knowledge_health.py`, `scripts/health/health_dashboard.py`, `scripts/health/alert_dispatcher.py`.

---

## 1. Overview

Hive-Mind observability has **four independent surfaces** that answer distinct questions:

| Surface | Question it answers | Where it lives | Surface tool |
|---|---|---|---|
| **Backend health** | "Are the 7 read organs alive?" | `core/memory/health.py` + `core/memory/circuit_breaker.py` | `sinapse_health()` |
| **Knowledge health (K8)** | "Is the brain intact and covering what it should?" | `scripts/health/knowledge_health.py` | `sinapse_health().knowledge_health`, `GET /api/v1/knowledge/health`, `hive-mind` health |
| **Model Gateway telemetry** | "Which model responded, at what cost, with what fallback?" | `core/model_telemetry.py` | `[model_gateway]` logs in stderr |
| **OTEL tracing** | "Where was time spent inside a call?" | `core/telemetry.py` | OTLP spans → self-hosted Langfuse |

No surface carries **payload** (prompt, neuron content, response). The anti-secret discipline is transversal and described in §6 ("Boundaries").

---

## 2. Backend health — `sinapse_health()`

`sinapse_health()` (MCP) / `sinapse-write.py health` / `GET /api/v1/health` return a single status package. The canonical implementation is `health_check()` in `core/memory/health.py`, which is **pure** (receives all parameters as arguments, no global state).

### 2.1 Response structure

```json
{
  "timestamp": "...",
  "backends":          { /* alias de compatibilidade = read_backends */ },
  "read_backends":     { "umc": true, "neural_memory": ..., "sqlite_vec": ...,
                         "claude_mem": ..., "graphify": ..., "graphiti": ..., "filesystem": ... },
  "components":        { "neural_memory": ..., "claude_mem": ..., "sqlite_vec_worker": ...,
                         "graphify_graph": ..., "graphiti": ..., "rtk": ... },
  "vault":             { "path": ..., "exists": true, "graph_nodes": 1234 },
  "plugin":            { "backends_registered": 7 },
  "knowledge_health":  { ... K8 metrics ... },
  "model_gateway":     { "enabled": ..., "models_total": ..., "healthy": ..., "unhealthy": ..., "default_roles": ... },
  "healthy":           true,
  "components_healthy": true
}
```

- `read_backends`/`backends` is the **correct contract of the 7 organs** fused by `sinapse_query`.
- `healthy` is the logical `AND` of all 7 read-backends.
- `components_healthy` is the logical `AND` of the auxiliary components (includes RTK, which is **not** a read-backend).
- `knowledge_health` is computed in **quick mode** (`quick=True`) inside the health check: `observation_vectors` is not inspected (cost) and `prune_orphans=False` (nothing is pruned during a health check).
- `model_gateway` is **always present**, even when disabled — a disabled gateway does no network probing and reports `enabled: false` explicitly (never omitted).

### 2.2 The 7 read-backends

| Backend | Brain organ | What it checks | Typical failure |
|---|---|---|---|
| `umc` | Cortex (central) | `query_hybrid` importable (SQLite + FTS5 + vec) | broken import/schema |
| `neural_memory` | Cortex (association) | `nmem` binary executable on PATH | binary missing |
| `sqlite_vec` | Cortex (local vector) | worker `:37701` responds to `/health` | worker down, `sqlite_vec` not loaded |
| `claude_mem` | Temporal (hippocampus) | worker `:37700` responds to `/health` with `status=ok` | worker down |
| `graphify` | Occipital (structural) | `graph.json` readable with `nodes > 0` | empty/corrupted graph |
| `graphiti` | Temporal (causality) | FalkorDB reachable (via injected callable) | FalkorDB `:6379` down |
| `filesystem` | Parietal (immediate sense) | vault directory exists | vault missing |

> **RTK is not a read-backend.** It appears only in `components` (shell optimization). It must never be wired into `sinapse_query`, `context_fusion`, `retrieval_router`, or any `read_backends` list (see [`architecture.md`](architecture.md) §2.6 and §3.2 of [`04-infrastructure.md`](04-infrastructure.md)).

### 2.3 Circuit breaker

Rule implemented in `core/memory/circuit_breaker.py` (stateless — state passed as a dict):

- A backend with **≥ 3 consecutive failures** within the last `cooldown` seconds is **skipped** (open circuit). `cooldown` default = **30 s**.
- **Only exceptions and timeouts count as failures.** An empty result (`[]`/`null`) does **not** count — a resultless search is not an illness.
- Success **resets** the failure counter (`failures = 0`).

```python
is_backend_healthy(name, backend_state, log_fn) -> bool   # False => circuito aberto
record_backend_result(name, success, backend_state)       # muta o estado in-place
```

Log event when the circuit opens: `log_fn("warn", "circuit_breaker_open", backend=name, failures=failures)`.

### 2.4 Context Fusion — time budget and dedup

`core/memory/context_fusion.py:query_vault_knowledge()` orchestrates the healthy backends in parallel:

- **`ThreadPoolExecutor`** with one worker per healthy backend.
- **Global timeout** (`global_query_timeout`, default **8 s**): whatever does not finish is cancelled and recorded as `query_timeout` (failure → feeds the circuit breaker).
- Backends that blew the timeout receive synthetic latency `= global_query_timeout`.
- **Cross-backend dedup** in the fusion (`_fuse_contexts`): observations deduplicated by `source_file | title | content[:40]`; nodes by `id | label`.
- Final result truncated by `max_observations` and `max_nodes` (see limits in [`architecture.md`](architecture.md) §5: `MAX_CONTEXT_CHARS=3000`, `MAX_NODES=5`).

Log events per backend: `backend_latency`, `backend_hit`, `backend_error`, `query_timeout`, `thread_unhandled_error`.

---

## 3. Knowledge health — `knowledge_health` (K8)

`scripts/health/knowledge_health.py` (v3.6.0) **adds** knowledge coverage metrics. It does **not replace** `health_dashboard.py`, `alert_dispatcher.py`, or `review_writer.py` (those remain the Insula's health). Access:

- `sinapse_health()` → `knowledge_health` block (quick mode, read-only).
- `GET /api/v1/knowledge/health` → full gate (allows `prune=true`).
- CLI: `python scripts/health/knowledge_health.py --json [--fail-closed] [--no-prune] [--no-report]`.
- Markdown report auto-generated at `cerebro/cortex/insula/saude/knowledge-health-<date>.md` (type `knowledge-health`, `auto:gerado — não editar à mão`).

### 3.1 Key metrics

| Metric | Signal | Detail |
|---|---|---|
| `neurons_total` | consolidated memory size | `COUNT(*) FROM neurons` |
| `neurons_vectorized_pct` | memory vector coverage | `search_vec` / `neurons` |
| `observations_total` | indexed temporal volume | non-quarantined observations |
| `observations_linked_pct` | **effective promotion** | obs with `neuron_id` filled / non-quarantined obs |
| `discoveries_pending` | **risk of learning loss** | `knowledge_candidates.status='candidate'` + observations `type IN (discovery, learning, decision)` with `archived=0` |
| `governance_review_queue` | governance queue | `{held_total, held_high_risk, held_hypothesis}` — candidates `status='held'` grouped by `risk` |
| `summary_vectors_total` | cadence coverage | vectors from `summary_vectors` |
| `orphan_vectors` | **dirty index** | vectors whose parent does not exist (detail in `orphan_vector_details`) |
| `orphan_vectors_before_prune` / `orphan_vectors_pruned` | pruning effect | — |
| `milvus_sync_lag` | **local × production divergence** | `{available, reason, total_lag, by_collection}` |
| `query_route_distribution` | which layers respond | by `first_route|intent` over the last 7 days |
| `tombstones_total` | accumulated auditable forgetting | `COUNT(*) FROM knowledge_tombstones` |
| `<collection>_vectorized_pct` | coverage **per canonical collection** | 7 collections (§3.4) |
| `collections` | per-collection block | `{source_total, vector_total, vectorized_pct}` |
| `promotion_lag` / `promotion_cost` | backlog and LLM cost per workspace | §30.5 of [`architecture.md`](architecture.md) |
| `vectors_model_mismatch` | embedding model divergence within a collection | §30.4 of [`architecture.md`](architecture.md) |

> K8 explicitly measures the **seven canonical collections** — the gate cannot inspect only `neurons_vectorized_pct`.

### 3.2 Fail-closed gates (SLO)

`evaluate_fail_closed(metrics)` returns the **list of failures** (empty = healthy). Final `status` is `ok` or `degraded`.

| SLO | Failure condition |
|---|---|
| Clean index | `orphan_vectors > 0` |
| Memory coverage | `neurons_total > 0` and `neurons_vectorized_pct` unknown |
| Document coverage | `document_vectors.source_total > 0` and `vectorized_pct` unknown |
| **SLO 1 — promotion** | `observations_total >= 100` and `observations_linked_pct < 80%` |
| **SLO 2 — drain** | `discoveries_pending > 500` |

CLI with `--fail-closed` exits with code 1 when there are failures.

### 3.3 `milvus_sync_lag`

`_milvus_sync_lag()` compares the local total per collection with Milvus's `backend.count(collection)`.

- Milvus disabled (`VECTOR_BACKEND != milvus` and `HIVE_KNOWLEDGE_HEALTH_MILVUS != 1`): `{available: false, reason: "milvus_not_enabled", total_lag: null}` — **expected behavior, not a failure**.
- Enabled but unhealthy: `{available: false, reason: <error>, total_lag: null}`.
- Enabled and healthy: `{available: true, total_lag: N, by_collection: {...}}`, where `lag = max(0, local - remote)`.

To measure real `milvus_sync_lag` instead of `milvus_not_enabled`, set `HIVE_KNOWLEDGE_HEALTH_MILVUS=1` (or `VECTOR_BACKEND=milvus`).

### 3.4 Measured canonical collections

| Collection | Source (`source_total`) | Vector table |
|---|---|---|
| `memory_vectors` | `neurons` | `search_vec` |
| `observation_vectors` | claude-mem observations (not measured in `quick`) | `vec_observations` (claude-mem) |
| `document_vectors` | `document_chunks` ∪ `neurons.type='document'` | `vec_documents` |
| `code_vectors` | `neurons.type='code'` | `vec_code` |
| `visual_vectors` | `visual_memories` | `vec_visual` |
| `graph_vectors` | `causal_edges` | `vec_graph` |
| `summary_vectors` | cadence `.md` files (session→annual) | `vec_summary` |

> **Implementation state (2026-07-03, `POST_AUDIT_FIX_LOG.md` Q2/R3):** the contract and schema exist for the 7 collections, but only `memory_vectors`, `observation_vectors`, `document_vectors`, and `visual_vectors` have semantic indexing wired end-to-end. `code_vectors`, `graph_vectors`, and `summary_vectors` have a table + `vector_jobs` enqueue (`core/indexing/vector_jobs_worker.py`), but **no producer populates real embeddings yet** — treat these 3 as a target contract, not a delivered feature.

### 3.5 Orphan vectors and auditable forgetting

- `find_orphan_vectors()` locates vectors whose parent does not exist (per collection, via `VECTOR_PARENT_SQL`).
- `prune_orphan_vectors()` calls `forget_vector()` with `reason="orphan_vector"`: **removes** the vector, cleans `vector_metadata` when applicable, and **writes `knowledge_tombstones`** (`target_type`, `target_id`, `collection`, `reason`, `actor`, `workspace_id`, `metadata_json`). There is never a silent delete.
- Valid `forget` reasons: `secret_leak | expired | superseded | user_request | orphan_vector` (see [`architecture.md`](architecture.md) §31.2).

---

## 4. Model Gateway telemetry

The Model Gateway (`core/model_gateway.py` + `core/model_registry.py`) is the **only** LLM execution path. Every call emits structured records via `core/model_telemetry.py`, **without payload** and with redacted fields.

### 4.1 `record_call` — per-call metrics

Canonical fields (signature with no prompt/content/response parameter by design):

| Field | Type | Meaning |
|---|---|---|
| `request_id` | string (uuid4) | call correlation |
| `workspace_id` | string | isolation boundary (default `default`) |
| `role` | string \| null | role that triggered it (`dreamer`, `validator`, `synthesis`, ...) |
| `selected_model_id` | string | effectively selected model |
| `provider` | string | resolved provider |
| `endpoint` | string \| null | **redacted** via `redact_for_export` |
| `capabilities_required` | dict | required capabilities (structured, vision, ...) |
| `fallback_used` | bool | whether the chain used fallback |
| `latency_ms` | float | latency rounded to 2 decimals |
| `input_tokens` / `output_tokens` | int \| null | token consumption |
| `cost_estimate` | float \| null | estimated cost |
| `error_type` | string \| null | **redacted** via `redact_for_export` |

Output: `print(f"[model_gateway] {record}", file=sys.stderr)`.

### 4.2 Canonical hooks (R10 spec)

| Hook | Event | Key fields |
|---|---|---|
| `record_gateway_attempt` | `gateway_attempt` | `request_id`, `role`, `provider`, `model`, `level`, `gateway_attempted=true` |
| `record_gateway_failure` | `gateway_failure` | `request_id`, `error_class`, `reason` (redacted), `gateway_failed=true` |
| `record_legacy_fallback_used` | `legacy_fallback` | `request_id`, `reason` (redacted), `legacy_fallback_used=true` |
| `record_setup_brain_role_configured` | `setup_brain_role_configured` | `role`, `primary`/`fallback`/`fallback2` (provider+model) |
| `record_provider_skipped_due_to_capability` | `provider_skipped_due_to_capability` | `missing_capability` (redacted) |
| `record_provider_unsupported_skipped` | `provider_unsupported_skipped` | `unsupported_reason` (redacted) |

`record_gateway_attempt` returns the `request_id` that **must be reused** in `record_gateway_failure` / `record_legacy_fallback_used` for correlation.

### 4.3 Error classification (`error_class`)

`record_gateway_failure` requires `error_class` with one of these values: `auth`, `transient`, `validation`, `rate_limit`, `unknown`.

Retry/fallback policy (see [`ai-models.md`](ai-models.md) § "Configuring fallback"):

- **`validation`** → does **not** trigger fallback (it is output quality, not availability); retry the same model up to `max_retries`, then `LLMValidationError`.
- **`auth` / 401 / 403 / 402 (balance)** → skips retries and goes straight to the next pair.
- **`rate_limit` / 429 / 5xx / timeout** → exponential backoff (ceiling 8 s), then fallback.

### 4.4 Anti-secret discipline (R10)

- `record_call` **only accepts metadata fields** — there is no prompt/content/response parameter.
- All hooks follow the same discipline: **no payload**; `endpoint`/`error_type`/`reason`/`missing_capability`/`unsupported_reason` go through `core.redactor.redact_for_export` before any write.
- API keys are resolved at call time via `ModelProfile.api_key_env` (`profile.api_key()`); **never** stored in the profile object, **never** logged.

---

## 5. OTEL tracing (self-hosted Langfuse)

`core/telemetry.py` exposes OpenTelemetry tracing → **self-hosted Langfuse** (see [`09-integration-study.md`](09-integration-study.md) §5 for the original rationale).

- **Activation:** set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (optional `LANGFUSE_HOST`, default `http://localhost:3100`, optional `HIVE_SERVICE_NAME`, default `hive-mind`). Without keys, `init_telemetry()` returns `False` and tracing becomes a no-op.
- **Resource:** `service.name` and `service.version` (fixed at `3.10.1`).
- **Exporter:** `OTLPSpanExporter` to `<LANGFUSE_HOST>/api/public/otel/v1/traces`, auth `Basic base64(pk:sk)`.
- **Processor:** `BatchSpanProcessor` with `max_export_batch_size=1` / `schedule_delay_millis=1` (dev/test); fallback `SimpleSpanProcessor` if the lib rejects parameters. In production, increase the batch to reduce overhead (v3.7.9+ comment in the file itself).
- **API:**
  - `init_telemetry() -> bool` — idempotent.
  - `span(name, attributes=None)` — context manager; `yield None` when disabled; coerces non-OTel types to `str`, preserves `bool/int/float/str` for typed queries.
  - `flush_telemetry()` — `force_flush(timeout_millis=5000)`; warn-once on stderr if the flush fails.
- **Security warning:** `LANGFUSE_HOST` over HTTP (not HTTPS) and a **non-local** host triggers a warn on stderr — Basic auth + traces in cleartext.

---

## 6. Insula health dashboard (health_dashboard + alert_dispatcher)

Operational complement to K8 health:

- `scripts/health/health_dashboard.py` aggregates **M1–M13** metrics into a Markdown snapshot at `cerebro/cortex/insula/saude/` (section `## Alertas` with `- ⚠️` lines). Consumes `knowledge_health`, task state, `logs/jobs/*-latest.json`, `services.managed.json`, capture doctor.
- `scripts/health/alert_dispatcher.py` reads the day's snapshot, extracts the active alerts, and writes **one note per alert** at `cerebro/cortex/parietal/inbox/YYYY/MM/DD/alerta-<HHMMSS>-<hash8>.md` (frontmatter `type: health-alert`, `severity: warning`, `metric`, `suggested_action`). No LLM, **idempotent by content-hash**. Usage: `--apply` to write (default dry-run). Metric **M13** counts alerts dispatched today.
- Alert rules (severity) are in the runbook — see [`incidents.md`](incidents.md).

---

## 7. Boundaries (what observability does NOT do)

1. **Never records payload.** Prompt, neuron content, and response have no path into telemetry — `record_call` and the gateway hooks have no payload parameter; query text **never** enters telemetry (`query_route_distribution` stores a **hash** of the query, not the text — [`architecture.md`](architecture.md) §26/§28).
2. **RTK is not a read-backend.** It appears only in `components` and never participates in `sinapse_query`/Context Fusion.
3. **Health check does not mutate.** `sinapse_health` uses `quick=True` and `prune_orphans=False`; orphan pruning only happens by explicit action (`knowledge_health.py` without `--no-prune`, or `GET /api/v1/knowledge/health?prune=true`).
4. **A disabled gateway does no probing.** `enabled: false` is reported explicitly, without adding network latency.
5. **An observability failure does not take down the flow.** OTEL is best-effort; `span()` is a no-op without keys; unavailable `knowledge_health` becomes `{status: "unavailable", error}` instead of breaking `sinapse_health`.
6. **Empty result ≠ failure.** The circuit breaker counts only exceptions/timeouts, never empty results.

---

## Cross-references

- [`architecture.md`](architecture.md) — principles, read flow, circuit breaker, Model Gateway (ADR-019).
- [`operations.md`](operations.md) — operation commands, cron, `hive-mind doctor`.
- [`data-pipeline.md`](data-pipeline.md) — Capture→Promotion→Index flow and the 7 collections.
- [`installation.md`](installation.md) — environment variables (`LANGFUSE_*`, `VECTOR_BACKEND`, `HIVE_KNOWLEDGE_HEALTH_MILVUS`).
- [`incidents.md`](incidents.md) — severity and runbooks per symptom.
- [`security.md`](security.md) — anti-secret discipline and PII redaction.
- [`ai-models.md`](ai-models.md) — full Model Gateway operation.
- [`blueprint.md`](blueprint.md) — ASCII architecture diagrams.
