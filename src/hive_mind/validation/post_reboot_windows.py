"""Fresh managed-state validation for the Windows post-reboot path.

The validator deliberately does not inspect legacy supervisor logs or a
manifest.  Those files describe prior intent; ``services.managed.json`` and
the current process tree are the operational authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import ctypes
from pathlib import Path
from typing import Mapping

from hive_mind.daemon.state import MANAGED_STATE_FILENAME, service_records

_STATE_RELATIVE_PATH = Path(".hive-mind") / "state" / MANAGED_STATE_FILENAME
_DEFAULT_MAX_AGE_SECONDS = 300


@dataclass(frozen=True)
class PostRebootReport:
    """Result of checking the live managed process tree."""

    status: str
    checks: dict[str, bool]
    failures: tuple[str, ...]
    state_path: str
    supervisor_pid: int | None
    services: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _read_managed_state(root: Path) -> tuple[Path, dict | None]:
    path = root / _STATE_RELATIVE_PATH
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return path, None
    return path, payload if isinstance(payload, dict) else None


def _windows_process_parents() -> dict[int, int | None]:
    """Read the current Windows process table without starting a shell."""

    if __import__("os").name != "nt":
        return {}

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", ctypes.c_ulong),
            ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_ulong),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        return {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        parents: dict[int, int | None] = {}
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return parents
        while True:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID) or None
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
        return parents
    finally:
        kernel32.CloseHandle(snapshot)


def _is_descendant(pid: int, supervisor_pid: int, parents: Mapping[int, int | None]) -> bool:
    seen: set[int] = set()
    current = pid
    while current not in seen:
        seen.add(current)
        parent = parents.get(current)
        if parent == supervisor_pid:
            return True
        if parent is None:
            return False
        current = parent
    return False


def _service_ready(service: Mapping[str, object]) -> bool:
    return service.get("state") == "running" and service.get("readiness", "ready") == "ready"


def validate_live_runtime(
    root: Path | str,
    *,
    process_parents: Mapping[int, int | None] | None = None,
    now: datetime | None = None,
    max_age_seconds: int = _DEFAULT_MAX_AGE_SECONDS,
) -> PostRebootReport:
    """Validate current Supervisor ownership from fresh managed state only.

    ``process_parents`` is injectable for deterministic tests.  In production
    it comes from ToolHelp, avoiding a PowerShell subprocess in the logon path.
    """

    root_path = Path(root)
    state_path, state = _read_managed_state(root_path)
    checks = {
        "managed_state_present": state is not None,
        "fresh_managed_state": False,
        "supervisor_alive": False,
        "managed_children_owned": False,
        "required_services_ready": False,
    }
    failures: list[str] = []
    supervisor_pid: int | None = None
    services: tuple[str, ...] = ()

    if state is None:
        failures.append("missing_managed_state")
        return PostRebootReport("fail", checks, tuple(failures), str(state_path), None, services)

    updated_at = _parse_timestamp(state.get("updated_at"))
    reference_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if updated_at is None or (reference_time - updated_at).total_seconds() > max_age_seconds:
        failures.append("stale_managed_state")
    else:
        checks["fresh_managed_state"] = True

    raw_pid = state.get("supervisor_pid")
    if isinstance(raw_pid, int) and raw_pid > 0:
        supervisor_pid = raw_pid
    else:
        failures.append("invalid_supervisor_pid")

    parents = dict(process_parents) if process_parents is not None else _windows_process_parents()
    if supervisor_pid is not None:
        if supervisor_pid in parents:
            checks["supervisor_alive"] = True
        else:
            failures.append("dead_supervisor")

    records = service_records(state)
    services = tuple(str(record.get("name", "unknown")) for record in records)
    required_ready = True
    children_owned = True
    for service in records:
        name = str(service.get("name", "unknown"))
        required = bool(service.get("required"))
        running = service.get("state") == "running"
        if required and not _service_ready(service):
            failures.append(f"unhealthy_required_service:{name}")
            required_ready = False
        # An optional service that has already exited has no live child to
        # own.  It must not turn an otherwise healthy runtime into a failed
        # post-reboot validation; a running optional child is still checked
        # strictly for orphaning.
        if not running and not required:
            continue
        pid = service.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            failures.append(f"missing_child_pid:{name}")
            children_owned = False
            continue
        if pid not in parents:
            failures.append(f"dead_child:{name}")
            children_owned = False
            continue
        if supervisor_pid is None or not _is_descendant(pid, supervisor_pid, parents):
            failures.append(f"orphan_child:{name}")
            children_owned = False
    checks["required_services_ready"] = required_ready
    checks["managed_children_owned"] = children_owned

    return PostRebootReport(
        "pass" if all(checks.values()) else "fail",
        checks,
        tuple(failures),
        str(state_path),
        supervisor_pid,
        services,
    )
