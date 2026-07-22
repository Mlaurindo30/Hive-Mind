"""Compatibility shim. Moved to `hive_mind.capture.session_events` (D004-R2).

`attach_project_identity` used to be the thing an entrypoint had to remember
to call. One did, one did not, and the one that did not wrote free labels into
the field Claude Mem groups by. Identity is now decided inside
`hive_mind.capture.ingest.ingest()`, unconditionally, so there is nothing left
for an entrypoint to forget.
"""
from __future__ import annotations

from hive_mind.capture.session_events import (  # noqa: F401
    attach_project_identity,
    session_to_events,
)

__all__ = ["attach_project_identity", "session_to_events"]
