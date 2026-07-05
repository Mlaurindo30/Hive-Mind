# 14 — Model Gateway + Capability Registry (Priority 1)

> Numbered 14, not 13: `docs/13-slo-and-observability.md` already exists
> locally (untracked). This is the first tracked doc after `12-*`.

## What it is

The Model Gateway is a routing layer that picks an LLM by **role** and
**required capability** (structured output, tools, vision, embeddings,
rerank, cost mode, health, fallback) instead of hardcoded provider logic
per call site. It sits in front of the existing `core/llm_client.py` and is
**disabled by default** — with `MODEL_GATEWAY_ENABLED` unset or `false`,
every LLM call behaves exactly as before this feature existed.

```
Hive-Mind call site (Promotion Layer, Dream Cycle, ...)
  → core/llm_client.py (unchanged legacy path, or routes to the gateway)
  → core/model_gateway.py  (ModelGateway: selection, fallback, telemetry)
  → core/model_registry.py (ModelRegistry: role/capability → ModelProfile)
  → integrations/model_gateway/<provider>_adapter.py
      → native          (wraps the existing core/llm_client.py role config)
      → openai_compatible / lmstudio / llamacpp / vllm / sglang
          (one shared adapter class — all four speak the same /v1 HTTP API)
      → litellm          (HTTP proxy mode only)
```

## Vocabulary

- **Provider** — which adapter family handles the call
  (`native`, `openai_compatible`, `lmstudio`, `llamacpp`, `vllm`, `sglang`,
  `litellm`). `lmstudio`/`llamacpp`/`vllm`/`sglang` all reuse the exact same
  `OpenAICompatibleAdapter` class — the label only affects logging/health,
  since all four expose the identical OpenAI `/v1` HTTP surface.
- **Adapter** — the code in `integrations/model_gateway/` that actually
  talks to a provider's HTTP API (or, for `native`, calls into
  `core/llm_client.py` directly).
- **Model profile** (`ModelProfile` in `core/model_registry.py`) — one
  entry in `config/model-gateway.yaml`: id, provider, endpoint, context
  window, cost, priority, roles, capabilities, fallback chain.
- **Role** — a logical purpose a call site declares (`dreamer`, `validator`,
  `router`, `distiller`, `synthesis`, `coding`, `fallback`, ...). A profile
  can serve multiple roles. `ModelRegistry.select(role, require, prefer)`
  picks the best enabled profile for a role, optionally filtered by
  required capabilities and tie-broken by `prefer` hints.

## Enabling / disabling

```bash
# .env (see config/model-gateway.env.example for the full block)
MODEL_GATEWAY_ENABLED=false          # default: gateway off, legacy path only
MODEL_GATEWAY_CONFIG=config/model-gateway.yaml
```

O bloco de variáveis do Model Gateway fica em
`config/model-gateway.env.example` porque `.env.example` não pôde ser
alterado nesta sessão. O install/documentation deve apontar para esse
arquivo como fonte canônica do exemplo de ambiente do Model Gateway.

Also mirrored in `config/sinapse.yaml`'s `model_gateway:` section
(`enabled`, `config`, `fail_open_to_legacy_llm_client`, `telemetry`) —
informational for humans; the actual runtime switch is the
`MODEL_GATEWAY_ENABLED` environment variable, read by
`core.model_gateway.gateway_enabled()`.

Flip it on:

```bash
export MODEL_GATEWAY_ENABLED=true
```

To go back to the legacy path, unset it (or set it to `false`) — no other
change is needed. If the gateway is enabled but `config/model-gateway.yaml`
is missing/broken, or a call fails end-to-end through every fallback,
`core/llm_client.py` **fails open** to the exact legacy behavior and logs a
warning to stderr (`[ModelGateway] ... falling back to legacy llm_client`)
— it never raises a new kind of error into an existing caller.

## Adding a backend

All four OpenAI-compatible backends follow the same recipe: start the
server, point the env var at it, flip `enabled: true` in
`config/model-gateway.yaml` (or leave the shipped profile as-is once the
default endpoint is reachable).

### LM Studio

```bash
lms get <model>          # download a model (none is bundled)
lms server start          # serves on http://localhost:1234/v1 by default
```
Then enable `lmstudio-local-json` in `config/model-gateway.yaml` (or set
`LMSTUDIO_BASE_URL`/`LMSTUDIO_MODEL` if non-default).

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
`docs/04-infrastructure.md`). It exposes the same OpenAI-compatible `/v1`
surface, so `config/model-gateway.yaml` ships an **enabled-by-default**
`ollama-openai-compat` profile using it — no extra server to start. This is
also the backend `tests/real/test_model_gateway_openai_compatible.py`
exercises for real in CI/dev, since it needs no separate setup.

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
`tokens_per_second`, `cost_estimate`, `fallback_rate`, `error_rate` per
model. A metric that doesn't apply to a given model (e.g.
`tool_call_valid_rate` when the model has no `tool_calling` capability) is
reported as `null`, never a fabricated `0`/`1`.

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

`enabled: false` is reported explicitly (not omitted) when the gateway is
off — a disabled gateway skips network probes entirely, so this health
check stays cheap.

## Configuring fallback

Each `ModelProfile.fallback_chain` is an ordered list of model ids tried,
in order, after the primary fails. Fallback:

- is **explicit and logged** — every attempt (primary + each fallback) is
  recorded via `core/model_telemetry.py`, and the final `ModelResponse`
  reports `fallback_used`/`fallback_chain` with every id actually tried;
- **skips disabled models** in the chain;
- **detects cycles** (a chain that loops back to an already-tried model)
  and stops rather than looping forever;
- **never returns a fabricated success** — if every model in the chain
  fails, the gateway returns `ok=False` with a classified `error`, never an
  unhandled exception and never a silent `ok=True`.

## Avoiding secret leakage

- `core/model_telemetry.record_call()` accepts only metadata fields — its
  signature has no `prompt`/`content`/`response` parameter, so a raw
  payload cannot reach it even by mistake.
- Every `error` string (from an adapter's own classification, or from an
  unexpected exception message) is passed through
  `core.redactor.redact_for_export` before it reaches `ModelResponse.error`
  or a telemetry log line.
- API keys are resolved from `ModelProfile.api_key_env` at call time
  (`profile.api_key()`) — never stored on the profile object, never logged.

## Going back to the legacy `llm_client`

Set `MODEL_GATEWAY_ENABLED=false` (or unset it) — that's the entire
rollback. No code path is removed; `core/llm_client.py`'s
`call_llm_with_fallback` checks the flag at the top of the function and,
when off, runs exactly the code that existed before this feature.

## Known limitations

- **LiteLLM direct-SDK mode is out of scope.** Only the HTTP proxy mode is
  implemented in this build; the `litellm` Python package is not a project
  dependency.
- **Streaming is not implemented.** `capabilities.streaming` is recorded
  for future use, but `chat()` always returns a complete response, even for
  a backend that supports streaming.
- **JSON Schema → Pydantic conversion is best-effort and flat.**
  `core/model_gateway.json_schema_to_model()` (used both for `structured()`
  response validation and by the `native` adapter to bridge into
  `core/llm_client.py`'s Pydantic-only contract) supports top-level
  `object` schemas with primitive-typed properties (`string`, `integer`,
  `number`, `boolean`, `array`, `object`). Nested object/array *internals*
  are accepted as opaque `dict`/`list`, not recursively validated. Complex
  nested schemas may validate more loosely than a full JSON Schema
  validator would.
- **SSRF hardening is basic, not exhaustive.** `integrations/model_gateway/openai_compatible_adapter.py`'s `_reject_unsafe_endpoint()` blocks non-http(s) schemes (`file://`, `ftp://`, ...) and the known AWS/GCP metadata addresses (`169.254.169.254`, `metadata.google.internal`, AWS IMDSv2 IPv6), and warns (not blocks) on `0.0.0.0`. **DNS-rebinding protection is NOT implemented** — a hostname that resolves to a blocked IP only at request time (not at config-parse time) would not be caught. Endpoints come from `config/model-gateway.yaml`/env vars (operator-controlled, not end-user input) in every call site in this build, which is the main mitigating factor. Treat
  this as an accepted gap for a follow-up, not a false claim of coverage.
- **`/api/v1/health` now includes `model_gateway`.** It remains a public,
  unauthenticated, rate-limited uptime probe; the addition is a new key in
  the JSON body, not a change to `status`/`engine`, so it does not break
  the existing smoke suite or the Docker zero-to-green install test (which
  only assert `status == "online"`). `/api/v1/health`, the authenticated
  `/api/v1/metrics` endpoint, and `sinapse-write.py health` all surface the
  same underlying `core.memory.health.health_check()` result, which always
  includes a `model_gateway` key (`enabled: false` reported explicitly when
  off).
- **`.env.example` was not updated by this build** — file access to it was
  blocked by this session's permission settings (directory-level deny, not
  a design choice), confirmed on repeated attempts across two build
  sessions. The exact block is instead tracked in
  `config/model-gateway.env.example` — the canonical source until
  `.env.example` can be edited directly.
- **Tool-calling is declared but not exercised end-to-end.** Profiles can
  set `capabilities.tool_calling: true` and the OpenAI-compatible adapter's
  `chat()` accepts `tool_calls` in a response, but no call site in this
  build passes `tools`/`tool_choice` through — `model_benchmark.py --all`
  reports `tool_call_valid_rate: null` for every profile as a result.
