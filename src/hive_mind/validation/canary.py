"""Multiagent capture canary over real data (D004-R1).

Replaces `scripts/health/canary_multiagent_runner.py`, which built a synthetic
session, created mock SQLite schemas and monkeypatched the bridge's
`get_connection`. That proved the wiring of code it had already replaced with
doubles — it could not fail while real capture was broken.

This canary injects nothing and writes nothing. For each provider it:

  1. resolves the provider's **real** source files from the adapter registry;
  2. runs the provider's **real** parser over the newest one;
  3. resolves identity with the **real** shipped alias registry;
  4. reports the **real** delivery state (outbox + UMC), read-only.

A provider only passes when its real sessions resolve to a canonical
project id AND its captured events actually reached a destination.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from hive_mind.validation import sources
from hive_mind.validation.delivery import (
    OutboxState,
    UmcState,
    inspect_outbox,
    inspect_umc,
)
from hive_mind.validation.models import CanaryReport, CanaryResult, CanaryStatus


@dataclass(frozen=True)
class CanaryPaths:
    outbox_db: Path
    umc_db: Path


def _resolver():
    """The real ProjectIdentityResolver with the shipped alias registry."""
    import sys

    from hive_mind.project import resolve_project_root

    root = resolve_project_root()
    for entry in (str(root), str(root / "scripts" / "capture")):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    from hive_mind.projects.identity import (  # noqa: PLC0415 - until D003-R1
        ProjectAliasRegistry,
        ProjectIdentityResolver,
    )

    registry_path = root / "config" / "project-aliases.yaml"
    return ProjectIdentityResolver(registry=ProjectAliasRegistry.load(registry_path))


def _attach_identity(provider: str, session: dict, resolver, surface: str):
    from scripts.capture.session_events import (  # noqa: PLC0415 - until D003-R1
        attach_project_identity,
    )

    return attach_project_identity(
        provider=provider, session=session, resolver=resolver,
        default_surface=surface,
    )


def run_provider(
    provider: str,
    *,
    resolver=None,
    outbox: Optional[OutboxState] = None,
) -> CanaryResult:
    """Validate one provider against its real sources and real delivery."""
    started = time.monotonic()

    def done(status, **kw) -> CanaryResult:
        return CanaryResult(
            provider=provider, status=status,
            duration_seconds=round(time.monotonic() - started, 3), **kw
        )

    inv = sources.inventory(provider)
    if not inv.found:
        return done(CanaryStatus.SKIPPED, reason="no real source file on this host")

    try:
        sessions = sources.parse_sessions(provider, inv.newest)
    except Exception as exc:  # noqa: BLE001 - a parser failure is a real result
        return done(CanaryStatus.ERROR, reason=f"parser failed: {type(exc).__name__}: {exc}")

    if not sessions:
        return done(
            CanaryStatus.FAILED,
            reason=f"parser produced no session from {inv.newest.name}",
        )

    resolver = resolver or _resolver()
    canonical = 0
    project_id = None          # first id seen, for diagnostics
    canonical_id = None        # first *classified* id — what justifies a pass
    for session in sessions:
        normalized = _attach_identity(provider, session, resolver, "cli")
        pid = normalized.get("project_id")
        project_id = project_id or pid
        if pid and not pid.startswith("unclassified/"):
            canonical += 1
            canonical_id = canonical_id or pid

    if project_id is None:
        return done(CanaryStatus.FAILED, reason="no project identity attached")

    # An `unclassified/<provider>` id means identity resolution failed on real
    # data. Passing on it would make the canary agree with a broken pipeline.
    if canonical == 0:
        return done(
            CanaryStatus.FAILED,
            project_id=project_id,
            reason=(
                f"{len(sessions)} real session(s) parsed but none resolved to a "
                f"classified project (got {project_id})"
            ),
        )

    # Real delivery: were this provider's captured events ever delivered?
    undelivered = 0
    if outbox is not None and outbox.exists:
        undelivered = dict(outbox.by_provider).get(provider, 0)
        if undelivered and outbox.delivered == 0:
            return done(
                CanaryStatus.FAILED,
                project_id=project_id,
                reason=(
                    f"{undelivered} captured events sit undelivered in the outbox "
                    "(nothing was ever delivered)"
                ),
            )

    # Report the identity that justified the pass, not merely the first seen.
    return done(CanaryStatus.PASSED, project_id=canonical_id, inserted=canonical)


def run(
    providers: Optional[list[str]] = None, *, paths: Optional[CanaryPaths] = None
) -> tuple[CanaryReport, OutboxState, UmcState]:
    """Run the canary across providers. Reads only; writes nothing."""
    paths = paths or default_paths()
    outbox = inspect_outbox(paths.outbox_db)
    umc = inspect_umc(paths.umc_db)
    resolver = _resolver()

    targets = providers if providers is not None else sources.provider_ids()
    results = tuple(
        run_provider(p, resolver=resolver, outbox=outbox) for p in targets
    )
    return CanaryReport(results=results), outbox, umc


def default_paths() -> CanaryPaths:
    """Real database locations on this host."""
    import os

    home = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
    runtime = Path(os.environ.get("SINAPSE_HOME") or "D:/Hive-Mind")
    return CanaryPaths(
        outbox_db=home / ".claude-mem" / "capture.db",
        umc_db=runtime / "hive_mind.db",
    )
