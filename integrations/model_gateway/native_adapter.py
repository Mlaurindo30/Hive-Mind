"""
integrations/model_gateway/native_adapter.py — Bridges the Model Gateway to
the existing core/llm_client.py role-based provider resolution
(HIVE_<ROLE>_PROVIDER/MODEL), so a `provider: native` profile in
config/model-gateway.yaml exercises the same, already-proven call path used
before this gateway existed (specs/model-gateway.md Requirement 22-23, the
"existing-dreamer" example profile).

core/llm_client.py's call_llm_with_fallback/call_llm_structured require a
Pydantic response_model (they call `.model_json_schema()` on it). For plain
chat(), this adapter wraps the prompt in a single-field {"response": str}
schema and unwraps it; for structured(), it converts the caller's JSON
Schema into a Pydantic model via core.model_gateway.json_schema_to_model
(best-effort, flat schemas — see docs/13-model-gateway.md "Known
limitations").
"""
from __future__ import annotations

import os

from integrations.model_gateway.base import BaseModelAdapter

_CHAT_WRAPPER_SCHEMA = {
    "type": "object",
    "properties": {"response": {"type": "string"}},
    "required": ["response"],
}


def _messages_to_prompt(messages: list[dict]) -> tuple[str, str]:
    """core/llm_client.py's contract is (system_prompt, prompt) — flatten OpenAI-style messages."""
    system_parts = [m.get("content", "") for m in messages if m.get("role") == "system"]
    other_parts = [m.get("content", "") for m in messages if m.get("role") != "system"]
    system_prompt = "\n".join(str(p) for p in system_parts) or "You are a helpful assistant."
    prompt = "\n".join(str(p) for p in other_parts)
    return system_prompt, prompt


def _role_for_profile(profile) -> str:
    """core/llm_client.py resolves by role name (HIVE_<ROLE>_PROVIDER/MODEL);
    use the profile's first declared role, falling back to 'dreamer'."""
    return profile.roles[0] if profile.roles else "dreamer"


class NativeAdapter(BaseModelAdapter):
    provider = "native"

    def chat(self, profile, messages, temperature=None, max_tokens=None, timeout_s=None, **_):
        from core.llm_client import LLMChainFailure, call_llm_with_fallback
        from core.model_gateway import ModelResponse, json_schema_to_model

        role = _role_for_profile(profile)
        system_prompt, prompt = _messages_to_prompt(messages)
        wrapper_prompt = (
            f"{prompt}\n\nRespond with a JSON object of exactly this shape: "
            '{"response": "<your answer as a string>"}'
        )
        model_cls = json_schema_to_model("ChatWrapper", _CHAT_WRAPPER_SCHEMA)
        try:
            result = call_llm_with_fallback(role, wrapper_prompt, system_prompt, model_cls)
            return ModelResponse(
                ok=True, content=getattr(result, "response", None), model_id=profile.id,
                provider=self.provider, endpoint=None, latency_ms=0.0, input_tokens=None,
                output_tokens=None, cost_estimate=None, fallback_used=False, fallback_chain=[],
                error=None,
            )
        except LLMChainFailure as exc:
            return self._error(profile, f"native_chain_failure:{exc}")
        except Exception as exc:
            return self._error(profile, f"native_error:{exc}")

    def structured(self, profile, messages, schema, timeout_s=None, **_):
        from core.llm_client import LLMChainFailure, call_llm_with_fallback
        from core.model_gateway import ModelResponse, json_schema_to_model

        role = _role_for_profile(profile)
        system_prompt, prompt = _messages_to_prompt(messages)
        try:
            model_cls = json_schema_to_model("NativeStructured", schema)
        except ValueError as exc:
            return self._error(profile, f"unsupported_schema:{exc}")
        try:
            result = call_llm_with_fallback(role, prompt, system_prompt, model_cls)
            return ModelResponse(
                ok=True, content=result.model_dump(), model_id=profile.id, provider=self.provider,
                endpoint=None, latency_ms=0.0, input_tokens=None, output_tokens=None,
                cost_estimate=None, fallback_used=False, fallback_chain=[], error=None,
            )
        except LLMChainFailure as exc:
            return self._error(profile, f"native_chain_failure:{exc}")
        except Exception as exc:
            return self._error(profile, f"native_error:{exc}")

    def health(self, profile) -> dict:
        role = _role_for_profile(profile)
        provider_env = f"HIVE_{role.upper()}_PROVIDER"
        healthy = bool(os.environ.get(provider_env) or os.environ.get("HIVE_DREAMER_PROVIDER"))
        return {"model_id": profile.id, "provider": self.provider, "healthy": healthy}

    def _error(self, profile, error: str):
        from core.model_gateway import ModelResponse
        return ModelResponse(ok=False, content=None, model_id=profile.id, provider=self.provider,
                              endpoint=None, latency_ms=0.0, input_tokens=None, output_tokens=None,
                              cost_estimate=None, fallback_used=False, fallback_chain=[], error=error)
