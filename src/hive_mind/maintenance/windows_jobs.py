"""Native Windows scheduled-job registration for Hive-Mind."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from hive_mind.maintenance.lock import MaintenanceLock


TASK_DESCRIPTION = "Hive-Mind scheduled knowledge job"
TASK_TIME = "02:00"


@dataclass(frozen=True)
class WindowsJobSpec:
    name: str
    execute: str
    arguments: str
    working_directory: str
    description: str = TASK_DESCRIPTION
    schedule_time: str = TASK_TIME
    source_script: str | None = None
    exists: bool = True
    # ISO-8601 duration of the intra-day repetition (e.g. "PT4H"). When set,
    # the task fires at schedule_time and repeats every repeat_interval for the
    # rest of the day — matches the runtime.yaml cron (ex.: dream-cycle "0 */4 * * *").
    repeat_interval: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WindowsJobResult:
    name: str
    execute: str
    arguments: str
    working_directory: str
    source_script: str | None
    status: str
    reason: str
    backup_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WindowsJobsReport:
    project_root: str
    backup_dir: str
    apply: bool
    scanned: int
    registered: int
    skipped: int
    entries: tuple[WindowsJobResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "project_root": self.project_root,
            "backup_dir": self.backup_dir,
            "apply": self.apply,
            "scanned": self.scanned,
            "registered": self.registered,
            "skipped": self.skipped,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def windows_job_specs(root: str | Path) -> list[WindowsJobSpec]:
    root = Path(root).resolve()
    python = root / ".venv" / "Scripts" / "pythonw.exe"
    jobs: list[WindowsJobSpec] = []

    def _script_job(name: str, rel_script: str) -> WindowsJobSpec:
        target = root / rel_script
        return WindowsJobSpec(
            name=name,
            execute=str(python),
            arguments=f'"{target}"',
            working_directory=str(root),
            source_script=rel_script.replace("/", "\\"),
            exists=target.exists() and python.exists(),
        )

    jobs.append(
        WindowsJobSpec(
            name="HiveMind-DreamCycle",
            execute=str(python),
            arguments=f'"{root / "scripts" / "dream" / "dream_cycle.py"}"',
            working_directory=str(root),
            source_script=r"scripts\dream\dream_cycle.py",
            exists=python.exists() and (root / "scripts" / "dream" / "dream_cycle.py").exists(),
            # runtime.yaml: dream-cycle cron "0 */4 * * *" (a cada 4h).
            repeat_interval="PT4H",
        )
    )
    jobs.append(_script_job("HiveMind-ClaudeMemBridge", r"scripts\services\claude_mem_bridge.py"))
    jobs.append(_script_job("HiveMind-KnowledgeHealth", r"scripts\health\audit_memory.py"))
    jobs.append(
        WindowsJobSpec(
            name="HiveMind-Backup",
            execute=str(python),
            arguments="-m hive_mind.cli backup run --apply",
            working_directory=str(root),
            exists=python.exists(),
        )
    )

    # P1-I (2026-08-12): registrar os jobs da cadência hierárquica e manutenção
    # declarados no runtime.yaml mas nunca registrados no Task Scheduler. Sem
    # eles, frontal/cerebelo/diencéfalo ficam vazios — só o DreamCycle, o
    # bridge, o audit e o backup rodavam. Cada job abaixo é um script Python
    # com schedule próprio no runtime.yaml (a task XML usa TASK_TIME como
    # horário default; o disparo real é governado pelo próprio script/daemon).
    _cadence_jobs = [
        ("HiveMind-DailyWriter", r"scripts\dream\daily_writer.py"),
        ("HiveMind-WeeklySynthesizer", r"scripts\dream\weekly_synthesizer.py"),
        ("HiveMind-HealthDashboard", r"scripts\health\health_dashboard.py"),
        ("HiveMind-AlertDispatcher", r"scripts\health\alert_dispatcher.py"),
        ("HiveMind-DecisionPromoter", r"scripts\knowledge\decision_promoter.py"),
        ("HiveMind-ProjectSynthesizer", r"scripts\knowledge\project_synthesizer.py"),
        ("HiveMind-WorkTracker", r"scripts\knowledge\work_tracker.py"),
        ("HiveMind-PatternDistiller", r"scripts\knowledge\pattern_distiller.py"),
        ("HiveMind-ConflictDetector", r"scripts\knowledge\conflict_detector.py"),
        ("HiveMind-TopicConsolidator", r"scripts\knowledge\topic_consolidator.py"),
        ("HiveMind-ReviewWriter", r"scripts\knowledge\review_writer.py"),
        ("HiveMind-DriftDetector", r"scripts\knowledge\drift_detector.py"),
        ("HiveMind-CaptureMaintenance", r"scripts\capture\capture_maintenance.py"),
    ]
    for name, rel in _cadence_jobs:
        jobs.append(_script_job(name, rel))
    return jobs


def _run_schtasks(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["schtasks.exe", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def export_task_definition(task_name: str, destination: str | Path) -> str | None:
    result = _run_schtasks("/query", "/tn", task_name, "/xml", "ONE")
    if result.returncode != 0:
        return None
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    target = destination / f"{task_name}.{stamp}.xml"
    target.write_text(result.stdout, encoding="utf-16")
    return str(target)


def restore_task_definition(task_name: str, xml_path: str | Path) -> None:
    xml_path = Path(xml_path)
    if not xml_path.is_file():
        raise FileNotFoundError(xml_path)
    result = _run_schtasks("/create", "/tn", task_name, "/xml", str(xml_path), "/f")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "schtasks restore failed")


def _task_xml(job: WindowsJobSpec) -> str:
    root = ET.Element("Task", version="1.4", xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task")
    reg = ET.SubElement(root, "RegistrationInfo")
    ET.SubElement(reg, "Description").text = job.description

    triggers = ET.SubElement(root, "Triggers")
    cal = ET.SubElement(triggers, "CalendarTrigger")
    ET.SubElement(cal, "StartBoundary").text = f"{datetime.now():%Y-%m-%d}T{job.schedule_time}:00"
    ET.SubElement(cal, "Enabled").text = "true"
    sched = ET.SubElement(cal, "ScheduleByDay")
    ET.SubElement(sched, "DaysInterval").text = "1"
    if job.repeat_interval:
        rep = ET.SubElement(cal, "Repetition")
        ET.SubElement(rep, "Interval").text = job.repeat_interval
        ET.SubElement(rep, "Duration").text = "P1D"
        ET.SubElement(rep, "StopAtDurationEnd").text = "false"

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
        ("StartWhenAvailable", "true"),
        ("RunOnlyIfNetworkAvailable", "false"),
        ("AllowStartOnDemand", "true"),
        ("Enabled", "true"),
        ("Hidden", "true"),
        ("RunOnlyIfIdle", "false"),
        ("WakeToRun", "false"),
        ("ExecutionTimeLimit", "PT0S"),
        ("Priority", "7"),
    ):
        ET.SubElement(settings, tag).text = value
    idle = ET.SubElement(settings, "IdleSettings")
    ET.SubElement(idle, "StopOnIdleEnd").text = "false"
    ET.SubElement(idle, "RestartOnIdle").text = "false"

    actions = ET.SubElement(root, "Actions", Context="Author")
    exec_node = ET.SubElement(actions, "Exec")
    ET.SubElement(exec_node, "Command").text = job.execute
    ET.SubElement(exec_node, "Arguments").text = job.arguments
    ET.SubElement(exec_node, "WorkingDirectory").text = job.working_directory

    return '<?xml version="1.0" encoding="UTF-16"?>\n' + ET.tostring(root, encoding="unicode")


def register_windows_jobs(
    *,
    root: str | Path,
    apply: bool = False,
    backup_dir: str | Path | None = None,
) -> WindowsJobsReport:
    root = Path(root).resolve()
    backup_dir = Path(backup_dir) if backup_dir else root / "logs" / "scheduled-tasks"
    specs = windows_job_specs(root)
    results: list[WindowsJobResult] = []
    registered = 0
    skipped = 0

    if not apply:
        for job in specs:
            status = "DRY_RUN" if job.exists else "SKIPPED"
            reason = "would register scheduled task" if job.exists else "target missing; would leave existing task untouched"
            if not job.exists:
                skipped += 1
            results.append(
                WindowsJobResult(
                    name=job.name,
                    execute=job.execute,
                    arguments=job.arguments,
                    working_directory=job.working_directory,
                    source_script=job.source_script,
                    status=status,
                    reason=reason,
                )
            )
        return WindowsJobsReport(
            project_root=str(root),
            backup_dir=str(backup_dir),
            apply=False,
            scanned=len(specs),
            registered=0,
            skipped=skipped,
            entries=tuple(results),
        )

    lock_path = root / ".hive-mind" / "state" / "windows-jobs.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with MaintenanceLock(lock_path):
        with tempfile.TemporaryDirectory(prefix="hive-mind-tasks-") as tmp:
            tmpdir = Path(tmp)
            for job in specs:
                if not job.exists:
                    skipped += 1
                    results.append(
                        WindowsJobResult(
                            name=job.name,
                            execute=job.execute,
                            arguments=job.arguments,
                            working_directory=job.working_directory,
                            source_script=job.source_script,
                            status="SKIPPED",
                            reason="target missing; leaving existing task untouched",
                        )
                    )
                    continue
                backup = export_task_definition(job.name, backup_dir)
                xml_path = tmpdir / f"{job.name}.xml"
                xml_path.write_text(_task_xml(job), encoding="utf-16")
                result = _run_schtasks("/create", "/tn", job.name, "/xml", str(xml_path), "/f")
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout).strip() or f"schtasks create failed for {job.name}")
                registered += 1
                results.append(
                    WindowsJobResult(
                        name=job.name,
                        execute=job.execute,
                        arguments=job.arguments,
                        working_directory=job.working_directory,
                        source_script=job.source_script,
                        status="REGISTERED",
                        reason="scheduled task registered",
                        backup_path=backup,
                    )
                )

    return WindowsJobsReport(
        project_root=str(root),
        backup_dir=str(backup_dir),
        apply=True,
        scanned=len(specs),
        registered=registered,
        skipped=skipped,
        entries=tuple(results),
    )
