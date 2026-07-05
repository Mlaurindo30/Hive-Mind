"""
core/model_registry.py — Capability Registry for the Model Gateway (Priority 1).

Loads `config/model-gateway.yaml` into typed `ModelProfile` records and
selects a model by role + required/preferred capabilities. See
specs/model-gateway.md and docs/13-model-gateway.md for the full contract.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import yaml

SINAPSE_HOME = Path(os.environ.get(
    "SINAPSE_HOME", str(Path(__file__).resolve().parent.parent)))

DEFAULT_CONFIG_PATH = SINAPSE_HOME / "config" / "model-gateway.yaml"

ModelProvider = Literal[
    "native",
    "litellm",
    "openai_compatible",
    "lmstudio",
    "llamacpp",
    "vllm",
    "sglang",
]

_KNOWN_PROVIDERS = {
    "native", "litellm", "openai_compatible", "lmstudio", "llamacpp", "vllm", "sglang",
}


class ModelRegistryError(Exception):
    """Config load/parse/lookup failure. Distinct from validate()'s diagnostics."""


class ModelNotFoundError(ModelRegistryError):
    pass


class NoModelForRoleError(ModelRegistryError):
    pass


class UnknownCapabilityError(ModelRegistryError):
    pass


@dataclass
class ModelCapabilities:
    chat: bool = True
    streaming: bool = False
    tool_calling: bool = False
    structured_output: bool = False
    vision: bool = False
    embeddings: bool = False
    rerank: bool = False
    json_schema: bool = False
    regex_schema: bool = False
    ebnf_schema: bool = False


_CAPABILITY_FIELDS = set(ModelCapabilities.__dataclass_fields__)


@dataclass
class ModelProfile:
    id: str
    provider: ModelProvider
    model: str
    endpoint: Optional[str] = None
    api_key_env: Optional[str] = None
    context_window: int = 4096
    max_output_tokens: int = 1024
    cost_mode: Literal["local", "paid", "unknown"] = "unknown"
    input_cost_per_1k: Optional[float] = None
    output_cost_per_1k: Optional[float] = None
    priority: int = 100
    enabled: bool = True
    roles: list[str] = field(default_factory=list)
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    fallback_chain: list[str] = field(default_factory=list)

    def api_key(self) -> Optional[str]:
        """Resolve the secret from the environment at call time. Never cached on the profile."""
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env)


@dataclass
class GatewayDefaults:
    timeout_s: float = 60.0
    max_retries: int = 1
    fallback_enabled: bool = True
    telemetry_enabled: bool = True


# ${VAR}, ${VAR:-default}, and bare $VAR — bash-style expansion used by
# config/model-gateway.yaml so machines without a given backend can leave
# the env var unset and fall back to the declared default.
_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        def _sub(m: re.Match) -> str:
            name = m.group(1) or m.group(4)
            default = m.group(3)
            resolved = os.environ.get(name)
            if resolved:
                return resolved
            return default if default is not None else ""
        return _ENV_VAR_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def _build_capabilities(raw: dict | None) -> ModelCapabilities:
    raw = raw or {}
    unknown = set(raw) - _CAPABILITY_FIELDS
    if unknown:
        raise ModelRegistryError(f"unknown capability field(s): {sorted(unknown)}")
    return ModelCapabilities(**raw)


def _build_profile(raw: dict) -> ModelProfile:
    if "id" not in raw:
        raise ModelRegistryError("model entry missing required 'id'")
    provider = raw.get("provider")
    if provider not in _KNOWN_PROVIDERS:
        raise ModelRegistryError(
            f"model {raw['id']!r}: unknown provider {provider!r}; "
            f"must be one of {sorted(_KNOWN_PROVIDERS)}"
        )
    return ModelProfile(
        id=raw["id"],
        provider=provider,
        model=raw.get("model", ""),
        endpoint=raw.get("endpoint") or None,
        api_key_env=raw.get("api_key_env") or None,
        context_window=int(raw.get("context_window", 4096)),
        max_output_tokens=int(raw.get("max_output_tokens", 1024)),
        cost_mode=raw.get("cost_mode", "unknown"),
        input_cost_per_1k=raw.get("input_cost_per_1k"),
        output_cost_per_1k=raw.get("output_cost_per_1k"),
        priority=int(raw.get("priority", 100)),
        enabled=bool(raw.get("enabled", True)),
        roles=list(raw.get("roles") or []),
        capabilities=_build_capabilities(raw.get("capabilities")),
        fallback_chain=list(raw.get("fallback_chain") or []),
    )


class ModelRegistry:
    """In-memory, read-only view of config/model-gateway.yaml."""

    def __init__(self, profiles: list[ModelProfile], defaults: GatewayDefaults | None = None):
        self._order = [p.id for p in profiles]
        self._profiles: dict[str, ModelProfile] = {p.id: p for p in profiles}
        self.defaults = defaults or GatewayDefaults()

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> "ModelRegistry":
        config_path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not config_path.is_file():
            raise ModelRegistryError(f"model gateway config not found: {config_path}")
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ModelRegistryError(f"failed to parse {config_path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ModelRegistryError(f"{config_path}: expected a YAML mapping at top level")

        raw = _expand_env(raw)

        defaults_raw = raw.get("defaults") or {}
        defaults = GatewayDefaults(
            timeout_s=float(defaults_raw.get("timeout_s", 60.0)),
            max_retries=int(defaults_raw.get("max_retries", 1)),
            fallback_enabled=bool(defaults_raw.get("fallback_enabled", True)),
            telemetry_enabled=bool(defaults_raw.get("telemetry_enabled", True)),
        )

        profiles: list[ModelProfile] = []
        seen_ids: set[str] = set()
        for entry in raw.get("models") or []:
            profile = _build_profile(entry)
            if profile.id in seen_ids:
                raise ModelRegistryError(f"duplicate model id: {profile.id!r}")
            seen_ids.add(profile.id)
            profiles.append(profile)

        return cls(profiles, defaults=defaults)

    def list_models(self) -> list[ModelProfile]:
        return [self._profiles[mid] for mid in self._order]

    def get(self, model_id: str) -> ModelProfile:
        try:
            return self._profiles[model_id]
        except KeyError:
            raise ModelNotFoundError(f"no model registered with id {model_id!r}") from None

    def select(
        self,
        role: str,
        require: dict | None = None,
        prefer: dict | None = None,
    ) -> ModelProfile:
        require = require or {}
        prefer = prefer or {}
        unknown_caps = set(require) - _CAPABILITY_FIELDS
        if unknown_caps:
            raise UnknownCapabilityError(f"unknown capability in require={sorted(unknown_caps)}")

        def matches_require(p: ModelProfile) -> bool:
            return all(
                getattr(p.capabilities, cap) for cap, wanted in require.items() if wanted
            )

        enabled = [p for p in self.list_models() if p.enabled]

        candidates = [p for p in enabled if role in p.roles and matches_require(p)]
        if not candidates:
            candidates = [p for p in enabled if "fallback" in p.roles and matches_require(p)]
        if not candidates:
            raise NoModelForRoleError(
                f"no enabled model satisfies role={role!r} require={require!r}"
            )

        def sort_key(p: ModelProfile) -> tuple[int, int]:
            prefer_mismatch = 0
            for key, wanted in prefer.items():
                actual = getattr(p, key, None)
                if actual is None:
                    actual = getattr(p.capabilities, key, None)
                if actual != wanted:
                    prefer_mismatch = 1
                    break
            return (p.priority, prefer_mismatch)

        candidates.sort(key=sort_key)
        return candidates[0]

    def validate(self) -> list[dict]:
        """Diagnostic sweep — never raises. Empty list means the config is clean."""
        problems: list[dict] = []
        for p in self.list_models():
            if p.provider not in _KNOWN_PROVIDERS:
                problems.append({"model_id": p.id, "issue": "unknown_provider", "detail": p.provider})
            if not p.roles:
                problems.append({"model_id": p.id, "issue": "no_roles"})
            if p.cost_mode == "paid" and (p.input_cost_per_1k is None or p.output_cost_per_1k is None):
                problems.append({"model_id": p.id, "issue": "paid_without_cost_fields"})
            for fb_id in p.fallback_chain:
                if fb_id not in self._profiles:
                    problems.append({"model_id": p.id, "issue": "fallback_target_missing", "detail": fb_id})
        return problems
