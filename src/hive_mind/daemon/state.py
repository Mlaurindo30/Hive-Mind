"""Shared read-only access to daemon state files."""
from __future__ import annotations

import json
from pathlib import Path

SHADOW_STATE_FILENAME = "services.shadow.json"
MANAGED_STATE_FILENAME = "services.managed.json"


def read_state(state_dir: Path | str) -> dict | None:
    """Read the best available daemon state.

    Managed state takes precedence over shadow state because once the runtime
    is cut over the daemon becomes the owner, not just an observer.
    """
    state_path = Path(state_dir)
    for filename in (MANAGED_STATE_FILENAME, SHADOW_STATE_FILENAME):
        candidate = state_path / filename
        if not candidate.exists():
            continue
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def expected_state_paths(state_dir: Path | str) -> tuple[Path, Path]:
    state_path = Path(state_dir)
    return (
        state_path / MANAGED_STATE_FILENAME,
        state_path / SHADOW_STATE_FILENAME,
    )


def service_records(state: dict | None) -> list[dict]:
    if not state:
        return []
    services = state.get("services") or []
    if isinstance(services, dict):
        return [{"name": name, **payload} for name, payload in services.items()]
    return list(services)


def state_ready(state: dict | None) -> bool:
    if not state:
        return False
    if "ready" in state:
        return bool(state["ready"])
    records = service_records(state)
    required = [svc for svc in records if svc.get("required")]
    if not required:
        return True
    return all(
        svc.get("state") == "running" or svc.get("readiness") == "ready"
        for svc in required
    )
