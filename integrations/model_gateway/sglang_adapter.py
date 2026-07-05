"""integrations/model_gateway/sglang_adapter.py — SGLang's OpenAI-compatible
API server; this only fixes the provider label. See specs/model-gateway.md
Requirement 15."""
from __future__ import annotations

from integrations.model_gateway.openai_compatible_adapter import OpenAICompatibleAdapter


class SGLangAdapter(OpenAICompatibleAdapter):
    def __init__(self):
        super().__init__(provider="sglang")
