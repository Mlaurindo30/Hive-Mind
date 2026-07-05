# 14 — Model Gateway (canonical LLM execution layer)

> Tracks `specs/model-gateway-unification.md` (R1–R10, D1–D6). The
> gateway is the **sole entry point** for LLM execution in the Hive-Mind.
> The pre-unification "opt-in / opt-out" semantics documented in earlier
> revisions is replaced by `MODEL_GATEWAY_MODE` (`auto` / `on` / `off`)
> with `HIVE_FORCE_LEGACY_LLM=true` as the emergency bypass.

## What it is

The Model Gateway is the **only** layer in the Hive-Mind that executes
LLM calls. It reads the legacy role configuration (`HIVE_{ROLE}_PROVIDER`
/ `MODEL` / `FALLBACK*` in `.env`) via `core.auth.PROVIDERS_CONFIG`,
composes the result with optional overrides from `config/model-gateway.yaml`,
selects a `ModelProfile` by role + required capability, and dispatches
to a provider adapter. The `core/llm_client.call_llm_with_fallback`
function is now a thin wrapper that delegates here — it is no longer a
parallel execution path.

```
Hive-Mind call site (Promotion Layer, Dream Cycle, ...)
  → core/llm_client.call_llm_with_fallback  (wrapper, R4)
      → core/model_gateway.ModelGateway.from_combined_config()
      → core/model_registry.ModelRegistry.from_combined_config()
          reads:
            core/auth.PROVIDERS_CONFIG (base_url, env_var, auth_type)
            HIVE_{ROLE}_PROVIDER/MODEL/FALLBACK* (primary, fallback, fallback2)
            config/model-gateway.yaml (capabilities, cost_mode, role overrides)
      → integrations/model_gateway/<adapter>
          (openai_compatible / litellm / native / lmstudio /
           llamacpp / vllm / sglang)
```

## Vocabulary

- **Provider** (legacy, in `PROVIDERS_CONFIG`) — a logical backend name
  that the user configures in `.env` (e.g. `openai`, `ollama`,
  `gemini-cli`, `antigravity`, `deepseek`, `nvidia`, `qwen`,
  `omniroute`, `huggingface`, `google`, `gemini`, `anthropic`,
  `openrouter`, `ollama-cloud`, `lmstudio`). All 15 are representable in
  the registry; the mapping to runtime adapters is in
  `core/model_registry.PROVIDER_ADAPTER_HINT` (R2).
- **Adapter** (runtime, in `integrations/model_gateway/`) — the code
  that actually talks to a provider's HTTP API. Today: `native`,
  `openai_compatible`, `litellm`, `lmstudio`, `llamacpp`, `vllm`,
  `sglang`. The `lmstudio`/`llamacpp`/`vllm`/`sglang` adapters all
  reuse the same `OpenAICompatibleAdapter` class — the label only
  affects logging/health.
- **Model profile** (`ModelProfile` in `core/model_registry.py`) — one
  per `(role, level)` triple, with `level ∈ {primary, fallback,
  fallback2}`. Built from the `.env` + `PROVIDERS_CONFIG`; the YAML
  contributes overrides only.
- **Role** — a logical purpose a call site declares (`dreamer`,
  `graphify`, `vision`, `synthesis`, `claude_mem`, ...). A profile
  always belongs to exactly one role and one level.
- **Adapter hint** — the runtime adapter family a legacy provider maps
  to (e.g. `ollama → openai_compatible`, `gemini-cli → native`).
  `unsupported_explicit` is reported when no hint exists.

## Operating modes (R5)

`MODEL_GATEWAY_MODE` is the canonical switch. `MODEL_GATEWAY_ENABLED`
remains as a deprecated shim. `HIVE_FORCE_LEGACY_LLM` is the emergency
bypass.

| `MODEL_GATEWAY_MODE` | Behaviour | Legacy fallback? |
|---|---|---|
| `auto` *(default)* | Gateway via `ModelRegistry.from_combined_config()`. If the registry fails to validate or the gateway call fails, the wrapper logs a structured warning (`gateway_attempted=true, gateway_failed=true, legacy_fallback_used=true`) and delegates to `_legacy_call_llm_with_fallback`. | **Yes**, with explicit warning + telemetry. Never silent. |
| `on` | Gateway mandatory. If it fails end-to-end, the wrapper raises a structured `RuntimeError` and NEVER falls back. | **No.** Set `HIVE_FORCE_LEGACY_LLM=true` to bypass. |
| `off` *(deprecated)* | Gateway disabled, `_legacy_call_llm_with_fallback` runs directly. Emits a deprecation warning. | Always. |
| `HIVE_FORCE_LEGACY_LLM=true` | Emergency bypass — wins over every `MODEL_GATEWAY_MODE`. Emits `HIVE_FORCE_LEGACY_LLM=true is an emergency bypass; legacy path will be used` on stderr. | Always. |

`MODEL_GATEWAY_ENABLED` is still readable: `true` → `on` and
`false` → `off`, each emitting a `DeprecationWarning` that points
operators at the new key. New deployments should set
`MODEL_GATEWAY_MODE=auto` (the default) and let the gateway do its
work.

### Example env block

```bash
# config/model-gateway.env.example — copied into .env by install.sh
MODEL_GATEWAY_MODE=auto
# HIVE_FORCE_LEGACY_LLM=false   # emergency bypass; do NOT set by default
# MODEL_GATEWAY_ENABLED=false   # DEPRECATED; use MODEL_GATEWAY_MODE

# Optional overrides for the `models[]` block in the YAML.
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=
LLAMACPP_BASE_URL=http://localhost:8080/v1
VLLM_BASE_URL=http://localhost:8000/v1
SGLANG_BASE_URL=http://localhost:30000/v1
LITELLM_BASE_URL=http://localhost:4000/v1
LITELLM_API_KEY=
```

## Provider → adapter mapping (R2)

`core/model_registry.PROVIDER_ADAPTER_HINT` is the single source of
truth. The default mapping is:

| Legacy provider | Runtime adapter |
|---|---|
| `openai`, `openrouter`, `deepseek`, `nvidia`, `qwen`, `omniroute`, `ollama`, `ollama-cloud`, `anthropic` | `openai_compatible` |
| `google`, `gemini`, `huggingface` | `litellm` |
| `gemini-cli`, `antigravity` | `native` (legacy bridge) |
| `lmstudio` | `lmstudio` |
| `llamacpp`, `vllm`, `sglang` | dedicated (already shipped) |

Every provider in `PROVIDERS_CONFIG` is either mapped to an adapter or
surfaced as `unsupported_explicit` in `ModelRegistry.validate()`. New
providers are added by extending `PROVIDER_ADAPTER_HINT` and (if
needed) implementing a new `integrations/model_gateway/<name>_adapter.py`.

## Configuration sources

The registry combines three sources, in this priority order:

1. **`HIVE_{ROLE}_PROVIDER/MODEL` in `.env`** — primary, fallback,
   fallback2 per role. Inherited roles fall back to `HIVE_DREAMER_*`
   exactly as before.
2. **`PROVIDERS_CONFIG` in `core/auth.py`** — base URL, env var,
   auth type per legacy provider. Source of credentials and endpoint
   base, not a separate configuration.
3. **`config/model-gateway.yaml`** — OPTIONAL override layer:
   - `providers.<name>:` block for `adapter_hint`, `cost_mode`,
     `capabilities` overrides.
   - `roles.<name>:` block for `require`, `prefer`, `priority`,
     `cost_mode`, `context_window`, `max_output_tokens` overrides.
   - `roles.<name>.provider` / `model` are ignored unless
     `role_override: true` is set on that role. A warning is logged
     otherwise.
   - `models[]` block (legacy) for pre-registered backends (LM
     Studio, llama.cpp, vLLM, SGLang, LiteLLM proxy). Optional.

## What `setup-brain.py` does

`scripts/setup/setup-brain.py` continues to write the same
`HIVE_{ROLE}_PROVIDER/MODEL/FALLBACK*` env vars. After each
`save_env`, it now:

1. Emits a `setup_brain_role_configured` telemetry record (R9/R10).
2. Calls `ModelRegistry.from_combined_config().validate()` and prints
   a table with one row per `(role, level)` profile, including the
   resolved adapter and any `unsupported_explicit` reason.

This means the operator sees the gateway's view of their `.env` at the
end of every `setup-brain` save. A sample run (truncated):

```
Model Gateway — registry combinado (R9)
──────────────────────────────────────────
role      level      provider          model                   adapter              reason
──────────────────────────────────────────
dreamer   primary    ollama            qwen3:14b               openai_compatible
dreamer   fallback   openrouter        qwen/qwen3-32b          openai_compatible
dreamer   fallback2  openai            gpt-4o-mini             openai_compatible
──────────────────────────────────────────
```

## Adding a backend

All OpenAI-compatible backends follow the same recipe: start the
server, point the env var at it, flip `enabled: true` in
`config/model-gateway.yaml` (or leave the shipped profile as-is once
the default endpoint is reachable).

### LM Studio

```bash
lms get <model>          # download a model (none is bundled)
lms server start          # serves on http://localhost:1234/v1 by default
```
Then enable `lmstudio-local-json` in `config/model-gateway.yaml` (or
set `LMSTUDIO_BASE_URL`/`LMSTUDIO_MODEL` if non-default).

### llama.cpp

```bash
llama-server -m <model.gguf> --port 8080
```
Enable `llamacpp-local` / set `LLAMACPP_BASE_URL`/`LLAMACPP_MODEL`.

### LiteLLM (proxy mode only — see "Known limitations")

```bash
litellm --config litellm-config.yaml   # serves on http://localhost:4000/v1
```
Enable `litellm-proxy`, set `LITELLM_BASE_URL`/`LITELLM_API_KEY`/`LITELLM_MODEL`.

### vLLM

```bash
vllm serve <model>        # serves on http://localhost:8000/v1
```
Enable `vllm-local` / set `VLLM_BASE_URL`/`VLLM_MODEL`.

### SGLang

```bash
python -m sglang.launch_server --model-path <model>   # :30000/v1
```
Enable `sglang-local` / set `SGLANG_BASE_URL`/`SGLANG_MODEL`.

### Ollama (already shipped, enabled by default)

This project already runs Ollama locally for embeddings/vision (see
`docs/04-infrastructure.md`). It exposes the same OpenAI-compatible
`/v1` surface, so `config/model-gateway.yaml` ships an
**enabled-by-default** `ollama-openai-compat` profile using it — no
extra server to start. `tests/model_gateway/test_openai_compat_real.py`
exercises this backend for real in CI/dev.

## Running the benchmark CLI

```bash
python scripts/analytics/model_benchmark.py --list
python scripts/analytics/model_benchmark.py --health
python scripts/analytics/model_benchmark.py --role validator --prompt "Say OK"
python scripts/analytics/model_benchmark.py --role validator --prompt "Return JSON" \
    --schema tests/fixtures/simple_schema.json
python scripts/analytics/model_benchmark.py --all --output logs/model-benchmark.json
```

`--all` runs a small fixed structured-output battery against every
*enabled* profile and reports `success_rate`, `json_valid_rate`,
`schema_valid_rate`, `tool_call_valid_rate`, `latency_p50`/`p95`,
`tokens_per_second`, `cost_estimate`, `fallback_rate`, `error_rate`
per model. A metric that doesn't apply to a given model (e.g.
`tool_call_valid_rate` when the model has no `tool_calling`
capability) is reported as `null`, never a fabricated `0`/`1`.

## Interpreting health

`ModelGateway.health()` (surfaced at `sinapse-write.py health`, the
authenticated `/api/v1/metrics` REST endpoint, and the public
`/api/v1/health` endpoint) returns:

```json
{
  "enabled": true,
  "models_total": 7,
  "healthy": 2,
  "unhealthy": 5,
  "default_roles": {"validator": "ollama-openai-compat", "dreamer": "existing-dreamer"}
}
```

`enabled: false` is reported explicitly (not omitted) when the gateway
is off — a disabled gateway skips network probes entirely, so this
health check stays cheap.

## Configuring fallback (R6)

Each role resolves to a `(primary, fallback, fallback2)` chain in
that strict order, mirroring the legacy `core/llm_client.py`
behaviour:

- **Explicit and logged** — every attempt is recorded via
  `core/model_telemetry.record_call` (legacy) or
  `record_gateway_attempt` / `record_gateway_failure` /
  `record_legacy_fallback_used` (gateway).
- **Skips disabled profiles** automatically.
- **Detects cycles** in YAML `fallback_chain` and stops rather than
  looping forever.
- **Never returns a fabricated success** — if every model in the
  chain fails, the gateway returns `ok=False` with a classified
  `error` and `error_chain`; the legacy path raises `LLMChainFailure`
  preserving `primary_exc` and `fallback_exc`.
- **Validation errors never trigger fallback** (R6 §1) — the
  caller retries on the same model up to `max_retries`, then
  raises `LLMValidationError`.
- **Auth / 401 / 403 / 402 / balance errors bypass retries** and go
  directly to the next pair (R6 §3).
- **429 / 5xx / timeouts** retry with exponential backoff (cap 8s),
  then fall back (R6 §2 / §4).

## Avoiding secret leakage (R10)

- `core/model_telemetry.record_call` accepts only metadata fields —
  its signature has no `prompt`/`content`/`response` parameter, so a
  raw payload cannot reach it even by mistake.
- The new `record_gateway_attempt` / `record_gateway_failure` /
  `record_legacy_fallback_used` / `record_setup_brain_role_configured`
  hooks follow the same discipline: no payload, secrets redacted
  via `core.redactor.redact_for_export` before any write.
- API keys are resolved from `ModelProfile.api_key_env` at call time
  (`profile.api_key()`) — never stored on the profile object, never
  logged.

## Going back to the legacy `llm_client`

Two escape hatches, both intentional:

1. **Per-process** — `HIVE_FORCE_LEGACY_LLM=true` bypasses the
   gateway entirely and runs `_legacy_call_llm_with_fallback` for
   every call. This is the recovery path when the gateway is
   misbehaving in production. It always emits a warning on stderr.
2. **Whole mode** — `MODEL_GATEWAY_MODE=off` (deprecated) disables
   the gateway for the process. Same warning, same effect.

The `core/llm_client.py` legacy path is preserved verbatim as
`_legacy_call_llm_with_fallback` so the contract for callers
(`LLMValidationError`, `LLMChainFailure` with `chain`,
`primary_exc`, `fallback_exc`) is unchanged.

## Known limitations

- **LiteLLM direct-SDK mode is out of scope.** Only the HTTP proxy
  mode is implemented in this build; the `litellm` Python package is
  not a project dependency.
- **Streaming is not implemented.** `capabilities.streaming` is
  recorded for future use, but `chat()` always returns a complete
  response, even for a backend that supports streaming.
- **JSON Schema → Pydantic conversion is best-effort and flat.**
  `core/model_gateway.json_schema_to_model()` supports top-level
  `object` schemas with primitive-typed properties (`string`,
  `integer`, `number`, `boolean`, `array`, `object`). Nested
  object/array *internals* are accepted as opaque `dict`/`list`, not
  recursively validated. Complex nested schemas may validate more
  loosely than a full JSON Schema validator would.
- **Vision is delegated to the legacy path (R8).** When a caller
  passes `image_path` to `call_llm_with_fallback`, the wrapper emits
  `legacy_vision_bridge_used=true` and routes the call through
  `_legacy_call_llm_with_fallback`. The gateway already exposes
  `capabilities.vision` on `ModelProfile` to prepare a future
  migration, but no adapter has a native vision path yet — the
  legacy `core/llm_client.call_llm_structured` knows how to
  inline-encode images for OpenAI Vision / Gemini, and we keep using
  that until adapter-level support lands.
- **SSRF hardening is basic, not exhaustive.**
  `integrations/model_gateway/openai_compatible_adapter.py`'s
  `_reject_unsafe_endpoint()` blocks non-http(s) schemes and the
  known AWS/GCP metadata addresses, and warns on `0.0.0.0`. **DNS-
  rebinding protection is NOT implemented.** Endpoints come from
  `config/model-gateway.yaml`/env vars (operator-controlled, not
  end-user input), which is the main mitigating factor.
- **Tool-calling is declared but not exercised end-to-end.** Profiles
  can set `capabilities.tool_calling: true` and the OpenAI-compatible
  adapter's `chat()` accepts `tool_calls` in a response, but no call
  site in this build passes `tools`/`tool_choice` through.
- **Migration shim**: `MODEL_GATEWAY_ENABLED` is still readable but
  deprecated. It will be removed in a future release; new
  deployments MUST set `MODEL_GATEWAY_MODE`.
