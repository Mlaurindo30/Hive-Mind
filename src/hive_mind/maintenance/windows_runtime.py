"""Native Windows autostart/runtime task registration for Hive-Mind."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from hive_mind.install.windows_launchers import (
    expected_gui_launchers,
    validate_gui_launchers,
)
from hive_mind.maintenance.lock import MaintenanceLock

TASK_DESCRIPTION = "Hive-Mind native Windows runtime"
TASK_NAMESPACE = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


@dataclass(frozen=True)
class WindowsRuntimeSpec:
    name: str
    execute: str
    arguments: str
    working_directory: str
    trigger: str
    description: str = TASK_DESCRIPTION
    start_when_available: bool = True
    restart_count: int = 0
    execution_time_limit: str = "PT0S"
    watchdog_interval_minutes: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WindowsRuntimeResult:
    name: str
    execute: str
    arguments: str
    working_directory: str
    status: str
    reason: str
    start_when_available: bool
    restart_count: int
    execution_time_limit: str
    watchdog_interval_minutes: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WindowsRuntimeReport:
    project_root: str
    apply: bool
    registered: int
    skipped: int
    entries: tuple[WindowsRuntimeResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "project_root": self.project_root,
            "apply": self.apply,
            "registered": self.registered,
            "skipped": self.skipped,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def windows_runtime_specs(root: str | Path) -> list[WindowsRuntimeSpec]:
    root = Path(root).resolve()
    launchers = expected_gui_launchers(root)
    supervisor_args = f'--project-root "{root}"'
    return [
        WindowsRuntimeSpec(
            name="HiveMind-Supervisor",
            execute=str(launchers["hive-mind-supervisorw"]),
            arguments=supervisor_args,
            working_directory=str(root),
            trigger="logon",
            restart_count=10,
        ),
        WindowsRuntimeSpec(
            name="HiveMind-PostRebootValidation",
            execute=str(launchers["hive-mind-post-rebootw"]),
            arguments="",
            working_directory=str(root),
            trigger="logon",
            execution_time_limit="PT1H",
        ),
    ]


def _run_schtasks(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["schtasks.exe", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _task_query_xml(task_name: str) -> str | None:
    result = _run_schtasks("/query", "/tn", task_name, "/xml", "ONE")
    if result.returncode == 0:
        return result.stdout
    detail = (result.stderr or result.stdout).strip()
    normalized = detail.lower()
    not_found_markers = (
        "cannot find the file specified",
        "cannot find the task",
        "does not exist",
        "nao existe",
        "não existe",
        "nao foi possivel localizar",
        "não foi possível localizar",
        "0x80070002",
    )
    if any(marker in normalized for marker in not_found_markers):
        return None
    raise RuntimeError(
        f"could not export Scheduled Task XML for {task_name}: "
        f"{detail or f'schtasks exited {result.returncode}'}"
    )


def _task_signature_from_xml(xml_text: str) -> tuple[str, str, str] | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    command = root.findtext(".//t:Actions/t:Exec/t:Command", namespaces=TASK_NAMESPACE)
    arguments = root.findtext(".//t:Actions/t:Exec/t:Arguments", namespaces=TASK_NAMESPACE)
    working_directory = root.findtext(".//t:Actions/t:Exec/t:WorkingDirectory", namespaces=TASK_NAMESPACE)
    if command is None:
        return None
    return (command, arguments or "", working_directory or "")


def _task_matches_spec(task_name: str, spec: WindowsRuntimeSpec) -> bool:
    xml = _task_query_xml(task_name)
    signature = _task_signature_from_xml(xml) if xml else None
    return signature == (spec.execute, spec.arguments, spec.working_directory)


def _task_xml(spec: WindowsRuntimeSpec) -> str:
    root = ET.Element("Task", version="1.4", xmlns=TASK_NAMESPACE["t"])
    reg = ET.SubElement(root, "RegistrationInfo")
    ET.SubElement(reg, "Description").text = spec.description

    triggers = ET.SubElement(root, "Triggers")
    if spec.trigger != "logon":
        raise ValueError(f"unsupported Windows runtime trigger: {spec.trigger}")
    logon = ET.SubElement(triggers, "LogonTrigger")
    ET.SubElement(logon, "Enabled").text = "true"

    principals = ET.SubElement(root, "Principals")
    principal = ET.SubElement(principals, "Principal", id="Author")
    ET.SubElement(principal, "LogonType").text = "InteractiveToken"
    ET.SubElement(principal, "RunLevel").text = "LeastPrivilege"

    settings = ET.SubElement(root, "Settings")
    for tag, value in (
        ("MultipleInstancesPolicy", "IgnoreNew"),
        ("DisallowStartIfOnBatteries", "false"),
        ("StopIfGoingOnBatteries", "false"),
        ("AllowHardTerminate", "true"),
        ("StartWhenAvailable", "true" if spec.start_when_available else "false"),
        ("RunOnlyIfNetworkAvailable", "false"),
        ("AllowStartOnDemand", "true"),
        ("Enabled", "true"),
        ("Hidden", "true"),
        ("RunOnlyIfIdle", "false"),
        ("WakeToRun", "false"),
        ("ExecutionTimeLimit", spec.execution_time_limit),
        ("Priority", "7"),
    ):
        ET.SubElement(settings, tag).text = value
    idle = ET.SubElement(settings, "IdleSettings")
    ET.SubElement(idle, "StopOnIdleEnd").text = "false"
    ET.SubElement(idle, "RestartOnIdle").text = "false"
    if spec.restart_count > 0:
        restart = ET.SubElement(settings, "RestartOnFailure")
        ET.SubElement(restart, "Interval").text = "PT1M"
        ET.SubElement(restart, "Count").text = str(spec.restart_count)

    actions = ET.SubElement(root, "Actions", Context="Author")
    exec_node = ET.SubElement(actions, "Exec")
    ET.SubElement(exec_node, "Command").text = spec.execute
    ET.SubElement(exec_node, "Arguments").text = spec.arguments
    ET.SubElement(exec_node, "WorkingDirectory").text = spec.working_directory
    return '<?xml version="1.0" encoding="UTF-16"?>\n' + ET.tostring(root, encoding="unicode")


def _is_access_denied(result: subprocess.CompletedProcess[str]) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    return result.returncode != 0 and ("access" in text or "acesso" in text or "0x80070005" in text)


def register_windows_runtime(*, root: str | Path, apply: bool = False) -> WindowsRuntimeReport:
    root = Path(root).resolve()
    specs = windows_runtime_specs(root)
    results: list[WindowsRuntimeResult] = []
    registered = 0
    skipped = 0
    if not apply:
        for spec in specs:
            results.append(
                WindowsRuntimeResult(
                    name=spec.name,
                    execute=spec.execute,
                    arguments=spec.arguments,
                    working_directory=spec.working_directory,
                    status="DRY_RUN",
                    reason="would register runtime task",
                    start_when_available=spec.start_when_available,
                    restart_count=spec.restart_count,
                    execution_time_limit=spec.execution_time_limit,
                    watchdog_interval_minutes=spec.watchdog_interval_minutes,
                )
            )
        return WindowsRuntimeReport(
            project_root=str(root),
            apply=False,
            registered=0,
            skipped=0,
            entries=tuple(results),
        )

    validate_gui_launchers(root)

    lock_path = root / ".hive-mind" / "state" / "windows-runtime.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with MaintenanceLock(lock_path):
        with tempfile.TemporaryDirectory(prefix="hive-mind-runtime-") as tmp:
            tmpdir = Path(tmp)
            backup_dir = (
                root
                / ".hive-mind"
                / "backups"
                / "windows-runtime"
                / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            )
            backups: dict[str, Path] = {}
            for spec in specs:
                prior_xml = _task_query_xml(spec.name)
                if prior_xml is None:
                    continue
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"{spec.name}.backup.xml"
                backup_path.write_text(prior_xml, encoding="utf-16")
                backups[spec.name] = backup_path

            created: list[str] = []
            try:
                for spec in specs:
                    xml_path = tmpdir / f"{spec.name}.xml"
                    xml_path.write_text(_task_xml(spec), encoding="utf-16")
                    result = _run_schtasks(
                        "/create", "/tn", spec.name, "/xml", str(xml_path), "/f"
                    )
                    if result.returncode != 0:
                        detail = (result.stderr or result.stdout).strip()
                        raise RuntimeError(detail or f"schtasks create failed for {spec.name}")
                    created.append(spec.name)
                    registered += 1
                    results.append(
                        WindowsRuntimeResult(
                            name=spec.name,
                            execute=spec.execute,
                            arguments=spec.arguments,
                            working_directory=spec.working_directory,
                            status="REGISTERED",
                            reason="runtime task registered",
                            start_when_available=spec.start_when_available,
                            restart_count=spec.restart_count,
                            execution_time_limit=spec.execution_time_limit,
                            watchdog_interval_minutes=spec.watchdog_interval_minutes,
                        )
                    )
            except Exception as exc:
                restore_errors: list[str] = []
                for name, backup_path in backups.items():
                    restore = _run_schtasks(
                        "/create", "/tn", name, "/xml", str(backup_path), "/f"
                    )
                    if restore.returncode != 0:
                        restore_errors.append(name)
                for name in created:
                    if name not in backups:
                        _run_schtasks("/delete", "/tn", name, "/f")
                message = f"Windows runtime registration failed: {exc}"
                if restore_errors:
                    message += "; failed to restore: " + ", ".join(restore_errors)
                raise RuntimeError(message) from exc

    return WindowsRuntimeReport(
        project_root=str(root),
        apply=True,
        registered=registered,
        skipped=skipped,
        entries=tuple(results),
    )
