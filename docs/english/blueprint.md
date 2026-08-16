# Blueprint — Hive-Mind

> One-page design document: what Hive-Mind is, what it does, the
> canonical flow, and the architecture decisions (ADR-level) with their consequences.
>
> **Reflected version:** v3.10.1 · **Normative reference:** [`architecture.md`](architecture.md)
> (canonical; ADRs in §32) · **Flowcharts:** [`blueprint.md`](blueprint.md) ·
> **Detailed anatomy:** [`architecture.md`](architecture.md)

---

## 1. What Hive-Mind is

Hive-Mind is a **universal, persistent, local-first memory layer for swarms of AI agents**.
It solves cross-session amnesia: everything the agents **do** (logs), **see** (screenshots),
**read** (PDF/DOCX), and **decide** is consolidated into a single persistent brain — the **Unified Memory Core (UMC)** —
and materialized in natural language inside an Obsidian vault (`cerebro/`), the single source of truth
readable by both humans and agents.

Multiple agents (Claude Code, Codex CLI, Cursor, Gemini CLI, Hermes, OpenClaw, among others) share
that same brain via **MCP**, native plugin, CLI, or **REST API** — on a single machine or across several,
synchronized over P2P.

In one sentence: **Hive-Mind is not just local RAG — it is a persistent brain** with temporal capture,
consolidated memory, documents, code, vision, structural graph, temporal causality, and
hybrid/vector search (see [`architecture.md` §22](architecture.md)).

### The problem it solves

| Without Hive-Mind | With Hive-Mind |
|---|---|
| Every agent session starts from zero (cross-session amnesia) | Consolidated, retrievable memory across sessions and across agents |
| Knowledge scattered in silos (logs, JSON, Chroma, SQLite) | A single `hive_mind.db` with multiple dimensions (graph + vectors + FTS + logs) |
| Facts without source or auditability | Every neuron carries SHA-256, `source_uri`, evidence, and citation |
| Data lost on pipeline failure | Quarantine (`archived=2`) — nothing is discarded by a promotion failure |
| Each agent needs its own plugin | A single MCP server (`sinapse-mcp.py`) serves all agents |

---

## 2. What Hive-Mind does

| Capability | How it delivers | Normative detail |
|---|---|---|
| **Capture** | hooks · MCP · CLI · browser · docs · code · screenshots · runtime | [`architecture.md` §23](architecture.md) step [1] |
| **Temporal memory** | claude-mem (hippocampus): `user_prompts`, `observations`, `discoveries`, `session_summaries` | §2.6, §7 stage 0.5 |
| **Consolidation** | Dream Cycle (Hive-Dreamer) — every 4h (`0 */4 * * *` / `PT4H`) | §7, `runtime.yaml` |
| **Promotion** | Knowledge Intake (K3) → Promotion Layer (K4): Distiller → Validator → Router | §27 |
| **Anatomical memory** | `cerebro/` (Obsidian vault) + UMC — a brain in 4 sibling lobes | §2, §12 |
| **Indexing** | FTS5 + `sqlite-vec` (1024d) + Graphify + Graphiti + LightRAG + Milvus (production) | §24 |
| **Retrieval** | `sinapse_query` (Context Fusion, 7 organs) + `RetrievalRouter` (K7, by intent) | §5, §26 |
| **Answer with citation** | `citations[{source_uri, offset_start, offset_end, score, parent}]` | §25.2 |
| **Vision** | screenshot → `visual_memories` (description + OCR + neuron_id) | §9 |
| **Documents** | `DocumentPipeline` (K6): parent/chunk/vector + auditable citation | §25 |
| **Multi-machine** | Syncthing P2P + UUID v4 + SHA-256 + Dialectic Synthesis | §8 |
| **Federation** | visibility (private/shared/public) + Ed25519 + PII redaction | §19, §30.3 |
| **Access** | MCP (16 tools) · Hermes plugin · CLI · REST FastAPI :37702 | §10 |

---

## 3. The founding rule

The entire design obeys a single rule, recorded in
[`architecture.md` §22.2](architecture.md):

```text
local-first by operation
born-large by architecture
pluggable by contract
anatomical by source of truth
auditable by evidence
```

No external backend can **replace** the brain. External backends **accelerate, scale, or
specialize indexes**. The truth remains in the anatomical vault (`cerebro/`) and in the UMC.

### Design principles (normative)

1. **Single source of truth readable by humans** — the Obsidian vault is the canonical layer; SQLite is the index; Markdown is the truth. On divergence, the auditor reconciles in favor of the vault.
2. **Local-first** — works 100% offline on a machine. Cloud and P2P are optional and additive.
3. **One database, multiple dimensions** — instead of graph JSON + claude-mem SQLite + Chroma, the UMC centralizes everything in a single `hive_mind.db`; cross-dimension queries become plain SQL.
4. **Agent and LLM agnosticism** — any agent connects via MCP/CLI/REST; any LLM serves the Dream Cycle via `HIVE_DREAMER_PROVIDER/MODEL`. No model is hardcoded.
5. **Fail-safe, not fail-silent** — a failed pipeline sends to quarantine (`archived=2`), never discards; the API without a key does not start; a backend with 3+ failures enters circuit breaker (30s cooldown).
6. **No version suffixes** in files, code, or schema — no `v2`, `v3` in names; migrations become `setup_<feature>.py` or `migrate_<feature>.py` (exception: upstream names).

---

## 4. Canonical flow on one page (9 steps)

Hive-Mind's knowledge flow — from capture to answer with citation and feedback — is a
**9-step** pipeline (K0–K10). Reproduced from [`architecture.md` §23](architecture.md)
and [`blueprint.md` §13](blueprint.md):

```text
  Agent / Human / System
          |
          v
  [1] Capture Layer
      hooks · MCP · CLI · browser · documents · code · screenshots · runtime
          |
          v
  [2] Temporal Hippocampus (claude-mem)
      user_prompts · observations · discoveries · session_summaries
      facts / narrative / concepts · files_read / files_modified
          |
          v
  [3] Knowledge Intake (core/knowledge/intake.py — K3)
      normalize · classify · deduplicate · preserve evidence
          |
          v
  [4] Promotion Layer (core/knowledge/promotion.py — K4)
      Distiller → Validator → Router
      raw -> summary -> fact / learning / decision / preference / task / rationale
          |
          v
  [5] Anatomical Memory
      cerebro/ + UMC:
        cortex temporal · frontal · parietal · occipital · insula
        cerebelo · diencefalo · tronco
          |
          v
  [6] Index Layer
      FTS · sqlite-vec · Milvus · vec_observations · Graphify · Graphiti · LightRAG
      (7 canonical collections — K1)
          |
          v
  [7] Retrieval Router (core/retrieval/router.py — K7)
      classify intent → choose temporal · memory · document · code · graph · chunk · hybrid
          |
          v
  [8] Answer + Citation
      answer with source · evidence · path · date
      (citations[{source_uri, offset_start, offset_end, score, parent}])
          |
          v
  [9] Feedback
      new observation, decision, learning, or task
```

**Boundary rule (normative):**

1. Each step is loosely coupled: a failure in [4] **does not block** [1]–[3] (the observation returns as `archived=0` or `archived=2`).
2. Each writer declares an explicit write contract (§27.4): does it create an observation? an anatomical file? a neuron? a vector? an edge? a task/goal? evidence? an idempotency key?
3. **Nothing is erased by a promotion failure**: transient error → `archived=0` (retry); structural error → `archived=2` (quarantine with reason).

---

## 5. Design decisions (ADR-level)

Each decision below is a **recorded ADR** — context, choice, rationale and, above all, **accepted consequence**.
The complete canonical record (ADR-001 through ADR-019) lives in
[`architecture.md` §32](architecture.md); if any other document
disagrees with an ADR there, **§32 prevails**.

### 5.1 Why the Obsidian vault is the source of truth (ADR-001)

**Decision:** the Obsidian vault with YAML frontmatter + WikiLinks is the primary storage; SQLite is only the index.

**Rationale:** plain-text Markdown is git-friendly, tool-agnostic, and readable without special software. Obsidian
is a mature editor with graph view, backlinks, and a plugin ecosystem. On divergence, **the auditor reconciles in favor of the vault**.

**Accepted consequences:**
- Dependency on the Watcher to keep SQLite synchronized in real time (~2s).
- Obsidian is optional — the vault works without it.
- "Critical convention" discipline (K3/K4): large files may exist for human reading, but the **searchable unit is atomic** (`Patterns.md` is a human reference; each learning becomes an individual `type=learning` in `cortex/temporal/`).

### 5.2 Born-large by architecture (ADR-010/011/012/013/014/015)

**Decision:** separate **capture, promotion, storage, indexing, and retrieval from day one** — without depending on
late structural refactoring to support Milvus, advanced document pipelines, or composite routers. Hive-Mind
**is born ready to scale** ("born ready to scale"):

- **K3/K4 — layered promotion** (ADR-010): `Knowledge Intake` (normalize/classify/dedup) separate from `Promotion Layer` (Distiller → Validator → Router → Persistence → Indexing). Makes promotion **idempotent** and **testable without a real LLM**, with a `candidate-only` mode.
- **K1 — 7 canonical vector collections** (ADR-011): `memory_vectors`, `observation_vectors`, `document_vectors`, `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors` — each with canonical metadata. A single "everything" collection would pollute ranking and prevent per-type coverage.
- **K0 — single vector contract** (ADR-012): `upsert/delete/query/hybrid_query/count/health`, backend-independent (sqlite-vec ↔ Milvus). The application **never calls Milvus outside the contract**.
- **K6 — documents with parent/chunk/citation** (ADR-013): every document becomes `document_memories` (parent) + `document_chunks` (atoms) + `document_vectors` (vectors). Without a parent, a chunk is loose text — not auditable, not deduplicable, not re-ingestible.
- **K7 — routing by intent** (ADR-014): `RetrievalRouter` classifies intent **before** searching and returns `retrieval_path` + `citations` + `confidence` + `missing_context`.
- **K10 — workspace as isolation boundary** (ADR-015): every critical table carries `workspace_id` (default `'default'`); Milvus uses `partition_key=workspace_id`. Leakage between workspaces is a **security bug**, not a ranking issue.

**Accepted consequences:**
- More UMC tables and more metadata per vector (mitigated by `vector_metadata` and by collection identity `(name, embedding_model, dim)`).
- The vector contract must remain stable; a Milvus schema change requires a versioned embedding migration (§30.4).
- Intent classifiers can fail (mitigated by fallback to `sinapse_query`/Context Fusion and the `intent_accuracy` metric).
- Every query carries `workspace_id` (mitigated by hot indexes `(workspace_id, …)` and the `'default'` default).

### 5.3 Quarantine instead of discard (ADR-008 + ADR-016)

**Decision:** a failed pipeline writes `archived=2` instead of deleting or ignoring the observation. ADR-016 refines the contract:
**transient error** (network down, zero credit, new schema) → `archived=0` (future retry); **structural error** → `archived=2`
(quarantine with reason).

**Rationale:** memory data is valuable; transient failures must not cause permanent loss of context. The
normative contract is **fail-safe, not fail-silent**.

**Accepted consequences:**
- Accumulation of quarantined data requires periodic cleanup — mitigated by `K8 knowledge_health` exposing
  `observations_pending`/`discoveries_pending` as a gate, by the reprocessing pipeline, and by
  `forget()` with a reason (`secret_leak | expired | superseded | user_request | orphan_vector`, §31.2).
- The temporal lobe's `hipocampo/` is the Dream Cycle staging area + quarantine (§2.1.1).

### 5.4 Risk-proportional promotion

**Decision:** the promotion of raw observation → typed knowledge is not uniform. It is **risk-proportional**:
what is verified and low-risk is promoted right away; hypotheses only rise after being drained/validated; what is
high-risk (potentially wrong or dangerous) only rises with explicit approval.

**Mechanisms that implement this:**

| Mechanism | What it guarantees | Source |
|---|---|---|
| **Epistemic discipline (verified vs hypothesis)** | `sinapse_save_decision`/`sinapse_save_learning` with `evidence` writes `confidence: verified`; without evidence writes `hypothesis`, demoted in ranking until validation | MCP protocol |
| **Review TTL (staleness)** | each decision/learning carries `next_review` (default 90d); once expired, `RetrievalRouter` applies the `HIVE_STALENESS_PENALTY` penalty (default 0.85) — never deletes, only demotes | MCP protocol |
| **Validator in the Promotion Layer** | the Validator (Pydantic) approves or rejects; rejected goes back to the Distiller (max 2 retries); structurally invalid goes to quarantine | §7 stage 2 |
| **Automatic promotion rule** | allowed: `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` (with traceable source); forbidden: turning every bullet into a fact, creating a neuron without source, vectorizing duplicates without `parent_id`, promoting temporary opinion to architecture decision, overwriting decisions without conflict/`invalid_at` | §27.3 |

**Accepted consequences:**
- Unverified notes remain demoted until validation; a refuted hypothesis must be **corrected**, not left in place (a refuted hypothesis left in place poisons future retrieval).
- The promotion cost is one LLM (classify) + one embedding per observation — scales as a queue with backpressure and a per-workspace cost cap (§30.5, `HIVE_PROMOTION_BUDGET_*`).

### 5.5 MCP as the universal integration protocol (ADR-003)

**Decision:** expose the tools via **MCP stdio** (`sinapse-mcp.py`, 16 tools) instead of building agent-specific plugins.

**Rationale:** MCP is an open standard adopted by Anthropic, OpenAI, GitHub, and the community. A single server serves
all agents without adaptation.

**Accepted consequences:**
- Less automatic integration (hooks) than native plugins — compensated by CLI (`sinapse-write.py`) and external hooks (SessionStart, PostToolUse, Stop via `sinapse-hook.py`).
- Hermes keeps the **native plugin** (`plugins/hermes/sinapse-memory.py`, hooks `pre_gateway_dispatch` / `post_tool_call` / `on_session_end`) — the only component aware of all layers.
- Single operational instruction block: `config/sinapse-agent-prompt.md`, injected between the `<!-- BEGIN HIVE-MIND SINAPSE -->` / `<!-- END HIVE-MIND SINAPSE -->` markers — correcting that prompt is the only action needed to propagate operational policy to all future clean installations.

### 5.6 Model Gateway as the canonical LLM execution layer (ADR-019)

**Decision:** `core/model_gateway.py` + `core/model_registry.py` are the **only** LLM execution path.
`core/llm_client.call_llm_with_fallback` is a thin wrapper that delegates to `ModelGateway.from_combined_config()`;
the legacy `_legacy_call_llm_with_fallback` is only reachable via `HIVE_FORCE_LEGACY_LLM=true` (emergency bypass)
or `image_path` (vision bridge). `MODEL_GATEWAY_MODE=auto` (default) uses the gateway and falls back to legacy on failure with
a warning + telemetry; `on` makes the gateway mandatory; `MODEL_GATEWAY_ENABLED` is a deprecated shim.

**Rationale:** a single source of truth for LLM execution eliminates the dual-path confusion (opt-in gateway alongside
legacy code). New inference backends enter via `config/model-gateway.yaml` overrides, not by touching call sites.

**Accepted consequences:**
- The registry unifies three config sources (legacy `HIVE_{ROLE}_*` + `PROVIDERS_CONFIG` + YAML), creating a small
  migration surface for operators who pinned `roles.<name>.provider` in YAML — mitigated by
  `ModelRegistry.validate()` reporting `unsupported_explicit` and by `setup-brain.py` printing the resolved table.
- Explicit fallback (never silent success) and redacted telemetry preserve the guarantees of the legacy path.

### 5.7 Other founding ADRs (summary with consequence)

| ADR | Decision | Accepted consequence |
|---|---|---|
| ADR-002 | Parallel hybrid search across 7 organs (UMC, NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem) with fusion and dedup | Slightly higher I/O; mitigated by circuit breaker (30s after 3+ failures) and optional rerank |
| ADR-004 | Atomic writes via `tempfile.mkstemp()` + `os.replace()` | Slightly more complex; justified for persistent memory data |
| ADR-005 | Cloud memory API (FastAPI :37702, Bearer), fail-closed without `HIVE_MIND_API_KEY` | Requires a stable network; automatic fallback to local when `cloud.enabled=false` |
| ADR-006 | Pydantic structured output across the whole Dream Cycle (`model_validate_json`) | One extra LLM validation call per run |
| ADR-007 | UUID v4 in all PKs | Less readable IDs in logs; irrelevant for programmatic use |
| ADR-009 | Per-role LLM config with Dreamer inheritance and opt-in fallback; **automatic provider cascade rejected** | Up to 16 environment variables; the minimal case stays at 2 (`HIVE_DREAMER_PROVIDER/MODEL`) |
| ADR-017 | Hierarchical cadence session→daily→weekly→monthly→yearly with dedicated LLM roles | More roles to configure; mitigated by `dreamer` inheritance in `setup-brain` |
| ADR-018 | Negative vendoring contract via `components.lock.json` (source clones only with pinned commit) | Lock maintenance; mitigated by generation via `install.sh` + PR review |

---

## 6. Current state (v3.10.1)

| Front | State |
|---|---|
| **Version** | `3.10.1` (release 2026-08-15) |
| **Native Windows** | native Windows runtime in local `.venv`, no WSL2; host agents (Claude Code, Cursor, Copilot) reach memory directly; `hive-mind services` supervisor |
| **Model Gateway** | canonical LLM execution layer (`MODEL_GATEWAY_MODE=auto`); `reasoning=True` per role (dreamer/validator/synthesis) |
| **Dream Cycle** | every 4h (`0 */4 * * *` / `PT4H`), aligned with `runtime.yaml` |
| **Docker** | unified `Dockerfile` + `docker-compose.yml` (FalkorDB, Milvus, RAGFlow stack + app); `docker/entrypoint.sh` materializes the vault idempotently; `unless-stopped` restart policy on mandatory services |
| **Capture** | universal provider capture (`src/hive_mind/capture/`): single transport (`engine.py`), per-provider identity (`identity.py`), content-hash idempotency, `SeenStore` on WAL SQLite |
| **Phases** | HM-01…HM-12 delivered · K0–K10 implemented and revalidated in local-full · real K9 gate in `tests/run_real_knowledge.sh` |

> **Note on phase status:** the phase record lives in [`architecture.md` §21](architecture.md)
> ("Phase Governance") and §22–§31 (Born-Large). See [`operations.md`](operations.md) and [`runtime.md`](runtime.md) for the
> control plane (`hive-mindd`, `config/runtime.yaml`).

---

## 7. Further reading (new docs)

| Topic | Document |
|---|---|
| Brain anatomy, UMC, canonical paths, external organs | [`architecture.md`](architecture.md) |
| Capture → Intake → Promotion → Indexing | [`data-pipeline.md`](data-pipeline.md) |
| LLMs, embeddings, roles, fallback | [`ai-models.md`](ai-models.md) |
| Control plane and daemon (`hive-mindd`) | [`runtime.md`](runtime.md) |
| Command-line interface | [`cli.md`](cli.md) |
| Agent integration (MCP/plugin/hooks) | [`agents.md`](agents.md) |
| Universal provider capture | [`capture.md`](capture.md) |
| Installation (incl. native Windows) | [`installation.md`](installation.md) |
| Operations (cron/jobs/backup) | [`operations.md`](operations.md) |
| Observability and health metrics (K8) | [`observability.md`](observability.md) |
| Incident response and recovery | [`incidents.md`](incidents.md) |
| Security (secrets, redaction, signing) | [`security.md`](security.md) |
| How to develop and extend | [`development.md`](development.md) |
| State handover | [`HANDOVER.md`](HANDOVER.md) |
