"""Canonical runtime path policy and Windows collector contracts."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from hive_mind.validation.runtime_paths import (
    RuntimePathReference,
    find_runtime_path_violations,
)


ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_PATH = ROOT / "scripts" / "health" / "audit_runtime_paths_windows.py"
SPEC = importlib.util.spec_from_file_location(
    "audit_runtime_paths_windows", COLLECTOR_PATH
)
COLLECTOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(COLLECTOR)


@pytest.mark.parametrize(
    ("value", "family"),
    [
        (r"C:\Users\me\.codex\worktrees\cutover\repo\worker.py", ".codex/worktrees"),
        ("D:/src/.WORKTREES/cutover/repo/worker.py", ".worktrees"),
        (r"D:\backups/worktrees\old\repo\worker.py", "backups/worktrees"),
        (r"D:\Hive-Mind-Archive\20260722\repo\worker.py", "hive-mind-archive"),
        ("D:/hive-mind-consolidation/20260722/repo/worker.py", "hive-mind-consolidation"),
    ],
)
def test_policy_rejects_forbidden_runtime_path_families(value, family):
    findings = find_runtime_path_violations(
        [RuntimePathReference(source="process:42:command_line", value=value)],
        canonical_root=r"D:\Hive-Mind",
    )

    assert len(findings) == 1
    assert findings[0].source == "process:42:command_line"
    assert findings[0].reason == "forbidden_path_family"
    assert findings[0].matched == family


def test_policy_rejects_another_hive_mind_repository_root():
    findings = find_runtime_path_violations(
        [
            RuntimePathReference(
                source="service:sinapse:path_name",
                value=r'"E:\deploy\Hive-Mind\.venv\Scripts\python.exe" worker.py',
            )
        ],
        canonical_root=r"D:\Hive-Mind",
    )

    assert [finding.reason for finding in findings] == ["noncanonical_hive_mind_root"]
    assert findings[0].matched == "e:/deploy/hive-mind"


def test_policy_accepts_canonical_and_unrelated_provider_paths_without_name_false_positives():
    findings = find_runtime_path_violations(
        [
            RuntimePathReference(
                source="task:HiveMind-Backup:executable",
                value=r"D:\Hive-Mind\.venv\Scripts\python.exe",
            ),
            RuntimePathReference(
                source="task:HiveMind-Backup:arguments",
                value=r"D:\Hive-Mind\scripts\maintenance\backup.py",
            ),
            RuntimePathReference(
                source="process:provider:command_line",
                value=r'"C:\Program Files\Provider\provider.exe" --data D:\data\backups',
            ),
        ],
        canonical_root="d:/hive-mind/",
    )

    assert findings == []


def test_injected_windows_snapshot_collects_only_operational_fields(tmp_path):
    snapshot = {
        "processes": [
            {"ProcessId": 41, "Name": "python.exe", "CommandLine": r"D:\Hive-Mind\worker.py"}
        ],
        "scheduled_tasks": [
            {
                "TaskName": "HiveMind-Backup",
                "Execute": "python.exe",
                "Arguments": r"D:\Hive-Mind-Consolidation\repo\job.py",
                "WorkingDirectory": r"D:\Hive-Mind",
            }
        ],
        "services": [
            {"Name": "HiveMindApi", "PathName": r"D:\Hive-Mind\.venv\Scripts\python.exe"}
        ],
    }
    documents = {
        "config/runtime.yaml": {
            "services": [
                {"name": "api", "command": ["python", r"D:\Hive-Mind\api.py"], "working_directory": r"D:\Hive-Mind"}
            ]
        },
        "logs/supervisor/manifest.json": {
            "root": r"D:\Hive-Mind",
            "services": [{"name": "worker", "command": ["python", "worker.py"]}],
        },
    }

    references = COLLECTOR.collect_runtime_references(
        tmp_path, snapshot=snapshot, documents=documents
    )
    findings = find_runtime_path_violations(references, r"D:\Hive-Mind")

    assert [finding.source for finding in findings] == [
        "scheduled_task:HiveMind-Backup:arguments"
    ]


def test_operational_document_loader_ignores_docs_tests_and_archive_reports(tmp_path):
    config = tmp_path / "config" / "runtime.yaml"
    manifest = tmp_path / "logs" / "supervisor" / "manifest.json"
    ignored = tmp_path / "docs" / "archive-report.json"
    config.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)
    ignored.parent.mkdir(parents=True)
    config.write_text("services: []\n", encoding="utf-8")
    manifest.write_text('{"services": []}\n', encoding="utf-8")
    ignored.write_text('{"root": "D:/Hive-Mind-Archive"}\n', encoding="utf-8")

    documents = COLLECTOR.load_operational_documents(tmp_path)

    assert set(documents) == {
        "config/runtime.yaml",
        "logs/supervisor/manifest.json",
    }


def test_audit_accepts_injected_collectors_without_live_machine_access(tmp_path):
    calls = []

    def snapshot_loader():
        calls.append("snapshot")
        return {"processes": [], "scheduled_tasks": [], "services": []}

    def document_loader(root):
        calls.append(("documents", root))
        return {
            "config/runtime.yaml": {
                "services": [
                    {
                        "name": "worker",
                        "working_directory": r"D:\Hive-Mind-Archive\old",
                    }
                ]
            }
        }

    findings = COLLECTOR.audit_runtime_paths(
        r"D:\Hive-Mind",
        snapshot_loader=snapshot_loader,
        document_loader=document_loader,
    )

    assert calls == ["snapshot", ("documents", Path(r"D:\Hive-Mind"))]
    assert findings[0]["source"] == "operational_file:config/runtime.yaml:services[0].working_directory"
    assert findings[0]["reason"] == "forbidden_path_family"
