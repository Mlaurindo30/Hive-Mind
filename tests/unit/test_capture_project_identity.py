from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

from scripts.capture.capture_events import ProviderEvent
from scripts.capture.project_identity import ProjectIdentity, ProjectIdentityResolver
from scripts.capture.session_events import attach_project_identity, session_to_events


ROOT = Path(__file__).resolve().parents[2]
REALTIME_SCRIPT = ROOT / "scripts" / "capture" / "capture-realtime.py"
HOOK_SCRIPT = ROOT / "scripts" / "capture" / "capture-hook.py"
IDENTITY_KEYS = {
    "schema_version",
    "project_id",
    "project_name",
    "workspace_root",
    "repository_root",
    "repository_remote",
    "git_common_dir",
    "worktree_name",
    "branch",
    "provider",
    "surface",
    "resolution_method",
    "resolution_confidence",
    "referenced_projects",
}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _identity(provider: str = "copilot", surface: str = "ide") -> ProjectIdentity:
    return ProjectIdentity(
        project_id="hive-mind",
        project_name="Hive-Mind",
        workspace_root=r"D:\\Hive-Mind",
        repository_root=r"D:\\Hive-Mind",
        repository_remote="github.com/mlaurindo30/hive-mind",
        git_common_dir=r"D:\\Hive-Mind\\.git",
        worktree_name="hive-mind-windows-zero-install",
        branch="codex/windows-zero-install",
        provider=provider,
        surface=surface,
        resolution_method="git_common_dir",
        resolution_confidence=0.96,
        referenced_projects=("another-project",),
    )


class _Registry:
    def by_alias(self, value):
        return object() if value == "Hive-Mind" else None


class RecordingResolver:
    registry = _Registry()

    def __init__(self, identity: ProjectIdentity | None = None):
        self.identity = identity or _identity()
        self.calls: list[dict] = []

    def resolve(self, **kwargs):
        self.calls.append(kwargs)
        return self.identity


def test_realtime_resolves_once_and_ingests_complete_identity_envelope(tmp_path, monkeypatch):
    module = _load(REALTIME_SCRIPT, "capture_realtime_project_identity")
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    resolver = RecordingResolver()
    delivered: list[dict] = []
    raw_session = {
        "sid": "session-1",
        "project": "Hive-Mind",
        "cwd": r"D:\\Hive-Mind",
        "surface": "ide",
        "prompt": "real prompt",
        "turns": [],
        "referenced_projects": ["another-project"],
    }

    monkeypatch.setattr(
        module.core,
        "ingest",
        lambda provider, session, store: delivered.append(session) or 1,
    )
    daemon = module.RealtimeCapture(
        {
            "copilot": {
                "parser": lambda path: [raw_session],
                "sources": [str(transcript)],
                "watch": [str(tmp_path)],
            }
        },
        object(),
        resolver=resolver,
    )

    assert daemon.handle_change(module.SourceChange("copilot", transcript, time.time())) == 1
    assert len(resolver.calls) == 1
    assert resolver.calls[0]["provider"] == "copilot"
    assert resolver.calls[0]["surface"] == "ide"
    assert resolver.calls[0]["explicit_project"] == "Hive-Mind"
    normalized = delivered[0]
    assert IDENTITY_KEYS == set(normalized["project_identity"])
    assert normalized["project"] == "Hive-Mind"
    assert normalized["project_id"] == "hive-mind"
    assert normalized["cwd"] == raw_session["cwd"]
    assert normalized["referenced_projects"] == ["another-project"]


def test_legacy_provider_application_and_profile_labels_do_not_become_project_id(tmp_path, monkeypatch):
    monkeypatch.delenv("HIVE_PROJECT_ID", raising=False)
    monkeypatch.delenv("HIVE_PROJECT_ROOT", raising=False)
    resolver = ProjectIdentityResolver(registry=ProjectIdentityResolver().registry)

    normalized = attach_project_identity(
        "hermes",
        {
            "sid": "legacy",
            "project": "hermes",
            "application": "Hermes App",
            "profile": "default",
            "cwd": str(tmp_path),
            "prompt": "prompt",
            "referenced_projects": ["Hive-Mind"],
        },
        resolver=resolver,
        default_surface="desktop",
    )

    assert normalized["project_id"] == "unclassified/hermes"
    assert normalized["project"] == "Unclassified (hermes)"
    assert normalized["project_identity"]["referenced_projects"] == ["hive-mind"]
    assert normalized["project_identity"]["project_id"] != "hive-mind"


def test_session_event_normalization_preserves_identity_without_changing_event_hash():
    resolver = RecordingResolver(_identity(provider="codex", surface="hook"))
    legacy = {
        "sid": "session-2",
        "project": "Hive-Mind",
        "cwd": r"D:\\Hive-Mind",
        "prompt": "same content",
    }
    normalized = attach_project_identity(
        "codex", legacy, resolver=resolver, default_surface="hook"
    )

    old_event = session_to_events("codex", legacy)[0]
    new_event = session_to_events("codex", normalized)[0]

    assert old_event.event_id == new_event.event_id
    assert new_event.project == "Hive-Mind"
    assert new_event.cwd == legacy["cwd"]
    assert new_event.metadata == {"project_identity": normalized["project_identity"]}


def test_capture_core_sends_identity_metadata_without_changing_content_hash(tmp_path, monkeypatch):
    module = _load(ROOT / "scripts" / "capture" / "capture_core.py", "capture_core_identity")
    resolver = RecordingResolver()
    session = attach_project_identity(
        "copilot",
        {
            "sid": "session-3",
            "project": "Hive-Mind",
            "cwd": r"D:\\Hive-Mind",
            "surface": "ide",
            "prompt": "prompt one",
            "turns": [
                {
                    "tool_name": "Message",
                    "tool_input": {},
                    "tool_response": "answer one",
                }
            ],
            "last": "answer one",
        },
        resolver=resolver,
    )
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(module, "_post", lambda path, payload: calls.append((path, payload)) or {"stored": True})
    store = module.SeenStore(tmp_path / "seen.db")
    before = module.content_hash("session-3", "o", "Message", module._norm("answer one"))
    try:
        assert module.ingest("copilot", session, store) == 1
        assert module.ingest("copilot", session, store) == 0
    finally:
        store.close()
    after = module.content_hash("session-3", "o", "Message", module._norm("answer one"))

    assert before == after
    assert [path for path, _ in calls] == [
        "/api/sessions/init",
        "/api/sessions/observations",
        "/api/sessions/summarize",
    ]
    expected = {"project_identity": session["project_identity"]}
    assert all(payload["metadata"] == expected for _, payload in calls)
    assert calls[0][1]["project"] == "Hive-Mind"


def test_hook_resolves_once_and_preserves_identity_in_event_metadata(tmp_path, monkeypatch):
    module = _load(HOOK_SCRIPT, "capture_hook_project_identity")
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(tmp_path / "capture.db"))
    resolver = RecordingResolver(_identity(provider="codex", surface="hook"))
    captured: list[ProviderEvent] = []

    class Queue:
        def __init__(self, path):
            pass

        def enqueue(self, event):
            captured.append(event)
            return True

        def close(self):
            pass

    monkeypatch.setattr(module, "IDENTITY_RESOLVER", resolver)
    monkeypatch.setattr(module, "CaptureQueue", Queue)
    result = module.process(
        "codex",
        "prompt",
        json.dumps(
            {
                "session_id": "hook-session",
                "cwd": r"D:\\Hive-Mind",
                "project": "Hive-Mind",
                "prompt": "hook prompt",
                "referenced_projects": ["another-project"],
            }
        ).encode("utf-8"),
    )

    assert result["enqueued"] is True
    assert len(resolver.calls) == 1
    assert resolver.calls[0]["surface"] == "hook"
    assert captured[0].project == "Hive-Mind"
    assert captured[0].cwd == r"D:\\Hive-Mind"
    assert captured[0].metadata == {"project_identity": resolver.identity.to_dict()}


def test_hook_reuses_persisted_identity_across_callbacks_and_store_reopen(tmp_path, monkeypatch):
    db_path = tmp_path / "capture.db"
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(db_path))
    first_module = _load(HOOK_SCRIPT, "capture_hook_project_identity_first_process")
    first_resolver = RecordingResolver(_identity(provider="codex", surface="hook"))
    captured: list[ProviderEvent] = []

    class Queue:
        def __init__(self, path):
            assert Path(path) == db_path

        def enqueue(self, event):
            captured.append(event)
            return True

        def close(self):
            pass

    monkeypatch.setattr(first_module, "IDENTITY_RESOLVER", first_resolver)
    monkeypatch.setattr(first_module, "CaptureQueue", Queue)
    first_payload = {
        "session_id": "cross-process-session",
        "event_id": "native-prompt-event",
        "cwd": r"D:\\Hive-Mind",
        "project": "Hive-Mind",
        "prompt": "first callback",
    }
    assert first_module.process(
        "codex", "prompt", json.dumps(first_payload).encode("utf-8")
    )["enqueued"] is True

    monkeypatch.setenv("HIVE_PROJECT_ID", "changed-after-session-start")
    monkeypatch.setenv("HIVE_PROJECT_ROOT", r"C:\\different-workspace")
    second_module = _load(HOOK_SCRIPT, "capture_hook_project_identity_second_process")
    second_resolver = RecordingResolver(
        ProjectIdentity(
            project_id="wrong-if-resolved-again",
            project_name="Wrong If Resolved Again",
            workspace_root=r"C:\\different-workspace",
            repository_root=None,
            repository_remote=None,
            git_common_dir=None,
            worktree_name=None,
            branch=None,
            provider="codex",
            surface="hook",
            resolution_method="explicit",
            resolution_confidence=1.0,
            referenced_projects=(),
        )
    )
    monkeypatch.setattr(second_module, "IDENTITY_RESOLVER", second_resolver)
    monkeypatch.setattr(second_module, "CaptureQueue", Queue)
    second_payload = {
        "session_id": "cross-process-session",
        "event_id": "native-tool-event",
        "cwd": r"C:\\different-workspace",
        "project_id": "changed-after-session-start",
        "tool_name": "Read",
        "tool_input": {"path": "README.md"},
        "tool_response": {"content": "ok"},
    }
    assert second_module.process(
        "codex", "tool_result", json.dumps(second_payload).encode("utf-8")
    )["enqueued"] is True

    assert len(first_resolver.calls) + len(second_resolver.calls) == 1
    assert len(first_resolver.calls) == 1
    assert len(second_resolver.calls) == 0
    assert [event.event_id for event in captured] == [
        "native-prompt-event",
        "native-tool-event",
    ]
    first_envelope = captured[0].metadata["project_identity"]
    second_envelope = captured[1].metadata["project_identity"]
    assert second_envelope == first_envelope
    assert first_envelope["project_id"] == "hive-mind"
    assert captured[0].project == captured[1].project == "Hive-Mind"
    assert captured[1].cwd == r"C:\\different-workspace"
    assert captured[1].metadata["tool_name"] == "Read"
    assert captured[1].metadata["native_event_id"] == "native-tool-event"
