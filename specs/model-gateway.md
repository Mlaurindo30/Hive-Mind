# Model Gateway + Capability Registry

## Goal

The Hive-Mind currently calls LLMs through `core/llm_client.py`, which hardcodes
provider-specific logic per call site. Priority 1 of the evolution roadmap adds a
**Model Gateway + Capability Registry**: a thin routing layer that selects a model
by role and required capability (structured output, tools, vision, embeddings,
rerank, cost mode, health, fallback) instead of by provider-specific code, so new
inference backends (LM Studio, llama.cpp, vLLM, SGLang, LiteLLM proxy, any
OpenAI-compatible endpoint) can be onboarded via config, not core changes. This
build is incremental and additive: the legacy `core/llm_client.py` path keeps
working unchanged and is the default; the gateway is opt-in via
`MODEL_GATEWAY_ENABLED=false` by default.

## Requirements

### Capability Registry (`core/model_registry.py`)

1. The module MUST define `ModelProvider` as a `Literal` of exactly: `native`,
   `litellm`, `openai_compatible`, `lmstudio`, `llamacpp`, `vllm`, `sglang`.
2. The module MUST define a `ModelCapabilities` dataclass with boolean fields:
   `chat` (default `True`), `streaming`, `tool_calling`, `structured_output`,
   `vision`, `embeddings`, `rerank`, `json_schema`, `regex_schema`, `ebnf_schema`
   (all other defaults `False`).
3. The module MUST define a `ModelProfile` dataclass with fields: `id: str`,
   `provider: ModelProvider`, `model: str`, `endpoint: Optional[str]`,
   `api_key_env: Optional[str]`, `context_window: int`, `max_output_tokens: int`,
   `cost_mode: Literal["local", "paid", "unknown"] = "unknown"`,
   `input_cost_per_1k: Optional[float] = None`,
   `output_cost_per_1k: Optional[float] = None`, `priority: int = 100`,
   `enabled: bool = True`, `roles: list[str]`, `capabilities: ModelCapabilities`,
   `fallback_chain: list[str]`.
4. The module MUST define `class ModelRegistry` with:
   - `list_models() -> list[ModelProfile]` — all profiles, in config order.
   - `get(model_id: str) -> ModelProfile` — raises a clear, typed error if the
     id does not exist.
   - `select(role: str, require: dict | None = None, prefer: dict | None = None) -> ModelProfile`
     — filters to `enabled=True` models whose `roles` contains `role` (or the
     literal role `"fallback"` if no role-specific model exists) AND whose
     `capabilities` satisfy every truthy key in `require` (e.g.
     `{"structured_output": True}` excludes any profile with
     `capabilities.structured_output == False`). Among survivors, MUST break
     ties by ascending `priority` (lower priority number wins), then by
     `prefer` hints (e.g. `{"cost_mode": "local"}` moves matching profiles
     ahead of non-matching ones with equal priority). MUST raise a typed,
     clear error (not a generic `Exception`) when no model satisfies the
     role+require combination.
   - `validate() -> list[dict]` — returns one dict per configuration problem
     found (duplicate `id`, unknown `provider`, missing `roles`, `cost_mode:
     paid` without both cost fields, etc.); returns `[]` when the config is
     clean. MUST NOT raise — this is a diagnostic, not a loader.
5. `ModelRegistry` MUST load from `config/model-gateway.yaml` by a
   `ModelRegistry.from_yaml(path: str) -> ModelRegistry` constructor (or
   equivalent factory) that expands `${VAR}` and `${VAR:-default}` shell-style
   environment variable references in every string field before dataclass
   construction.
6. Loading a missing YAML file, or a YAML file that fails to parse, MUST raise
   a clear, typed error identifying the path and the underlying cause — never
   a silent empty registry.

### Model Gateway (`core/model_gateway.py`)

7. The module MUST define `class ModelGateway` with a `from_config() -> ModelGateway`
   classmethod that reads `MODEL_GATEWAY_CONFIG` (default
   `config/model-gateway.yaml`) and constructs the underlying `ModelRegistry`.
8. `ModelGateway` MUST expose `chat`, `structured`, `embed`, `rerank`, `health`
   with exactly the signatures given in the request (§5.2), all returning one
   of `ModelResponse`, `EmbeddingResponse`, `RerankResponse`, or `dict` (for
   `health`).
9. `ModelResponse` MUST be a dataclass with exactly: `ok: bool`,
   `content: str | dict | None`, `model_id: str`, `provider: str`,
   `endpoint: str | None`, `latency_ms: float`, `input_tokens: int | None`,
   `output_tokens: int | None`, `cost_estimate: float | None`,
   `fallback_used: bool`, `fallback_chain: list[str]`, `error: str | None`,
   `raw: dict | None = None`. `EmbeddingResponse`/`RerankResponse` follow the
   same shape (`ok`, provenance fields, `error`) plus their own payload
   (`vectors: list[list[float]]` / `results: list[dict]` with per-document
   scores).
10. `chat()`/`structured()`/`embed()`/`rerank()` MUST resolve a model via
    `ModelRegistry.select()` (or use `model_id` directly if given, bypassing
    selection but still validating `enabled=True`), dispatch to the matching
    provider adapter, measure wall-clock `latency_ms` around the adapter call,
    and populate `ModelResponse` accordingly.
11. On adapter failure, `chat()`/`structured()` MUST walk the resolved
    profile's `fallback_chain` in order, retrying with each fallback profile,
    and MUST set `fallback_used=True` and populate `fallback_chain` with the
    ids actually attempted in the final `ModelResponse`. If every profile in
    the chain fails, MUST return `ok=False` with a non-empty, redacted
    `error` string — MUST NOT raise an unhandled exception and MUST NOT
    return `ok=True` with a fabricated or empty `content` (no silent
    success).
12. `structured()` MUST validate the adapter's returned content against the
    given JSON Schema (`schema` argument) before returning `ok=True`; a
    response that parses as JSON but violates the schema MUST be treated as a
    failure for that attempt (eligible for fallback), with `error` describing
    the schema violation.
13. `health()` MUST return, at minimum: `enabled` (bool, whether the gateway
    itself is active per `MODEL_GATEWAY_ENABLED`), `models_total` (int),
    `healthy` (int), `unhealthy` (int), and `default_roles` (dict mapping each
    role that appears in the config to the id of the model `select()` would
    currently pick for it).

### Provider adapters (`integrations/model_gateway/`)

14. `integrations/model_gateway/base.py` MUST define `class BaseModelAdapter`
    with a `provider: str` class attribute and methods `chat`, `structured`,
    `embed`, `rerank`, `health`, each accepting `(self, profile: ModelProfile, ...)`
    and returning the corresponding response dataclass. A capability not
    supported by a given adapter/profile (e.g. `embed()` on a chat-only
    profile) MUST return `ok=False` with an `error` naming the missing
    capability — MUST NOT raise `NotImplementedError` uncaught into caller
    code.
15. `integrations/model_gateway/openai_compatible_adapter.py` MUST implement
    `BaseModelAdapter` against `POST {endpoint}/chat/completions`, and MUST
    additionally support `POST {endpoint}/embeddings` and
    `POST {endpoint}/rerank` when the profile's capabilities claim them, plus
    `response_format` (JSON Schema) for `structured()` and `tools`/
    `tool_choice` for tool-calling profiles. This adapter is reused (via
    `provider` string dispatch, not subclassing per backend) for
    `lmstudio`, `llamacpp`, `vllm`, and `sglang` profiles, since all four are
    OpenAI-compatible over HTTP; the `provider` field on `ModelProfile` is
    used only for logging/health labeling and to allow a future backend-
    specific override without changing the registry contract.
16. `integrations/model_gateway/litellm_adapter.py` MUST implement
    `BaseModelAdapter` by calling a LiteLLM **proxy** over its OpenAI-
    compatible HTTP surface (same request/response shape as
    `openai_compatible_adapter.py`) — the direct-SDK mode is explicitly out
    of scope for this build (§ Out of Scope).
17. Every HTTP-based adapter MUST set the request timeout from
    `timeout_s` (call-level override, else `config/model-gateway.yaml`'s
    `defaults.timeout_s`) and MUST catch connection errors, timeouts,
    non-2xx responses, and non-JSON response bodies, converting each into an
    `ok=False` `ModelResponse`/`EmbeddingResponse`/`RerankResponse` with a
    classified `error` string (e.g. `"timeout"`, `"connection_refused"`,
    `"auth_error"`, `"rate_limited"`, `"malformed_response"`) — never an
    unhandled exception propagating to the gateway.

### Configuration

18. `config/model-gateway.yaml` MUST exist with `version: 1`, a `defaults`
    block (`timeout_s`, `max_retries`, `fallback_enabled`, `telemetry_enabled`),
    and a `models` list. MUST ship with at least the four example profiles
    from the request (§6.1): `existing-dreamer` (native), `lmstudio-local-json`,
    `llamacpp-local`, `litellm-proxy`) as a working, documented starting
    point — profiles MAY be `enabled: false` if the corresponding backend is
    not present on a given machine.
19. `.env.example` MUST gain the block from §6.2 verbatim (env var names,
    defaults, comments), appended in a clearly labeled new section.
20. `config/sinapse.yaml` MUST gain a `model_gateway` section per §6.3
    (`enabled: false`, `config: config/model-gateway.yaml`,
    `fail_open_to_legacy_llm_client: true`, `telemetry: true`).
21. With `MODEL_GATEWAY_ENABLED` unset or `false` (the shipped default),
    every existing call path through `core/llm_client.py` MUST behave
    exactly as before this change — verified by the full existing test
    suites passing unmodified in behavior (not just unmodified test files).

### Core integration

22. `core/llm_client.py` (or a new `core/llm_runtime.py` wrapper called from
    it) MUST check `MODEL_GATEWAY_ENABLED` at call time and route to
    `ModelGateway.from_config()` when true, else execute the existing legacy
    logic unchanged. The routing check MUST be a single, easily greppable
    conditional — not scattered per call site.
23. `core/knowledge/promotion.py` and `scripts/dream/dream_cycle.py` call
    sites that invoke an LLM SHOULD be updated to pass a `role` (one of
    `distiller`, `validator`, `router`, `dreamer`, `synthesis`, matching
    existing usage) so that, once the gateway is enabled, those calls
    resolve through it. This is a non-breaking, additive parameter — the
    call sites' behavior when the gateway is disabled MUST be unchanged.
24. `RetrievalRouter` (`core/retrieval/router.py`) MUST NOT be modified in
    this build beyond, at most, a passthrough `role="reranker"` /
    `capability.rerank=True` constant/comment marking the future integration
    point. No reranker call is wired in this build.
25. `scripts/services/sinapse-write.py health`, `sinapse-api.py`'s
    `/api/v1/health`, MUST include a `model_gateway` object shaped per §7.4
    when the gateway is configured (even if `enabled: false` — report
    `enabled: false` explicitly, not omit the key). `scripts/health/k8_gate.py`
    integration is optional (only if it doesn't change the gate's pass/fail
    semantics for the existing K8 metrics).

### Telemetry (`core/model_telemetry.py`)

26. The module MUST expose a function (e.g. `record_call(...)`) that accepts
    the fields listed in §8 (`request_id`, `workspace_id`, `role`,
    `selected_model_id`, `provider`, `endpoint`, `capabilities_required`,
    `fallback_used`, `latency_ms`, `input_tokens`, `output_tokens`,
    `cost_estimate`, `error_type`) and MUST NOT accept or persist a raw
    prompt/response payload field.
27. Before any error string or logged payload leaves `model_telemetry.py` or
    an adapter, it MUST pass through `core.redactor.redact_for_export`. A
    provider error message that happens to echo back a request header
    (e.g. an auth error including the attempted `Authorization` value) MUST
    NOT leak the raw secret into logs or `ModelResponse.error`.

### Benchmark CLI (`scripts/analytics/model_benchmark.py`)

28. MUST support `--list` (print all configured profiles + capabilities),
    `--health` (print `ModelGateway.health()` as JSON), `--role <role>
    --prompt <text> [--schema <path>]` (single ad-hoc call, structured if
    `--schema` given), and `--all --output <path>` (run every enabled
    profile through a small fixed battery and write a JSON report).
29. The `--all` report MUST include, per profile that was actually
    reachable: `success_rate`, `json_valid_rate`, `schema_valid_rate`,
    `tool_call_valid_rate`, `latency_p50`, `latency_p95`,
    `tokens_per_second`, `cost_estimate`, `fallback_rate`, `error_rate`.
    Metrics that don't apply to a profile (e.g. `tool_call_valid_rate` for a
    profile without `tool_calling`) MUST be `null`, not fabricated as `0` or
    `1`.

## Out of Scope

- **LiteLLM direct-SDK mode.** Only the HTTP proxy mode is implemented; the
  `litellm` Python package is not added as a dependency in this build.
- **Full SSRF hardening.** Only the basic checks in Edge Cases (block
  `file://`/`ftp://`, block the AWS/GCP metadata IPs/hostnames, warn on
  `0.0.0.0`) are required. DNS-rebinding protection for "localhost masked via
  a remote A record" is explicitly acknowledged as unimplemented; document
  the gap, do not attempt a partial fix that could give false confidence.
- **Wiring the reranker into `RetrievalRouter`.** Only the capability/role
  naming convention is reserved (§ Requirement 24); no retrieval behavior
  changes.
- **Priorities 2–6** (Retrieval Quality Gate, Parser Router, full
  observability/evals, MCP Security Broker, DSPy prompt optimization) — no
  code for these, though the gateway's `role`/`require` vocabulary MAY be
  referenced by name in docs as a forward-looking note.
- **Streaming responses.** `capabilities.streaming` is recorded in the
  registry for future use, but `ModelGateway.chat()` in this build always
  returns a complete, non-streamed `ModelResponse` — no SSE/streaming
  transport is implemented even for adapters whose backend supports it.
- **Automatic cost tracking against a live billing API.** `cost_estimate` is
  computed from the static `input_cost_per_1k`/`output_cost_per_1k` config
  fields times observed token counts — no external pricing lookup.

## Edge Cases & Error Handling

Each entry names the input/state, then the expected response — this list is
authoritative and MUST all be covered by tests (§ Definition of Done, D16–D17):

1. `config/model-gateway.yaml` does not exist → `ModelRegistry.from_yaml` /
   `ModelGateway.from_config` raise a clear, typed error naming the path.
2. YAML present but malformed → clear, typed error naming the parse failure.
3. A model has `enabled: false` → `select()` never returns it, even if it is
   otherwise the best match.
4. A `role` has no matching enabled model → `select()` raises a typed error
   naming the role and, if any, the closest disabled/unmatched candidates.
5. `require` names a capability key that does not exist on
   `ModelCapabilities` → typed error at call time, not a silent no-op match.
6. Endpoint offline (connection refused) → adapter returns `ok=False`,
   `error="connection_refused"` (or equivalent classified string); gateway
   attempts `fallback_chain` if configured.
7. Request exceeds `timeout_s` → `ok=False`, `error="timeout"`.
8. Auth failure (401/403) → `ok=False`, `error` classified as an auth error,
   and the attempted credential value MUST NOT appear in `error` or logs.
9. Rate limited (429) → `ok=False`, `error` classified as rate-limit; MUST
   NOT be silently retried in an unbounded loop (respect `max_retries`).
10. Backend returns HTML instead of JSON (e.g. a misconfigured endpoint
    hitting a login page) → `ok=False`, `error="malformed_response"`, no
    exception escapes the adapter.
11. Backend returns JSON without a `choices` key → same as above.
12. `structured()` receives non-JSON content from the backend → treated as a
    failure for that attempt, eligible for fallback.
13. `structured()` receives syntactically valid JSON that violates the given
    schema → treated as a failure for that attempt (Requirement 12).
14. Tool call returned without an `arguments` field → `ok=False` for that
    call with a descriptive `error`, not a `KeyError`.
15. Tool call `arguments` is a string that fails to parse as JSON →
    `ok=False` with a descriptive `error`, not an unhandled exception.
16. `embed()` returns vectors whose dimension does not match what the
    profile declares (if declared) → `ok=False`, `error` naming the
    mismatch — never silently returned as if correct.
17. `rerank()` returns a different number of scores than documents supplied
    → `ok=False`, `error` naming the count mismatch.
18. A `fallback_chain` points back to a model already tried in the same
    call (a cycle) → the gateway MUST detect this and stop, returning
    `ok=False` rather than looping.
19. A `fallback_chain` entry references a model with `enabled: false` →
    skipped (treated as if absent from the chain), not attempted.
20. Any raised exception message from an adapter or the gateway itself that
    could contain an API key MUST be passed through `core.redactor` before
    reaching `ModelResponse.error` or any log line.
21. A prompt supplied by the caller happens to contain a string that looks
    like a secret (e.g. a fake `api_key=...` in test fixture text) → the
    prompt itself is not required to be redacted before being sent to the
    provider (that would break real usage); only gateway/adapter **logs and
    error output** are redacted (Requirement 27 is about telemetry/errors,
    not about mutating the user's actual prompt content).
22. `endpoint` configured without a `/v1` (or other required) path suffix →
    documented as a configuration responsibility; the adapter MAY normalize
    a trailing-slash-only case but MUST NOT silently guess unrelated paths.
23. `max_tokens` requested exceeds the profile's `max_output_tokens` →
    adapter clamps to `max_output_tokens` and notes this in `raw`, rather
    than sending an unbounded request or failing outright.
24. `context_window` insufficient for the given messages → `ok=False` with a
    descriptive `error` before the request is sent (client-side check), when
    a token-counting utility is available; if not available, this MAY be
    deferred to the backend's own error (still must classify per Edge Case 10).
25. `cost_mode: paid` without both `input_cost_per_1k`/`output_cost_per_1k`
    set → `ModelRegistry.validate()` flags this; `cost_estimate` on
    `ModelResponse` is `None` for that profile rather than a fabricated 0.
26. `provider` value not in the `ModelProvider` literal → `validate()` flags
    it; `from_yaml` raises rather than silently defaulting to a provider.
27. Two profiles share the same `id` → `from_yaml` raises a typed
    "duplicate model id" error at load time.
28. A model has an empty `roles` list → it is never selected by `select(role=...)`
    (no implicit "matches everything") — it can still be targeted directly
    via `model_id=`.
29. `capabilities.streaming: true` on a profile whose adapter does not
    implement streaming in this build → `chat()` still returns a complete
    non-streamed response (per Out of Scope); this is not treated as an
    error, since streaming is not exercised in this build.
30. `MODEL_GATEWAY_ENABLED=false` (or unset) → `core/llm_client.py`'s
    existing behavior is used, unchanged; `ModelGateway` is never
    constructed on that path.
31. `MODEL_GATEWAY_ENABLED=true` but `config/model-gateway.yaml` (or the
    path in `MODEL_GATEWAY_CONFIG`) is missing → per
    `sinapse.yaml`'s `fail_open_to_legacy_llm_client: true`, the call falls
    back to the legacy `core/llm_client.py` path rather than raising into
    the caller; this fallback MUST be logged at warning level (not silent).
32. `health()` when some but not all configured models are reachable →
    `healthy`/`unhealthy` counts reflect exactly that split; `default_roles`
    still resolves using only the healthy subset, and falls back further if
    the top pick for a role is unhealthy.
33. `health()` when every configured model is unreachable → `healthy: 0`,
    `unhealthy: models_total`, `default_roles` MAY be empty; MUST NOT raise.

## Definition of Done

- [ ] D1. `core/model_registry.py` exists and implements Requirements 1–6.
- [ ] D2. `core/model_gateway.py` exists and implements Requirements 7–13.
- [ ] D3. `integrations/model_gateway/{base,openai_compatible_adapter,litellm_adapter}.py`
      exist and implement Requirements 14–17. (`lmstudio_adapter.py`,
      `llamacpp_adapter.py`, `vllm_adapter.py`, `sglang_adapter.py` MAY be
      thin modules that re-export/configure the OpenAI-compatible adapter
      with a fixed `provider` label, per Requirement 15 — they do not need
      independent HTTP logic.)
- [ ] D4. `config/model-gateway.yaml` exists per Requirement 18.
- [ ] D5. `.env.example` updated per Requirement 19.
- [ ] D6. `config/sinapse.yaml` updated per Requirement 20.
- [ ] D7. Health endpoints show `model_gateway` per Requirement 25.
- [ ] D8. `scripts/analytics/model_benchmark.py` exists per Requirements 28–29.
- [ ] D9. `pytest tests/unit/ tests/integration/ tests/e2e/ -q` and
      `bash tests/smoke/test_smoke.sh` pass with `MODEL_GATEWAY_ENABLED`
      unset — proving the legacy path is unaffected (Requirement 21).
- [ ] D10. A unit test demonstrates `select()` choosing a model by role AND
      by a `require` capability filter together (e.g. role=`validator` +
      `structured_output=True` picks a different model than role=`validator`
      alone when only one candidate has that capability).
- [ ] D11. A unit or contract test demonstrates `structured()` rejecting a
      schema-violating response and returning `ok=False` (Requirement 12).
- [ ] D12. A test demonstrates `fallback_chain` being walked and
      `fallback_used=True`/`fallback_chain` populated on the response
      (Requirement 11), including the "all fallbacks exhausted" case
      returning `ok=False` rather than raising.
- [ ] D13. A test demonstrates a classified, non-generic `error` string for
      at least: timeout, connection-refused, malformed-response, and
      schema-invalid (Edge Cases 7, 6, 10, 13).
- [ ] D14. A test demonstrates that an adapter/gateway error containing a
      fake secret never reaches `ModelResponse.error` unredacted
      (Requirement 27, Edge Case 20).
- [ ] D15. At least one **real** backend is exercised by a `tests/real/`
      test that is not skipped in this environment. Given no dedicated LM
      Studio/llama.cpp/vLLM/SGLang/LiteLLM server was running in this
      environment at spec time, this MUST be satisfied by one of: (a)
      starting LM Studio's server via the installed `lms` CLI and running
      `tests/real/test_model_gateway_lmstudio.py` against it, or (b)
      exercising the `openai_compatible` adapter for real against Ollama's
      native OpenAI-compatible endpoint (`http://localhost:11434/v1`,
      confirmed running) as a stand-in `openai_compatible` profile. The
      other real-backend test files (llamacpp, litellm, vllm, sglang) MUST
      exist and SKIP with an explicit, named reason when their target is
      not configured — never a false pass.
- [ ] D16. All new unit tests listed in the request (§10.1–10.2) exist and
      pass: `test_model_registry.py`, `test_model_gateway_selection.py`,
      `test_model_gateway_config.py`, `test_model_gateway_response_contract.py`,
      `test_model_gateway_redaction.py`, `test_model_adapters_contract.py`.
- [ ] D17. `tests/e2e/test_model_gateway_e2e.py` exists and passes, covering
      at minimum: gateway-disabled-legacy-still-works,
      gateway-enabled-selects-by-role, structured-validator-returns-valid-json,
      fallback-used-and-logged, health-includes-model_gateway,
      telemetry-omits-raw-prompt.
- [ ] D18. Full regression suite passes: `python -m compileall -q core
      scripts plugins integrations`, `pytest tests/unit/ -q`,
      `pytest tests/integration/ -q`, `pytest tests/e2e/ -q`,
      `bash tests/run_real_knowledge.sh`, `bash tests/smoke/test_smoke.sh` —
      with zero regressions in write path, Dream Cycle, DocumentPipeline,
      workspace isolation, redactor, MCP tools, or the K8 gate.
- [ ] D19. `docs/13-model-gateway.md` created per §13's content list, and
      `docs/01-architecture.md`, `docs/04-infrastructure.md`,
      `docs/installation.md`, `docs/README.md`, `AGENTS.md` each gain at
      least one accurate reference to the Model Gateway's existence and
      disabled-by-default status.
- [ ] D20. Final report delivered per the 15-point structure in the
      request's §16, including `git diff --stat`, `git status --short`, and
      an explicit `OK`/`PARCIAL`/`FALHA` verdict — never `OK` if any of the
      request's §16 disqualifying conditions hold (legacy path broken, zero
      real backends tested, structured output not schema-validated, silent
      fallback, a secret in a log, an existing test broken, or health
      missing `model_gateway`).
