"""Guard the single-owner contract for capture delivery.

The canonical pipeline is::

    provider/parser -> normalized session -> capture_core.ingest() -> Claude Mem

The deprecated ``ProviderEvent -> CaptureQueue -> outbox`` path is retained on
disk for historical auditing only and must never be wired into the runtime:
nothing drains that outbox, so a second delivery owner silently loses events.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "scripts" / "setup"
CAPTURE = ROOT / "scripts" / "capture"

DEPRECATED_TOKENS = ("install-capture-hooks", "capture-hook", "CaptureQueue")


def _executable_lines(path: Path) -> list[str]:
    """Return the script's lines with comment-only lines removed.

    Comments are allowed to *mention* the deprecated path -- that is how the
    decision stays documented at the call site it was removed from.
    """
    lines = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        lines.append(raw)
    return lines


def test_register_mcp_ps1_does_not_wire_the_outbox_pipeline():
    script = SETUP / "register-mcp.ps1"
    offenders = [
        (n, line)
        for n, line in enumerate(_executable_lines(script), 1)
        for token in DEPRECATED_TOKENS
        if token in line
    ]
    assert offenders == [], (
        "register-mcp.ps1 must not register the deprecated outbox delivery "
        f"path, found: {offenders}"
    )


@pytest.mark.parametrize(
    "relative",
    [
        "scripts/setup/register-windows-runtime.ps1",
        "scripts/setup/register-windows-jobs.ps1",
        "scripts/setup/install_services.py",
        "install.ps1",
    ],
)
def test_runtime_entrypoints_do_not_reference_capture_queue(relative):
    path = ROOT / relative
    if not path.exists():
        pytest.skip(f"{relative} not present in this layout")
    text = path.read_text(encoding="utf-8-sig")
    for token in DEPRECATED_TOKENS:
        assert token not in text, (
            f"{relative} must not reference the deprecated outbox path ({token})"
        )


def _adapters():
    if str(CAPTURE) not in sys.path:
        sys.path.insert(0, str(CAPTURE))
    import capture_adapters

    return capture_adapters.ADAPTERS


def test_codex_is_delivered_by_capture_core_ingest():
    adapters = _adapters()
    assert "codex" in adapters, "codex must stay registered as a parser adapter"
    assert adapters["codex"]["owner"] == "realtime", (
        "codex must be delivered by capture-realtime.py, which calls "
        "hive_mind.capture.ingest()"
    )


@pytest.mark.parametrize("runner", ["capture-realtime.py", "capture-tailer.py"])
def test_delivery_runners_use_the_canonical_ingest(runner):
    """Both runners deliver through the one enforcing entrypoint.

    The canonical path moved from `capture_core.ingest` to
    `hive_mind.capture.ingest` in D004-R2, and the move is the point: the
    package decides project identity, so a runner cannot deliver without it.
    Calling the transport (`engine.emit`) directly would bypass that, which is
    exactly what the tailer used to do.
    """
    text = (CAPTURE / runner).read_text(encoding="utf-8")
    assert "capture.ingest(" in text, (
        f"{runner} must deliver through hive_mind.capture.ingest()"
    )
    assert "core.ingest(" not in text, (
        f"{runner} still calls the pre-D004-R2 entrypoint"
    )
    assert "engine.emit(" not in text and "core.emit(" not in text, (
        f"{runner} must not call the transport directly — that skips identity"
    )
    for token in ("CaptureQueue", "capture_queue"):
        assert token not in text, (
            f"{runner} must not import or use the deprecated {token}"
        )


def test_native_claude_code_capture_is_not_duplicated():
    """Claude Code ships its own native capture plugin.

    Hive-Mind must not register a competing adapter for it, otherwise the same
    session would be ingested twice.
    """
    adapters = _adapters()
    assert "claude" not in adapters
    assert "claude-code" not in adapters


def test_every_provider_has_exactly_one_delivery_owner():
    adapters = _adapters()
    for provider, spec in adapters.items():
        assert spec["owner"] in {"realtime", "timer"}, (
            f"{provider} has an unknown delivery owner: {spec['owner']!r}"
        )
