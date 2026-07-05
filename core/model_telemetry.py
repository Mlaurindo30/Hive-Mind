"""
core/model_telemetry.py — Structured, secret-free call metrics for the Model
Gateway. `record_call` takes only metadata fields by design (no prompt/response
payload parameter exists) and redacts `endpoint`/`error_type` before emitting.

The Gateway Unification spec (specs/model-gateway-unification.md R10) adds
the canonical hooks below. Every record redacts via `core.redactor` — secrets
NEVER reach the telemetry stream.
"""
from __future__ import annotations

import sys
import time
import uuid
from typing import Optional

from core.redactor import redact_for_export


def record_call(
    *,
    request_id: str,
    workspace_id: str,
    role: Optional[str],
    selected_model_id: str,
    provider: str,
    endpoint: Optional[str],
    capabilities_required: dict,
    fallback_used: bool,
    latency_ms: float,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    cost_estimate: Optional[float],
    error_type: Optional[str],
) -> dict:
    """Emit one structured telemetry record and return it (for tests/callers)."""
    record = {
        "request_id": request_id,
        "workspace_id": workspace_id,
        "role": role,
        "selected_model_id": selected_model_id,
        "provider": provider,
        "endpoint": redact_for_export(endpoint) if endpoint else endpoint,
        "capabilities_required": capabilities_required,
        "fallback_used": fallback_used,
        "latency_ms": round(latency_ms, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_estimate": cost_estimate,
        "error_type": redact_for_export(error_type) if error_type else error_type,
    }
    print(f"[model_gateway] {record}", file=sys.stderr)
    return record


# ---------------------------------------------------------------------------
# Gateway unification canonical hooks (R10)
# ---------------------------------------------------------------------------


def _new_request_id() -> str:
    return str(uuid.uuid4())


def record_gateway_attempt(
    *,
    role: Optional[str],
    provider: str,
    model: str,
    level: str,
    workspace_id: Optional[str] = None,
) -> str:
    """Emit a `gateway_attempted=true` record and return the request_id.

    Caller MUST reuse the returned request_id in the matching
    `record_gateway_failure` / `record_legacy_fallback_used` so the events
    can be correlated in the log stream.
    """
    request_id = _new_request_id()
    record = {
        "event": "gateway_attempt",
        "request_id": request_id,
        "workspace_id": workspace_id or os.environ.get("HIVE_WORKSPACE_ID", "default"),
        "role": role,
        "provider": provider,
        "model": model,
        "level": level,
        "gateway_attempted": True,
        "gateway_failed": False,
        "legacy_fallback_used": False,
    }
    print(f"[model_gateway] {record}", file=sys.stderr)
    return request_id


def record_gateway_failure(
    *,
    request_id: str,
    role: Optional[str],
    provider: str,
    model: str,
    level: str,
    error_class: str,
    reason: str,
    workspace_id: Optional[str] = None,
) -> None:
    """Emit a `gateway_failed=true` record (one per failed attempt).

    `error_class` MUST be one of: auth, transient, validation, rate_limit,
    unknown. `reason` is the redacted error string and MUST NOT contain
    secrets.
    """
    record = {
        "event": "gateway_failure",
        "request_id": request_id,
        "workspace_id": workspace_id or os.environ.get("HIVE_WORKSPACE_ID", "default"),
        "role": role,
        "provider": provider,
        "model": model,
        "level": level,
        "gateway_attempted": True,
        "gateway_failed": True,
        "error_class": error_class,
        "reason": redact_for_export(reason),
    }
    print(f"[model_gateway] {record}", file=sys.stderr)


def record_legacy_fallback_used(
    *,
    request_id: str,
    role: Optional[str],
    reason: str,
    level: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> None:
    """Emit a `legacy_fallback_used=true` record. Used both for emergency
    bypass (`HIVE_FORCE_LEGACY_LLM=true`) and for MODE=auto fail-open."""
    record = {
        "event": "legacy_fallback",
        "request_id": request_id,
        "workspace_id": workspace_id or os.environ.get("HIVE_WORKSPACE_ID", "default"),
        "role": role,
        "level": level,
        "gateway_attempted": True,
        "gateway_failed": True,
        "legacy_fallback_used": True,
        "reason": redact_for_export(reason),
    }
    print(f"[model_gateway] {record}", file=sys.stderr)


def record_setup_brain_role_configured(
    *,
    role: str,
    primary_provider: Optional[str],
    primary_model: Optional[str],
    fallback_provider: Optional[str],
    fallback_model: Optional[str],
    fallback2_provider: Optional[str],
    fallback2_model: Optional[str],
) -> None:
    """Emit a `setup_brain_role_configured` record (R9/R10)."""
    record = {
        "event": "setup_brain_role_configured",
        "role": role,
        "primary": {"provider": primary_provider, "model": primary_model},
        "fallback": {"provider": fallback_provider, "model": fallback_model},
        "fallback2": {"provider": fallback2_provider, "model": fallback2_model},
    }
    print(f"[setup_brain] {record}", file=sys.stderr)


def record_provider_skipped_due_to_capability(
    *,
    role: Optional[str],
    provider: str,
    model: str,
    level: str,
    missing_capability: str,
    workspace_id: Optional[str] = None,
    reason: str = "skipped_due_to_capability",
) -> None:
    """Emit a `provider_skipped_due_to_capability` event (R6.5).

    Triggered when the gateway encounters a profile in the chain that
    does not satisfy a `require={...}` capability. NEVER logs prompts
    or response payloads; only the metadata fields below. ALL string
    fields go through `redact_for_export` to prevent any secret that
    has slipped into a profile id, model name, or reason from reaching
    the telemetry stream (R10.3).
    """
    record = {
        "event": "provider_skipped_due_to_capability",
        "workspace_id": workspace_id or os.environ.get("HIVE_WORKSPACE_ID", "default"),
        "role": role,
        "provider": redact_for_export(provider),
        "model": redact_for_export(model),
        "level": redact_for_export(level),
        "missing_capability": redact_for_export(missing_capability),
        "reason": redact_for_export(reason),
        "gateway_attempted": True,
        "gateway_failed": False,
        "legacy_fallback_used": False,
    }
    print(f"[model_gateway] {record}", file=sys.stderr)


def record_provider_unsupported_skipped(
    *,
    role: Optional[str],
    provider: str,
    model: str,
    level: str,
    unsupported_reason: str,
    workspace_id: Optional[str] = None,
) -> None:
    """Emit a `provider_unsupported_skipped` event (EC-3).

    Triggered when a profile in the chain is marked `unsupported_reason`
    by the registry (e.g. legacy provider outside `PROVIDERS_CONFIG`).
    The gateway MUST skip these profiles without dispatching to the
    adapter, and MUST record this event so operators can see why a
    fallback was not tried.
    """
    record = {
        "event": "provider_unsupported_skipped",
        "workspace_id": workspace_id or os.environ.get("HIVE_WORKSPACE_ID", "default"),
        "role": role,
        "provider": provider,
        "model": model,
        "level": level,
        "unsupported_reason": redact_for_export(unsupported_reason),
        "gateway_attempted": True,
        "gateway_failed": False,
        "legacy_fallback_used": False,
    }
    print(f"[model_gateway] {record}", file=sys.stderr)


# Avoid importing os at module top — keep the import local so this module
# stays importable from tests without the full env loaded.
import os  # noqa: E402
