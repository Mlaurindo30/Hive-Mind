"""R6.5 — Telemetria de `provider_skipped_due_to_capability`.

O gateway emite um evento estruturado sempre que um profile é pulado por
não atender `require`. Este módulo cobre:

  * provider sem capability é pulado
  * evento `provider_skipped_due_to_capability` é registrado
  * provider/model/role/level aparecem no evento
  * capability ausente aparece no evento
  * nenhum segredo aparece no evento
"""
from __future__ import annotations

import ast

import pytest
from pydantic import BaseModel

from core import model_telemetry
from core.model_gateway import ModelGateway, ModelResponse
from core.model_registry import (
    ModelCapabilities,
    ModelProfile,
    ModelRegistry,
)

FAKE_SECRET = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnop"


def _profile(
    *,
    pid: str,
    role: str = "validator",
    level: str = "primary",
    structured_output: bool = True,
    vision: bool = False,
) -> ModelProfile:
    return ModelProfile(
        id=pid,
        provider="native",
        model=f"model-{pid}",
        endpoint="http://localhost:0",
        roles=[role, *(["fallback"] if level != "primary" else [])],
        role=role,
        level=level,
        capabilities=ModelCapabilities(
            chat=True,
            structured_output=structured_output,
            vision=vision,
        ),
    )


def _gateway_with_two_profiles() -> ModelGateway:
    reg = ModelRegistry([
        _profile(pid="structured", level="primary", structured_output=True),
        _profile(pid="plain", level="fallback", structured_output=False),
    ])
    return ModelGateway(reg)


def _parse_skipped_events(out: str) -> list[dict]:
    """Return the parsed `provider_skipped_due_to_capability` events
    from a captured stderr blob. The telemetry stream emits Python
    `repr(dict)` (single-quoted keys), so we parse with `ast.literal_eval`
    rather than `json.loads`."""
    events = []
    for line in out.splitlines():
        if "[model_gateway]" not in line:
            continue
        # Format: "[model_gateway] {...}"
        idx = line.find("{")
        if idx < 0:
            continue
        try:
            record = ast.literal_eval(line[idx:])
        except (ValueError, SyntaxError):
            continue
        if isinstance(record, dict) and record.get("event") == "provider_skipped_due_to_capability":
            events.append(record)
    return events


def _read_skipped_events(capsys) -> list[dict]:
    """Read stderr once and return the parsed skip events. Convenience
    wrapper for tests that do not also need the raw stderr string."""
    return _parse_skipped_events(capsys.readouterr().err)


def test_provider_without_capability_is_skipped():
    """A profile in the chain without `structured_output` MUST be skipped
    when the caller requires it, without dispatching to the adapter."""
    reg = ModelRegistry([
        _profile(pid="needs-so", level="primary", structured_output=True),
        _profile(pid="no-so", level="fallback", structured_output=False),
    ])
    gateway = ModelGateway(reg)

    # Sanity: the primary profile IS dispatched (it has structured_output).
    # The fallback profile (no structured_output) MUST be skipped.
    class _CapableAdapter:
        def structured(self, profile, *args, **kwargs):
            return ModelResponse(
                ok=True, content={"ok": True}, model_id=profile.id,
                provider=profile.provider, endpoint=profile.endpoint,
                latency_ms=1.0, input_tokens=1, output_tokens=1,
                cost_estimate=None, fallback_used=False, fallback_chain=[],
                error=None,
            )

    from unittest.mock import patch
    with patch("core.model_gateway._adapter_for", return_value=_CapableAdapter()):
        resp = gateway.structured(
            messages=[{"role": "user", "content": "hi"}],
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            role="validator",
            require={"structured_output": True},
        )
    assert resp.ok is True
    # The primary was used; the no-so fallback was skipped.
    assert "needs-so" in resp.model_id


def test_skip_event_is_emitted_when_falling_back(capsys):
    """When the primary profile misses a capability, the skip event is
    recorded with the required metadata fields (R6.5 §B)."""
    reg = ModelRegistry([
        # Primary DOES NOT have structured_output, fallback does.
        _profile(pid="plain-primary", level="primary", structured_output=False),
        _profile(pid="structured-fallback", level="fallback", structured_output=True),
    ])
    gateway = ModelGateway(reg)

    class _FakeAdapter:
        def structured(self, profile, *args, **kwargs):
            return ModelResponse(
                ok=True, content={"ok": True}, model_id=profile.id,
                provider=profile.provider, endpoint=profile.endpoint,
                latency_ms=1.0, input_tokens=1, output_tokens=1,
                cost_estimate=None, fallback_used=False, fallback_chain=[],
                error=None,
            )

    from unittest.mock import patch
    with patch("core.model_gateway._adapter_for", return_value=_FakeAdapter()):
        resp = gateway.structured(
            messages=[{"role": "user", "content": "hi"}],
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            role="validator",
            require={"structured_output": True},
        )
    assert resp.ok is True
    assert "structured-fallback" in resp.model_id
    assert resp.fallback_used is True
    assert resp.fallback_chain == ["plain-primary", "structured-fallback"]

    events = _read_skipped_events(capsys)
    assert len(events) == 1, events
    e = events[0]
    assert e["event"] == "provider_skipped_due_to_capability"
    assert e["role"] == "validator"
    assert e["provider"] == "native"
    assert "plain-primary" in e["model"]
    assert e["level"] == "primary"
    assert e["missing_capability"] == "structured_output"
    assert e["reason"] == "skipped_due_to_capability"
    assert e["gateway_attempted"] is True


def test_skip_event_carries_provider_model_role_level(capsys):
    """The skip event MUST include provider/model/role/level fields (R6.5 §C)."""
    reg = ModelRegistry([
        _profile(pid="x", level="primary", structured_output=False),
    ])
    gateway = ModelGateway(reg)
    from unittest.mock import patch
    with patch("core.model_gateway._adapter_for") as adapter_ctor:
        adapter_ctor.side_effect = AssertionError("should not be called")
        resp = gateway.structured(
            messages=[{"role": "user", "content": "hi"}],
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            role="validator",
            require={"structured_output": True},
        )
    assert resp.ok is False
    assert resp.error == "no_qualifying_provider"

    events = _read_skipped_events(capsys)
    assert len(events) == 1, events
    e = events[0]
    for field in ("provider", "model", "role", "level", "missing_capability"):
        assert field in e and e[field], f"{field} missing in {e}"


def test_no_secrets_in_skip_event(capsys):
    """R10.3 — telemetry MUST NOT carry secrets. We embed a fake secret
    in a profile's `endpoint` (the only place that could leak through)
    and assert the skip event does not include it."""
    profile_with_secret = ModelProfile(
        id="leaky",
        provider="native",
        model=f"m-{FAKE_SECRET}",
        endpoint=f"http://example.com/{FAKE_SECRET}",
        roles=["validator"],
        role="validator",
        level="primary",
        capabilities=ModelCapabilities(chat=True, structured_output=False),
    )
    reg = ModelRegistry([profile_with_secret])
    gateway = ModelGateway(reg)
    from unittest.mock import patch
    with patch("core.model_gateway._adapter_for") as adapter_ctor:
        adapter_ctor.side_effect = AssertionError("should not be called")
        resp = gateway.structured(
            messages=[{"role": "user", "content": "hi"}],
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            role="validator",
            require={"structured_output": True},
        )
    assert resp.ok is False
    out = capsys.readouterr().err
    # Use `out` for both assertions — `capsys.readouterr()` empties the
    # buffer, so calling it twice would lose the events on the second
    # call.
    events = _parse_skipped_events(out)
    assert FAKE_SECRET not in out, "secret leaked into telemetry stream"
    # The endpoint itself (which would carry the secret) is NOT part of
    # the skip event payload — only metadata fields.
    assert events, f"no skip event captured; stderr was: {out!r}"
    for e in events:
        assert "endpoint" not in e
