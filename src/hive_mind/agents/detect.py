"""Native provider detection (ADR-013).

A provider is present when any of its commands is on PATH, or any of its
marker directories exists. All environment access (HOME, APPDATA, command
lookup) is injectable so detection is deterministic and cross-platform.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from hive_mind.agents.registry import PROVIDERS, ProviderSpec


@dataclass(frozen=True)
class DetectionResult:
    id: str
    name: str
    detected: bool
    evidence: Optional[str] = None


def _default_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))


def _default_appdata() -> Path:
    return Path(os.environ.get("APPDATA") or (_default_home() / "AppData" / "Roaming"))


def detect_providers(
    *,
    home: Optional[Path] = None,
    appdata: Optional[Path] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
) -> list[DetectionResult]:
    """Detect every registered provider. Returns one result per provider."""
    home = Path(home) if home is not None else _default_home()
    appdata = Path(appdata) if appdata is not None else _default_appdata()
    lookup = which if which is not None else shutil.which

    results: list[DetectionResult] = []
    for spec in PROVIDERS:
        detected, evidence = _detect_one(spec, home, appdata, lookup)
        results.append(
            DetectionResult(
                id=spec.id, name=spec.name, detected=detected, evidence=evidence
            )
        )
    return results


def _detect_one(
    spec: ProviderSpec,
    home: Path,
    appdata: Path,
    lookup: Callable[[str], Optional[str]],
) -> tuple[bool, Optional[str]]:
    for command in spec.commands:
        if lookup(command):
            return True, f"command: {command}"
    for marker in spec.home_markers:
        path = home / marker
        if path.exists():
            return True, f"path: {path}"
    for marker in spec.appdata_markers:
        path = appdata / marker
        if path.exists():
            return True, f"path: {path}"
    return False, None
