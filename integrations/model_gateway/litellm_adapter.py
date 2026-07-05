"""
integrations/model_gateway/litellm_adapter.py — Adapter for a LiteLLM proxy.

HTTP proxy mode only in this build (direct-SDK mode is out of scope — see
specs/model-gateway.md § Out of Scope). LiteLLM's proxy exposes the same
OpenAI-compatible /v1 surface as any other backend, so this only fixes the
provider label used for logging/health/telemetry.
"""
from __future__ import annotations

from integrations.model_gateway.openai_compatible_adapter import OpenAICompatibleAdapter


class LiteLLMAdapter(OpenAICompatibleAdapter):
    def __init__(self):
        super().__init__(provider="litellm")
