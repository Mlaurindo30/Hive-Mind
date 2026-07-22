#!/usr/bin/env python3
"""Read-only audit of Windows operational runtime path references."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Mapping

import yaml

from hive_mind.validation.runtime_paths import (
    RuntimePathReference,
    find_runtime_path_violations,
)


_OPERATIONAL_DOCUMENTS = (
    ("config/runtime.yaml", "yaml"),
    ("logs/supervisor/manifest.json", "json"),
)
_REFERENCE_KEYS = {
    "arguments",
    "command",
    "commands",
    "env_file",
    "executable",
    "file",
    "log_dir",
    "path_name",
    "paths",
    "pyproject_root",
    "root",
    "vault",
    "working_directory",
}


def collect_windows_snapshot(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, list[dict]]:
    """Read processes, Scheduled Tasks and services without mutating them."""

    if os.name != "nt":
        return {"processes": [], "scheduled_tasks": [], "services": []}
    powershell = shutil.which("powershell.exe") or "powershell.exe"
    script = r"""
$processes = @(Get-CimInstance Win32_Process | Select-Object ProcessId, Name, CommandLine)
$scheduledTasks = @(
  foreach ($task in Get-ScheduledTask) {
    foreach ($action in $task.Actions) {
      [PSCustomObject]@{
        TaskName = $task.TaskName
        Execute = $action.Execute
        Arguments = $action.Arguments
        WorkingDirectory = $action.WorkingDirectory
      }
    }
  }
)
$services = @(Get-CimInstance Win32_Service | Select-Object Name, PathName)
[PSCustomObject]@{
  processes = $processes
  scheduled_tasks = $scheduledTasks
  services = $services
} | ConvertTo-Json -Depth 6 -Compress
"""
    completed = runner(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    return {
        key: list(payload.get(key) or [])
        for key in ("processes", "scheduled_tasks", "services")
    }


def load_operational_documents(root: Path) -> dict[str, object]:
    """Load only declared runtime inputs, never docs, tests or archive reports."""

    documents: dict[str, object] = {}
    for relative_path, format_name in _OPERATIONAL_DOCUMENTS:
        path = root / Path(relative_path)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        documents[relative_path] = (
            yaml.safe_load(text) if format_name == "yaml" else json.loads(text)
        )
    return documents


def _document_references(
    document_name: str,
    value: object,
    path: str = "",
    active: bool = False,
) -> list[RuntimePathReference]:
    references: list[RuntimePathReference] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            references.extend(
                _document_references(
                    document_name,
                    child,
                    child_path,
                    active or str(key).casefold() in _REFERENCE_KEYS,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            references.extend(
                _document_references(
                    document_name,
                    child,
                    f"{path}[{index}]",
                    active,
                )
            )
    elif active and isinstance(value, str) and value.strip():
        references.append(
            RuntimePathReference(
                source=f"operational_file:{document_name}:{path}",
                value=value,
            )
        )
    return references


def collect_runtime_references(
    root: Path,
    *,
    snapshot: Mapping[str, object],
    documents: Mapping[str, object],
) -> list[RuntimePathReference]:
    """Convert injected machine/file observations into named references."""

    references: list[RuntimePathReference] = []
    for process in snapshot.get("processes", []) or []:
        command_line = process.get("CommandLine")
        if command_line:
            identity = process.get("ProcessId") or process.get("Name") or "unknown"
            references.append(
                RuntimePathReference(
                    source=f"process:{identity}:command_line", value=str(command_line)
                )
            )
    for task in snapshot.get("scheduled_tasks", []) or []:
        name = task.get("TaskName") or "unknown"
        for field, label in (
            ("Execute", "executable"),
            ("Arguments", "arguments"),
            ("WorkingDirectory", "working_directory"),
        ):
            if task.get(field):
                references.append(
                    RuntimePathReference(
                        source=f"scheduled_task:{name}:{label}",
                        value=str(task[field]),
                    )
                )
    for service in snapshot.get("services", []) or []:
        if service.get("PathName"):
            name = service.get("Name") or "unknown"
            references.append(
                RuntimePathReference(
                    source=f"service:{name}:path_name",
                    value=str(service["PathName"]),
                )
            )
    for document_name, document in documents.items():
        references.extend(_document_references(document_name, document))
    return references


def audit_runtime_paths(
    canonical_root: str | Path,
    *,
    snapshot_loader: Callable[[], Mapping[str, object]] = collect_windows_snapshot,
    document_loader: Callable[[Path], Mapping[str, object]] = load_operational_documents,
) -> list[dict[str, str]]:
    """Collect and audit operational references with injectable read boundaries."""

    root = Path(canonical_root)
    references = collect_runtime_references(
        root,
        snapshot=snapshot_loader(),
        documents=document_loader(root),
    )
    return [
        finding.to_dict()
        for finding in find_runtime_path_violations(references, str(root))
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    findings = audit_runtime_paths(args.root)
    print(json.dumps({"findings": findings}, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
