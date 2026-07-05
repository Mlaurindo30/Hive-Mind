"""integrations/model_gateway/vllm_adapter.py — vLLM's OpenAI-compatible API
server; this only fixes the provider label. See specs/model-gateway.md
Requirement 15."""
from __future__ import annotations

from integrations.model_gateway.openai_compatible_adapter import OpenAICompatibleAdapter


class VLLMAdapter(OpenAICompatibleAdapter):
    def __init__(self):
        super().__init__(provider="vllm")
