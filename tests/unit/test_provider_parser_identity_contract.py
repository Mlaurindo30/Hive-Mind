from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PARSERS = ROOT / "scripts" / "capture" / "parsers"
CAPTURE = ROOT / "scripts" / "capture"
if str(CAPTURE) not in sys.path:
    sys.path.insert(0, str(CAPTURE))

PROVIDERS = (
    "antigravity", "codex", "copilot", "hermes", "kilo", "kimi",
    "mimo", "qwen", "roo", "screenpipe", "swarmclaw",
)


def _load(name: str):
    path = PARSERS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"contract_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("provider", PROVIDERS)
def test_parser_does_not_classify_project_locally(provider: str) -> None:
    source = (PARSERS / f"{provider}.py").read_text(encoding="utf-8")
    assert "project_from_cwd" not in source
    assert '"project":' not in source
    assert "'project':" not in source
    assert "SWARMCLAW_PROJECT" not in source


def test_codex_preserves_source_cwd_and_surface_without_project(tmp_path: Path) -> None:
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text("\n".join([
        json.dumps({"type": "session_meta", "payload": {
            "id": "codex-1", "cwd": "D:/Hive-Mind", "source": "vscode",
        }}),
        json.dumps({"type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "prompt"}],
        }}),
    ]), encoding="utf-8")

    session = _load("codex").parse(rollout)[0]

    assert session["cwd"] == "D:/Hive-Mind"
    assert session["source"] == "vscode"
    assert session["surface"] == "ide"
    assert "project" not in session


def test_copilot_ide_preserves_workspace_as_cwd_without_project(tmp_path: Path) -> None:
    root = tmp_path / "workspaceStorage" / "hash"
    transcript = root / "GitHub.copilot-chat" / "transcripts" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    (root / "workspace.json").write_text(
        json.dumps({"folder": "file:///D:/Hive-Mind"}), encoding="utf-8"
    )
    transcript.write_text(json.dumps({
        "type": "user.message", "data": {"content": "prompt"},
    }), encoding="utf-8")

    session = _load("copilot").parse(transcript)[0]

    assert session["cwd"] == "D:/Hive-Mind"
    assert session["source"] == "vscode"
    assert session["surface"] == "ide"
    assert "project" not in session


def test_roo_preserves_official_workspace_without_project(tmp_path: Path) -> None:
    task = tmp_path / "12345678-1234-1234-1234-123456789abc"
    task.mkdir()
    (task / "history_item.json").write_text(
        json.dumps({"workspace": "D:/Hive-Mind"}), encoding="utf-8"
    )
    ui = task / "ui_messages.json"
    ui.write_text(json.dumps([{"type": "say", "say": "text", "text": "prompt"}]), encoding="utf-8")

    session = _load("roo").parse(ui)[0]

    assert session["official_workspace"] == "D:/Hive-Mind"
    assert session["cwd"] == "D:/Hive-Mind"
    assert session["surface"] == "ide"
    assert "project" not in session


def test_antigravity_surface_is_inferred_from_storage_path(tmp_path: Path) -> None:
    sid = "12345678-1234-1234-1234-123456789abc"
    transcript = tmp_path / ".gemini" / "antigravity-ide" / "brain" / sid / ".system_generated" / "logs" / "transcript_full.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(json.dumps({
        "type": "USER_INPUT", "step_index": 1,
        "content": "<USER_REQUEST>prompt</USER_REQUEST>",
    }), encoding="utf-8")

    session = _load("antigravity").parse(transcript)[0]

    assert session["source"] == "antigravity-ide"
    assert session["surface"] == "ide"
    assert "project" not in session
@pytest.mark.parametrize(
    ("provider", "db_parts", "expected_surface"),
    [
        ("kilo", ("Code", "User", "globalStorage", "kilocode.kilo-code", "kilo.db"), "ide"),
        ("mimo", (".local", "share", "mimocode", "mimocode.db"), "cli"),
    ],
)
def test_sqlite_parsers_preserve_directory_as_evidence(
    provider: str,
    db_parts: tuple[str, ...],
    expected_surface: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import sqlite3

    module = _load(provider)
    monkeypatch.setattr(module.core, "SESSION_CUTOFF_MS", 0)
    database = tmp_path.joinpath(*db_parts)
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE session (id TEXT, title TEXT, directory TEXT, time_updated INTEGER);
            CREATE TABLE message (id TEXT, session_id TEXT, data TEXT, time_created INTEGER);
            CREATE TABLE part (message_id TEXT, data TEXT, time_created INTEGER);
            """
        )
        connection.execute(
            "INSERT INTO session VALUES (?, ?, ?, ?)",
            ("session-1", "title", "D:/Hive-Mind", 10),
        )
        connection.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?)",
            ("message-1", "session-1", json.dumps({"role": "user"}), 11),
        )
        connection.execute(
            "INSERT INTO part VALUES (?, ?, ?)",
            ("message-1", json.dumps({"type": "text", "text": "prompt"}), 12),
        )

    session = module.parse(database)[0]

    assert session["cwd"] == "D:/Hive-Mind"
    assert session["official_workspace"] == "D:/Hive-Mind"
    assert session["surface"] == expected_surface
    assert "project" not in session


def test_swarmclaw_preserves_runtime_cwd_without_hardcoded_project(
    tmp_path: Path, monkeypatch
) -> None:
    import sqlite3

    module = _load("swarmclaw")
    monkeypatch.setattr(module.core, "SESSION_CUTOFF_MS", 0)
    database = tmp_path / "swarmclaw.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE sessions (id TEXT, data TEXT);
            CREATE TABLE runtime_runs (data TEXT);
            """
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?)",
            ("session-1", json.dumps({"name": "chat", "lastActiveAt": 10, "cwd": "D:/Hive-Mind"})),
        )
        connection.execute(
            "INSERT INTO runtime_runs VALUES (?)",
            (json.dumps({"sessionId": "session-1", "messagePreview": "prompt", "resultPreview": "answer", "queuedAt": 11, "status": "done"}),),
        )

    session = module.parse(database)[0]

    assert session["cwd"] == "D:/Hive-Mind"
    assert session["official_workspace"] == "D:/Hive-Mind"
    assert session["source"] == "swarmclaw"
    assert session["surface"] == "app"
    assert "project" not in session

def test_qwen_preserves_explicit_desktop_source_and_surface(tmp_path: Path) -> None:
    chat = tmp_path / "qwen.jsonl"
    chat.write_text(json.dumps({
        "sessionId": "qwen-1",
        "type": "user",
        "cwd": "D:/Hive-Mind",
        "source": "qwen-code-desktop",
        "surface": "desktop",
        "message": {"parts": [{"text": "prompt"}]},
    }), encoding="utf-8")

    session = _load("qwen").parse(chat)[0]

    assert session["source"] == "qwen-code-desktop"
    assert session["surface"] == "desktop"
    assert session["official_workspace"] == "D:/Hive-Mind"
    assert "project" not in session


def test_screenpipe_distinguishes_ocr_and_audio_surfaces(monkeypatch) -> None:
    module = _load("screenpipe")
    monkeypatch.setattr(module, "_api", lambda path, _params=None: {
        "data": [{
            "content_id": "1",
            "content": (
                {"text": "screen text", "app_name": "Code"}
                if "ocr" in str(_params) else
                {"transcription": "audio text"}
            ),
        }]
    })

    ocr = module.fetch_recent_ocr()[0]
    audio = module.fetch_recent_audio()[0]

    assert (ocr["source"], ocr["surface"]) == ("screenpipe-ocr", "ocr")
    assert (audio["source"], audio["surface"]) == ("screenpipe-audio", "audio")
    assert "project" not in ocr
    assert "project" not in audio
