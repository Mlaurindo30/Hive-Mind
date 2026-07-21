"""Discovery of real provider capture sources (read-only).

No synthetic data: every path here is a file a provider actually wrote on
this machine. The adapter registry declares the glob patterns; this module
resolves them and reports what exists, with recency.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class SourceInventory:
    provider: str
    files: tuple[Path, ...]
    newest: Optional[Path]
    newest_mtime: Optional[float]

    @property
    def found(self) -> bool:
        return bool(self.files)


def _adapters() -> dict:
    """The capture adapter registry (still legacy-located; see D003-R1)."""
    import sys

    from hive_mind.project import resolve_project_root

    root = resolve_project_root()
    capture_dir = root / "scripts" / "capture"
    for entry in (str(root), str(capture_dir)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    import capture_adapters  # noqa: PLC0415 - legacy location until D003-R1

    return capture_adapters.ADAPTERS


def provider_ids() -> list[str]:
    return sorted(_adapters())


def inventory(provider: str, *, limit: int = 5) -> SourceInventory:
    """Resolve a provider's real source files, newest first."""
    adapters = _adapters()
    spec = adapters.get(provider)
    if spec is None:
        return SourceInventory(provider, (), None, None)

    hits: set[str] = set()
    for pattern in spec.get("sources") or ():
        hits.update(glob.glob(pattern, recursive=True))
    files = sorted(
        (Path(h) for h in hits if os.path.isfile(h)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    if not files:
        return SourceInventory(provider, (), None, None)
    return SourceInventory(
        provider, tuple(files), files[0], files[0].stat().st_mtime
    )


def parse_sessions(provider: str, source: Path) -> list[dict]:
    """Run the provider's real parser over a real source file."""
    spec = _adapters().get(provider)
    if spec is None:
        raise KeyError(provider)
    return list(spec["parser"](source) or [])
