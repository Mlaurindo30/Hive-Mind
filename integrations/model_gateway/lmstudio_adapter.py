"""integrations/model_gateway/lmstudio_adapter.py — LM Studio's local server
exposes the OpenAI-compatible /v1 surface directly; this only fixes the
provider label. See specs/model-gateway.md Requirement 15."""
from __future__ import annotations

from integrations.model_gateway.openai_compatible_adapter import OpenAICompatibleAdapter


class LMStudioAdapter(OpenAICompatibleAdapter):
    def __init__(self):
        super().__init__(provider="lmstudio")
