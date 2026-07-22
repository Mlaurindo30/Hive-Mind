"""What an identity decision is, and what may be done with it (D004-R2).

The three statuses exist because the two obvious policies are both wrong.

Accepting whatever the parser called the project is how
`preciso-que-verifique-o-por-que-3` became a project with 37 observations,
and how this repository's own worktree became a project separate from its
root. Refusing everything without a Git repository is the opposite mistake:
plenty of legitimate capture happens outside one, and losing it to protect a
dropdown is a bad trade.

So: resolve when there is evidence, fall back to a deterministic
`unclassified/<provider>` when there is not, and refuse only what is actually
broken.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class IdentityStatus(str, Enum):
    """How much the resolver could establish, and what that permits."""

    CLASSIFIED = "classified"
    """Identity resolved from evidence. Delivery allowed."""

    UNCLASSIFIED = "unclassified"
    """Not enough evidence. Delivery allowed, flagged, health degraded."""

    INVALID = "invalid"
    """Envelope malformed, inconsistent or unresolvable. Delivery refused."""


class IdentityRefused(Exception):
    """Raised before anything is written, never after.

    Carries the reason so the caller can log why a session was dropped
    instead of discovering a silent gap later.
    """

    def __init__(self, reason: str, *, provider: str = "", detail: str = "") -> None:
        self.reason = reason
        self.provider = provider
        self.detail = detail
        super().__init__(f"{provider or 'session'}: {reason}"
                         + (f" ({detail})" if detail else ""))


@dataclass(frozen=True)
class CaptureIdentity:
    """One canonical identity decision, with the evidence that produced it.

    `raw_label` is what the parser called the project. It is kept so the
    decision can be audited — and kept *only* here, never in a field anything
    groups, filters or paths by.
    """

    project_id: str
    project_name: str
    status: IdentityStatus
    provider: str
    surface: str = "unknown"
    resolution_method: str = ""
    resolution_confidence: float = 0.0
    workspace_root: Optional[str] = None
    repository_root: Optional[str] = None
    repository_remote: Optional[str] = None
    git_common_dir: Optional[str] = None
    worktree_name: Optional[str] = None
    branch: Optional[str] = None
    referenced_projects: tuple[str, ...] = ()
    raw_label: Optional[str] = None
    envelope: dict[str, Any] = field(default_factory=dict)

    @property
    def deliverable(self) -> bool:
        return self.status is not IdentityStatus.INVALID

    @property
    def degraded(self) -> bool:
        return self.status is IdentityStatus.UNCLASSIFIED

    def to_metadata(self) -> dict[str, Any]:
        """The metadata block a delivered observation carries.

        Two separate namespaces, deliberately:

        - `project_identity` is the canonical envelope. Anything downstream —
          Dream Cycle, vault paths, graph namespaces — reads from here.
        - `capture` is audit trail. The raw parser label lives here and
          nowhere else, so it cannot be mistaken for authority by a later
          reader who did not know the difference.
        """
        envelope = dict(self.envelope) if self.envelope else {}
        envelope.setdefault("project_id", self.project_id)
        envelope.setdefault("project_name", self.project_name)
        envelope["identity_status"] = self.status.value
        if self.resolution_method:
            envelope.setdefault("resolution_method", self.resolution_method)

        capture: dict[str, Any] = {"provider": self.provider,
                                   "surface": self.surface}
        if self.raw_label is not None:
            capture["raw_project_label"] = self.raw_label
        return {"project_identity": envelope, "capture": capture}
