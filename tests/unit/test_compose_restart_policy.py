"""Required infrastructure must come back when Docker restarts.

Docker Desktop autostarts with Windows, but a container only returns if its
compose service declares a restart policy. Observed on the live host:
`sinapse-falkordb` had `unless-stopped` and came back, while milvus and the
five ragflow containers had `restart: no` and stayed down — so the stack
looked "enabled" while two of the three required projects were absent.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "runtime.yaml"

RESTORING_POLICIES = {"always", "unless-stopped"}


def _required_compose_files() -> list[Path]:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    files = []
    for project in data.get("compose_projects", []):
        # `required` defaults to true in the schema; only an explicit false opts out
        if project.get("required") is False:
            continue
        path = ROOT / project["file"]
        if path.is_file():
            files.append(path)
    return files


def test_manifest_declares_compose_projects():
    assert _required_compose_files(), "no required compose project resolved"


@pytest.mark.parametrize(
    "compose_file",
    _required_compose_files(),
    ids=lambda p: p.parent.name or p.name,
)
def test_every_required_service_restarts_with_docker(compose_file: Path):
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    missing = [
        name
        for name, service in (data.get("services") or {}).items()
        if str(service.get("restart", "no")) not in RESTORING_POLICIES
    ]
    assert missing == [], (
        f"{compose_file.relative_to(ROOT)}: these services will not come back "
        f"when Docker restarts: {missing}"
    )
