"""
integrations/model_gateway/base.py — Adapter contract for the Model Gateway.

Every adapter method returns a response dataclass with `ok=False` and a
classified `error` on failure — never an unhandled exception, and never a
capability silently no-op'd as success. See specs/model-gateway.md
Requirement 14.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.model_gateway import EmbeddingResponse, ModelResponse, RerankResponse
    from core.model_registry import ModelProfile


class BaseModelAdapter:
    provider: str = "base"

    def chat(self, profile: "ModelProfile", messages: list[dict], **kwargs) -> "ModelResponse":
        return self._unsupported(profile, "chat")

    def structured(
        self, profile: "ModelProfile", messages: list[dict], schema: dict, **kwargs
    ) -> "ModelResponse":
        return self._unsupported(profile, "structured_output")

    def embed(self, profile: "ModelProfile", texts: list[str], **kwargs) -> "EmbeddingResponse":
        return self._unsupported_embedding(profile, "embeddings")

    def rerank(
        self, profile: "ModelProfile", query: str, documents: list[str], **kwargs
    ) -> "RerankResponse":
        return self._unsupported_rerank(profile, "rerank")

    def health(self, profile: "ModelProfile") -> dict:
        return {"model_id": profile.id, "provider": self.provider, "healthy": False,
                "error": "health check not implemented for this adapter"}

    # -- shared "capability not supported" builders -------------------------

    def _unsupported(self, profile: "ModelProfile", capability: str) -> "ModelResponse":
        from core.model_gateway import ModelResponse
        return ModelResponse(
            ok=False, content=None, model_id=profile.id, provider=profile.provider,
            endpoint=profile.endpoint, latency_ms=0.0, input_tokens=None, output_tokens=None,
            cost_estimate=None, fallback_used=False, fallback_chain=[],
            error=f"capability_not_supported:{capability}",
        )

    def _unsupported_embedding(self, profile: "ModelProfile", capability: str) -> "EmbeddingResponse":
        from core.model_gateway import EmbeddingResponse
        return EmbeddingResponse(
            ok=False, vectors=[], model_id=profile.id, provider=profile.provider,
            endpoint=profile.endpoint, latency_ms=0.0,
            error=f"capability_not_supported:{capability}",
        )

    def _unsupported_rerank(self, profile: "ModelProfile", capability: str) -> "RerankResponse":
        from core.model_gateway import RerankResponse
        return RerankResponse(
            ok=False, results=[], model_id=profile.id, provider=profile.provider,
            endpoint=profile.endpoint, latency_ms=0.0,
            error=f"capability_not_supported:{capability}",
        )
