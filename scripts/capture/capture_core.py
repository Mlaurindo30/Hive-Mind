"""Compatibility shim. The implementation moved to the package (D004-R2).

`scripts/capture/capture_core.py` was the capture engine, and it decided
project identity with a permissive fallback:

    proj = sess.get("project_name") or sess.get("project") or PROJECT

That is how `preciso-que-verifique-o-por-que-3` became a project with 37
observations, and how this repository's worktree became a project separate
from its own root. The engine now lives at `hive_mind.capture.engine` and does
transport only; identity is decided once, in `hive_mind.capture.identity`.

Nothing new should be added here. `ingest` is re-exported from
`hive_mind.capture.ingest`, so a caller that still imports this module gets
the enforcing version rather than the old one.
"""
from __future__ import annotations

from hive_mind.capture.engine import (  # noqa: F401
    BASE,
    DATA_DIR,
    OBS_CAP,
    PROJECT,
    ROOT,
    STATE,
    STATE_DIR,
    CanonicalIdentityRequired,
    SeenStore,
    _norm,
    _post,
    _safe_print,
    _src_mtime,
    content_hash,
    emit,
    load_state,
    project_from_cwd,
    save_state,
    text_content,
    worker_alive,
)
from hive_mind.capture.ingest import ingest, ingest_many  # noqa: F401

__all__ = [
    "BASE", "DATA_DIR", "OBS_CAP", "PROJECT", "ROOT", "STATE", "STATE_DIR",
    "CanonicalIdentityRequired", "SeenStore", "content_hash", "emit", "ingest",
    "ingest_many", "load_state", "project_from_cwd", "save_state",
    "text_content", "worker_alive",
]
