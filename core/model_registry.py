"""
core/model_registry.py — Capability Registry for the Model Gateway.

Loads `config/model-gateway.yaml` and/or the legacy role configuration
(`HIVE_{ROLE}_PROVIDER/MODEL/FALLBACK*` in `.env`) into typed
`ModelProfile` records, then selects a model by role + required/preferred
capabilities. See specs/model-gateway.md, specs/model-gateway-unification.md
and docs/14-model-gateway.md for the full contract.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import yaml

_LOG = logging.getLogger(__name__)

Level = Literal["primary", "fallback", "fallback2"]

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

# Specs/model-gateway-unification.md R2.
# Single source of truth for legacy-provider → adapter-hint mapping.
# Adding a new legacy provider here is enough to make it representable in
# the registry; the runtime adapter itself still has to be implemented in
# integrations/model_gateway/.
PROVIDER_ADAPTER_HINT: dict[str, str] = {
    "openai": "openai_compatible",
    "openrouter": "openai_compatible",
    "deepseek": "openai_compatible",
    "nvidia": "openai_compatible",
    "ollama-cloud": "openai_compatible",
    "ollama": "openai_compatible",
    "qwen": "openai_compatible",
    "omniroute": "openai_compatible",
    "google": "litellm",
    "gemini": "litellm",
    "huggingface": "litellm",
    "anthropic": "openai_compatible",
    "gemini-cli": "native",
    "antigravity": "native",
    "lmstudio": "lmstudio",
    "llamacpp": "llamacpp",
    "vllm": "vllm",
    "sglang": "sglang",
}

# Suffixes used in HIVE_{ROLE}_{SUFFIX}PROVIDER / MODEL / FALLBACK*.
LEVEL_SUFFIX: tuple[tuple[Level, str], ...] = (
    ("primary", ""),
    ("fallback", "FALLBACK_"),
    ("fallback2", "FALLBACK2_"),
)

LEVEL_ROLE_SUFFIX = {level: suffix for level, suffix in LEVEL_SUFFIX}


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
    # --- Model Gateway unification (specs/model-gateway-unification.md R1) ---
    role: Optional[str] = None
    level: Level = "primary"
    auth_type: list[str] = field(default_factory=list)
    unsupported_reason: Optional[str] = None
    source: Literal["yaml", "legacy", "combined"] = "yaml"
    # The original legacy provider name (e.g. "ollama") — distinct from
    # `provider` (the runtime adapter, e.g. "openai_compatible"). Used by
    # YAML `providers.<name>:` overrides to match against the .env value.
    legacy_provider: Optional[str] = None

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
        source="yaml",
    )


_OVERRIDE_FIELDS = {
    "adapter_hint", "priority", "cost_mode",
    "context_window", "max_output_tokens", "roles",
}


def _apply_provider_override(profile: ModelProfile, override: dict) -> None:
    if not override:
        return
    if "adapter_hint" in override and override["adapter_hint"] in _KNOWN_PROVIDERS:
        profile.provider = override["adapter_hint"]  # type: ignore[assignment]
    for field_name in ("cost_mode",):
        if field_name in override:
            profile.cost_mode = override[field_name]
    cap_override = override.get("capabilities")
    if isinstance(cap_override, dict):
        try:
            profile.capabilities = _build_capabilities({**profile.capabilities.__dict__, **cap_override})
        except ModelRegistryError as exc:
            _LOG.warning("provider %r capability override ignored: %s", profile.id, exc)


def _apply_role_override(profile: ModelProfile, override: dict) -> None:
    if not override:
        return
    explicit = bool(override.get("role_override"))
    # `provider`/`model` overlap warning — we never overwrite them by
    # accident (R7 §3).
    if "provider" in override or "model" in override:
        if not explicit:
            _LOG.warning(
                "provider/model in YAML overlaps with .env HIVE_* for role %r; "
                "YAML value ignored unless role_override=true",
                profile.role,
            )
            return
        # role_override: true — apply YAML provider/model, rebuild the
        # base fields that the original .env had populated.
        if "provider" in override:
            new_provider = override["provider"]
            try:
                rebuilt = ModelRegistry.build_profile_from_provider(
                    role=profile.role,
                    provider=new_provider,
                    model=override.get("model", profile.model),
                    level=profile.level,
                )
            except ModelRegistryError as exc:
                _LOG.warning(
                    "role_override for role %r failed to build profile: %s",
                    profile.role, exc,
                )
                return
            profile.id = rebuilt.id
            profile.provider = rebuilt.provider
            profile.endpoint = rebuilt.endpoint
            profile.api_key_env = rebuilt.api_key_env
            profile.auth_type = rebuilt.auth_type
            profile.unsupported_reason = rebuilt.unsupported_reason
            # The model on the profile is the YAML value (already
            # applied by `rebuilt`).
        if "model" in override:
            profile.model = override["model"]
        return
    for field_name in ("priority", "cost_mode", "context_window", "max_output_tokens"):
        if field_name in override:
            setattr(profile, field_name, override[field_name])
    if "roles" in override and isinstance(override["roles"], list):
        profile.roles = list(override["roles"])
    # require/prefer are metadata only — applied by the selector, not stored.


class ModelRegistry:
    """In-memory, read-only view of one or more config sources."""

    def __init__(self, profiles: list[ModelProfile], defaults: GatewayDefaults | None = None):
        self._order = [p.id for p in profiles]
        self._profiles: dict[str, ModelProfile] = {p.id: p for p in profiles}
        self.defaults = defaults or GatewayDefaults()

    # ------------------------------------------------------------------
    # Legacy (HIVE_{ROLE}_PROVIDER/MODEL) integration
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_adapter_hint(provider: str) -> tuple[Optional[str], Optional[str]]:
        """Return (adapter_hint, unsupported_reason) for a legacy provider.

        An adapter_hint is returned for every provider in `PROVIDERS_CONFIG`
        and for the adapter-only providers (`lmstudio`, `llamacpp`, `vllm`,
        `sglang`). A None return means we have no knowledge of the provider
        at all — callers should treat that as `not_in_PROVIDERS_CONFIG`.
        """
        if provider in PROVIDER_ADAPTER_HINT:
            return PROVIDER_ADAPTER_HINT[provider], None
        return None, "not_in_PROVIDERS_CONFIG"

    @classmethod
    def build_profile_from_provider(
        cls,
        role: str,
        provider: str,
        model: str,
        level: Level = "primary",
    ) -> ModelProfile:
        """Build a `ModelProfile` from a (role, provider, model) triple.

        Uses `core.auth.PROVIDERS_CONFIG` to fill base_url/env_var/auth_type.
        Raises `ModelRegistryError` if `provider` is not registered anywhere.
        If `provider` is registered but no adapter is mapped yet, the profile
        is returned with `unsupported_reason` set instead of raising.
        """
        from core.auth import PROVIDERS_CONFIG

        # Late import to avoid a core<->core circular import (auth imports
        # llm_client lazily already).
        role = role.lower()
        if not role:
            raise ModelRegistryError("role is required to build a profile")
        if not provider or not model:
            raise ModelRegistryError(
                f"provider and model are required (got provider={provider!r}, model={model!r})"
            )

        cfg = PROVIDERS_CONFIG.get(provider)
        adapter_hint: Optional[str] = None
        unsupported_reason: Optional[str] = None
        base_url: Optional[str] = None
        env_var: Optional[str] = None
        auth_type: list[str] = []

        if cfg is None:
            # Provider is unknown to PROVIDERS_CONFIG. Per R2 §3 and the
            # `unsupported_explicit` edge case, the registry MUST list it
            # explicitly (with a reason) instead of disappearing silently.
            adapter_hint, unsupported_reason = cls.resolve_adapter_hint(provider)
            return ModelProfile(
                id=f"{role}/{provider}/{model}/{level}",
                provider="native",  # placeholder — `unsupported_reason` is set
                model=model,
                endpoint=None,
                api_key_env=None,
                roles=[role, *(["fallback"] if level != "primary" else [])],
                capabilities=ModelCapabilities(),
                role=role,
                level=level,
                auth_type=[],
                unsupported_reason=(
                    unsupported_reason
                    or f"provider {provider!r} is not in PROVIDERS_CONFIG "
                       "and has no adapter mapping"
                ),
                source="legacy",
                legacy_provider=provider,
            )
        adapter_hint, unsupported_reason = cls.resolve_adapter_hint(provider)
        base_url = cfg.get("base_url")
        env_var = cfg.get("env_var")
        auth_type = list(cfg.get("auth_type") or [])

        # Provider name is used as `ModelProfile.provider` (the Literal type
        # accepts the values in `_KNOWN_PROVIDERS`). For legacy providers
        # the runtime adapter is the hint, so we coerce: e.g. `openai` →
        # `openai_compatible`. If we have no hint, mark unsupported.
        runtime_provider: ModelProvider
        if adapter_hint in _KNOWN_PROVIDERS:
            runtime_provider = adapter_hint  # type: ignore[assignment]
        else:
            runtime_provider = "native"  # last-resort default
            if unsupported_reason is None:
                unsupported_reason = (
                    f"no adapter for legacy provider {provider!r} "
                    f"(hint={adapter_hint!r})"
                )

        capabilities = ModelCapabilities(
            chat=True,
            structured_output=adapter_hint != "native",
        )

        profile_id = f"{role}/{provider}/{model}/{level}"
        return ModelProfile(
            id=profile_id,
            provider=runtime_provider,
            model=model,
            endpoint=base_url,
            api_key_env=env_var,
            roles=[role, *(["fallback"] if level != "primary" else [])],
            capabilities=capabilities,
            role=role,
            level=level,
            auth_type=auth_type,
            unsupported_reason=unsupported_reason,
            source="legacy",
            legacy_provider=provider,
        )

    @classmethod
    def from_legacy_roles(
        cls,
        roles: Optional[list[str]] = None,
        get_role_config: Optional[callable] = None,
    ) -> "ModelRegistry":
        """Build a registry by reading `HIVE_{ROLE}_PROVIDER/MODEL/FALLBACK*`
        from the environment via `core.auth.get_role_config`. One
        `ModelProfile` is created per (role, level) tuple, in the order
        primary → fallback → fallback2.
        """
        if get_role_config is None:
            from core.auth import get_role_config as _get_role_config
            get_role_config = _get_role_config

        if roles is None:
            # Auto-discover roles from the env by listing keys that match
            # HIVE_{ROLE}_PROVIDER — but exclude the FALLBACK*/FALLBACK2*
            # suffixes so we don't list "DREAMER_FALLBACK" as a role.
            suffixes = ("_FALLBACK2_PROVIDER", "_FALLBACK_PROVIDER", "_PROVIDER")
            roles = set()
            for key in os.environ:
                if not key.startswith("HIVE_") or not key.endswith("_PROVIDER"):
                    continue
                if key.endswith("_FALLBACK2_PROVIDER"):
                    role = key[len("HIVE_"):-len("_FALLBACK2_PROVIDER")]
                elif key.endswith("_FALLBACK_PROVIDER"):
                    role = key[len("HIVE_"):-len("_FALLBACK_PROVIDER")]
                else:
                    role = key[len("HIVE_"):-len("_PROVIDER")]
                if role:
                    roles.add(role.lower())
            roles = sorted(roles)

        profiles: list[ModelProfile] = []
        for role in roles:
            cfg = get_role_config(role) or {}
            primary = (cfg.get("provider"), cfg.get("model"))
            fallback = (cfg.get("fallback_provider"), cfg.get("fallback_model"))
            fallback2 = (cfg.get("fallback2_provider"), cfg.get("fallback2_model"))

            chain: list[ModelProfile] = []
            for level, (p, m) in zip(
                ("primary", "fallback", "fallback2"),
                (primary, fallback, fallback2),
            ):
                if not p or not m:
                    continue
                chain.append(cls.build_profile_from_provider(role, p, m, level=level))
            if chain:
                chain[0].fallback_chain = [profile.id for profile in chain[1:]]
                profiles.extend(chain)
        return cls(profiles)

    @classmethod
    def from_combined_config(
        cls,
        roles: Optional[list[str]] = None,
        yaml_path: str | Path | None = None,
    ) -> "ModelRegistry":
        """Combined registry: legacy `.env` first, then YAML overrides layered
        on top of the same (role, level, provider, model) profiles.

        Provider/model/role/level come from the legacy sources
        (`HIVE_*_PROVIDER/MODEL` + `PROVIDERS_CONFIG`). The YAML, when
        present, contributes only capabilities, adapter_hint, priority,
        cost_mode, context_window, max_output_tokens and role overrides —
        never a mandatory `provider`/`model` for a role.
        """
        from core.auth import get_role_config

        registry = cls.from_legacy_roles(roles=roles, get_role_config=get_role_config)
        if not yaml_path:
            yaml_path = os.environ.get("MODEL_GATEWAY_CONFIG") or DEFAULT_CONFIG_PATH
        yaml_path = Path(yaml_path) if yaml_path else DEFAULT_CONFIG_PATH

        if not Path(yaml_path).is_file():
            for p in registry.list_models():
                p.source = "combined"
            return registry

        with open(yaml_path, encoding="utf-8") as fh:
            try:
                raw = yaml.safe_load(fh) or {}
            except yaml.YAMLError as exc:
                raise ModelRegistryError(f"failed to parse {yaml_path}: {exc}") from exc

        raw = _expand_env(raw)

        # Provider-level overrides (capabilities, cost_mode, adapter_hint).
        # Match against `legacy_provider` (the .env name), NOT the runtime
        # adapter — e.g. `providers.ollama:` applies to every profile whose
        # legacy_provider == "ollama", regardless of which adapter resolves.
        provider_overrides: dict[str, dict] = (raw.get("providers") or {})
        for p in registry.list_models():
            key = p.legacy_provider or p.provider
            if key in provider_overrides:
                _apply_provider_override(p, provider_overrides[key])

        # Role-level overrides (require, prefer, priority, cost_mode,
        # context_window, max_output_tokens). Provider/model in YAML are
        # NOT applied unless role_override: true.
        role_overrides: dict[str, dict] = (raw.get("roles") or {})
        for p in registry.list_models():
            if p.role and p.role in role_overrides:
                _apply_role_override(p, role_overrides[p.role])
            p.source = "combined"
        return registry

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
        role = role.lower()
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
            # No profile in the chain satisfies `require`. Fall back to
            # ANY profile in the role so the gateway can iterate the
            # chain and emit a per-profile `provider_skipped_due_to_capability`
            # event (R6.5). The caller (gateway) MUST handle the case
            # where the primary profile is itself missing the required
            # capability — see `_run_with_fallback`.
            any_role = [p for p in enabled if role in p.roles or "fallback" in p.roles]
            if not any_role:
                raise NoModelForRoleError(
                    f"no enabled model serves role={role!r} at all"
                )
            candidates = any_role

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

    def missing_capabilities(self, profile: ModelProfile, require: dict) -> list[str]:
        """Return the list of capability names the profile is missing for
        the given `require` map. An empty list means the profile
        satisfies the requirement. Used by the gateway to emit
        `provider_skipped_due_to_capability` events (R6.5)."""
        if not require:
            return []
        missing: list[str] = []
        for cap, wanted in require.items():
            if not wanted:
                continue
            if cap not in _CAPABILITY_FIELDS:
                # Unknown capability — surface it so the operator sees the typo.
                missing.append(cap)
                continue
            if not getattr(profile.capabilities, cap):
                missing.append(cap)
        return missing

    def find_role_candidates(
        self,
        role: str,
        require: dict | None = None,
    ) -> list[ModelProfile]:
        """Return every enabled profile that serves `role` (primary or
        fallback), regardless of `require`. Profiles that the registry
        marked as `unsupported_reason` are INCLUDED here so the gateway
        can emit a `provider_unsupported_skipped` event for each one
        (EC-3) before the chain moves on. The gateway itself decides
        whether to dispatch or skip.
        """
        require = require or {}
        enabled = [p for p in self.list_models() if p.enabled]
        role_candidates = [p for p in enabled if role in p.roles or "fallback" in p.roles]
        # Stable order: respect the registry order so the chain is
        # deterministic across runs.
        order = {p.id: idx for idx, p in enumerate(self.list_models())}
        role_candidates.sort(key=lambda p: order.get(p.id, 0))
        return role_candidates

    def find_vision_capable(self, role: str) -> list[ModelProfile]:
        """Return every enabled, non-unsupported profile for `role`
        whose `capabilities.vision` is True. Used by the gateway to
        pre-flight the chain when the caller requires vision (R8.3)."""
        enabled = [p for p in self.list_models() if p.enabled and not p.unsupported_reason]
        return [p for p in enabled if (role in p.roles or "fallback" in p.roles) and p.capabilities.vision]

    def validate(self) -> list[dict]:
        """Diagnostic sweep — never raises. Empty list means the registry is clean.

        Reports:
          * `unknown_provider` — `profile.provider` not in `_KNOWN_PROVIDERS`
            (R1 §6). The gateway cannot dispatch to an unknown adapter.
          * `no_roles` — legacy profile missing `role`/roles (R1 §4).
          * `unsupported_explicit` — legacy provider with no adapter
            mapping (R2 §3). Listed explicitly, never silently dropped.
          * `paid_without_cost_fields` — provider flagged as paid but
            missing cost metadata (kept from previous build).
          * `fallback_target_missing` — fallback chain target not in the
            registry (kept from previous build).
        """
        problems: list[dict] = []
        for p in self.list_models():
            if p.provider not in _KNOWN_PROVIDERS:
                problems.append({
                    "model_id": p.id, "issue": "unknown_provider",
                    "detail": p.provider,
                })
            if not p.roles and not p.role:
                problems.append({"model_id": p.id, "issue": "no_roles"})
            if p.unsupported_reason:
                problems.append({
                    "model_id": p.id, "issue": "unsupported_explicit",
                    "provider": p.provider, "reason": p.unsupported_reason,
                })
            if p.cost_mode == "paid" and (
                p.input_cost_per_1k is None or p.output_cost_per_1k is None
            ):
                problems.append({
                    "model_id": p.id, "issue": "paid_without_cost_fields",
                })
            for fb_id in p.fallback_chain:
                if fb_id not in self._profiles:
                    problems.append({
                        "model_id": p.id, "issue": "fallback_target_missing",
                        "detail": fb_id,
                    })
        return problems
