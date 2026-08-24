import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "capture"
if str(CAPTURE) not in sys.path:
    sys.path.insert(0, str(CAPTURE))

from parsers import zcode  # noqa: E402


def _model_io(
    request_id="req-1",
    session_id="sess_0e59cc0f",
    system_text=None,
    messages=None,
    body_messages=None,
    text="resposta do assistente",
    tool_calls=None,
):
    body = {"system": [{"type": "text", "text": system_text or ""}]}
    if body_messages is not None:
        body["messages"] = body_messages
    return {
        "type": "model_io",
        "sessionId": session_id,
        "requestId": request_id,
        "request": {
            "body": body,
            "messages": messages if messages is not None else [
                {"role": "user", "content": [{"type": "text", "text": "prompt um"}]},
            ],
        },
        "response": {"text": text, "toolCalls": tool_calls or []},
    }


def _write(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return path


def test_parses_session_with_prompts_turns_and_last(tmp_path: Path) -> None:
    rollout = _write(tmp_path / "model-io-sess_abc.jsonl", [_model_io(
        system_text="# Environment\nPrimary working directory: D:\\Hive-Mind\n",
        tool_calls=[{"id": "call_1", "name": "Read", "input": {"file_path": "x"}}],
    )])

    sessions = zcode.parse(rollout)

    assert len(sessions) == 1
    session = sessions[0]
    assert session["sid"] == "sess_0e59cc0f"
    assert session["prompt"] == "prompt um"
    assert session["prompts"] == ["prompt um"]
    assert session["turns"] == [{
        "tool_name": "Read",
        "tool_input": {"file_path": "x"},
        "tool_response": "",
    }]
    assert session["last"] == "resposta do assistente"
    assert session["cwd"] == "D:\\Hive-Mind"
    assert session["official_workspace"] == "D:\\Hive-Mind"
    assert session["source"] == "zcode"
    assert session["surface"] == "cli"


def test_deduplicates_prompts_repeated_across_model_io_calls(tmp_path: Path) -> None:
    rollout = _write(tmp_path / "rollout.jsonl", [
        _model_io(request_id="req-1"),
        _model_io(request_id="req-2", messages=[
            {"role": "user", "content": [{"type": "text", "text": "prompt um"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
            {"role": "user", "content": [{"type": "text", "text": "prompt dois"}]},
        ]),
    ])

    session = zcode.parse(rollout)[0]

    assert session["prompts"] == ["prompt um", "prompt dois"]
    assert [event["event_id"] for event in session["prompt_events"]] == ["req-1", "req-2"]


def test_strips_system_reminder_blocks_from_prompts(tmp_path: Path) -> None:
    rollout = _write(tmp_path / "rollout.jsonl", [_model_io(messages=[
        {"role": "user", "content": [
            {"type": "text", "text": "<system-reminder>hook noise</system-reminder>pedido real"},
        ]},
        {"role": "user", "content": [
            {"type": "text", "text": "<system-reminder>só ruído</system-reminder>"},
        ]},
    ])])

    session = zcode.parse(rollout)[0]

    assert session["prompts"] == ["pedido real"]


def test_sid_falls_back_to_filename_for_records_without_sessionid(tmp_path: Path) -> None:
    path = tmp_path / "model-io-sess_subagent_agent_7fb0.jsonl"
    record = _model_io(session_id=None)
    record.pop("sessionId")
    _write(path, [record])

    session = zcode.parse(path)[0]

    assert session["sid"] == "sess_subagent_agent_7fb0"


def test_returns_empty_without_usable_content(tmp_path: Path) -> None:
    garbage = tmp_path / "broken.jsonl"
    garbage.write_text("isto não é json\n{\n", encoding="utf-8")
    assert zcode.parse(garbage) == []

    empty = _write(tmp_path / "empty.jsonl", [])
    assert zcode.parse(empty) == []

    no_content = _write(tmp_path / "nocontent.jsonl", [
        _model_io(text="", messages=[]),
    ])
    assert zcode.parse(no_content) == []


def test_cwd_is_also_found_when_injected_as_a_message(tmp_path: Path) -> None:
    rollout = _write(tmp_path / "rollout.jsonl", [
        _model_io(
            request_id="req-env",
            system_text="",
            messages=[
                {"role": "user", "content": (
                    "# Environment\nPrimary working directory: D:\\Hive-Mind\n"
                )},
            ],
        ),
        _model_io(
            request_id="req-2",
            system_text="",
            messages=[
                {"role": "user", "content": [{"type": "text", "text": "prompt real"}]},
            ],
        ),
    ])

    session = zcode.parse(rollout)[0]

    assert session["cwd"] == "D:\\Hive-Mind"
    assert session["prompts"] == ["prompt real"]


def test_strips_task_notification_blocks_from_prompts(tmp_path: Path) -> None:
    rollout = _write(tmp_path / "rollout.jsonl", [_model_io(messages=[
        {"role": "user", "content": [
            {"type": "text", "text": (
                "<task-notification>\n<task-id>exec_123</task-id>\n"
                "<status>completed</status>\n</task-notification>\ncontinua o trabalho"
            )},
        ]},
        {"role": "user", "content": [
            {"type": "text", "text": "<task-notification>\n<task-id>só_ruído</task-id>\n</task-notification>"},
        ]},
    ])])

    session = zcode.parse(rollout)[0]

    assert session["prompts"] == ["continua o trabalho"]


def test_quoted_cwd_reference_in_user_message_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    rollout = _write(tmp_path / "rollout.jsonl", [
        _model_io(messages=[
            {"role": "user", "content": (
                'Parser should read "Primary working directory: X" from the system '
                "block — cuidado com falsos positivos em mensagens"
            )},
        ]),
        _model_io(messages=[
            {"role": "user", "content": "# Environment\nPrimary working directory: D:\\Hive-Mind\n"},
        ]),
    ])

    session = zcode.parse(rollout)[0]

    assert session["cwd"] == "D:\\Hive-Mind"


def test_cwd_is_found_in_wire_format_body_messages(tmp_path: Path) -> None:
    """Pós-compactação o ZCode põe o ambiente em body.messages (formato wire)."""
    rollout = _write(tmp_path / "rollout.jsonl", [_model_io(
        system_text="",
        messages=[{"role": "user", "content": "prompt real"}],
        body_messages=[
            {"role": "user", "content": (
                "# Environment\nPrimary working directory: D:\\Hive-Mind\n"
            )},
        ],
    )])

    session = zcode.parse(rollout)[0]

    assert session["cwd"] == "D:\\Hive-Mind"
    assert session["prompts"] == ["prompt real"]


def test_quoted_env_blob_from_another_project_loses_to_genuine_injection(
    tmp_path: Path,
) -> None:
    """Reproduz o caso real: mensagem citando o env de OUTRO projeto em forma
    escapada (uma única linha, sem \\n reais) contra a injeção genuína."""
    quoted_blob = (
        "discutindo o parser, veja o que apareceu: "
        '"# Environment\\nPrimary working directory: C:\\\\Users\\\\miche\\\\projeto_errado\\n'
        '- Is a git repository: yes\\n"'
    )
    rollout = _write(tmp_path / "rollout.jsonl", [_model_io(
        system_text="",
        messages=[
            {"role": "user", "content": quoted_blob},
            {"role": "user", "content": "prompt real"},
        ],
        body_messages=[
            {"role": "user", "content": (
                "# Environment\nPrimary working directory: D:\\Hive-Mind\n"
            )},
        ],
    )])

    session = zcode.parse(rollout)[0]

    assert session["cwd"] == "D:\\Hive-Mind"
    assert "projeto_errado" not in (session["cwd"] or "")
    assert "prompt real" in session["prompts"]


def test_cwd_accepts_bullet_list_environment_format(tmp_path: Path) -> None:
    """Formato genuíno das versões atuais do ZCode (lista com bullet)."""
    rollout = _write(tmp_path / "rollout.jsonl", [_model_io(
        system_text=(
            "You have been invoked in the following environment:\n"
            "- Primary working directory: D:\\Hive-Mind\n"
            "- Is a git repository: yes\n"
        ),
    )])

    session = zcode.parse(rollout)[0]

    assert session["cwd"] == "D:\\Hive-Mind"


def test_workspace_from_zcode_db_resolves_subagent_directory(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    with sqlite3.connect(db) as connection:
        connection.execute("""
            CREATE TABLE session (
                id TEXT PRIMARY KEY,
                directory TEXT NOT NULL,
                path TEXT
            )
        """)
        connection.execute(
            "INSERT INTO session (id, directory, path) VALUES (?, ?, ?)",
            ("sess_subagent_agent_7fb0", "D:\\Hive-Mind", "D:\\Hive-Mind"),
        )

    assert zcode._workspace_from_db("sess_subagent_agent_7fb0", db) == "D:\\Hive-Mind"


def test_workspace_from_zcode_db_is_read_only_and_safe(tmp_path: Path) -> None:
    assert zcode._workspace_from_db("sess_missing", tmp_path / "missing.db") is None
    broken = tmp_path / "broken.db"
    broken.write_text("not sqlite", encoding="utf-8")
    assert zcode._workspace_from_db("sess_missing", broken) is None


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert zcode.parse(tmp_path / "nao-existe.jsonl") == []
