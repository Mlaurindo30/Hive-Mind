"""Testes do parser DEDICADO do Antigravity (Desktop e CLI).

Garante que TODOS os prompts do usuário são coletados (não apenas o último),
que cada prompt expõe o step_index nativo como event_id com posição de origem
estável, e que a normalização session→ProviderEvent preserva a ordem.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARSER = ROOT / "scripts" / "capture" / "parsers" / "antigravity.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_parser():
    spec = importlib.util.spec_from_file_location("antigravity_parser", PARSER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _user_input(step_index: int | None, text: str) -> str:
    record: dict = {"type": "USER_INPUT", "content": f"<USER_REQUEST>{text}</USER_REQUEST>"}
    if step_index is not None:
        record["step_index"] = step_index
    return json.dumps(record)


def _write_transcript(tmp_path: Path, lines: list[str]) -> Path:
    transcript = (
        tmp_path
        / "68f4d64e-9de6-4f73-99f7-66f173d38de0"
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
    transcript.parent.mkdir(parents=True)
    transcript.write_text("\n".join(lines), encoding="utf-8")
    return transcript


def test_antigravity_keeps_every_user_input(tmp_path: Path) -> None:
    transcript = _write_transcript(
        tmp_path,
        [
            _user_input(1, "one"),
            _user_input(2, "two"),
        ],
    )

    session = _load_parser().parse(transcript)[0]

    assert session["prompts"] == ["one", "two"]
    assert session["prompt_events"][1]["event_id"] == "2"


def test_antigravity_session_prompt_is_first_user_input(tmp_path: Path) -> None:
    transcript = _write_transcript(
        tmp_path,
        [
            _user_input(1, "primeiro pedido"),
            _user_input(4, "segundo pedido"),
        ],
    )

    session = _load_parser().parse(transcript)[0]

    assert session["prompt"] == "primeiro pedido"
    assert session["sid"] == "68f4d64e-9de6-4f73-99f7-66f173d38de0"


def test_prompt_events_expose_stable_source_positions(tmp_path: Path) -> None:
    transcript = _write_transcript(
        tmp_path,
        [
            _user_input(1, "one"),
            _user_input(2, "two"),
        ],
    )
    parser = _load_parser()

    first_pass = parser.parse(transcript)[0]["prompt_events"]
    second_pass = parser.parse(transcript)[0]["prompt_events"]

    assert first_pass == second_pass
    positions = [event["source_position"] for event in first_pass]
    assert all(positions), "toda entrada precisa de posição de origem"
    assert len(set(positions)) == len(positions), "posições devem ser únicas"
    assert [event["content"] for event in first_pass] == ["one", "two"]


def test_user_input_without_step_index_is_still_collected(tmp_path: Path) -> None:
    transcript = _write_transcript(
        tmp_path,
        [
            _user_input(None, "sem indice"),
            _user_input(7, "com indice"),
        ],
    )

    session = _load_parser().parse(transcript)[0]

    assert session["prompts"] == ["sem indice", "com indice"]
    first, second = session["prompt_events"]
    assert first["event_id"] is None
    assert first["source_position"]
    assert second["event_id"] == "7"


def test_tool_turns_and_last_content_are_preserved(tmp_path: Path) -> None:
    transcript = _write_transcript(
        tmp_path,
        [
            _user_input(1, "analise o arquivo"),
            json.dumps({
                "step_index": 2,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [{"name": "ViewFile", "args": {"toolSummary": "abrindo arquivo"}}],
            }),
            json.dumps({"step_index": 3, "type": "VIEW_FILE", "content": "conteudo do arquivo"}),
        ],
    )

    session = _load_parser().parse(transcript)[0]

    assert [t["tool_name"] for t in session["turns"]] == ["ViewFile", "ViewFile"]
    assert session["turns"][0]["tool_response"] == "abrindo arquivo"
    assert session["last"] == "conteudo do arquivo"


# ── session_to_events: normalização session dict → ProviderEvent ─────────────

def test_session_to_events_maps_prompts_tools_and_assistant(tmp_path: Path) -> None:
    from scripts.capture.session_events import session_to_events

    transcript = _write_transcript(
        tmp_path,
        [
            _user_input(1, "one"),
            _user_input(2, "two"),
            json.dumps({
                "step_index": 3,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [{"name": "ViewFile", "args": {"toolSummary": "lendo"}}],
            }),
            json.dumps({"step_index": 4, "type": "VIEW_FILE", "content": "resposta final"}),
        ],
    )
    session = _load_parser().parse(transcript)[0]

    events = session_to_events("antigravity", session)

    types = [event.event_type.value for event in events]
    assert types == [
        "prompt",
        "prompt",
        "tool_use",
        "tool_result",
        "tool_use",
        "tool_result",
        "assistant",
    ]
    assert all(event.provider == "antigravity" for event in events)
    assert all(event.session_id == session["sid"] for event in events)
    assert [event.content for event in events[:2]] == ["one", "two"]
    assert [event.event_id for event in events[:2]] == ["1", "2"]
    assert events[-1].content == "resposta final"


def test_session_to_events_is_deterministic(tmp_path: Path) -> None:
    from scripts.capture.session_events import session_to_events

    transcript = _write_transcript(
        tmp_path,
        [
            _user_input(1, "one"),
            json.dumps({"step_index": 2, "type": "VIEW_FILE", "content": "saida"}),
        ],
    )
    session = _load_parser().parse(transcript)[0]

    first = session_to_events("antigravity", session)
    second = session_to_events("antigravity", session)

    assert [e.dedupe_key() for e in first] == [e.dedupe_key() for e in second]
    assert len({e.dedupe_key() for e in first}) == len(first)


def test_session_to_events_supports_plain_prompt_lists() -> None:
    """Sessões de outros parsers (ex.: codex) não têm prompt_events."""
    from scripts.capture.session_events import session_to_events

    session = {
        "sid": "ses-1",
        "prompt": "primeiro",
        "prompts": ["primeiro", "segundo"],
        "turns": [
            {"tool_name": "exec_command", "tool_input": {"cmd": "ls"}, "tool_response": "ok"},
        ],
        "last": "feito",
    }

    events = session_to_events("codex", session)

    types = [event.event_type.value for event in events]
    assert types == ["prompt", "prompt", "tool_use", "tool_result", "assistant"]
    assert [event.content for event in events[:2]] == ["primeiro", "segundo"]
    repeat = session_to_events("codex", session)
    assert [e.dedupe_key() for e in events] == [e.dedupe_key() for e in repeat]


def test_session_to_events_without_sid_returns_empty() -> None:
    from scripts.capture.session_events import session_to_events

    assert session_to_events("codex", {"prompt": "orfao"}) == []
    assert session_to_events("codex", {}) == []
