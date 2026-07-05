"""
core/model_telemetry.py — Structured, secret-free call metrics for the Model
Gateway. `record_call` takes only metadata fields by design (no prompt/response
payload parameter exists) and redacts `endpoint`/`error_type` before emitting.
"""
from __future__ import annotations

import sys
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
