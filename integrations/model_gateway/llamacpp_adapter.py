"""integrations/model_gateway/llamacpp_adapter.py — llama.cpp's `server`
binary exposes the OpenAI-compatible /v1 surface (chat, embeddings, rerank);
this only fixes the provider label. See specs/model-gateway.md Requirement 15."""
from __future__ import annotations

from integrations.model_gateway.openai_compatible_adapter import OpenAICompatibleAdapter


class LlamaCppAdapter(OpenAICompatibleAdapter):
    def __init__(self):
        super().__init__(provider="llamacpp")
