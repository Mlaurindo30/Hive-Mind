"""
core/model_gateway.py — Model Gateway (canonical LLM execution layer).

Routes chat/structured/embed/rerank calls to a provider adapter chosen by
role + capability via `ModelRegistry.from_combined_config()`, applies
explicit fallback (never silent success), and records redacted telemetry.

See specs/model-gateway.md and specs/model-gateway-unification.md for the
full contract. After the unification build, the gateway is the SOLE entry
point for LLM execution — `core/llm_client.call_llm_with_fallback` is a
thin wrapper that delegates here (or, under `HIVE_FORCE_LEGACY_LLM=true`,
to the legacy `_legacy_call_llm_with_fallback`).
"""
from __future__ import annotations

import os
import time
import uuid
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from core import model_telemetry
from core.model_registry import ModelNotFoundError, ModelProfile, ModelRegistry
from core.redactor import redact_for_export


class ModelGatewayError(Exception):
    pass


GatewayMode = Literal["auto", "on", "off"]

VALID_MODES: tuple[str, ...] = ("auto", "on", "off")


def resolve_gateway_mode() -> GatewayMode:
    """Resolve the gateway mode from `MODEL_GATEWAY_MODE` (canonical) and
    the deprecated `MODEL_GATEWAY_ENABLED` (compatibility shim).

    Precedence:
      1. `MODEL_GATEWAY_MODE` if set — valid values are `auto` (default),
         `on`, `off`. Invalid values raise `ModelGatewayError`.
      2. `MODEL_GATEWAY_ENABLED=true|false` — translates to `on` / `off`
         respectively, with a deprecation warning emitted once.
      3. Absent → `auto`.
    """
    raw = os.environ.get("MODEL_GATEWAY_MODE")
    if raw is not None:
        value = raw.strip().lower()
        if value not in VALID_MODES:
            raise ModelGatewayError(
                f"invalid MODEL_GATEWAY_MODE={raw!r}; must be one of {VALID_MODES}"
            )
        return value  # type: ignore[return-value]

    legacy = os.environ.get("MODEL_GATEWAY_ENABLED")
    if legacy is not None:
        value = legacy.strip().lower()
        if value in ("1", "true", "yes"):
            warnings.warn(
                "MODEL_GATEWAY_ENABLED=true is deprecated; use MODEL_GATEWAY_MODE=on",
                DeprecationWarning,
                stacklevel=2,
            )
            return "on"
        if value in ("0", "false", "no"):
            warnings.warn(
                "MODEL_GATEWAY_ENABLED=false is deprecated; use "
                "MODEL_GATEWAY_MODE=off (or HIVE_FORCE_LEGACY_LLM=true for emergency bypass)",
                DeprecationWarning,
                stacklevel=2,
            )
            return "off"
    return "auto"


def force_legacy_llm() -> bool:
    """True if the operator has set `HIVE_FORCE_LEGACY_LLM=true` — an
    emergency bypass, NOT a recommended operational mode."""
    raw = os.environ.get("HIVE_FORCE_LEGACY_LLM", "").strip().lower()
    return raw in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Back-compat: original `gateway_enabled()` is kept for any caller that
# still checks the boolean. Returns True only when the gateway should be
# used (i.e. mode=on, or mode=auto and force_legacy=False).
# ---------------------------------------------------------------------------


def gateway_enabled() -> bool:
    mode = resolve_gateway_mode()
    if force_legacy_llm():
        return False
    return mode in ("auto", "on")


@dataclass
class ModelResponse:
    ok: bool
    content: Any
    model_id: str
    provider: str
    endpoint: Optional[str]
    latency_ms: float
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    cost_estimate: Optional[float]
    fallback_used: bool
    fallback_chain: list[str]
    error: Optional[str]
    raw: Optional[dict] = None
    # Per-attempt error chain [(provider, model, error)] — preserved when
    # the entire primary → fallback → fallback2 chain fails (R3 §5).
    error_chain: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class EmbeddingResponse:
    ok: bool
    vectors: list[list[float]]
    model_id: str
    provider: str
    endpoint: Optional[str]
    latency_ms: float
    fallback_used: bool = False
    fallback_chain: list[str] = field(default_factory=list)
    error: Optional[str] = None
    raw: Optional[dict] = None


@dataclass
class RerankResponse:
    ok: bool
    results: list[dict]
    model_id: str
    provider: str
    endpoint: Optional[str]
    latency_ms: float
    fallback_used: bool = False
    fallback_chain: list[str] = field(default_factory=list)
    error: Optional[str] = None
    raw: Optional[dict] = None


def gateway_enabled() -> bool:
    return os.environ.get("MODEL_GATEWAY_ENABLED", "false").strip().lower() in ("1", "true", "yes")


def _mask_error(err: Optional[str]) -> Optional[str]:
    return redact_for_export(err) if err else err


def _adapter_for(provider: str):
    """Lazy import to avoid a core<->integrations import cycle at module load."""
    if provider == "native":
        from integrations.model_gateway.native_adapter import NativeAdapter
        return NativeAdapter()
    if provider == "litellm":
        from integrations.model_gateway.litellm_adapter import LiteLLMAdapter
        return LiteLLMAdapter()
    if provider == "lmstudio":
        from integrations.model_gateway.lmstudio_adapter import LMStudioAdapter
        return LMStudioAdapter()
    if provider == "llamacpp":
        from integrations.model_gateway.llamacpp_adapter import LlamaCppAdapter
        return LlamaCppAdapter()
    if provider == "vllm":
        from integrations.model_gateway.vllm_adapter import VLLMAdapter
        return VLLMAdapter()
    if provider == "sglang":
        from integrations.model_gateway.sglang_adapter import SGLangAdapter
        return SGLangAdapter()
    if provider == "openai_compatible":
        from integrations.model_gateway.openai_compatible_adapter import OpenAICompatibleAdapter
        return OpenAICompatibleAdapter(provider=provider)
    raise ModelGatewayError(f"no adapter registered for provider {provider!r}")


# ---------------------------------------------------------------------------
# Best-effort JSON Schema -> Pydantic bridge (no new dependency: pydantic is
# already a project dependency, `jsonschema` is not). Supports flat/shallow
# object schemas with primitive-typed properties; nested object/array
# internals are accepted as opaque dict/list, not recursively validated.
# See docs/13-model-gateway.md "Known limitations".
# ---------------------------------------------------------------------------
from pydantic import BaseModel, ValidationError, create_model  # noqa: E402

_JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def json_schema_to_model(name: str, schema: dict) -> type[BaseModel]:
    if schema.get("type") not in (None, "object"):
        raise ValueError(f"only 'object' schemas are supported, got {schema.get('type')!r}")
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    fields: dict[str, tuple] = {}
    for prop_name, prop_schema in properties.items():
        py_type = _JSON_TYPE_MAP.get((prop_schema or {}).get("type"), Any)
        if prop_name in required:
            fields[prop_name] = (py_type, ...)
        else:
            fields[prop_name] = (Optional[py_type], None)
    if not fields:
        fields["_placeholder"] = (Optional[str], None)
    return create_model(name, **fields)  # type: ignore[call-overload]


def validate_against_schema(content: Any, schema: dict) -> tuple[bool, Optional[str]]:
    if not isinstance(content, dict):
        return False, f"expected a JSON object, got {type(content).__name__}"
    try:
        model_cls = json_schema_to_model("StructuredResponse", schema)
        model_cls(**content)
        return True, None
    except (ValidationError, ValueError) as exc:
        return False, str(exc)


class ModelGateway:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    @classmethod
    def from_combined_config(cls) -> "ModelGateway":
        """Canonical entry point (R3 §2). Uses `ModelRegistry.from_combined_config`,
        which composes PROVIDERS_CONFIG + HIVE_*_PROVIDER/MODEL + optional
        YAML overrides. The gateway no longer needs a separate YAML-only
        path — providers and roles come from the legacy `.env` plus the
        YAML as an override layer.
        """
        return cls(ModelRegistry.from_combined_config())

    @classmethod
    def from_config(cls, path: Optional[str] = None) -> "ModelGateway":
        """DEPRECATED — kept for backward compatibility with callers that
        still pass an explicit YAML path. New code MUST use
        `from_combined_config`. Emits a `DeprecationWarning` on use.
        """
        warnings.warn(
            "ModelGateway.from_config() is deprecated; use from_combined_config() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        config_path = path or os.environ.get("MODEL_GATEWAY_CONFIG")
        return cls(ModelRegistry.from_yaml(config_path))

    # -- public API -----------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        role: Optional[str] = None,
        model_id: Optional[str] = None,
        require: Optional[dict] = None,
        prefer: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout_s: Optional[float] = None,
    ) -> ModelResponse:
        require = require or {}
        # R8.3 — pre-flight vision check BEFORE profile resolution so the
        # canonical error fires even when `select()` would have raised.
        if role is not None and require.get("vision"):
            pre = self._preflight_vision(role, require)
            if pre is not None:
                return pre
        profile = self._resolve_profile(role, model_id, require, prefer)
        return self._run_with_fallback(
            "chat", profile, role, require,
            args=(messages,),
            kwargs=dict(
                temperature=temperature, max_tokens=max_tokens,
                timeout_s=timeout_s or self.registry.defaults.timeout_s,
            ),
        )

    def structured(
        self,
        messages: list[dict],
        schema: dict,
        role: Optional[str] = None,
        model_id: Optional[str] = None,
        require: Optional[dict] = None,
        timeout_s: Optional[float] = None,
    ) -> ModelResponse:
        require = dict(require or {})
        require.setdefault("structured_output", True)
        # R8.3 — pre-flight vision check BEFORE profile resolution.
        if role is not None and require.get("vision"):
            pre = self._preflight_vision(role, require)
            if pre is not None:
                return pre
        profile = self._resolve_profile(role, model_id, require, None)

        def _validate(response: ModelResponse) -> tuple[bool, Optional[str]]:
            return validate_against_schema(response.content, schema)

        return self._run_with_fallback(
            "structured", profile, role, require,
            args=(messages, schema),
            kwargs=dict(timeout_s=timeout_s or self.registry.defaults.timeout_s),
            validate_fn=_validate,
        )

    def embed(
        self, texts: list[str], role: Optional[str] = None, model_id: Optional[str] = None,
    ) -> EmbeddingResponse:
        require = {"embeddings": True}
        profile = self._resolve_profile(role or "embeddings", model_id, require, None)
        return self._run_with_fallback("embed", profile, role, require, args=(texts,), kwargs={})

    def rerank(
        self, query: str, documents: list[str], role: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> RerankResponse:
        require = {"rerank": True}
        profile = self._resolve_profile(role or "rerank", model_id, require, None)
        return self._run_with_fallback(
            "rerank", profile, role, require, args=(query, documents), kwargs={}
        )

    def health(self) -> dict:
        models = self.registry.list_models()
        healthy = 0
        unhealthy = 0
        details = []
        for p in models:
            if not p.enabled:
                continue
            try:
                h = _adapter_for(p.provider).health(p)
            except Exception as exc:  # never let health() raise
                h = {"model_id": p.id, "provider": p.provider, "healthy": False,
                     "error": _mask_error(str(exc))}
            if h.get("healthy"):
                healthy += 1
            else:
                unhealthy += 1
            details.append(h)

        default_roles: dict[str, str] = {}
        for role in {r for p in models for r in p.roles}:
            try:
                default_roles[role] = self.registry.select(role).id
            except Exception:
                continue

        return {
            "enabled": gateway_enabled(),
            "models_total": len(models),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "default_roles": default_roles,
            "details": details,
        }

    # -- internals --------------------------------------------------------

    def _resolve_profile(
        self, role: Optional[str], model_id: Optional[str],
        require: Optional[dict], prefer: Optional[dict],
    ) -> ModelProfile:
        if model_id:
            profile = self.registry.get(model_id)
            if not profile.enabled:
                raise ModelNotFoundError(f"model {model_id!r} is disabled")
            return profile
        if not role:
            raise ModelGatewayError("either role or model_id must be given")
        return self.registry.select(role, require=require, prefer=prefer)

    def _fallback_targets(self, profile: ModelProfile) -> list[ModelProfile]:
        targets: list[ModelProfile] = []
        seen = {profile.id}
        for fb_id in profile.fallback_chain:
            if fb_id in seen:
                break  # cycle guard (Edge Case 18)
            seen.add(fb_id)
            try:
                fb_profile = self.registry.get(fb_id)
            except ModelNotFoundError:
                continue
            if not fb_profile.enabled:
                continue  # Edge Case 19
            targets.append(fb_profile)
        return targets

    def _preflight_vision(
        self, role: str, require: dict,
    ) -> Optional[ModelResponse]:
        """R8.3 — when the caller requires `vision`, check up-front whether
        any profile for `role` is vision-capable. If none, return a
        structured `ModelResponse(ok=False, error='no_vision_capable_provider')`
        without ever dispatching to an adapter."""
        if not (require or {}).get("vision"):
            return None
        capable = self.registry.find_vision_capable(role)
        if capable:
            return None
        placeholder = ModelResponse(
            ok=False, content=None,
            model_id="(none)", provider="(none)", endpoint=None,
            latency_ms=0.0, input_tokens=None, output_tokens=None,
            cost_estimate=None, fallback_used=False, fallback_chain=[],
            error="no_vision_capable_provider",
        )
        # Telemetry is recorded once at the call site (the caller has the
        # full request context). The error is canonical and machine-readable.
        return placeholder

    def _error_response(self, capability: str, profile: ModelProfile, error: str):
        if capability == "embed":
            return EmbeddingResponse(ok=False, vectors=[], model_id=profile.id,
                                      provider=profile.provider, endpoint=profile.endpoint,
                                      latency_ms=0.0, error=error)
        if capability == "rerank":
            return RerankResponse(ok=False, results=[], model_id=profile.id,
                                   provider=profile.provider, endpoint=profile.endpoint,
                                   latency_ms=0.0, error=error)
        return ModelResponse(ok=False, content=None, model_id=profile.id,
                              provider=profile.provider, endpoint=profile.endpoint,
                              latency_ms=0.0, input_tokens=None, output_tokens=None,
                              cost_estimate=None, fallback_used=False, fallback_chain=[],
                              error=error)

    def _run_with_fallback(
        self, capability: str, profile: ModelProfile, role: Optional[str], require: dict,
        args: tuple, kwargs: dict, validate_fn: Optional[Callable[[Any], tuple[bool, Optional[str]]]] = None,
    ):
        # R8.3 — pre-flight vision check. If the caller requires vision and
        # no profile for this role is vision-capable, return the canonical
        # error BEFORE any adapter dispatch.
        if role is not None:
            vision_block = self._preflight_vision(role, require)
            if vision_block is not None:
                return vision_block

        request_id = str(uuid.uuid4())
        chain_ids: list[str] = [profile.id]
        fallback_used = False
        last_response = None

        # Build the chain: primary profile + the registry's primary/fallback
        # candidates for the role. Using `find_role_candidates` gives us a
        # full ordered list so we can also emit capability-skip events
        # (R6.5) for every profile that misses a required capability.
        if role is not None:
            role_candidates = self.registry.find_role_candidates(role, require=require)
            if role_candidates:
                candidates = role_candidates
            else:
                # No role-based candidates at all (e.g. unknown role) —
                # fall back to the original primary + fallback_chain.
                candidates = [profile]
                if self.registry.defaults.fallback_enabled:
                    candidates += self._fallback_targets(profile)
        else:
            candidates = [profile]
            if self.registry.defaults.fallback_enabled:
                candidates += self._fallback_targets(profile)

        for idx, candidate in enumerate(candidates):
            # EC-3 — never dispatch an adapter for a profile the registry
            # explicitly marked unsupported.
            if candidate.unsupported_reason:
                model_telemetry.record_provider_unsupported_skipped(
                    role=role,
                    provider=candidate.legacy_provider or candidate.provider,
                    model=candidate.model,
                    level=candidate.level or "primary",
                    unsupported_reason=candidate.unsupported_reason,
                )
                # Treat as a soft skip: continue to the next candidate in
                # the chain without recording it as a fallback attempt.
                continue

            # R6.5 — emit a `provider_skipped_due_to_capability` event for
            # every profile in the chain that misses a required capability,
            # then skip the adapter call. This is the source of truth for
            # the spec's "skip" observability.
            missing = self.registry.missing_capabilities(candidate, require or {})
            if missing:
                model_telemetry.record_provider_skipped_due_to_capability(
                    role=role,
                    provider=candidate.legacy_provider or candidate.provider,
                    model=candidate.model,
                    level=candidate.level or "primary",
                    missing_capability=",".join(missing),
                )
                continue

            start = time.monotonic()
            try:
                adapter = _adapter_for(candidate.provider)
                fn = getattr(adapter, capability)
                response = fn(candidate, *args, **kwargs)
            except Exception as exc:
                response = self._error_response(
                    capability, candidate, f"adapter_exception:{_mask_error(str(exc))}"
                )
            elapsed_ms = (time.monotonic() - start) * 1000.0
            if not response.latency_ms:
                response.latency_ms = elapsed_ms
            response.error = _mask_error(response.error)

            if response.ok and validate_fn is not None:
                valid, reason = validate_fn(response)
                if not valid:
                    response.ok = False
                    response.error = _mask_error(f"schema_invalid:{reason}")

            if idx > 0:
                fallback_used = True
                if candidate.id not in chain_ids:
                    chain_ids.append(candidate.id)

            model_telemetry.record_call(
                request_id=request_id,
                workspace_id=os.environ.get("HIVE_WORKSPACE_ID", "default"),
                role=role, selected_model_id=candidate.id, provider=candidate.provider,
                endpoint=candidate.endpoint, capabilities_required=require,
                fallback_used=fallback_used, latency_ms=response.latency_ms,
                input_tokens=getattr(response, "input_tokens", None),
                output_tokens=getattr(response, "output_tokens", None),
                cost_estimate=getattr(response, "cost_estimate", None),
                error_type=response.error,
            )

            if response.ok:
                response.fallback_used = fallback_used
                response.fallback_chain = chain_ids if fallback_used else []
                return response
            last_response = response

        if last_response is None:
            # Every candidate was skipped (capability / unsupported) — no
            # adapter was actually called. Return a structured error
            # referencing the canonical reason so the operator can see
            # why nothing tried.
            last_response = ModelResponse(
                ok=False, content=None, model_id=profile.id,
                provider=profile.provider, endpoint=profile.endpoint,
                latency_ms=0.0, input_tokens=None, output_tokens=None,
                cost_estimate=None, fallback_used=False, fallback_chain=[],
                error="no_qualifying_provider",
            )

        last_response.fallback_used = fallback_used
        last_response.fallback_chain = chain_ids
        return last_response
